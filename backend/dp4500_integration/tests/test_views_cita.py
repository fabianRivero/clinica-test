"""Cita biometric verify view tests — Phase 2A5 of
dp4500-host-app-integration-phase2.

Covers the contract documented in
``openspec/changes/dp4500-host-app-integration-phase2/specs/cita-biometric-verification/spec.md``:

1. Happy path: a signed payload ``{challenge_id, signature, timestamp}``
   from the browser transitions the cita to ``CONFIRMADA`` and populates
   the three ``CitaMedica.biometric_*`` fields atomically.
2. 503 no service key: the view returns ``503`` with ``Retry-After: 60``
   when the ``Sucursal`` has no ``dp4500_service_key_id`` configured.
3. Concurrent verify: two parallel POSTs serialize on
   ``select_for_update``; the loser sees ``409 cita_no_longer_pending``.
"""

from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from unittest import mock

import httpx
import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import Rol, Usuario
from catalogs.models import (
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from customers.models import Cliente
from dp4500_integration.client import HTTPClient
from operations.models import CitaMedica, Operacion


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _build_graph():
    """Branch + admin + cliente + operacion graph for the verify tests.

    Mirrors the shape used in
    ``backend/tests/test_appointment_close_split.py::_make_fixtures``
    so reviewers can trace the lineage.
    """
    rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
    rol_cliente = Rol.objects.create(rol="CLIENTE")

    sucursal = Sucursal.objects.create(nombre="Verificar-Centro", activa=True)
    # dp4500_service_key_id intentionally nullable — the no-service-key
    # test depends on it being absent. The happy-path + concurrent
    # tests set it explicitly via ``Sucursal.objects.update(...)``.
    admin = Usuario.objects.create_user(
        username="verify.admin",
        password="password123",
        primer_nombre="Verify",
        apellido_paterno="Admin",
        email="verify.admin@example.com",
        rol=rol_admin,
        sucursal=sucursal,
    )
    tipo = TipoServicio.objects.create(tipo="Verificar-Tratamiento", activo=True)
    servicio = ServicioConfig.objects.create(
        tipo_servicio=tipo, precio_base=Decimal("240.00"),
    )
    cliente_user = Usuario.objects.create_user(
        username="verificar.cliente",
        password="password123",
        primer_nombre="Carl",
        apellido_paterno="Verify",
        rol=rol_cliente,
    )
    cliente_user.sucursal = sucursal
    cliente_user.save()
    cliente = Cliente.objects.create(
        usuario=cliente_user,
        sucursal_origen=sucursal,
        fecha_nacimiento=date.today().replace(year=date.today().year - 30),
        estado_cliente=Cliente.Estado.ACTIVO,
    )
    operacion = Operacion.objects.create(
        paciente=cliente,
        servicio_config=servicio,
        precio_total=Decimal("240.00"),
        cuotas_totales=1,
        sesiones_totales=1,
        estado=Operacion.Estado.EN_PROCESO,
    )
    return {
        "sucursal": sucursal,
        "admin": admin,
        "cliente": cliente,
        "operacion": operacion,
    }


def _build_pending_cita(graph):
    """Create a fresh ``REALIZADA_PENDIENTE_VERIFICACION`` cita tied to
    the supplied graph. The cita gets the wizard-minted UUID mirrored
    on the cliente so ``CitaBiometricVerifyView`` can resolve it.
    """
    user_external_id = uuid.UUID(
        "11111111-2222-3333-4444-555555555555",
    )
    # Mirror the wizard-mint pattern: same UUID lives on both
    # ``Usuario.biometric_external_id`` and ``Cliente.external_id`` so
    # the verify view's lookup works from either side.
    graph["cliente"].usuario.biometric_external_id = user_external_id
    graph["cliente"].usuario.save(
        update_fields=["biometric_external_id", "updated_at"],
    )
    graph["cliente"].external_id = user_external_id
    graph["cliente"].save(update_fields=["external_id", "updated_at"])

    return CitaMedica.objects.create(
        operacion=graph["operacion"],
        sucursal=graph["sucursal"],
        fecha_hora=datetime(2026, 9, 27, 10, 0, 0),
        estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        # ``CitaMedica.clean()`` raises ValidationError when a cita is
        # CONFIRMADA via metodo_confirmacion=BIOMETRICO unless
        # ``verif_biometria`` is set. The verify view transitions the
        # cita to CONFIRMADA + BIOMETRICO in one ``save()`` (which
        # triggers full_clean()), so pre-stamping the flag here keeps
        # the happy path test in sync with the production transition.
        verif_biometria=True,
    )


def _patch_dp4500_with_handlers(*, challenge_handler, verify_handler):
    """Build a ``mock.patch`` that replaces ``dp4500_integration.views.HTTPClient``
    with a MockTransport-backed instance that routes POST /challenge/identity/
    through ``challenge_handler`` and POST /verify/identity/ through
    ``verify_handler``. Avoids the production client's no_service_key
    short-circuit by short-circuiting before ``_request`` sees the
    branch resolution.
    """
    def make_route(name, handler):
        def route(request):
            if name in str(request.url):
                return handler(request)
            raise AssertionError(
                f"Unexpected request to {request.url} while expecting {name}",
            )
        return route

    def handler_dispatch(request):
        url = str(request.url)
        if "/challenge/identity/" in url:
            return challenge_handler(request)
        if "/verify/identity/" in url:
            return verify_handler(request)
        if "/templates/" in url:
            # Cascade delete path — not exercised here.
            return httpx.Response(204, request=request)
        raise AssertionError(f"Unexpected request to {url}")

    def factory(*args, **kwargs):
        client = HTTPClient(
            base_url="https://dp4500.test",
            timeout_seconds=5,
            key_resolver=lambda _: "SeK_test",
        )
        client._client = httpx.Client(
            transport=httpx.MockTransport(handler_dispatch),
        )
        return client

    return mock.patch(
        "dp4500_integration.views.HTTPClient",
        side_effect=factory,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class VerifyHappyPathTests(TestCase):
    """``POST /api/integration/dp4500/citas/<id>/verificar/`` with a
    browser-signed payload transitions the cita to CONFIRMADA + writes
    the three biometric fields atomically.
    """

    @classmethod
    def setUpTestData(cls):
        cls.graph = _build_graph()

    def setUp(self):
        self.cita = _build_pending_cita(self.graph)
        self.client = Client()
        self.client.force_login(self.graph["admin"])

    def _payload(self):
        return {
            "challenge_id": "tok-abc",
            "signature": "sig-xyz",
            "timestamp": "2026-09-27T10:00:00+00:00",
        }

    def _happy_handlers(self):
        def challenge_handler(request):
            return httpx.Response(
                200,
                json={
                    "capture_token": "tok-abc",
                    "server_nonce": "nonce-1",
                    "ttl_seconds": 60,
                    "has_fingerprint": True,
                    "server_pubkey_jwk": {},
                },
                request=request,
            )

        def verify_handler(request):
            return httpx.Response(
                200,
                json={
                    "matched": True,
                    "audit_hash": "audit-happy",
                },
                request=request,
            )

        return challenge_handler, verify_handler

    def test_happy_path_writes_biometric_fields_and_transitions(self):
        ch, vf = self._happy_handlers()
        with _patch_dp4500_with_handlers(
            challenge_handler=ch, verify_handler=vf,
        ):
            response = self.client.post(
                f"/api/integration/dp4500/citas/{self.cita.pk}/verificar/",
                data=json.dumps(self._payload()),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["audit_hash"], "audit-happy")

        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.CONFIRMADA)
        self.assertEqual(
            self.cita.metodo_confirmacion,
            CitaMedica.MetodoConfirmacion.BIOMETRICO,
        )
        self.assertEqual(self.cita.biometric_challenge_id, "tok-abc")
        self.assertIsNotNone(self.cita.biometric_match_confidence)
        self.assertIsNotNone(self.cita.biometric_verified_at)


# ---------------------------------------------------------------------------
# 503 no service key
# ---------------------------------------------------------------------------


class VerifyNoServiceKeyTests(TestCase):
    """``503`` + ``Retry-After: 60`` when the ``Sucursal`` has no
    ``dp4500_service_key_id``. The view must never fall back to a
    zero/stub for the bearer — it must short-circuit before the HTTP
    client.
    """

    @classmethod
    def setUpTestData(cls):
        cls.graph = _build_graph()
        # ``Sucursal.dp4500_service_key_id`` stays NULL (default). The
        # backend's ``env_key_resolver(sucursal_id)`` looks up an env var
        # (``DP4500_SERVICE_KEY_SUCURSAL_<id>``); the test environment
        # has none of those set, so the resolver returns ``None``.
        cls.cita = _build_pending_cita(cls.graph)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.graph["admin"])

    def test_returns_503_with_retry_after(self):
        response = self.client.post(
            f"/api/integration/dp4500/citas/{self.cita.pk}/verificar/",
            data=json.dumps({
                "challenge_id": "tok-x",
                "signature": "sig-y",
                "timestamp": "2026-09-27T10:00:00+00:00",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers.get("Retry-After"), "60")
        body = response.json()
        self.assertEqual(body["code"], "dp4500_unavailable")
        # Cita stays pending.
        self.cita.refresh_from_db()
        self.assertEqual(
            self.cita.estado,
            CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        )
        self.assertIsNone(self.cita.biometric_challenge_id)


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


class VerifyConcurrentTests(TestCase):
    """Two concurrent verifies for the same cita serialize on
    ``select_for_update()``. The first commits the transition; the
    second sees ``estado != REALIZADA_PENDIENTE_VERIFICACION`` and
    returns ``409 cita_no_longer_pending``.
    """

    @classmethod
    def setUpTestData(cls):
        cls.graph = _build_graph()
        cls.cita = _build_pending_cita(cls.graph)

    @pytest.mark.skipif(
        connection.settings_dict.get("ENGINE", "").endswith("sqlite3"),
        reason="SQLite serializes writes — concurrent force_login cannot run; this test requires PostgreSQL/MySQL",
    )
    def test_concurrent_returns_409_to_loser(self):
        # The happy-path challenge/verify handlers respond immediately.
        def challenge_handler(request):
            return httpx.Response(
                200,
                json={
                    "capture_token": "tok-race",
                    "server_nonce": "nonce-race",
                    "ttl_seconds": 60,
                    "has_fingerprint": True,
                    "server_pubkey_jwk": {},
                },
                request=request,
            )

        def verify_handler(request):
            return httpx.Response(
                200,
                json={"matched": True, "audit_hash": "audit-race"},
                request=request,
            )

        # Atomic barrier used to coordinate the two client requests so
        # they both hit the view before either commits. Without the
        # barrier, the second thread's TCP handshake may complete
        # after the first response is returned, defeating the test.
        barrier = threading.Barrier(2)

        # Cookie-jar authenticated session per worker so each Django
        # Client carries its own session-cookie state — the standard
        # ``self.client`` fixture is shared, and concurrent
        # ``client.post(...)`` calls would interleave request headers.
        sessions = []

        def worker():
            session_client = Client()
            session_client.force_login(self.graph["admin"])
            sessions.append(session_client)
            barrier.wait()
            return session_client.post(
                f"/api/integration/dp4500/citas/{self.cita.pk}/verificar/",
                data=json.dumps({
                    "challenge_id": "tok-race",
                    "signature": "sig-race",
                    "timestamp": "2026-09-27T10:00:00+00:00",
                }),
                content_type="application/json",
            )

        with _patch_dp4500_with_handlers(
            challenge_handler=challenge_handler,
            verify_handler=verify_handler,
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                response_a, response_b = list(pool.map(lambda _: worker(), range(2)))

        status_codes = sorted([response_a.status_code, response_b.status_code])
        # Exactly one 200 + one 409.
        self.assertEqual(status_codes, [200, 409])
        # The 409 carries the documented code.
        losing = (
            response_a if response_a.status_code == 409 else response_b
        )
        self.assertEqual(
            losing.json()["code"], "cita_no_longer_pending",
        )
        # Cita is in CONFIRMADA with the three biometric fields set.
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.CONFIRMADA)
        self.assertEqual(self.cita.biometric_challenge_id, "tok-race")
