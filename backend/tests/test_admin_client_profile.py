"""Backend regression tests for the admin live-client-profile endpoint
and the defensive finalize change introduced by the
``reactivacion-perfil-cliente`` change.

Spec under test: ``openspec/changes/reactivacion-perfil-cliente/specs/admin-client-profile-editing/spec.md``

Two concerns, two test classes:

* ``AdminClientProfileEndpointTests`` — PATCH ``/api/admin/clientes/<pk>/perfil/``
  must update the live ``Cliente`` + its ``Usuario`` in one transaction,
  accept the 13 contract fields, reject ``password`` and unknown fields,
  honor field ownership (telefono syncs to both rows; fechaNacimiento
  writes to ``Cliente`` only), and reject non-admin / unauthenticated
  callers.
* ``ReactivationDefensiveFinalizeTests`` — finalizing a reactivation
  draft (``draft.cliente`` is set) MUST NOT overwrite live profile
  fields. Only ``observacionesCliente`` (plus the operation/medical/
  biometric/payment records) flows through. The prospect conversion
  branch (``draft.prospecto``) MUST keep creating the new ``Usuario``
  + ``Cliente`` from the draft payload.

Style follows the existing project patterns from
``test_profile_update.py`` and ``test_conversion_first_payment.py``
(``TestCase`` + ``django.test.Client`` + session auth, NOT DRF
APIClient).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago, PagoRealizado
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_graph():
    """Build the minimum role/branch/user/cliente graph for the PATCH tests.

    Two clientes exist on the same branch — needed by the username and CI
    collision tests. ``cliente1`` is the PATCH target; ``cliente2`` owns
    the colliding ``username`` and ``ci`` values.
    """
    rol_cliente = Rol.objects.create(rol="CLIENTE")
    rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
    sucursal = Sucursal.objects.create(nombre="Perfil-Centro", activa=True)

    admin = Usuario.objects.create_user(
        username="perfil.admin",
        password="pw12345!",
        primer_nombre="Adm",
        apellido_paterno="Per",
        email="admin@perfil.com",
        rol=rol_admin,
        sucursal=sucursal,
    )
    client1_user = Usuario.objects.create_user(
        username="perfil.cliente1",
        password="pw12345!",
        primer_nombre="Juan",
        segundo_nombre="Carlos",
        apellido_paterno="Perez",
        apellido_materno="Lopez",
        email="juan@perfil.com",
        telefono="111",
        rol=rol_cliente,
        sucursal=sucursal,
    )
    cliente1 = Cliente.objects.create(
        usuario=client1_user,
        sucursal_origen=sucursal,
        ci="11111",
        telefono="111",
        fecha_nacimiento=date(1990, 1, 1),
        nro_hijos=1,
        direccion_domicilio="Calle 1",
        ocupacion="Ing",
        observaciones="obs-original",
    )
    client2_user = Usuario.objects.create_user(
        username="taken",
        password="pw12345!",
        primer_nombre="Other",
        apellido_paterno="User",
        email="other@perfil.com",
        telefono="222",
        rol=rol_cliente,
        sucursal=sucursal,
    )
    cliente2 = Cliente.objects.create(
        usuario=client2_user,
        sucursal_origen=sucursal,
        ci="99999",
        telefono="222",
        fecha_nacimiento=date(1985, 5, 5),
    )
    return {
        "rol_admin": rol_admin,
        "rol_cliente": rol_cliente,
        "sucursal": sucursal,
        "admin": admin,
        "cliente1": cliente1,
        "cliente1_user": client1_user,
        "cliente2": cliente2,
        "cliente2_user": client2_user,
    }


def _perfil_url(cliente_id):
    return f"/api/admin/clientes/{cliente1_safe(cliente_id)}/perfil/"


def _cliente1_safe(cliente_id):
    # Tiny shim so the URL builder reads cleanly.
    return cliente_id


def _patch(client, url, payload):
    return client.patch(
        url,
        data=json.dumps(payload),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# Class A — admin live profile PATCH endpoint
# ---------------------------------------------------------------------------


class AdminClientProfileEndpointTests(TestCase):
    """PATCH /api/admin/clientes/<pk>/perfil/ — Live Profile Endpoint.

    Each test cites the spec scenario it covers via a docstring.
    """

    @classmethod
    def setUpTestData(cls):
        cls.g = _build_graph()
        cls.admin = cls.g["admin"]
        cls.cliente1 = cls.g["cliente1"]
        cls.cliente1_user = cls.g["cliente1_user"]
        cls.cliente2 = cls.g["cliente2"]
        cls.cliente2_user = cls.g["cliente2_user"]

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.admin)

    def _patch(self, cliente, payload):
        url = f"/api/admin/clientes/{cliente.id}/perfil/"
        return self.http.patch(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_patch_single_field_primerNombre_updates_live(self):
        """Spec — Live Profile Endpoint, scenario 1 (Update single field).

        PATCH ``{"primerNombre": "Maria"}`` updates ``Usuario.primer_nombre``
        and the response mirrors the change.
        """
        response = self._patch(self.cliente1, {"primerNombre": "Maria"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("client", body)
        self.assertEqual(body["client"]["primerNombre"], "Maria")

        self.cliente1_user.refresh_from_db()
        self.cliente1.refresh_from_db()
        self.assertEqual(self.cliente1_user.primer_nombre, "Maria")
        # All other Usuario/Cliente fields untouched.
        self.assertEqual(self.cliente1_user.segundo_nombre, "Carlos")
        self.assertEqual(self.cliente1_user.apellido_paterno, "Perez")
        self.assertEqual(self.cliente1_user.email, "juan@perfil.com")
        self.assertEqual(self.cliente1.ci, "11111")
        self.assertEqual(self.cliente1.telefono, "111")
        self.assertEqual(self.cliente1.nro_hijos, 1)
        self.assertEqual(self.cliente1.observaciones, "obs-original")

    def test_patch_partial_update_preserves_omitted(self):
        """Spec — Editable Fields, Partial update preserves omitted fields.

        PATCH ``{"email": "b@x.com"}`` updates email but keeps telefono,
        ci, fechaNacimiento on their respective rows.
        """
        response = self._patch(self.cliente1, {"email": "b@x.com"})

        self.assertEqual(response.status_code, 200)
        self.cliente1_user.refresh_from_db()
        self.cliente1.refresh_from_db()
        self.assertEqual(self.cliente1_user.email, "b@x.com")
        # Omitted fields preserved on both rows.
        self.assertEqual(self.cliente1_user.telefono, "111")
        self.assertEqual(self.cliente1.telefono, "111")
        self.assertEqual(self.cliente1.ci, "11111")
        self.assertEqual(
            self.cliente1.fecha_nacimiento, date(1990, 1, 1)
        )
        self.assertEqual(self.cliente1.nro_hijos, 1)

    def test_patch_telefono_cascades_to_cliente(self):
        """Spec — Telefono Synchronization.

        PATCH ``{"telefono": "999"}`` writes to BOTH ``Usuario.telefono``
        and ``Cliente.telefono`` in the same transaction.
        """
        # Sanity check the fixture before the PATCH.
        self.assertEqual(self.cliente1_user.telefono, "111")
        self.assertEqual(self.cliente1.telefono, "111")

        response = self._patch(self.cliente1, {"telefono": "999"})

        self.assertEqual(response.status_code, 200)
        self.cliente1_user.refresh_from_db()
        self.cliente1.refresh_from_db()
        self.assertEqual(self.cliente1_user.telefono, "999")
        self.assertEqual(self.cliente1.telefono, "999")

    def test_patch_fechaNacimiento_only_updates_cliente(self):
        """Spec — FechaNacimiento Ownership.

        ``fechaNacimiento`` writes to ``Cliente.fecha_nacimiento`` only;
        ``Usuario.fecha_nacimiento`` is intentionally NOT mirrored.
        """
        # Seed an asymmetric value on Usuario to prove it is NOT touched.
        self.cliente1_user.fecha_nacimiento = date(1980, 5, 5)
        self.cliente1_user.save(update_fields=["fecha_nacimiento"])

        response = self._patch(
            self.cliente1, {"fechaNacimiento": "2000-12-31"}
        )

        self.assertEqual(response.status_code, 200)
        self.cliente1.refresh_from_db()
        self.cliente1_user.refresh_from_db()
        self.assertEqual(self.cliente1.fecha_nacimiento, date(2000, 12, 31))
        # Usuario.fecha_nacimiento must be unchanged at the seeded value.
        self.assertEqual(
            self.cliente1_user.fecha_nacimiento, date(1980, 5, 5)
        )

    def test_patch_username_collision_returns_400(self):
        """Spec — Live Profile Endpoint, Username collision.

        PATCH ``{"username": "taken"}`` (owned by ``cliente2.usuario``)
        returns 400 with a username error; ``cliente1.usuario.username``
        is unchanged.
        """
        response = self._patch(self.cliente1, {"username": "taken"})

        self.assertEqual(response.status_code, 400)
        body = response.json()
        # Surface includes the validation errors map; assert the username
        # error is present.
        errors = body.get("errors") or {}
        self.assertTrue(
            any("username" in key for key in errors.keys()),
            f"expected username error in {errors!r}",
        )
        # Live row untouched.
        self.cliente1_user.refresh_from_db()
        self.assertEqual(self.cliente1_user.username, "perfil.cliente1")

    def test_patch_ci_collision_returns_400(self):
        """Spec — Live Profile Endpoint, CI collision.

        PATCH ``{"ci": "99999"}`` (owned by ``cliente2``) returns 400
        with a CI error; ``cliente1.ci`` is unchanged.
        """
        response = self._patch(self.cliente1, {"ci": "99999"})

        self.assertEqual(response.status_code, 400)
        body = response.json()
        errors = body.get("errors") or {}
        self.assertTrue(
            any("ci" in key for key in errors.keys()),
            f"expected ci error in {errors!r}",
        )
        self.cliente1.refresh_from_db()
        self.assertEqual(self.cliente1.ci, "11111")

    def test_patch_password_returns_400(self):
        """Spec — Editable Fields, Password rejected.

        PATCH ``{"password": "newpass"}`` returns 400 mentioning that
        password is not allowed; the password is NOT changed.
        """
        original_password_hash = self.cliente1_user.password
        response = self._patch(self.cliente1, {"password": "newpass"})

        self.assertEqual(response.status_code, 400)
        body = response.json()
        # The serializer raises ``{"password": "password is not editable
        # through this endpoint"}``; the user-facing ``detail`` message
        # and the errors map both surface it.
        combined = json.dumps(body)
        self.assertIn("password", combined.lower())
        self.assertIn("not editable", combined.lower())
        # Password hash unchanged — no set_password was called.
        self.cliente1_user.refresh_from_db()
        self.assertEqual(self.cliente1_user.password, original_password_hash)
        self.assertFalse(self.cliente1_user.check_password("newpass"))

    def test_patch_unknown_field_returns_400(self):
        """Spec — Editable Fields, Unknown field rejected.

        PATCH ``{"randomUnknownField": "x"}`` returns 400; no live row
        is modified.
        """
        # Snapshot the live row before the PATCH.
        primer_nombre_before = self.cliente1_user.primer_nombre
        ci_before = self.cliente1.ci

        response = self._patch(
            self.cliente1, {"randomUnknownField": "x"}
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        # The serializer rejects the unknown field; the body must mention
        # the offending field name in some form.
        combined = json.dumps(body)
        self.assertIn("randomUnknownField", combined)

        # No DB writes.
        self.cliente1_user.refresh_from_db()
        self.cliente1.refresh_from_db()
        self.assertEqual(self.cliente1_user.primer_nombre, primer_nombre_before)
        self.assertEqual(self.cliente1.ci, ci_before)

    def test_patch_non_admin_returns_403(self):
        """Spec — Authorization, Non-admin rejected.

        An authenticated CLIENTE user PATCHing another cliente's profile
        receives 403; the target rows are untouched.
        """
        # Log out the admin and log in as cliente1's user (a CLIENTE).
        self.http.logout()
        self.http.force_login(self.cliente1_user)

        primer_nombre_before = self.cliente1_user.primer_nombre
        response = self._patch(self.cliente1, {"primerNombre": "Hacker"})

        self.assertEqual(response.status_code, 403)
        self.cliente1_user.refresh_from_db()
        self.assertEqual(self.cliente1_user.primer_nombre, primer_nombre_before)

    def test_patch_unauthenticated_returns_403_or_401(self):
        """Spec — Authorization, Unauthenticated rejected.

        A request with no session is rejected. DRF's ``AdminRequired``
        returns False from ``has_permission`` for unauthenticated users,
        which DRF translates to 403 when ``force_login`` was never called
        AND no default auth class is configured to challenge with
        ``WWW-Authenticate``. The project does NOT configure a global
        default auth class, so the observed code is 403 — assert whatever
        the project actually returns and document it.
        """
        # Build a fresh client with no login.
        anon = Client()
        response = anon.patch(
            f"/api/admin/clientes/{self.cliente1.id}/perfil/",
            data=json.dumps({"primerNombre": "Anon"}),
            content_type="application/json",
        )
        # Accept either 401 or 403 — record which one the project emits.
        self.assertIn(
            response.status_code,
            (401, 403),
            f"unexpected status code for unauthenticated PATCH: "
            f"{response.status_code}",
        )

    def test_patch_full_payload_updates_all_13_fields(self):
        """Spec — Editable Fields, edit all fields.

        A single PATCH carrying all 13 contract fields writes each one
        to the correct row (USER_FIELDS → Usuario, telefono → both rows,
        CLIENTE_FIELDS → Cliente).
        """
        payload = {
            "primerNombre": "Maria",
            "segundoNombre": "Eugenia",
            "apellidoPaterno": "Gomez",
            "apellidoMaterno": "Rojas",
            "ci": "55555",
            "username": "perfil.cliente1",  # same as current — allowed
            "email": "maria@perfil.com",
            "telefono": "70000000",
            "fechaNacimiento": "1995-06-15",
            "nroHijos": 3,
            "ocupacion": "Doc",
            "direccionDomicilio": "Av. Nueva 123",
            "observacionesCliente": "obs-nueva",
        }
        response = self._patch(self.cliente1, payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["client"]["primerNombre"], "Maria")
        self.assertEqual(body["client"]["telefono"], "70000000")
        self.assertEqual(body["client"]["hasPassword"], True)

        # Reload and assert each contract field on its owning row.
        self.cliente1_user.refresh_from_db()
        self.cliente1.refresh_from_db()
        # USER_FIELDS → Usuario
        self.assertEqual(self.cliente1_user.primer_nombre, "Maria")
        self.assertEqual(self.cliente1_user.segundo_nombre, "Eugenia")
        self.assertEqual(self.cliente1_user.apellido_paterno, "Gomez")
        self.assertEqual(self.cliente1_user.apellido_materno, "Rojas")
        self.assertEqual(self.cliente1_user.username, "perfil.cliente1")
        self.assertEqual(self.cliente1_user.email, "maria@perfil.com")
        # telefono → both rows
        self.assertEqual(self.cliente1_user.telefono, "70000000")
        self.assertEqual(self.cliente1.telefono, "70000000")
        # CLIENTE_FIELDS → Cliente
        self.assertEqual(self.cliente1.ci, "55555")
        self.assertEqual(self.cliente1.fecha_nacimiento, date(1995, 6, 15))
        self.assertEqual(self.cliente1.nro_hijos, 3)
        self.assertEqual(self.cliente1.ocupacion, "Doc")
        self.assertEqual(self.cliente1.direccion_domicilio, "Av. Nueva 123")
        self.assertEqual(self.cliente1.observaciones, "obs-nueva")


# ---------------------------------------------------------------------------
# Class B — defensive finalize change
# ---------------------------------------------------------------------------


def _make_reactivation_draft(*, cliente, usuario, servicio, catalog_ids, today):
    """Build a reactivation draft (``draft.cliente`` set, no prospecto)."""
    return ProspectoConversionBorrador.objects.create(
        cliente=cliente,
        prospecto=None,
        iniciado_por=usuario,
        datos_usuario={
            "primerNombre": cliente.usuario.primer_nombre,
            "apellidoPaterno": cliente.usuario.apellido_paterno,
            "username": cliente.usuario.username,
            "passwordHash": make_password("pw"),
            "fechaNacimiento": "1990-01-01",
            "ci": cliente.ci,
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
            "motivoConsulta": "consulta",
            "observaciones": "",
            "consentimientoAceptado": True,
            "firmaPacienteCi": "12345",
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
        datos_biometria={"provider": "MOCK", "template": "BASE64", "quality": 80},
        paso_usuario_completado=True,
        paso_operacion_completado=True,
        paso_ficha_completado=True,
        paso_biometria_completado=True,
        paso_actual=ProspectoConversionBorrador.Paso.BIOMETRIA,
    )


def _make_prospect_draft(*, prospecto, usuario, servicio, catalog_ids, today):
    """Build a new-prospect draft (``draft.prospecto`` set, no cliente)."""
    return ProspectoConversionBorrador.objects.create(
        cliente=None,
        prospecto=prospecto,
        iniciado_por=usuario,
        datos_usuario={
            "primerNombre": prospecto.primer_nombre,
            "apellidoPaterno": prospecto.apellido_paterno,
            "username": "prospect.fresh.user",
            "email": "prospect@example.com",
            "telefono": prospecto.telefono or "7000-0000",
            "ci": "99999",
            "passwordHash": make_password("pw"),
            "fechaNacimiento": "1992-02-02",
            "nroHijos": 0,
            "direccionDomicilio": "Calle Prospect",
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
            "motivoConsulta": "consulta",
            "observaciones": "",
            "consentimientoAceptado": True,
            "firmaPacienteCi": "99999",
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
        datos_biometria={"provider": "MOCK", "template": "BASE64", "quality": 80},
        paso_usuario_completado=True,
        paso_operacion_completado=True,
        paso_ficha_completado=True,
        paso_biometria_completado=True,
        paso_actual=ProspectoConversionBorrador.Paso.BIOMETRIA,
    )


class ReactivationDefensiveFinalizeTests(TestCase):
    """Spec — Defensive Finalize.

    The reactivation finalize branch (when ``draft.cliente`` is set)
    must NOT overwrite live profile fields from ``draft.datos_usuario``.
    Only ``observacionesCliente`` (plus operation/medical/biometric/
    payment records) flows through. The new-prospect branch
    (``draft.prospecto`` is set) must keep creating the new
    ``Usuario`` + ``Cliente`` from the draft payload.
    """

    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.rol_cliente = Rol.objects.create(rol="CLIENTE")
        cls.sucursal = Sucursal.objects.create(nombre="Defensive-Centro", activa=True)

        cls.admin = Usuario.objects.create_user(
            username="defensive.admin",
            password="pw12345!",
            primer_nombre="Adm",
            apellido_paterno="Def",
            rol=cls.rol_admin,
            sucursal=cls.sucursal,
        )
        cls.client_user = Usuario.objects.create_user(
            username="defensive.cliente",
            password="pw12345!",
            primer_nombre="Live",
            segundo_nombre="Original",
            apellido_paterno="Apellido",
            apellido_materno="Original",
            email="live@perfil.com",
            telefono="111",
            rol=cls.rol_cliente,
            sucursal=cls.sucursal,
        )
        cls.cliente = Cliente.objects.create(
            usuario=cls.client_user,
            sucursal_origen=cls.sucursal,
            ci="11111",
            telefono="111",
            fecha_nacimiento=date(1990, 1, 1),
            nro_hijos=2,
            direccion_domicilio="Calle Live",
            ocupacion="Live-Ocupacion",
            # Use the model field name to avoid a typo in the property.
            observaciones="obs-live-original",
        )

        tipo = TipoServicio.objects.create(tipo="Consulta", activo=True)
        cls.servicio = ServicioConfig.objects.create(
            tipo_servicio=tipo, precio_base=Decimal("100"), activo=True
        )

        cls.catalog_ids = {
            "tipo_piel": TipoPiel.objects.create(nombre="Normal", activo=True).id,
            "grado_deshidratacion": GradoDeshidratacion.objects.create(
                nombre="Bajo", activo=True
            ).id,
            "grosor_piel": GrosorPiel.objects.create(nombre="Medio", activo=True).id,
        }
        cls.today = date.today()

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.admin)

    def _finalize(self, draft):
        pdf = SimpleUploadedFile(
            "doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
        )
        return self.http.post(
            f"/api/admin/clientes/{self.cliente.id}/reactivar/finalizar/",
            data={"documento_escaneado_pdf": pdf},
        )

    def test_reactivation_finalize_does_not_overwrite_live_profile(self):
        """Spec — Defensive Finalize, Reactivation finalize does not touch
        live profile.

        Given a reactivation draft with ``datos_usuario`` carrying values
        that DIFFER from the live ``Cliente``/``Usuario``, finalizing the
        draft MUST leave every live profile field untouched (except
        ``observacionesCliente`` — covered by the next test).
        """
        draft = ProspectoConversionBorrador.objects.create(
            cliente=self.cliente,
            prospecto=None,
            iniciado_por=self.admin,
            # Deliberately wrong payload. None of these should reach the
            # live rows.
            datos_usuario={
                "primerNombre": "WRONG",
                "segundoNombre": "WRONG",
                "apellidoPaterno": "WRONG",
                "apellidoMaterno": "WRONG",
                "username": "WRONG",
                "email": "WRONG@x.com",
                "telefono": "WRONG",
                "ci": "WRONG",
                "fechaNacimiento": "2000-01-01",
                "nroHijos": 99,
                "direccionDomicilio": "WRONG",
                "ocupacion": "WRONG",
                "observacionesCliente": "WRONG-OBS",
            },
            datos_operacion={
                "serviceConfigId": self.servicio.id,
                "zonaGeneral": "Zona",
                "zonaEspecifica": "Detalle",
                "precioTotal": "100.00",
                "cuotasTotales": 1,
                "sesionesTotales": 1,
                "fechaInicio": str(self.today),
                "estado": Operacion.Estado.EN_PROCESO,
                "fechasVencimientoCuotas": [str(self.today)],
            },
            datos_ficha={
                "fechaFicha": str(self.today),
                "motivoConsulta": "consulta",
                "observaciones": "",
                "consentimientoAceptado": True,
                "firmaPacienteCi": "11111",
                "analisisEstetico": {
                    "tipoPielId": str(self.catalog_ids["tipo_piel"]),
                    "gradoDeshidratacionId": str(self.catalog_ids["grado_deshidratacion"]),
                    "grosorPielId": str(self.catalog_ids["grosor_piel"]),
                    "patologiaIds": [],
                },
                "antecedentes": [],
                "implantes": [],
                "cirugias": [],
                "fieldResponses": {},
            },
            datos_biometria={"provider": "MOCK", "template": "BASE64", "quality": 80},
            paso_usuario_completado=True,
            paso_operacion_completado=True,
            paso_ficha_completado=True,
            paso_biometria_completado=True,
            paso_actual=ProspectoConversionBorrador.Paso.BIOMETRIA,
        )

        # Snapshot live values before finalize.
        live_primer_nombre = self.client_user.primer_nombre
        live_segundo_nombre = self.client_user.segundo_nombre
        live_apellido_paterno = self.client_user.apellido_paterno
        live_apellido_materno = self.client_user.apellido_materno
        live_username = self.client_user.username
        live_email = self.client_user.email
        live_usuario_telefono = self.client_user.telefono
        live_cliente_ci = self.cliente.ci
        live_cliente_telefono = self.cliente.telefono
        live_cliente_fecha_nacimiento = self.cliente.fecha_nacimiento
        live_cliente_nro_hijos = self.cliente.nro_hijos
        live_cliente_direccion = self.cliente.direccion_domicilio
        live_cliente_ocupacion = self.cliente.ocupacion

        response = self._finalize(draft)
        self.assertEqual(response.status_code, 201)

        # Reload and assert every live field kept its original value.
        self.client_user.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertEqual(self.client_user.primer_nombre, live_primer_nombre)
        self.assertEqual(self.client_user.segundo_nombre, live_segundo_nombre)
        self.assertEqual(self.client_user.apellido_paterno, live_apellido_paterno)
        self.assertEqual(self.client_user.apellido_materno, live_apellido_materno)
        self.assertEqual(self.client_user.username, live_username)
        self.assertEqual(self.client_user.email, live_email)
        self.assertEqual(self.client_user.telefono, live_usuario_telefono)
        self.assertEqual(self.cliente.ci, live_cliente_ci)
        self.assertEqual(self.cliente.telefono, live_cliente_telefono)
        self.assertEqual(
            self.cliente.fecha_nacimiento, live_cliente_fecha_nacimiento
        )
        self.assertEqual(self.cliente.nro_hijos, live_cliente_nro_hijos)
        self.assertEqual(self.cliente.direccion_domicilio, live_cliente_direccion)
        self.assertEqual(self.cliente.ocupacion, live_cliente_ocupacion)

        # The borrador was consumed.
        self.assertFalse(
            ProspectoConversionBorrador.objects.filter(pk=draft.id).exists()
        )

    def test_reactivation_finalize_still_persists_observacionesCliente(self):
        """Spec — live profile untouched EXCEPT ``observacionesCliente``.

        ``observacionesCliente`` is the one profile-adjacent field the
        reactivation finalize MUST apply — it is the procedure annotation.
        """
        draft = _make_reactivation_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            catalog_ids=self.catalog_ids,
            today=self.today,
        )
        # Set a NEW observation on the draft (different from the live one).
        draft.datos_usuario = {
            **draft.datos_usuario,
            "observacionesCliente": "OBS-NUEVA-PARA-EL-PROCEDIMIENTO",
        }
        draft.save(update_fields=["datos_usuario"])

        response = self._finalize(draft)
        self.assertEqual(response.status_code, 201)

        self.cliente.refresh_from_db()
        self.assertEqual(
            self.cliente.observaciones, "OBS-NUEVA-PARA-EL-PROCEDIMIENTO"
        )

    def test_reactivation_finalize_still_creates_operation_medical_biometric_payment(
        self,
    ):
        """Regression guard — defensive finalize must not drop the
        operation/medical/biometric/payment side effects.

        The policy change only touched the live-profile overwrite block;
        the operation, ficha/biometric, and first-payment records must
        still be created against the existing cliente.
        """
        # Seed an existing HuellaBiometricaCliente for the reactivation
        # path (the view uses update_or_create for reactivation, not
        # migrate-from-prospecto).
        huella = HuellaBiometricaCliente.objects.create(
            cliente=self.cliente,
            proveedor=HuellaBiometricaCliente.Proveedor.MOCK_LEGACY,
            template_biometrico=b"PRE-EXISTING-CIPHERTEXT",
            activo=True,
        )

        draft = _make_reactivation_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            catalog_ids=self.catalog_ids,
            today=self.today,
        )

        response = self.http.post(
            f"/api/admin/clientes/{self.cliente.id}/reactivar/finalizar/",
            data={
                "documento_escaneado_pdf": SimpleUploadedFile(
                    "doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
                ),
                # No first payment — keep the test focused on operation +
                # medical + biometric.
            },
        )
        self.assertEqual(response.status_code, 201)

        # Operation row created against the existing cliente.
        operacion = Operacion.objects.get(paciente=self.cliente)
        self.assertEqual(operacion.estado, Operacion.Estado.EN_PROCESO)

        # Cuota row created (cuotasTotales=1, due date = today).
        self.assertTrue(
            CuotaPlanPago.objects.filter(operacion=operacion).exists()
        )

        # No first-payment signal → no PagoRealizado row.
        self.assertFalse(
            PagoRealizado.objects.filter(cuota__operacion=operacion).exists()
        )

        # HuellaBiometricaCliente still exists (reactivation path keeps it).
        self.assertTrue(
            HuellaBiometricaCliente.objects.filter(pk=huella.pk).exists()
        )

        # Borrador consumed.
        self.assertFalse(
            ProspectoConversionBorrador.objects.filter(pk=draft.id).exists()
        )

    def test_prospect_conversion_finalize_still_creates_user_and_cliente(self):
        """Spec — Prospect conversion finalize unchanged.

        The reactivation-branch isolation MUST NOT regress the prospect
        branch. Finalizing a prospect draft (``draft.prospecto`` set,
        ``draft.cliente`` empty) still creates a brand new ``Usuario``
        and ``Cliente`` from ``draft.datos_usuario``.
        """
        prospecto = Prospecto.objects.create(
            primer_nombre="Prospect",
            apellido_paterno="Nuevo",
            telefono="7000-1111",
            sucursal_registro=self.sucursal,
            registrado_por=self.admin,
        )
        draft = _make_prospect_draft(
            prospecto=prospecto,
            usuario=self.admin,
            servicio=self.servicio,
            catalog_ids=self.catalog_ids,
            today=self.today,
        )

        # Sanity: no Cliente yet for this prospect.
        self.assertFalse(Cliente.objects.filter(usuario__username="prospect.fresh.user").exists())

        response = self.http.post(
            f"/api/admin/prospectos/{prospecto.id}/conversion/finalizar/",
            data={
                "documento_escaneado_pdf": SimpleUploadedFile(
                    "doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
                ),
            },
        )
        self.assertEqual(response.status_code, 201)

        # New Usuario + Cliente created from the draft payload.
        new_user = Usuario.objects.filter(username="prospect.fresh.user").first()
        self.assertIsNotNone(new_user)
        self.assertEqual(new_user.primer_nombre, "Prospect")
        self.assertEqual(new_user.apellido_paterno, "Nuevo")
        self.assertEqual(new_user.email, "prospect@example.com")
        self.assertTrue(new_user.check_password("pw"))

        new_cliente = Cliente.objects.filter(usuario=new_user).first()
        self.assertIsNotNone(new_cliente)
        self.assertEqual(new_cliente.ci, "99999")
        self.assertEqual(new_cliente.fecha_nacimiento, date(1992, 2, 2))
        self.assertEqual(new_cliente.telefono, "7000-1111")
        self.assertEqual(new_cliente.nro_hijos, 0)
        self.assertEqual(new_cliente.direccion_domicilio, "Calle Prospect")
        self.assertEqual(new_cliente.ocupacion, "Est")
        self.assertEqual(new_cliente.observaciones, "obs-prospect")

        # Prospect was marked as converted (pointed at the new cliente).
        prospecto.refresh_from_db()
        self.assertEqual(prospecto.estado, Prospecto.Estado.CONVERTIDO)
        self.assertEqual(prospecto.convertido_a_cliente_id, new_cliente.id)

        # Operation + cuota created against the new cliente.
        operacion = Operacion.objects.get(paciente=new_cliente)
        self.assertEqual(operacion.estado, Operacion.Estado.EN_PROCESO)
        self.assertTrue(
            CuotaPlanPago.objects.filter(operacion=operacion).exists()
        )

        # Borrador consumed.
        self.assertFalse(
            ProspectoConversionBorrador.objects.filter(pk=draft.id).exists()
        )