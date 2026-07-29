"""End-to-end tests for the biometric HTTP endpoints.

Django's ``TestCase`` wraps each test in a transaction so the SQLite
database is reset between methods without paying the cost of a full
migration. ``self.client`` is a Django test ``Client``; we use
``force_login`` to exercise session-based auth.

URL prefixes covered:

- ``/api/biometric/clientes/<id>/huella/enroll/``
- ``/api/biometric/clientes/<id>/huella/enroll/finalize/``
- ``/api/biometric/citas/<id>/huella/verify-init/``
- ``/api/biometric/citas/<id>/huella/verify-confirm/``
- ``/api/biometric/citas/<id>/huella/confirm-manual/``
- ``/api/biometric/agents/``
- ``/api/biometric/agents/list/``
- ``/api/biometric/agents/<id>/heartbeat/``
- ``/api/biometric/agents/<id>/``
"""

from __future__ import annotations

import json
import unittest
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from accounts.models import Rol, Usuario
from biometric.models import AgentToken, BiometricAttempt
from biometric.services.capture_tokens import capture_token_store
from catalogs.models import ProcEstetico, ProcEsteticosTipo, ServicioConfig, Sucursal, TipoServicio
from customers.models import Cliente, HuellaBiometricaCliente
from operations.models import CitaMedica, Operacion


def _payload(data):
    return json.dumps(data)


class BiometricEndpointBase(TestCase):
    """Shared setUp: roles, branches, users, a client and a cita."""

    @classmethod
    def setUpTestData(cls):
        cls.rol_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.rol_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        cls.rol_trabajador = Rol.objects.create(rol="TRABAJADOR")
        cls.rol_cliente = Rol.objects.create(rol="CLIENTE")

        cls.sucursal_a = Sucursal.objects.create(nombre="SucA-End", activa=True)
        cls.sucursal_b = Sucursal.objects.create(nombre="SucB-End", activa=True)

        cls.user_principal = Usuario.objects.create_user(
            username="end.principal",
            password="pw12345!",
            primer_nombre="Adm",
            apellido_paterno="P",
            rol=cls.rol_principal,
            sucursal=None,
        )
        cls.user_sucursal_a = Usuario.objects.create_user(
            username="end.sucursal.a",
            password="pw12345!",
            primer_nombre="Adm",
            apellido_paterno="A",
            rol=cls.rol_sucursal,
            sucursal=cls.sucursal_a,
        )
        cls.user_sucursal_b = Usuario.objects.create_user(
            username="end.sucursal.b",
            password="pw12345!",
            primer_nombre="Adm",
            apellido_paterno="B",
            rol=cls.rol_sucursal,
            sucursal=cls.sucursal_b,
        )

        cls.cliente_usuario = Usuario.objects.create_user(
            username="end.cliente",
            password="pw12345!",
            primer_nombre="Cli",
            apellido_paterno="Test",
            rol=cls.rol_cliente,
            fecha_nacimiento="1990-01-01",
        )
        cls.cliente = Cliente.objects.create(
            usuario=cls.cliente_usuario,
            fecha_nacimiento=cls.cliente_usuario.fecha_nacimiento,
            sucursal_registro=cls.sucursal_a,
        )

        cls.tipo_servicio = TipoServicio.objects.create(tipo="Consulta bio")
        cls.proc_tipo = ProcEsteticosTipo.objects.create(tipo="dep")
        cls.proc_estetico = ProcEstetico.objects.create(
            tipo_p_estetico=cls.proc_tipo, proceso="Depilacion definitiva"
        )
        cls.servicio_config = ServicioConfig.objects.create(
            tipo_servicio=cls.tipo_servicio,
            precio_base=Decimal("100.00"),
            activo=True,
        )

        cls.operacion = Operacion.objects.create(
            paciente=cls.cliente,
            servicio_config=cls.servicio_config,
            precio_total=Decimal("100.00"),
            cuotas_totales=1,
            sesiones_totales=1,
            estado=Operacion.Estado.EN_PROCESO,
        )
        cls.cita = CitaMedica.objects.create(
            operacion=cls.operacion,
            sucursal=cls.sucursal_a,
            fecha_hora="2099-01-01T10:00:00Z",
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        )

    def setUp(self):
        capture_token_store.reset()
        # Lock the threshold so threshold-related tests are stable.
        self._threshold_patch = mock.patch.dict(
            "os.environ", {"BIOMETRIC_MATCH_THRESHOLD": "0.85"}
        )
        self._threshold_patch.start()
        # Always use the mock agent client.
        self._agent_patch = mock.patch.dict(
            "os.environ",
            {
                "AGENT_CLIENT_CLASS": "biometric.services.agent_client.MockAgentClient",
                "AGENT_QUALITY_SCORE": "80",
                "AGENT_MATCH_SCORE": "0.93",
                "AGENT_FAIL_WITH": "",
            },
        )
        self._agent_patch.start()
        # Register an active agent so enroll/verify paths have a
        # target. PR #2 lifted the agent requirement; tests that
        # exercise the "no agent" path explicitly delete this row.
        # Use a hash that does not collide with the per-class hash
        # values in AgentListEndpointTests / AgentHeartbeatTests.
        self.agent = AgentToken.objects.create(
            name="Base endpoint agent",
            sucursal=self.sucursal_a,
            token_hash="f" * 64,
            public_url="https://agent.example.com",
            is_active=True,
        )

    def tearDown(self):
        self._agent_patch.stop()
        self._threshold_patch.stop()
        capture_token_store.reset()

    # --- helpers ----------------------------------------------------------

    def post(self, url, payload=None, user=None, headers=None):
        body = _payload(payload or {})
        headers = headers or {}
        if user is not None:
            self.client.force_login(user)
            csrf = headers.pop("csrf", None)
            extra = {"content_type": "application/json"}
            return self.client.post(url, body, **extra, **headers)
        extra = {"content_type": "application/json"}
        return self.client.post(url, body, **extra, **headers)


class EnrollmentEndpointTests(BiometricEndpointBase):
    def test_enroll_requires_authentication(self):
        url = reverse(
            "biometric:cliente-huella-enroll",
            kwargs={"cliente_id": self.cliente.id},
        )
        response = self.client.post(
            url,
            data=_payload({"consentimiento_aceptado": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_enroll_requires_consent(self):
        url = reverse(
            "biometric:cliente-huella-enroll",
            kwargs={"cliente_id": self.cliente.id},
        )
        response = self.post(
            url, {"consentimiento_aceptado": False}, user=self.user_principal
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "CONSENT_REQUIRED")

    def test_enroll_succeeds_and_persists_ciphertext(self):
        url = reverse(
            "biometric:cliente-huella-enroll",
            kwargs={"cliente_id": self.cliente.id},
        )
        response = self.post(
            url, {"consentimiento_aceptado": True}, user=self.user_principal
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertTrue(data["ok"])
        # Ciphertext is persisted (BinaryField returns bytes).
        huella = HuellaBiometricaCliente.objects.get(cliente=self.cliente)
        self.assertIsNotNone(huella.template_biometrico)
        self.assertTrue(bytes(huella.template_biometrico).startswith(b"gAAAAA"))
        self.assertEqual(huella.proveedor, "DIGITAL_PERSONA")
        # Audit log entry.
        attempt = BiometricAttempt.objects.filter(
            cliente=self.cliente, operation="ENROLL"
        ).first()
        self.assertIsNotNone(attempt)
        self.assertTrue(attempt.success)

    def test_enroll_worker_is_forbidden(self):
        url = reverse(
            "biometric:cliente-huella-enroll",
            kwargs={"cliente_id": self.cliente.id},
        )
        user = Usuario.objects.create_user(
            username="end.worker",
            password="pw12345!",
            primer_nombre="Tr",
            apellido_paterno="W",
            rol=self.rol_trabajador,
            sucursal=self.sucursal_a,
        )
        response = self.post(
            url, {"consentimiento_aceptado": True}, user=user
        )
        self.assertEqual(response.status_code, 403)

    def test_enroll_low_quality_returns_400_and_attempt(self):
        url = reverse(
            "biometric:cliente-huella-enroll",
            kwargs={"cliente_id": self.cliente.id},
        )
        with mock.patch.dict("os.environ", {"AGENT_QUALITY_SCORE": "10"}):
            response = self.post(
                url, {"consentimiento_aceptado": True}, user=self.user_principal
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "LOW_QUALITY")
        self.assertTrue(
            BiometricAttempt.objects.filter(
                cliente=self.cliente,
                operation="ENROLL",
                failure_reason="LOW_QUALITY",
            ).exists()
        )

    def test_enroll_agent_offline_returns_503(self):
        url = reverse(
            "biometric:cliente-huella-enroll",
            kwargs={"cliente_id": self.cliente.id},
        )
        with mock.patch.dict("os.environ", {"AGENT_FAIL_WITH": "NO_IMAGE"}):
            response = self.post(
                url, {"consentimiento_aceptado": True}, user=self.user_principal
            )
        self.assertEqual(response.status_code, 503)
        self.assertTrue(
            BiometricAttempt.objects.filter(
                cliente=self.cliente,
                operation="ENROLL",
                failure_reason="NO_IMAGE",
            ).exists()
        )


class FinalizeEndpointTests(BiometricEndpointBase):
    def test_finalize_with_capture_token(self):
        token = capture_token_store.create(
            {"kind": "enroll", "cliente_id": self.cliente.id,
             "user_id": self.user_principal.id},
        )
        url = reverse(
            "biometric:cliente-huella-enroll-finalize",
            kwargs={"cliente_id": self.cliente.id},
        )
        template_hex = "00" * 64
        response = self.post(
            url,
            {
                "capture_token": token,
                "template_b64": template_hex,
                "quality_score": 80,
                "device_serial": "PC-01",
                "template_format": "ANSI_378",
            },
            user=self.user_principal,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(
            HuellaBiometricaCliente.objects.filter(cliente=self.cliente).exists()
        )

    def test_finalize_missing_token(self):
        url = reverse(
            "biometric:cliente-huella-enroll-finalize",
            kwargs={"cliente_id": self.cliente.id},
        )
        response = self.post(url, {}, user=self.user_principal)
        self.assertEqual(response.status_code, 400)

    def test_finalize_expired_token(self):
        url = reverse(
            "biometric:cliente-huella-enroll-finalize",
            kwargs={"cliente_id": self.cliente.id},
        )
        response = self.post(
            url,
            {
                "capture_token": "never-issued",
                "template_b64": "00" * 64,
                "quality_score": 80,
            },
            user=self.user_principal,
        )
        self.assertEqual(response.status_code, 422)


class VerificationInitEndpointTests(BiometricEndpointBase):
    def test_verify_init_returns_capture_token_when_template_exists(self):
        # Enroll first.
        template_bytes = b"\x01\x02\x03" * 32
        from biometric.services.encryption import encrypt_template

        HuellaBiometricaCliente.objects.create(
            cliente=self.cliente,
            proveedor="DIGITAL_PERSONA",
            template_biometrico=encrypt_template(template_bytes),
            template_format="DP_PROPRIETARY",
            consentimiento_aceptado=True,
            activo=True,
            device_serial="MOCK-001",
        )
        url = reverse(
            "biometric:cita-huella-verify-init",
            kwargs={"cita_id": self.cita.id},
        )
        response = self.post(url, {}, user=self.user_sucursal_a)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["has_fingerprint"])
        self.assertIn("capture_token", data)
        # Backend orchestrates the match; the frontend never sees
        # agent_url. The score and threshold come back so the UI can
        # show "matched / not matched" pending verify_confirm.
        self.assertIn("score", data)
        self.assertIn("threshold", data)
        self.assertNotIn("agent_url", data)

    def test_verify_init_without_template_returns_manual_only(self):
        url = reverse(
            "biometric:cita-huella-verify-init",
            kwargs={"cita_id": self.cita.id},
        )
        response = self.post(url, {}, user=self.user_sucursal_a)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["has_fingerprint"])
        self.assertTrue(data["manual_only"])

    def test_verify_init_cita_in_wrong_state(self):
        self.cita.estado = CitaMedica.Estado.PROGRAMADA
        self.cita.save()
        url = reverse(
            "biometric:cita-huella-verify-init",
            kwargs={"cita_id": self.cita.id},
        )
        response = self.post(url, {}, user=self.user_sucursal_a)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_STATE")

    def test_verify_init_no_agent_returns_503(self):
        AgentToken.objects.all().delete()
        # Need to enroll a fingerprint first.
        from biometric.services.encryption import encrypt_template

        HuellaBiometricaCliente.objects.create(
            cliente=self.cliente,
            proveedor="DIGITAL_PERSONA",
            template_biometrico=encrypt_template(b"x" * 64),
            template_format="DP_PROPRIETARY",
            consentimiento_aceptado=True,
            activo=True,
            device_serial="MOCK-001",
        )
        url = reverse(
            "biometric:cita-huella-verify-init",
            kwargs={"cita_id": self.cita.id},
        )
        response = self.post(url, {}, user=self.user_sucursal_a)
        self.assertEqual(response.status_code, 503)


class VerificationConfirmEndpointTests(BiometricEndpointBase):
    def setUp(self):
        super().setUp()
        from biometric.services.encryption import encrypt_template

        self.huella = HuellaBiometricaCliente.objects.create(
            cliente=self.cliente,
            proveedor="DIGITAL_PERSONA",
            template_biometrico=encrypt_template(b"x" * 64),
            template_format="DP_PROPRIETARY",
            consentimiento_aceptado=True,
            activo=True,
            device_serial="MOCK-001",
        )
        self.agent = AgentToken.objects.create(
            name="Confirm-agent",
            sucursal=self.sucursal_a,
            token_hash="e" * 64,
            public_url="https://confirm.example.com",
            is_active=True,
        )
        self.token = capture_token_store.create(
            {
                "kind": "verify",
                "cita_id": self.cita.id,
                "cliente_id": self.cliente.id,
                "agent_id": self.agent.id,
                "user_id": self.user_sucursal_a.id,
            },
        )

    def test_match_above_threshold_confirms_cita(self):
        url = reverse(
            "biometric:cita-huella-verify-confirm",
            kwargs={"cita_id": self.cita.id},
        )
        response = self.post(
            url,
            {"capture_token": self.token, "score": 0.92},
            user=self.user_sucursal_a,
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["matched"])
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.CONFIRMADA)
        self.assertEqual(self.cita.metodo_confirmacion, "BIOMETRICO")
        self.assertTrue(self.cita.verif_biometria)
        self.huella.refresh_from_db()
        self.assertIsNotNone(self.huella.last_match_at)
        self.assertEqual(self.huella.last_match_score, Decimal("0.92"))

    def test_match_below_threshold_keeps_pending(self):
        url = reverse(
            "biometric:cita-huella-verify-confirm",
            kwargs={"cita_id": self.cita.id},
        )
        response = self.post(
            url,
            {"capture_token": self.token, "score": 0.50},
            user=self.user_sucursal_a,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["matched"])
        self.cita.refresh_from_db()
        self.assertEqual(
            self.cita.estado,
            CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        )
        self.assertTrue(
            BiometricAttempt.objects.filter(
                cita=self.cita, success=False, failure_reason="BELOW_THRESHOLD"
            ).exists()
        )

    def test_invalid_capture_token_returns_422(self):
        url = reverse(
            "biometric:cita-huella-verify-confirm",
            kwargs={"cita_id": self.cita.id},
        )
        response = self.post(
            url,
            {"capture_token": "never-issued", "score": 0.9},
            user=self.user_sucursal_a,
        )
        self.assertEqual(response.status_code, 422)

    def test_invalid_score_returns_400(self):
        url = reverse(
            "biometric:cita-huella-verify-confirm",
            kwargs={"cita_id": self.cita.id},
        )
        response = self.post(
            url,
            {"capture_token": self.token, "score": "not-a-number"},
            user=self.user_sucursal_a,
        )
        self.assertEqual(response.status_code, 400)


class CrossSucursalVerificationTests(BiometricEndpointBase):
    """Explicit cross-sucursal lookup test (spec requirement 7)."""

    def test_template_enrolled_in_branch_a_visible_from_branch_b(self):
        # Enroll in branch A (admin_sucursal_a is the operator).
        url_enroll = reverse(
            "biometric:cliente-huella-enroll",
            kwargs={"cliente_id": self.cliente.id},
        )
        response_enroll = self.post(
            url_enroll,
            {"consentimiento_aceptado": True},
            user=self.user_sucursal_a,
        )
        self.assertEqual(response_enroll.status_code, 201, response_enroll.content)

        # Move the cita to branch B (a different branch of the same
        # cliente). Branch admin B calls verify-init.
        self.cita.sucursal = self.sucursal_b
        self.cita.save()
        AgentToken.objects.create(
            name="Branch B agent",
            sucursal=self.sucursal_b,
            token_hash="b" * 64,
            public_url="https://agent-b.example.com",
            is_active=True,
        )

        url_init = reverse(
            "biometric:cita-huella-verify-init",
            kwargs={"cita_id": self.cita.id},
        )
        response_init = self.post(url_init, {}, user=self.user_sucursal_b)
        self.assertEqual(response_init.status_code, 200, response_init.content)
        data = response_init.json()
        # The lookup finds the row even though it was enrolled at A.
        self.assertTrue(data["has_fingerprint"])


class AgentCreateEndpointTests(BiometricEndpointBase):
    def test_principal_can_create(self):
        url = reverse("biometric:agent-root")
        response = self.post(
            url,
            {
                "name": "PC-1",
                "sucursal_id": self.sucursal_a.id,
                "public_url": "https://agent-1.example.com",
            },
            user=self.user_principal,
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertIn("token", data)
        self.assertEqual(len(data["token"]), 43)  # token_urlsafe(32) length
        # The raw token is also exposed; the create response includes
        # both fields for clarity.
        self.assertTrue(AgentToken.objects.filter(name="PC-1").exists())
        # PR #2: the token is Fernet-encrypted on the row so the
        # backend can perform outbound calls (HttpAgentClient).
        agent = AgentToken.objects.get(name="PC-1")
        self.assertIsNotNone(agent.token_encrypted)
        self.assertTrue(
            bytes(agent.token_encrypted).startswith(b"gAAAAA"),
            f"Encryption marker missing: {bytes(agent.token_encrypted)[:16]!r}",
        )
        # The raw token decrypts back to the same value the response
        # advertised.
        self.assertEqual(
            agent.decrypt_raw_token(),
            data["token"],
        )
        # No token_hash or raw token leaks in subsequent list.
        response_list = self.client.get(
            reverse("biometric:agent-root"),
        )
        self.client.force_login(self.user_principal)
        response_list = self.client.get(reverse("biometric:agent-root"))
        self.assertEqual(response_list.status_code, 200)
        listed = response_list.json()["results"]
        for entry in listed:
            self.assertNotIn("token", entry)
            self.assertNotIn("token_hash", entry)

    def test_branch_admin_cannot_create(self):
        url = reverse("biometric:agent-root")
        response = self.post(
            url,
            {
                "name": "PC-2",
                "sucursal_id": self.sucursal_a.id,
                "public_url": "https://agent-2.example.com",
            },
            user=self.user_sucursal_a,
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_fields(self):
        url = reverse("biometric:agent-root")
        response = self.post(url, {"name": "x"}, user=self.user_principal)
        self.assertEqual(response.status_code, 400)

    def test_duplicate_public_url_rejected(self):
        AgentToken.objects.create(
            name="existing",
            sucursal=self.sucursal_a,
            token_hash="a" * 64,
            public_url="https://dup.example.com",
            is_active=True,
        )
        url = reverse("biometric:agent-root")
        response = self.post(
            url,
            {
                "name": "dup",
                "sucursal_id": self.sucursal_a.id,
                "public_url": "https://dup.example.com",
            },
            user=self.user_principal,
        )
        self.assertEqual(response.status_code, 422)


class AgentListEndpointTests(BiometricEndpointBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Hand-create a couple of agents so we can test visibility.
        cls.agent_a = AgentToken.objects.create(
            name="A-agent",
            sucursal=cls.sucursal_a,
            token_hash="a" * 64,
            public_url="https://a.example.com",
            is_active=True,
        )
        cls.agent_b = AgentToken.objects.create(
            name="B-agent",
            sucursal=cls.sucursal_b,
            token_hash="b" * 64,
            public_url="https://b.example.com",
            is_active=True,
        )

    def test_principal_sees_all(self):
        self.client.force_login(self.user_principal)
        response = self.client.get(reverse("biometric:agent-root"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # 1 base agent + 2 hand-created = 3 active rows.
        self.assertEqual(len(data["results"]), 3)
        for entry in data["results"]:
            self.assertNotIn("token", entry)
            self.assertIn("token_fingerprint", entry)

    def test_branch_admin_sees_only_own_sucursal(self):
        self.client.force_login(self.user_sucursal_a)
        response = self.client.get(reverse("biometric:agent-root"))
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        # The base endpoint agent + A-agent both belong to sucursal_a.
        self.assertEqual(len(results), 2)
        ids = {r["id"] for r in results}
        self.assertIn(self.agent_a.id, ids)
        self.assertIn(self.agent.id, ids)

    def test_unauthenticated_is_rejected(self):
        response = self.client.get(reverse("biometric:agent-root"))
        self.assertEqual(response.status_code, 401)


class AgentHeartbeatTests(BiometricEndpointBase):
    def setUp(self):
        super().setUp()
        # Replace the default placeholder agent with one that has
        # a real, deterministic hash so the heartbeat path can
        # authenticate against it.
        self.agent.delete()
        self.agent = AgentToken.objects.create(
            name="HB-agent",
            sucursal=self.sucursal_a,
            token_hash="1" * 64,
            public_url="https://hb.example.com",
            is_active=True,
        )
        self.raw = "raw-token-123"

    def _bearer(self, raw):
        return f"Bearer {raw}"

    def test_heartbeat_updates_last_seen(self):
        # The hash must match.
        import hashlib

        self.agent.token_hash = hashlib.sha256(self.raw.encode()).hexdigest()
        self.agent.save()
        from django.utils import timezone

        before = timezone.now()
        response = self.client.post(
            reverse(
                "biometric:agent-heartbeat",
                kwargs={"agent_id": self.agent.id},
            ),
            HTTP_AUTHORIZATION=self._bearer(self.raw),
        )
        self.assertEqual(response.status_code, 204)
        self.agent.refresh_from_db()
        self.assertIsNotNone(self.agent.last_seen_at)
        self.assertGreaterEqual(self.agent.last_seen_at, before)

    def test_heartbeat_with_invalid_token_returns_401(self):
        response = self.client.post(
            reverse(
                "biometric:agent-heartbeat",
                kwargs={"agent_id": self.agent.id},
            ),
            HTTP_AUTHORIZATION="Bearer wrong-token",
        )
        self.assertEqual(response.status_code, 401)

    def test_heartbeat_without_bearer_returns_401(self):
        response = self.client.post(
            reverse(
                "biometric:agent-heartbeat",
                kwargs={"agent_id": self.agent.id},
            ),
        )
        self.assertEqual(response.status_code, 401)

    def test_heartbeat_inactive_agent_rejected(self):
        import hashlib

        self.agent.token_hash = hashlib.sha256(self.raw.encode()).hexdigest()
        self.agent.is_active = False
        self.agent.save()
        response = self.client.post(
            reverse(
                "biometric:agent-heartbeat",
                kwargs={"agent_id": self.agent.id},
            ),
            HTTP_AUTHORIZATION=self._bearer(self.raw),
        )
        self.assertEqual(response.status_code, 401)


class AgentDeleteTests(BiometricEndpointBase):
    def setUp(self):
        super().setUp()
        self.agent = AgentToken.objects.create(
            name="del-agent",
            sucursal=self.sucursal_a,
            token_hash="d" * 64,
            public_url="https://del.example.com",
            is_active=True,
        )

    def test_principal_can_soft_delete(self):
        self.client.force_login(self.user_principal)
        response = self.client.delete(
            reverse(
                "biometric:agent-detail",
                kwargs={"agent_id": self.agent.id},
            ),
        )
        self.assertEqual(response.status_code, 204)
        self.agent.refresh_from_db()
        self.assertFalse(self.agent.is_active)

    def test_branch_admin_cannot_delete(self):
        self.client.force_login(self.user_sucursal_a)
        response = self.client.delete(
            reverse(
                "biometric:agent-detail",
                kwargs={"agent_id": self.agent.id},
            ),
        )
        self.assertEqual(response.status_code, 403)
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.is_active)

    def test_anonymous_is_rejected(self):
        response = self.client.delete(
            reverse(
                "biometric:agent-detail",
                kwargs={"agent_id": self.agent.id},
            ),
        )
        self.assertEqual(response.status_code, 401)


class ManualConfirmationTests(BiometricEndpointBase):
    def test_manual_confirm_works_alongside_biometric_failures(self):
        # Drive 3 failed biometric attempts first.
        from biometric.services.encryption import encrypt_template

        huella = HuellaBiometricaCliente.objects.create(
            cliente=self.cliente,
            proveedor="DIGITAL_PERSONA",
            template_biometrico=encrypt_template(b"x" * 64),
            template_format="DP_PROPRIETARY",
            consentimiento_aceptado=True,
            activo=True,
            device_serial="MOCK-001",
        )
        for _ in range(3):
            BiometricAttempt.objects.create(
                cita=self.cita,
                cliente=self.cliente,
                operation=BiometricAttempt.Operation.VERIFY,
                success=False,
                score=Decimal("0.10"),
                failure_reason="BELOW_THRESHOLD",
            )

        # Manual fallback should still succeed.
        url = reverse(
            "biometric:cita-huella-confirm-manual",
            kwargs={"cita_id": self.cita.id},
        )
        response = self.post(url, {"metodo": "MANUAL"}, user=self.user_sucursal_a)
        self.assertEqual(response.status_code, 200, response.content)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.CONFIRMADA)
        self.assertEqual(self.cita.metodo_confirmacion, "MANUAL")
        self.assertFalse(self.cita.verif_biometria)
        # 3 previous attempts logged + cita still confirmable.
        self.assertEqual(
            BiometricAttempt.objects.filter(cita=self.cita).count(), 3
        )

    def test_manual_confirm_rejects_wrong_state(self):
        self.cita.estado = CitaMedica.Estado.PROGRAMADA
        self.cita.save()
        url = reverse(
            "biometric:cita-huella-confirm-manual",
            kwargs={"cita_id": self.cita.id},
        )
        response = self.post(url, {}, user=self.user_sucursal_a)
        self.assertEqual(response.status_code, 400)
