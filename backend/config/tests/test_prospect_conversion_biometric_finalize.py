"""Tests for the wizard's biometric step validation + finalize persistence.

Phase 2A5 of dp4500-host-app-integration-phase2.

Two contracts under test:

1. ``_validate_biometric_step`` round-trips the wizard-minted
   ``externalId`` UUID into ``datos_biometria`` so the finalize handler
   can read it back.
2. ``admin_prospect_conversion_finalize`` persists the wizard-minted
   UUID into BOTH ``Usuario.biometric_external_id`` AND
   ``Cliente.external_id``, inside the same ``transaction.atomic()``
   block that creates the user/cliente rows.

The fixture chain follows the pattern in
``backend/config/tests/test_prospect_conversion_direct.py``
(``_build_graph`` + minimal direct-mode draft).
"""

from __future__ import annotations

import json
import uuid
from datetime import date

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
from config.prospect_conversion_views import _validate_biometric_step
from customers.models import (
    Cliente,
    Prospecto,
    ProspectoConversionBorrador,
)
from operations.models import Operacion


# ---------------------------------------------------------------------------
# Helpers — mirror the minimal direct-mode graph from
# `test_prospect_conversion_direct.py` so the new test reads alongside
# the existing suite.
# ---------------------------------------------------------------------------


def _build_graph():
    """Branch + admin + catalog graph for the finalize tests."""
    rol_cliente = Rol.objects.create(rol="CLIENTE")
    rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
    sucursal = Sucursal.objects.create(
        nombre="Validate-Step-Biometria", activa=True,
    )
    admin = Usuario.objects.create_user(
        username="validate.step.admin",
        password="pw12345!",
        primer_nombre="Admin",
        apellido_paterno="Validate",
        email="validate.step@example.com",
        rol=rol_admin,
        sucursal=sucursal,
    )

    tipo_servicio = TipoServicio.objects.create(
        tipo="Validate-Step-Limpieza", activo=True,
    )
    servicio = ServicioConfig.objects.create(
        tipo_servicio=tipo_servicio,
        activo=True,
        precio_base=100,
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
        "catalog_ids": {
            "tipo_piel": tipo_piel.id,
            "grado_deshidratacion": grado.id,
            "grosor_piel": grosor.id,
        },
    }


def _make_draft_with_external_id(*, admin, servicio, catalog_ids, today, external_id):
    """Build a direct-mode draft with the wizard's
    ``datos_biometria.externalId`` already populated (the Phase 2A4
    frontend mints and persists it at capture time).
    """
    user_payload = {
        "primerNombre": "Maria",
        "segundoNombre": "Luisa",
        "apellidoPaterno": "Validate",
        "apellidoMaterno": "Step",
        "username": "maria.validate.step",
        "email": "maria.validate.step@example.com",
        "telefono": "7000-1111",
        "ci": "7777777",
        "passwordHash": make_password("pw-validate"),
        "fechaNacimiento": "1992-03-03",
        "nroHijos": 1,
        "direccionDomicilio": "Calle Validate 123",
        "ocupacion": "Estudiante",
        "observacionesCliente": "obs-validate",
    }
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
            "motivoConsulta": "consulta-validate",
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
        datos_biometria={
            "provider": "DIGITAL_PERSONA",
            "template": "BASE64-validate",
            "quality": 80,
            "deviceSerial": "",
            "consentAccepted": True,
            "capturedAt": "",
            "externalId": str(external_id),
        },
        paso_usuario_completado=True,
        paso_operacion_completado=True,
        paso_ficha_completado=True,
        paso_biometria_completado=True,
        paso_actual=ProspectoConversionBorrador.Paso.BIOMETRIA,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class ValidateBiometricStepRoundTripTests(TestCase):
    """``_validate_biometric_step`` must round-trip the wizard-minted
    ``externalId`` UUID into the returned dict so the finalize handler
    can read it back from ``draft.datos_biometria["externalId"]``.
    """

    def test_external_id_round_trips_into_validated_dict(self):
        external_id = uuid.uuid4()
        payload = {
            "provider": "DIGITAL_PERSONA",
            "template": "BASE64-roundtrip",
            "quality": 80,
            "deviceSerial": "",
            "consentAccepted": True,
            "capturedAt": "",
            "externalId": str(external_id),
        }
        result, errors = _validate_biometric_step(payload)
        self.assertIsNone(errors, f"expected no errors, got: {errors!r}")
        self.assertIsNotNone(result)
        self.assertEqual(result["externalId"], str(external_id))

    def test_external_id_omitted_kept_absent(self):
        """Drafts that omit ``externalId`` must NOT receive one (legacy
        path stays untouched so existing flows keep working).
        """
        payload = {
            "provider": "DIGITAL_PERSONA",
            "template": "BASE64-no-external",
            "quality": 80,
            "deviceSerial": "",
            "consentAccepted": True,
            "capturedAt": "",
        }
        result, errors = _validate_biometric_step(payload)
        self.assertIsNone(errors)
        self.assertIsNotNone(result)
        # ``externalId`` is optional. When omitted from the payload,
        # the validated dict stays free of the field rather than
        # receiving an empty string.
        self.assertNotIn("externalId", result)


class FinalizePersistsExternalIdTests(TestCase):
    """``admin_prospect_conversion_finalize`` must persist the
    wizard-minted UUID into BOTH ``Usuario.biometric_external_id`` AND
    ``Cliente.external_id`` inside the same atomic block.
    """

    @classmethod
    def setUpTestData(cls):
        cls.graph = _build_graph()
        cls.today = date.today()
        cls.external_id = uuid.UUID(
            "11111111-2222-3333-4444-555555555555",
        )

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.graph["admin"])

    def _finalize(self, draft):
        pdf = SimpleUploadedFile(
            "doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf",
        )
        return self.http.post(
            f"/api/admin/clientes/directo/{draft.id}/finalizar/",
            data={"documento_escaneado_pdf": pdf},
        )

    def test_finalize_persists_external_id_to_usuario_and_cliente(self):
        """Direct finalize with a wizard-minted ``externalId`` writes
        the same UUID into Usuario + Cliente. The pre_save signal
        normally auto-mints a fresh UUID; the finalize handler must
        prefer the wizard-supplied value to keep the cross-system
        handle stable between the enroll and verify round-trips.
        """
        draft = _make_draft_with_external_id(
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
            external_id=self.external_id,
        )

        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = self._finalize(draft)

        self.assertEqual(response.status_code, 201, response.content)
        cliente = Cliente.objects.get(usuario__username="maria.validate.step")
        self.assertEqual(
            cliente.external_id,
            self.external_id,
            "Cliente.external_id must equal the wizard-minted UUID",
        )
        self.assertEqual(
            str(cliente.usuario.biometric_external_id),
            str(self.external_id),
            "Usuario.biometric_external_id must equal the wizard-minted UUID",
        )

    def test_finalize_without_external_id_keeps_signal_mint(self):
        """Drafts without ``externalId`` must NOT clobber the pre_save
        signal's auto-minted UUID — the dual-UUID pattern documented in
        the recon spec means the signal stays as the defensive fallback
        for non-wizard users.
        """
        draft = _make_draft_with_external_id(
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
            external_id=uuid.uuid4(),
        )
        # Strip the wizard-minted UUID to simulate a legacy draft.
        datos = dict(draft.datos_biometria)
        datos.pop("externalId", None)
        draft.datos_biometria = datos
        draft.save(update_fields=["datos_biometria", "updated_at"])

        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = self._finalize(draft)

        self.assertEqual(response.status_code, 201, response.content)
        cliente = Cliente.objects.get(usuario__username="maria.validate.step")
        # No ``externalId`` payload → no override → Cliente.external_id
        # stays NULL and the Usuario row keeps whatever the pre_save
        # signal minted on INSERT.
        self.assertIsNone(
            cliente.external_id,
            "Cliente.external_id must stay NULL when the draft omits externalId",
        )
        self.assertIsNotNone(
            cliente.usuario.biometric_external_id,
            "pre_save signal must still have minted a UUID on Usuario insert",
        )
