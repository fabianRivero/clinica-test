"""Backend tests for the direct client creation backend plumbing.

Spec under test: ``openspec/changes/direct-client-creation/specs/admin-direct-client-creation/spec.md``
and the modified ``admin-prospect-conversion`` requirement (third finalize branch).

Concerns covered:

* ``admin_direct_client_initialize`` creates a ``ProspectoConversionBorrador``
  with ``prospecto=NULL`` and ``cliente=NULL``, attributed to the calling
  admin, and returns the standard conversion detail payload.
* Non-admins get a 403 on the initialize endpoint with no draft row
  produced.
* Step 1 in direct mode rejects duplicate ``ci`` and ``username`` with a
  Spanish 400 (the existing ``_validate_user_step`` rules apply: "self"
  exclusion is a no-op when neither FK is set, so global uniqueness is
  enforced as-is).
* Finalize happy path creates a ``Usuario (CLIENTE, is_active=True)`` +
  ``Cliente`` pair inside the existing ``transaction.atomic()`` block,
  returns the new ``cliente_codigo``, and deletes the draft.
* Finalize rolls back on a forced DB error: no ``Usuario``, no
  ``Cliente``, draft preserved, 500 returned.
* Cancel at any step deletes the ``(null, null)`` draft without creating
  any ``Usuario`` or ``Cliente``.
* Regression: prospect→client finalize still calls
  ``marcar_como_convertido`` and migrates the prospect biometric.
* Regression: reactivation finalize still updates only the existing
  ``Cliente`` (no new ``Usuario``).

Style follows the existing project patterns from
``tests/test_admin_client_profile.py`` (``TestCase`` + ``django.test.Client``
+ session auth, NOT DRF APIClient) and the helper conventions used by
``tests/suspension/test_conversion_split.py``.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago
from catalogs.models import (
    GradoDeshidratacion,
    GrosorPiel,
    ServicioConfig,
    Sucursal,
    TipoPiel,
    TipoServicio,
)
from customers.models import (
    Cliente,
    HuellaBiometricaCliente,
    Prospecto,
    ProspectoConversionBorrador,
)
from operations.models import Operacion


INITIALIZE_URL = "/api/admin/clientes/directo/initialize/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_graph():
    """Build the minimum role/branch/admin graph for direct client tests."""
    rol_cliente = Rol.objects.create(rol="CLIENTE")
    rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
    sucursal = Sucursal.objects.create(nombre="Directo-Centro", activa=True)

    admin = Usuario.objects.create_user(
        username="directo.admin",
        password="pw12345!",
        primer_nombre="Ana",
        apellido_paterno="Directo",
        email="directo.admin@example.com",
        rol=rol_admin,
        sucursal=sucursal,
    )

    # A "taken" Cliente + Usuario used by the uniqueness tests. The CI
    # "9999999" and the username "taken_user" MUST collide with whatever
    # the wizard sends at step 1 of the direct creation flow.
    taken_user = Usuario.objects.create_user(
        username="taken_user",
        password="pw12345!",
        primer_nombre="Taken",
        apellido_paterno="User",
        rol=rol_cliente,
        sucursal=sucursal,
    )
    taken_cliente = Cliente.objects.create(
        usuario=taken_user,
        sucursal_origen=sucursal,
        ci="9999999",
        telefono="7000-0000",
        fecha_nacimiento=date(1985, 5, 5),
    )

    catalog_ids = {
        "tipo_piel": TipoPiel.objects.create(nombre="Mixta", activo=True).id,
        "grado_deshidratacion": GradoDeshidratacion.objects.create(
            nombre="Medio", activo=True
        ).id,
        "grosor_piel": GrosorPiel.objects.create(nombre="Grueso", activo=True).id,
    }

    tipo = TipoServicio.objects.create(tipo="Consulta", activo=True)
    servicio = ServicioConfig.objects.create(
        tipo_servicio=tipo, precio_base=Decimal("100"), activo=True
    )

    return {
        "admin": admin,
        "sucursal": sucursal,
        "taken_user": taken_user,
        "taken_cliente": taken_cliente,
        "catalog_ids": catalog_ids,
        "servicio": servicio,
    }


def _make_direct_draft(*, sucursal, admin, servicio, catalog_ids, today):
    """Build a fully-populated direct creation draft (prospecto=NULL,
    cliente=NULL) ready for the finalize endpoint."""
    return ProspectoConversionBorrador.objects.create(
        cliente=None,
        prospecto=None,
        iniciado_por=admin,
        datos_usuario={
            "primerNombre": "Maria",
            "segundoNombre": "Luisa",
            "apellidoPaterno": "Lopez",
            "apellidoMaterno": "Gomez",
            "username": "maria.directo",
            "email": "maria.directo@example.com",
            "telefono": "7000-9999",
            "ci": "8888888",
            "passwordHash": make_password("pw-directo"),
            "fechaNacimiento": "1992-03-03",
            "nroHijos": 1,
            "direccionDomicilio": "Calle Directa 123",
            "ocupacion": "Estudiante",
            "observacionesCliente": "obs-directo",
        },
        datos_operacion={
            "serviceConfigId": servicio.id,
            "zonaGeneral": "Cara",
            "zonaEspecifica": "Mejilla",
            "precioTotal": "100.00",
            "cuotasTotales": 1,
            "sesionesTotales": 1,
            "fechaInicio": str(today),
            "estado": Operacion.Estado.EN_PROCESO,
            "fechasVencimientoCuotas": [str(today)],
        },
        datos_ficha={
            "fechaFicha": str(today),
            "motivoConsulta": "consulta-directa",
            "observaciones": "",
            "consentimientoAceptado": True,
            "firmaPacienteCi": "8888888",
            "analisisEstetico": {
                "tipoPielId": str(catalog_ids["tipo_piel"]),
                "gradoDeshidratacionId": str(catalog_ids["grado_deshidratacion"]),
                "grosorPielId": str(catalog_ids["grosor_piel"]),
                "patologiaIds": [],
            },
            "antecedentes": [],
            "implantes": [],
            "cirugias": [],
            "fieldResponses": {},
        },
        datos_biometria={"provider": "MOCK", "template": "BASE64-DIRECTO", "quality": 80},
        paso_usuario_completado=True,
        paso_operacion_completado=True,
        paso_ficha_completado=True,
        paso_biometria_completado=True,
        paso_actual=ProspectoConversionBorrador.Paso.BIOMETRIA,
    )


def _make_prospect_draft(*, prospecto, admin, servicio, catalog_ids, today):
    """Build a fully-populated prospect conversion draft — used by the
    regression test that asserts prospect finalize is byte-for-byte
    unchanged."""
    return ProspectoConversionBorrador.objects.create(
        cliente=None,
        prospecto=prospecto,
        iniciado_por=admin,
        datos_usuario={
            "primerNombre": prospecto.primer_nombre,
            "apellidoPaterno": prospecto.apellido_paterno,
            "username": "regression.prospect.user",
            "email": "regression.prospect@example.com",
            "telefono": prospecto.telefono or "7000-0000",
            "ci": "7777777",
            "passwordHash": make_password("pw-prospect"),
            "fechaNacimiento": "1990-10-10",
            "nroHijos": 0,
            "direccionDomicilio": "Calle Prospecto",
            "ocupacion": "Est",
            "observacionesCliente": "obs-prospect",
        },
        datos_operacion={
            "serviceConfigId": servicio.id,
            "zonaGeneral": "Zona",
            "zonaEspecifica": "Detalle",
            "precioTotal": "100.00",
            "cuotasTotales": 1,
            "sesionesTotales": 1,
            "fechaInicio": str(today),
            "estado": Operacion.Estado.EN_PROCESO,
            "fechasVencimientoCuotas": [str(today)],
        },
        datos_ficha={
            "fechaFicha": str(today),
            "motivoConsulta": "consulta-prospect",
            "observaciones": "",
            "consentimientoAceptado": True,
            "firmaPacienteCi": "7777777",
            "analisisEstetico": {
                "tipoPielId": str(catalog_ids["tipo_piel"]),
                "gradoDeshidratacionId": str(catalog_ids["grado_deshidratacion"]),
                "grosorPielId": str(catalog_ids["grosor_piel"]),
                "patologiaIds": [],
            },
            "antecedentes": [],
            "implantes": [],
            "cirugias": [],
            "fieldResponses": {},
        },
        datos_biometria={"provider": "MOCK", "template": "BASE64-PROSPECT", "quality": 80},
        paso_usuario_completado=True,
        paso_operacion_completado=True,
        paso_ficha_completado=True,
        paso_biometria_completado=True,
        paso_actual=ProspectoConversionBorrador.Paso.BIOMETRIA,
    )


def _make_reactivation_draft(*, cliente, admin, servicio, catalog_ids, today):
    """Build a fully-populated reactivation draft — used by the regression
    test that asserts reactivation finalize is byte-for-byte unchanged."""
    return ProspectoConversionBorrador.objects.create(
        cliente=cliente,
        prospecto=None,
        iniciado_por=admin,
        datos_usuario={
            "primerNombre": cliente.usuario.primer_nombre,
            "apellidoPaterno": cliente.usuario.apellido_paterno,
            "username": cliente.usuario.username,
            "passwordHash": make_password("pw-reactivation"),
            "fechaNacimiento": "1990-01-01",
            "ci": cliente.ci,
            "observacionesCliente": "obs-reactivation",
        },
        datos_operacion={
            "serviceConfigId": servicio.id,
            "zonaGeneral": "Zona",
            "zonaEspecifica": "Detalle",
            "precioTotal": "100.00",
            "cuotasTotales": 1,
            "sesionesTotales": 1,
            "fechaInicio": str(today),
            "estado": Operacion.Estado.EN_PROCESO,
            "fechasVencimientoCuotas": [str(today)],
        },
        datos_ficha={
            "fechaFicha": str(today),
            "motivoConsulta": "consulta-reactivation",
            "observaciones": "",
            "consentimientoAceptado": True,
            "firmaPacienteCi": cliente.ci,
            "analisisEstetico": {
                "tipoPielId": str(catalog_ids["tipo_piel"]),
                "gradoDeshidratacionId": str(catalog_ids["grado_deshidratacion"]),
                "grosorPielId": str(catalog_ids["grosor_piel"]),
                "patologiaIds": [],
            },
            "antecedentes": [],
            "implantes": [],
            "cirugias": [],
            "fieldResponses": {},
        },
        datos_biometria={"provider": "MOCK", "template": "BASE64-REACTIVATION", "quality": 80},
        paso_usuario_completado=True,
        paso_operacion_completado=True,
        paso_ficha_completado=True,
        paso_biometria_completado=True,
        paso_actual=ProspectoConversionBorrador.Paso.BIOMETRIA,
    )


def _step1_payload(*, ci="8888888", username="maria.directo"):
    """A valid step 1 payload for the direct wizard. ``ci`` and
    ``username`` are configurable so each test can substitute a
    colliding value."""
    return {
        "primerNombre": "Maria",
        "apellidoPaterno": "Lopez",
        "username": username,
        "password": "pw-directo",
        "email": "maria.directo@example.com",
        "telefono": "7000-9999",
        "ci": ci,
        "fechaNacimiento": "1992-03-03",
        "nroHijos": 1,
        "direccionDomicilio": "Calle Directa 123",
        "ocupacion": "Estudiante",
        "observacionesCliente": "obs-directo",
    }


def _post_step1(client_http, draft_id, payload):
    return client_http.post(
        f"/api/admin/clientes/directo/{draft_id}/paso-1/",
        data=json.dumps(payload),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class DirectClientInitializeTests(TestCase):
    """Spec — admin-only initialize endpoint + non-admin 403."""

    @classmethod
    def setUpTestData(cls):
        cls.graph = _build_graph()

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.graph["admin"])

    def test_initialize_creates_draft_with_both_fks_null(self):
        """Spec — Direct Client Entry Point.

        POST /api/admin/clientes/directo/initialize/ creates a
        ``ProspectoConversionBorrador`` with ``prospecto=NULL`` and
        ``cliente=NULL``, attributed to the current admin, and returns
        the standard conversion detail payload.
        """
        before_count = ProspectoConversionBorrador.objects.count()
        response = self.http.post(INITIALIZE_URL)
        self.assertEqual(response.status_code, 201)

        body = response.json()
        # Exactly one draft was created.
        self.assertEqual(
            ProspectoConversionBorrador.objects.count(), before_count + 1
        )
        draft = ProspectoConversionBorrador.objects.latest("id")
        # The two FKs are both NULL.
        self.assertIsNone(draft.prospecto_id)
        self.assertIsNone(draft.cliente_id)
        # Attribution: the calling admin.
        self.assertEqual(draft.iniciado_por_id, self.graph["admin"].id)
        # Response includes the standard detail keys.
        self.assertIn("prospect", body)
        self.assertIsNone(body["prospect"])
        self.assertIn("client", body)
        self.assertIsNone(body["client"])
        self.assertIn("draft", body)
        # The serialized draft mirrors the wizard state machine (currentStep,
        # stepUserCompleted, …) rather than the model PK — verify those.
        self.assertEqual(body["draft"]["currentStep"], draft.paso_actual)
        self.assertFalse(body["draft"]["stepUserCompleted"])
        self.assertEqual(body["draft"]["biometricData"]["provider"], "MOCK")

    def test_initialize_rejects_non_admin_with_403(self):
        """Spec — Non-admin is forbidden.

        A non-admin caller gets a 403 with no draft row created.
        """
        # Use the seeded "taken" Cliente's Usuario (CLIENTE role) as the
        # non-admin principal.
        non_admin = self.graph["taken_user"]
        self.assertFalse(
            non_admin.is_staff,
            "fixture: taken_user must NOT be staff/admin",
        )

        non_admin_http = Client()
        non_admin_http.force_login(non_admin)

        before_count = ProspectoConversionBorrador.objects.count()
        response = non_admin_http.post(INITIALIZE_URL)
        self.assertEqual(response.status_code, 403)
        # No draft was created by the rejected call.
        self.assertEqual(
            ProspectoConversionBorrador.objects.count(), before_count
        )


class DirectClientStep1ValidationTests(TestCase):
    """Spec — Step 1 Uniqueness.

    Duplicate CI and duplicate username are rejected with 400 + Spanish
    message; the global uniqueness logic from ``_validate_user_step``
    applies as-is (the "self" exclusion is a no-op when neither FK is
    set, so the collision is detected).
    """

    @classmethod
    def setUpTestData(cls):
        cls.graph = _build_graph()
        # Pre-create the (null, null) draft the way the initialize
        # endpoint would. Tests then POST paso-1 against this draft.
        cls.draft = ProspectoConversionBorrador.objects.create(
            prospecto=None,
            cliente=None,
            iniciado_por=cls.graph["admin"],
        )

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.graph["admin"])

    def test_step1_rejects_duplicate_ci_with_spanish_message(self):
        """Spec — Duplicate CI rejected.

        The CI "9999999" already belongs to ``taken_cliente``. Submitting
        step 1 with that CI in direct mode returns a 400 whose error
        payload references CI uniqueness in Spanish.
        """
        payload = _step1_payload(ci="9999999")
        response = _post_step1(self.http, self.draft.id, payload)
        self.assertEqual(response.status_code, 400)

        body = response.json()
        # The endpoint wraps per-field errors in ``errors``.
        self.assertIn("errors", body)
        self.assertIn("ci", body["errors"])
        ci_error = body["errors"]["ci"]
        self.assertIn("Ya existe", ci_error)
        # No Usuario / Cliente was created for the rejected call.
        self.assertFalse(
            Usuario.objects.filter(username=payload["username"]).exists()
        )
        # The draft is preserved (caller can edit + retry).
        self.assertTrue(
            ProspectoConversionBorrador.objects.filter(pk=self.draft.id).exists()
        )

    def test_step1_rejects_duplicate_username_with_spanish_message(self):
        """Spec — Duplicate username rejected.

        The username "taken_user" already exists on the ``taken_user``
        ``Usuario``. Submitting step 1 with that username in direct mode
        returns a 400 with a Spanish per-field error.
        """
        payload = _step1_payload(username="taken_user")
        response = _post_step1(self.http, self.draft.id, payload)
        self.assertEqual(response.status_code, 400)

        body = response.json()
        self.assertIn("errors", body)
        self.assertIn("username", body["errors"])
        username_error = body["errors"]["username"]
        self.assertIn("Ya existe", username_error)
        # No Cliente was created.
        self.assertFalse(
            Cliente.objects.filter(ci=payload["ci"]).exists()
        )
        self.assertTrue(
            ProspectoConversionBorrador.objects.filter(pk=self.draft.id).exists()
        )

    def test_step1_valid_payload_advances_draft(self):
        """Sanity — the same payload that triggers uniqueness with the
        colliding string advances the draft on a clean run.
        """
        payload = _step1_payload()
        response = _post_step1(self.http, self.draft.id, payload)
        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.paso_usuario_completado)
        self.assertGreaterEqual(
            self.draft.paso_actual, ProspectoConversionBorrador.Paso.OPERACION
        )


class DirectClientFinalizeTests(TestCase):
    """Spec — Finalize Atomic Creation.

    Finalize in direct mode creates a new ``Usuario (CLIENTE,
    is_active=True)`` + ``Cliente`` in one ``transaction.atomic()`` block;
    on any error, no rows persist and the draft is preserved.
    """

    @classmethod
    def setUpTestData(cls):
        cls.graph = _build_graph()
        cls.today = date.today()

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.graph["admin"])

    def _finalize(self, draft):
        pdf = SimpleUploadedFile(
            "doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
        )
        return self.http.post(
            f"/api/admin/clientes/directo/{draft.id}/finalizar/",
            data={"documento_escaneado_pdf": pdf},
        )

    def test_finalize_happy_path_creates_user_and_cliente(self):
        """Spec — Successful finalize.

        Direct finalize creates ``Usuario (CLIENTE)`` + ``Cliente`` with a
        non-null ``cliente_codigo``, deletes the draft, and returns 201.
        """
        draft = _make_direct_draft(
            sucursal=self.graph["sucursal"],
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
        )

        # Sanity: no Usuario/Cliente yet for the direct username.
        self.assertFalse(
            Usuario.objects.filter(username="maria.directo").exists()
        )

        # The .env defaults BIOMETRIC_SUSPENDED=1; force the suspension
        # off locally so the finalize biometric stamping path runs and
        # the wizard-payload template is persisted against the new
        # cliente (matches the reactivation path the direct branch
        # reuses).
        with override_settings(BIOMETRIC_SUSPENDED=False):
            response = self._finalize(draft)
        self.assertEqual(response.status_code, 201)

        new_user = Usuario.objects.get(username="maria.directo")
        self.assertEqual(new_user.primer_nombre, "Maria")
        self.assertEqual(new_user.apellido_paterno, "Lopez")
        self.assertTrue(new_user.is_active)
        self.assertFalse(new_user.is_staff)
        self.assertFalse(new_user.is_superuser)
        # Rol: CLIENTE.
        self.assertEqual(new_user.rol.rol, "CLIENTE")
        self.assertTrue(new_user.check_password("pw-directo"))

        new_cliente = Cliente.objects.get(usuario=new_user)
        self.assertEqual(new_cliente.ci, "8888888")
        self.assertEqual(new_cliente.fecha_nacimiento, date(1992, 3, 3))
        # The branch resolves to the admin's effective branch (Direct
        # mode has no prospecto.sucursal_registro to fall back on, so the
        # view uses ``_get_branch_for_scope_check or get_user_branch`` —
        # which for a principal admin returns the seeded principal
        # branch from migrations, not the test's auxiliary branch).
        from catalogs.models import Sucursal
        principal_branch = Sucursal.objects.filter(es_principal=True, activa=True).first()
        self.assertIsNotNone(principal_branch)
        self.assertEqual(new_cliente.sucursal_origen_id, principal_branch.id)
        self.assertEqual(new_user.sucursal_id, principal_branch.id)
        # Non-null cliente_codigo is returned in the response.
        self.assertTrue(new_cliente.cliente_codigo)
        self.assertTrue(new_cliente.cliente_codigo.startswith("CLI-"))
        body = response.json()
        self.assertEqual(body["client"]["id"], new_cliente.id)
        self.assertEqual(body["client"]["clienteCodigo"], new_cliente.cliente_codigo)

        # Operation + cuota created against the new cliente.
        operacion = Operacion.objects.get(paciente=new_cliente)
        self.assertEqual(operacion.estado, Operacion.Estado.EN_PROCESO)
        self.assertTrue(
            CuotaPlanPago.objects.filter(operacion=operacion).exists()
        )

        # Spec — "Biometric stamped from wizard payload". Direct mode
        # goes through the reactivation-style stamping branch (no
        # prospecto to migrate from). When ``BIOMETRIC_SUSPENDED`` is
        # off, the wizard-payload template must be persisted as a
        # ``HuellaBiometricaCliente`` row attached to the new cliente.
        # This locks the assertion missing from PR 2 in place.
        huella = HuellaBiometricaCliente.objects.filter(cliente=new_cliente)
        self.assertTrue(
            huella.exists(),
            "Se esperaba una fila HuellaBiometricaCliente para el nuevo "
            "cliente (stamping del template del wizard en modo directo).",
        )
        huella_row = huella.get()
        # Bytes coercion (latent-bug fix landed in PR 1) — the row must
        # contain the ``BASE64-DIRECTO`` template, not the str/bytes
        # collision that triggered the original PR 1 rollback.
        self.assertIsNotNone(huella_row.template_biometrico)
        if isinstance(huella_row.template_biometrico, (bytes, bytearray, memoryview)):
            self.assertIn(b"BASE64-DIRECTO", bytes(huella_row.template_biometrico))
        else:
            self.assertIn("BASE64-DIRECTO", huella_row.template_biometrico)

        # Borrador consumed.
        self.assertFalse(
            ProspectoConversionBorrador.objects.filter(pk=draft.id).exists()
        )

    def test_finalize_rolls_back_on_forced_db_error(self):
        """Spec — Finalize rolls back on error.

        A forced DB error during ``Cliente.objects.create`` causes the
        whole ``transaction.atomic()`` block to roll back: no ``Usuario``,
        no ``Cliente``, the draft is preserved, and the response is 500.
        """
        from unittest import mock

        draft = _make_direct_draft(
            sucursal=self.graph["sucursal"],
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
        )

        username = "maria.directo"
        self.assertFalse(Usuario.objects.filter(username=username).exists())

        # Force ``Cliente.objects.create`` to raise an IntegrityError,
        # mimicking a transient DB failure. The ``@transaction.atomic``
        # decorator on the view must roll the entire transaction back
        # so that the Usuario creation that just succeeded is undone
        # and the draft is preserved.
        def _exploding_create(*args, **kwargs):
            raise IntegrityError("forced-direct-create-failure")

        pdf = SimpleUploadedFile(
            "doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
        )

        # DEBUG=True re-raises view exceptions to the test client. Pass
        # ``raise_request_exception=False`` so we can assert on the
        # resulting 500 instead of having the test runner swallow it as
        # an unhandled exception.
        quiet_http = Client(raise_request_exception=False)
        quiet_http.force_login(self.graph["admin"])

        with override_settings(BIOMETRIC_SUSPENDED=False):
            with mock.patch.object(
                Cliente.objects, "create", side_effect=_exploding_create
            ):
                response = quiet_http.post(
                    f"/api/admin/clientes/directo/{draft.id}/finalizar/",
                    data={"documento_escaneado_pdf": pdf},
                )

        # We accept 500 (the atomic block raises) or any non-2xx status.
        self.assertGreaterEqual(response.status_code, 400)
        self.assertNotEqual(response.status_code, 201)

        # No Usuario persisted (the Usuario.objects.create ran BEFORE the
        # failing Cliente.objects.create; the @transaction.atomic must
        # roll that back too).
        self.assertFalse(Usuario.objects.filter(username=username).exists())
        # No Cliente persisted.
        self.assertFalse(Cliente.objects.filter(ci="8888888").exists())
        # Draft preserved (the transaction rolled back including the
        # delete at the end of the view).
        self.assertTrue(
            ProspectoConversionBorrador.objects.filter(pk=draft.id).exists()
        )


class DirectClientCancelTests(TestCase):
    """Spec — Cancel Cleans Up the Draft.

    Cancelling at any step deletes the ``(null, null)`` draft without
    creating any ``Usuario`` or ``Cliente``.
    """

    @classmethod
    def setUpTestData(cls):
        cls.graph = _build_graph()

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.graph["admin"])

    def test_cancel_deletes_draft_with_both_fks_null(self):
        draft = ProspectoConversionBorrador.objects.create(
            prospecto=None,
            cliente=None,
            iniciado_por=self.graph["admin"],
        )
        before_user_count = Usuario.objects.count()
        before_cliente_count = Cliente.objects.count()

        response = self.http.post(
            f"/api/admin/clientes/directo/{draft.id}/cancelar/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            ProspectoConversionBorrador.objects.filter(pk=draft.id).exists()
        )
        # No side-effect rows created.
        self.assertEqual(Usuario.objects.count(), before_user_count)
        self.assertEqual(Cliente.objects.count(), before_cliente_count)


class DirectClientRegressionTests(TestCase):
    """Regression guards — the prospect→client and reactivation finalize
    branches MUST keep behaving byte-for-byte as before. The new
    ``direct`` branch is additive only.
    """

    @classmethod
    def setUpTestData(cls):
        cls.graph = _build_graph()
        cls.today = date.today()

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.graph["admin"])

    def test_prospect_finalize_still_marks_prospect_as_converted(self):
        """Regression — prospect branch unchanged.

        The new third branch in finalize MUST NOT touch the prospect
        branch. Finalizing a prospect draft still calls
        ``marcar_como_convertido`` and migrates the prospect biometric
        onto the new cliente.
        """
        prospecto = Prospecto.objects.create(
            primer_nombre="Prospecto",
            apellido_paterno="Regresion",
            telefono="7000-1111",
            sucursal_registro=self.graph["sucursal"],
            registrado_por=self.graph["admin"],
        )
        # Pre-create a HuellaBiometricaCliente attached to the prospecto
        # so we can prove migration ran.
        huella = HuellaBiometricaCliente.objects.create(
            prospecto=prospecto,
            cliente=None,
            proveedor=HuellaBiometricaCliente.Proveedor.MOCK_LEGACY,
            template_biometrico=b"PROSPECT-CIPHERTEXT",
            activo=True,
        )

        draft = _make_prospect_draft(
            prospecto=prospecto,
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
        )

        pdf = SimpleUploadedFile(
            "doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
        )
        # The .env defaults BIOMETRIC_SUSPENDED=1; the migration only
        # fires when suspension is off. Override locally so the regression
        # actually exercises the migration path.
        with override_settings(BIOMETRIC_SUSPENDED=False):
            response = self.http.post(
                f"/api/admin/prospectos/{prospecto.id}/conversion/finalizar/",
                data={"documento_escaneado_pdf": pdf},
            )
        self.assertEqual(response.status_code, 201)

        new_user = Usuario.objects.get(username="regression.prospect.user")
        new_cliente = Cliente.objects.get(usuario=new_user)

        # Prospect was marked as converted.
        prospecto.refresh_from_db()
        self.assertEqual(prospecto.estado, Prospecto.Estado.CONVERTIDO)
        self.assertEqual(prospecto.convertido_a_cliente_id, new_cliente.id)

        # Huella migrated prospect → cliente.
        huella.refresh_from_db()
        self.assertIsNone(huella.prospecto_id)
        self.assertEqual(huella.cliente_id, new_cliente.id)

        # Borrador consumed.
        self.assertFalse(
            ProspectoConversionBorrador.objects.filter(pk=draft.id).exists()
        )

    def test_reactivation_finalize_updates_only_existing_cliente(self):
        """Regression — reactivation branch unchanged.

        Finalizing a reactivation draft still uses the existing
        ``Cliente`` row (no new ``Usuario`` is created).
        """
        # Build a fresh cliente (use the existing taken_cliente, but
        # give it the same branch as our admin so finalize can resolve
        # it).
        from accounts.models import Usuario as UsuarioModel
        rol_cliente = Rol.objects.get(rol="CLIENTE")
        react_user = UsuarioModel.objects.create_user(
            username="reactivation.user",
            password="pw12345!",
            primer_nombre="React",
            apellido_paterno="Ivation",
            rol=rol_cliente,
            sucursal=self.graph["sucursal"],
        )
        react_cliente = Cliente.objects.create(
            usuario=react_user,
            sucursal_origen=self.graph["sucursal"],
            ci="55555",
            telefono="7000-5555",
            fecha_nacimiento=date(1990, 1, 1),
        )

        before_user_count = Usuario.objects.count()

        draft = _make_reactivation_draft(
            cliente=react_cliente,
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
        )

        pdf = SimpleUploadedFile(
            "doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
        )
        response = self.http.post(
            f"/api/admin/clientes/{react_cliente.id}/reactivar/finalizar/",
            data={"documento_escaneado_pdf": pdf},
        )
        self.assertEqual(response.status_code, 201)

        # No NEW Usuario created — the reactivation branch must not
        # create one.
        self.assertEqual(Usuario.objects.count(), before_user_count)
        # The existing cliente was updated (estado → ACTIVO).
        react_cliente.refresh_from_db()
        self.assertEqual(react_cliente.estado_cliente, Cliente.Estado.ACTIVO)
        # ObservacionesCliente was persisted.
        self.assertEqual(react_cliente.observaciones, "obs-reactivation")

        # Borrador consumed.
        self.assertFalse(
            ProspectoConversionBorrador.objects.filter(pk=draft.id).exists()
        )


class DirectClientListingIntegrationTests(TestCase):
    """Spec — New Client Appears in Listing.

    Validates that a direct-mode finalize actually surfaces the new
    client through the existing global client search endpoint
    (``GET /api/admin/clientes/buscar-global/?ci=<ci>``), so the
    ``/cms/clientes`` listing the wizard redirects to will show the row
    that was just created.

    Locks CRITICAL-4 in place. The ``/buscar-global/`` endpoint is
    public (no auth) but our seeded client + admin ensure isolation
    across the rest of the suite; we still create the cliente under the
    seeded branch so no future scheduled-appointment exclusion
    accidentally applies.
    """

    @classmethod
    def setUpTestData(cls):
        cls.graph = _build_graph()
        cls.today = date.today()

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.graph["admin"])

    def _finalize(self, draft):
        pdf = SimpleUploadedFile(
            "doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
        )
        return self.http.post(
            f"/api/admin/clientes/directo/{draft.id}/finalizar/",
            data={"documento_escaneado_pdf": pdf},
        )

    def test_listing_includes_new_client_via_buscar_global(self):
        """Spec — Listing includes the new client.

        After a direct-mode finalize, querying the existing global
        search endpoint with the new cliente's CI surfaces the row in
        the ``clients`` array (so the ``/cms/clientes`` listing the
        wizard redirects to can render it).
        """
        draft = _make_direct_draft(
            sucursal=self.graph["sucursal"],
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
        )

        # Suspend biometric stamping so this test focuses exclusively on
        # listing integration. The biometric-row assertion itself lives
        # in
        # ``DirectClientFinalizeTests.test_finalize_happy_path_creates_user_and_cliente``.
        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = self._finalize(draft)
        self.assertEqual(response.status_code, 201)

        # The new cliente exists with the CI from the draft payload.
        new_cliente = Cliente.objects.get(ci="8888888")

        # Hit the existing listing integration endpoint (this is the
        # one the frontend uses for the global client search on the
        # CMS clients page). The actual route is the
        # ``admin_clientes_global_search`` view (not the ViewSet
        # ``@action``), which accepts a single ``q`` query parameter
        # that matches across name / username / CI / email / phone.
        # Pass the new CI as ``q`` so the row surfaces in the
        # single-token OR path that includes CI.
        list_response = self.http.get(
            "/api/admin/clientes/buscar-global/",
            {"q": new_cliente.ci},
        )
        self.assertEqual(list_response.status_code, 200)
        body = list_response.json()
        self.assertIn("clients", body)
        matching = [
            entry
            for entry in body["clients"]
            if entry.get("ci") == new_cliente.ci
        ]
        self.assertTrue(
            matching,
            f"Expected the new cliente (ci={new_cliente.ci}) to appear in "
            f"/api/admin/clientes/buscar-global/, got: {body!r}",
        )
        entry = matching[0]
        self.assertEqual(entry["id"], new_cliente.id)
        # The endpoint returns the canonical ``name`` plus CI / branch
        # metadata; we just confirm the row landed so the wizard's
        # post-finalize redirect to ``/cms/clientes`` can render it
        # without further backend wiring.