"""Tests for the ``origen`` field on the direct-mode finalize path.

Spec under test:
``openspec/changes/cliente-origen-recurrente/specs/cliente-origen/spec.md``
"Unknown origin value rejected on creation" + "origin values exposed
in API serialization" scenarios, plus the modified
``admin-prospect-conversion › Step 1 ReadOnly Behavior Per Mode``
requirement that the direct-mode finalize persist the radio choice.

Three concerns:

* Finalize with ``origen='RECURRENTE_PRE_SISTEMA'`` persists on the new
  ``Cliente`` row.
* Finalize without ``origen`` defaults to ``NUEVO``.
* Finalize with an unknown ``origen`` value returns 400 and does not
  create any ``Usuario`` or ``Cliente`` rows.

Style follows ``backend/tests/test_direct_client_conversion.py``
(``TestCase`` + ``django.test.Client`` + session auth) and the
helper conventions used by ``config/tests/test_admin_cobrar_cita_endpoint.py``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from accounts.models import Rol, Usuario
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
    ProspectoConversionBorrador,
)
from operations.models import Operacion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_graph():
    """Build a minimal role/branch/admin graph for direct finalize tests.

    Mirrors the helper shape used in
    ``backend/tests/test_direct_client_conversion.py::_build_graph``
    (which the original direct-creation tests share) so reviewers can
    trace the lineage.
    """
    rol_cliente = Rol.objects.create(rol="CLIENTE")
    rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
    sucursal = Sucursal.objects.create(nombre="Origen-Directo-Centro", activa=True)

    admin = Usuario.objects.create_user(
        username="origen.directo.admin",
        password="pw12345!",
        primer_nombre="Ana",
        apellido_paterno="Directo",
        email="origen.directo.admin@example.com",
        rol=rol_admin,
        sucursal=sucursal,
    )

    tipo_servicio = TipoServicio.objects.create(tipo="Origen-Limpieza", activo=True)
    servicio = ServicioConfig.objects.create(
        tipo_servicio=tipo_servicio,
        activo=True,
        precio_base=Decimal("100.00"),
    )
    tipo_piel = TipoPiel.objects.create(nombre="Normal", activo=True)
    grado = GradoDeshidratacion.objects.create(nombre="Bajo", activo=True)
    grosor = GrosorPiel.objects.create(nombre="Medio", activo=True)

    return {
        "rol_admin": rol_admin,
        "rol_cliente": rol_cliente,
        "sucursal": sucursal,
        "admin": admin,
        "servicio": servicio,
        "tipo_piel": tipo_piel,
        "grado_deshidratacion": grado,
        "grosor_piel": grosor,
        "catalog_ids": {
            "tipo_piel": tipo_piel.id,
            "grado_deshidratacion": grado.id,
            "grosor_piel": grosor.id,
        },
    }


def _make_direct_draft(*, admin, servicio, catalog_ids, today, origen=None):
    """Build a fully-populated direct creation draft (prospecto=NULL,
    cliente=NULL) ready for the finalize endpoint.

    ``origen`` is the optional key the wizard writes on step 1's radio;
    pass ``None`` (or omit) to simulate a draft that does not carry the
    field — the spec expects finalize to fall back to ``NUEVO``.
    """
    user_payload = {
        "primerNombre": "Maria",
        "segundoNombre": "Luisa",
        "apellidoPaterno": "Lopez",
        "apellidoMaterno": "Gomez",
        "username": "maria.origen",
        "email": "maria.origen@example.com",
        "telefono": "7000-9999",
        "ci": "8888888",
        "passwordHash": make_password("pw-origen"),
        "fechaNacimiento": "1992-03-03",
        "nroHijos": 1,
        "direccionDomicilio": "Calle Origen 123",
        "ocupacion": "Estudiante",
        "observacionesCliente": "obs-origen",
    }
    if origen is not None:
        user_payload["origen"] = origen

    return ProspectoConversionBorrador.objects.create(
        cliente=None,
        prospecto=None,
        iniciado_por=admin,
        datos_usuario=user_payload,
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
            "motivoConsulta": "consulta-origen",
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
        datos_biometria={"provider": "MOCK", "template": "BASE64-ORIGEN", "quality": 80},
        paso_usuario_completado=True,
        paso_operacion_completado=True,
        paso_ficha_completado=True,
        paso_biometria_completado=True,
        paso_actual=ProspectoConversionBorrador.Paso.BIOMETRIA,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class DirectFinalizeOrigenTests(TestCase):
    """Direct-mode finalize MUST validate and persist ``Cliente.origen``."""

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

    def test_finalize_persists_recurrente_pre_sistema(self):
        """Direct finalize with ``origen='RECURRENTE_PRE_SISTEMA'`` persists."""
        draft = _make_direct_draft(
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
            origen=Cliente.Origen.RECURRENTE_PRE_SISTEMA,
        )

        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = self._finalize(draft)

        self.assertEqual(response.status_code, 201)
        cliente = Cliente.objects.get(usuario__username="maria.origen")
        self.assertEqual(
            cliente.origen,
            Cliente.Origen.RECURRENTE_PRE_SISTEMA,
            "direct finalize must persist the radio-selected origen",
        )

    def test_finalize_without_origen_defaults_to_nuevo(self):
        """Draft without ``origen`` falls back to ``NUEVO``."""
        draft = _make_direct_draft(
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
            # origen omitted — the spec says the wizard payload omits it,
            # finalize defaults to NUEVO.
        )

        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = self._finalize(draft)

        self.assertEqual(response.status_code, 201)
        cliente = Cliente.objects.get(usuario__username="maria.origen")
        self.assertEqual(
            cliente.origen,
            Cliente.Origen.NUEVO,
            "origen must default to NUEVO when draft omits the field",
        )

    def test_finalize_with_unknown_origen_returns_400_and_no_rows_created(self):
        """Unknown ``origen`` value rejected on creation — no rows persist."""
        draft = _make_direct_draft(
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
            origen="ALGOTRO",
        )

        before_user_count = Usuario.objects.count()
        before_cliente_count = Cliente.objects.count()

        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = self._finalize(draft)

        self.assertEqual(response.status_code, 400)
        # No ``Usuario`` or ``Cliente`` row created — the entire
        # finalize transaction must roll back when validation fails.
        self.assertEqual(
            Usuario.objects.filter(username="maria.origen").count(),
            0,
        )
        self.assertEqual(Usuario.objects.count(), before_user_count)
        self.assertEqual(Cliente.objects.count(), before_cliente_count)