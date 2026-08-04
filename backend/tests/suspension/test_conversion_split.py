"""Task 2.4 — conversion wizard: new-prospect and reactivation split.

Behaviour under ``BIOMETRIC_SUSPENDED``:

- ``admin_prospect_conversion_biometric_step`` (both ``prospecto`` and
  ``cliente`` paths) accepts the step without a template. For
  reactivation the existing ``datos_biometria`` is preserved
  byte-for-byte except for the explicit ``template=""`` redaction; for
  new prospect a blank biometric record is set.
- ``admin_prospect_conversion_finalize``:
    * new-prospect branch — under suspension the prospect→cliente
      ``HuellaBiometricaCliente`` migration, the
      ``BiometricAttempt`` migration, and the legacy
      ``update_or_create`` fallback are ALL skipped. Prospect-owned
      rows/history stay unchanged.
    * reactivation branch — under suspension the
      ``update_or_create`` upsert is skipped; the existing
      ``HuellaBiometricaCliente`` ciphertext is preserved
      byte-for-byte.
- The auth/permission gate (``_get_draft_convertible``) runs BEFORE
  the suspended branch so the existing 400 errors (no encontrado, ya
  procesado, sin permisos) still surface.
- The view never reaches the agent (no ``agent_client.capture`` /
  ``match``) under suspension.
- Repeated calls are safe: a second POST to the suspended step must be
  idempotent and not change ``datos_biometria`` for reactivation.
"""

from __future__ import annotations

import json
from datetime import date
from unittest import mock

from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from biometric.models import BiometricAttempt
from biometric.services.encryption import encrypt_template
from customers.models import (
    HuellaBiometricaCliente,
    Prospecto,
    ProspectoConversionBorrador,
)
from operations.models import Operacion

from ._base import SuspensionGateTestBase, post_json


SUSPENDED = override_settings(BIOMETRIC_SUSPENDED=True)


def _make_full_draft(*, base, cliente=None, prospecto=None, usuario, servicio, today, biometric_data):
    """Build a draft ready for the conversion finalize view."""
    return ProspectoConversionBorrador.objects.create(
        cliente=cliente,
        prospecto=prospecto,
        iniciado_por=usuario,
        datos_usuario={
            "primerNombre": (cliente or prospecto).usuario.primer_nombre if cliente else prospecto.primer_nombre,
            "apellidoPaterno": (cliente or prospecto).usuario.apellido_paterno if cliente else prospecto.apellido_paterno,
            "username": getattr(getattr(cliente, "usuario", None), "username", "") or "",
            "passwordHash": make_password("pw"),
            "fechaNacimiento": "1990-01-01",
            "ci": "12345",
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
                "tipoPielId": str(base.tipo_piel.id),
                "gradoDeshidratacionId": str(base.grado_deshidratacion.id),
                "grosorPielId": str(base.grosor_piel.id),
                "patologiaIds": [],
            },
            "antecedentes": [],
            "implantes": [],
            "cirugias": [],
            "fieldResponses": {},
        },
        datos_biometria=biometric_data,
        paso_usuario_completado=True,
        paso_operacion_completado=True,
        paso_ficha_completado=True,
        paso_biometria_completado=True,
        paso_actual=ProspectoConversionBorrador.Paso.BIOMETRIA,
    )


# ---------------------------------------------------------------------------
# Step-4 endpoint (both prospect and reactivation URLs)
# ---------------------------------------------------------------------------


@SUSPENDED
class ConversionBiometricStepTests(SuspensionGateTestBase):
    """Endpoint-level tests for the suspended step-4 routes."""

    def _prospect_draft(self):
        prospecto = Prospecto.objects.create(
            primer_nombre="Pro",
            apellido_paterno="Spect",
            telefono="7000-0000",
            sucursal_registro=self.sucursal,
            registrado_por=self.admin_principal,
        )
        draft = ProspectoConversionBorrador.objects.create(
            prospecto=prospecto,
            iniciado_por=self.admin_principal,
            paso_usuario_completado=True,
            paso_operacion_completado=True,
            paso_ficha_completado=True,
        )
        return prospecto, draft

    def _reactivation_draft(self):
        existing_template = encrypt_template(b"REACTIVATE-CIPHERTEXT")
        draft = ProspectoConversionBorrador.objects.create(
            cliente=self.cliente,
            iniciado_por=self.admin_principal,
            datos_usuario={"passwordHash": make_password("pw")},
            paso_usuario_completado=True,
            paso_operacion_completado=True,
            paso_ficha_completado=True,
            datos_biometria={"provider": "MOCK_LEGACY", "template": "BASE64", "quality": 80},
        )
        return draft, existing_template

    def test_prospect_step4_advances_under_suspension(self):
        prospecto, draft = self._prospect_draft()
        with mock.patch("biometric.services.factory.get_agent_client") as factory_mock:
            self.login(self.admin_sucursal)
            response = post_json(
                self.client_http,
                f"/api/admin/prospectos/{prospecto.id}/conversion/paso-4/",
                {"template": "", "quality": 0},
            )
        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        self.assertTrue(draft.paso_biometria_completado)
        self.assertEqual(draft.datos_biometria.get("template"), "")
        # The view must NOT touch the agent client.
        factory_mock.assert_not_called()

    def test_reactivation_step4_advances_under_suspension(self):
        draft, _ = self._reactivation_draft()
        with mock.patch("biometric.services.factory.get_agent_client") as factory_mock:
            self.login(self.admin_principal)
            response = post_json(
                self.client_http,
                f"/api/admin/clientes/{self.cliente.id}/reactivar/paso-4/",
                {"template": "BASE64", "quality": 80},
            )
        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        self.assertTrue(draft.paso_biometria_completado)
        # The redaction only flips the template; metadata is preserved.
        self.assertEqual(draft.datos_biometria["template"], "")
        self.assertEqual(draft.datos_biometria["quality"], 80)
        self.assertEqual(draft.datos_biometria["provider"], "MOCK_LEGACY")
        factory_mock.assert_not_called()

    def test_reactivation_step4_preserves_draft_data_byte_for_byte(self):
        """Reactivation: the existing ``datos_biometria`` must keep every
        other field untouched. Only the ``template`` is redacted to the
        empty string."""
        draft, _ = self._reactivation_draft()
        original_keys = set(draft.datos_biometria.keys())
        original_quality = draft.datos_biometria["quality"]
        original_provider = draft.datos_biometria["provider"]
        self.login(self.admin_principal)
        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = post_json(
                self.client_http,
                f"/api/admin/clientes/{self.cliente.id}/reactivar/paso-4/",
                {"template": "anything-else", "quality": 90},
            )
        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        self.assertEqual(set(draft.datos_biometria.keys()), original_keys)
        self.assertEqual(draft.datos_biometria["quality"], original_quality)
        self.assertEqual(draft.datos_biometria["provider"], original_provider)
        self.assertEqual(draft.datos_biometria["template"], "")

    def test_prospect_step4_rejects_unauthorized_before_gate(self):
        prospecto, _ = self._prospect_draft()
        # No login at all.
        response = post_json(
            self.client_http,
            f"/api/admin/prospectos/{prospecto.id}/conversion/paso-4/",
            {},
        )
        self.assertIn(response.status_code, (401, 403))
        self.assertNotEqual(response.status_code, 503)

    def test_reactivation_step4_rejects_unauthorized_before_gate(self):
        # No login at all.
        response = post_json(
            self.client_http,
            f"/api/admin/clientes/{self.cliente.id}/reactivar/paso-4/",
            {},
        )
        self.assertIn(response.status_code, (401, 403))
        self.assertNotEqual(response.status_code, 503)

    def test_prospect_step4_preserves_existing_errors(self):
        # The auth/draft resolution runs BEFORE the suspended branch, so
        # "prospecto no encontrado" is preserved under suspension.
        self.login(self.admin_principal)
        response = post_json(
            self.client_http,
            "/api/admin/prospectos/999999/conversion/paso-4/",
            {},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_reactivation_step4_repeated_call_is_safe(self):
        draft, _ = self._reactivation_draft()
        self.login(self.admin_principal)
        with override_settings(BIOMETRIC_SUSPENDED=True):
            first = post_json(
                self.client_http,
                f"/api/admin/clientes/{self.cliente.id}/reactivar/paso-4/",
                {"template": "BASE64", "quality": 80},
            )
            second = post_json(
                self.client_http,
                f"/api/admin/clientes/{self.cliente.id}/reactivar/paso-4/",
                {"template": "BASE64", "quality": 80},
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        draft.refresh_from_db()
        self.assertTrue(draft.paso_biometria_completado)
        self.assertEqual(draft.datos_biometria["template"], "")


# ---------------------------------------------------------------------------
# Finalize behaviour
# ---------------------------------------------------------------------------


@SUSPENDED
class ConversionFinalizeSplitTests(SuspensionGateTestBase):
    """Reactivation finalize skips upsert; new-prospect finalize skips ALL
    fingerprint/attempt writes so prospect-owned rows stay intact."""

    def test_reactivation_finalize_skips_upsert_and_preserves_huella(self):
        ciphertext = encrypt_template(b"REACTIVATE-CIPHERTEXT")
        huella = HuellaBiometricaCliente.objects.create(
            cliente=self.cliente,
            proveedor=HuellaBiometricaCliente.Proveedor.MOCK_LEGACY,
            template_biometrico=ciphertext,
            activo=True,
        )
        draft = _make_full_draft(
            base=self,
            cliente=self.cliente,
            prospecto=None,
            usuario=self.admin_principal,
            servicio=self.servicio,
            today=date.today(),
            biometric_data={"provider": "MOCK_LEGACY", "template": "BASE64", "quality": 80},
        )
        pdf = SimpleUploadedFile("doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        self.login(self.admin_principal)
        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = self.client_http.post(
                f"/api/admin/clientes/{self.cliente.id}/reactivar/finalizar/",
                data={"documento_escaneado_pdf": pdf},
            )
        self.assertEqual(response.status_code, 201)
        huella.refresh_from_db()
        self.assertEqual(bytes(huella.template_biometrico), ciphertext)
        self.assertFalse(ProspectoConversionBorrador.objects.filter(pk=draft.id).exists())

    def test_new_prospect_finalize_preserves_prospect_owned_huella_and_attempts(self):
        prospecto = Prospecto.objects.create(
            primer_nombre="Pro",
            apellido_paterno="Spect",
            telefono="7000-0000",
            sucursal_registro=self.sucursal,
            registrado_por=self.admin_principal,
        )
        existing_huella_ciphertext = encrypt_template(b"PROSPECT-EXISTING-CIPHERTEXT")
        existing_huella = HuellaBiometricaCliente.objects.create(
            prospecto=prospecto,
            cliente=None,
            proveedor=HuellaBiometricaCliente.Proveedor.DIGITAL_PERSONA,
            template_biometrico=existing_huella_ciphertext,
            activo=True,
            calidad_captura=80,
            device_serial="dev-existing",
        )
        existing_attempt = BiometricAttempt.objects.create(
            prospecto=prospecto,
            cliente=None,
            usuario=self.admin_principal,
            operation=BiometricAttempt.Operation.ENROLL,
            success=True,
            score=0.8,
        )
        huella_count_before = HuellaBiometricaCliente.objects.count()
        attempt_count_before = BiometricAttempt.objects.count()

        # The prospect has no usuario (no user account yet) — build a draft
        # with a fully-formed user payload so finalize creates the cliente.
        draft = _make_full_draft(
            base=self,
            cliente=None,
            prospecto=prospecto,
            usuario=self.admin_principal,
            servicio=self.servicio,
            today=date.today(),
            biometric_data={"provider": "MOCK", "template": "BASE64", "quality": 70},
        )
        # _make_full_draft expects (cliente or prospecto).usuario for primerNombre; the
        # prospecto has no user, so patch the user payload explicitly.
        draft.datos_usuario = {
            **draft.datos_usuario,
            "primerNombre": prospecto.primer_nombre,
            "apellidoPaterno": prospecto.apellido_paterno,
            "username": "prospect.fresh.user",
            "email": "prospect@example.com",
            "telefono": prospecto.telefono,
            "ci": "99999",
        }
        draft.save()

        pdf = SimpleUploadedFile("doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        self.login(self.admin_principal)
        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = self.client_http.post(
                f"/api/admin/prospectos/{prospecto.id}/conversion/finalizar/",
                data={"documento_escaneado_pdf": pdf},
            )
        self.assertEqual(response.status_code, 201)

        # Existing prospect-owned huella stays byte-for-byte and the FK
        # is NOT silently retargeted to the new cliente.
        existing_huella.refresh_from_db()
        self.assertEqual(bytes(existing_huella.template_biometrico), existing_huella_ciphertext)
        self.assertEqual(existing_huella.prospecto_id, prospecto.id)
        self.assertIsNone(existing_huella.cliente_id)
        self.assertEqual(existing_huella.device_serial, "dev-existing")

        # Existing prospect-owned attempt row stays put.
        existing_attempt.refresh_from_db()
        self.assertEqual(existing_attempt.prospecto_id, prospecto.id)
        self.assertIsNone(existing_attempt.cliente_id)

        # No new Huella rows and no new BiometricAttempt rows were created
        # for the freshly-converted cliente.
        new_cliente_id = json.loads(response.content)["client"]["id"]
        self.assertEqual(HuellaBiometricaCliente.objects.count(), huella_count_before)
        self.assertEqual(BiometricAttempt.objects.count(), attempt_count_before)
        self.assertEqual(
            HuellaBiometricaCliente.objects.filter(cliente_id=new_cliente_id).count(), 0
        )
        self.assertEqual(
            BiometricAttempt.objects.filter(cliente_id=new_cliente_id).count(), 0
        )
        self.assertFalse(ProspectoConversionBorrador.objects.filter(pk=draft.id).exists())
