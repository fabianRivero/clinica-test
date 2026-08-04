"""Task 2.1 — canonical biometric mutations are fail-closed under suspension.

The canonical surface is everything mounted under ``/api/biometric/`` in
``backend/biometric/urls.py``: enrollment init/finalize, prospect
enrollment, verify init/confirm. Every mutation must:

- Run its existing authentication / permission check first (so 401/403
  wins over 503 — no information leak about suspension state).
- Return the family-specific ``BIOMETRIC_SUSPENDED`` body.
- Never write a ``HuellaBiometricaCliente``, ``BiometricAttempt``, or
  appointment transition.

Manual confirmation (``/huella/confirm-manual/``) is intentionally NOT
gated because the spec requires it as the supported replacement.
"""

from __future__ import annotations

from unittest import mock

from django.test import override_settings

from biometric.models import BiometricAttempt
from customers.models import HuellaBiometricaCliente, Prospecto
from operations.models import CitaMedica

from ._base import SuspensionGateTestBase, post_json


SUSPENDED = override_settings(BIOMETRIC_SUSPENDED=True)


@SUSPENDED
class CanonicalGatingTests(SuspensionGateTestBase):
    def test_enroll_init_returns_503_and_no_persistence(self):
        self.login(self.admin_sucursal)
        before = HuellaBiometricaCliente.objects.count()
        response = post_json(
            self.client_http,
            f"/api/biometric/clientes/{self.cliente.id}/huella/enroll/",
            {"consentimiento_aceptado": True},
        )
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["code"], "BIOMETRIC_SUSPENDED")
        self.assertFalse(body["enrollment_available"])
        self.assertEqual(HuellaBiometricaCliente.objects.count(), before)
        self.assertEqual(BiometricAttempt.objects.count(), 0)

    def test_enroll_finalize_returns_503_and_no_writes(self):
        self.login(self.admin_sucursal)
        huella_before = HuellaBiometricaCliente.objects.count()
        attempt_before = BiometricAttempt.objects.count()
        with override_settings(BIOMETRIC_SUSPENDED=True), \
             mock.patch("biometric.views.capture_token_store") as store_mock, \
             mock.patch("biometric.views.get_agent_client") as factory_mock, \
             mock.patch("biometric.views.encrypt_template") as encrypt_mock:
            response = post_json(
                self.client_http,
                f"/api/biometric/clientes/{self.cliente.id}/huella/enroll/finalize/",
                {"capture_token": "x"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "BIOMETRIC_SUSPENDED")
        # Live code reads/pops the token, encrypts the template and calls
        # the agent; under suspension NONE of these should run.
        store_mock.pop.assert_not_called()
        store_mock.create.assert_not_called()
        factory_mock.assert_not_called()
        encrypt_mock.assert_not_called()
        self.assertEqual(HuellaBiometricaCliente.objects.count(), huella_before)
        self.assertEqual(BiometricAttempt.objects.count(), attempt_before)

    def test_prospect_enroll_returns_503(self):
        prospecto = Prospecto.objects.create(
            primer_nombre="Pro",
            apellido_paterno="Spect",
            telefono="7000-0000",
            sucursal_registro=self.sucursal,
            registrado_por=self.admin_principal,
        )
        self.login(self.admin_sucursal)
        response = post_json(
            self.client_http,
            f"/api/biometric/prospectos/{prospecto.id}/huella/enroll/",
            {"consentimiento_aceptado": True},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "BIOMETRIC_SUSPENDED")
        self.assertEqual(
            HuellaBiometricaCliente.objects.filter(prospecto=prospecto).count(), 0
        )

    def test_verify_init_returns_503_unchanged_history(self):
        self.login(self.admin_sucursal)
        before_attempts = BiometricAttempt.objects.count()
        response = post_json(
            self.client_http, f"/api/biometric/citas/{self.cita.id}/huella/verify-init/"
        )
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["code"], "BIOMETRIC_SUSPENDED")
        self.assertTrue(body["manual_only"])
        self.assertFalse(body["matched"])
        self.assertEqual(BiometricAttempt.objects.count(), before_attempts)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION)

    def test_verify_confirm_returns_503_and_no_writes(self):
        self.login(self.admin_sucursal)
        attempt_before = BiometricAttempt.objects.count()
        with override_settings(BIOMETRIC_SUSPENDED=True), \
             mock.patch("biometric.views.capture_token_store") as store_mock, \
             mock.patch("biometric.views.get_agent_client") as factory_mock:
            response = post_json(
                self.client_http,
                f"/api/biometric/citas/{self.cita.id}/huella/verify-confirm/",
                {"capture_token": "x", "score": 80},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "BIOMETRIC_SUSPENDED")
        # Live code pops the token then writes a BiometricAttempt; under
        # suspension neither runs.
        store_mock.pop.assert_not_called()
        store_mock.create.assert_not_called()
        factory_mock.assert_not_called()
        self.assertEqual(BiometricAttempt.objects.count(), attempt_before)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION)
        self.assertFalse(self.cita.verif_biometria)

    def test_unauthorized_caller_still_rejected_before_gate(self):
        for path in [
            f"/api/biometric/clientes/{self.cliente.id}/huella/enroll/",
            f"/api/biometric/clientes/{self.cliente.id}/huella/enroll/finalize/",
            f"/api/biometric/citas/{self.cita.id}/huella/verify-init/",
            f"/api/biometric/citas/{self.cita.id}/huella/verify-confirm/",
        ]:
            with self.subTest(path=path):
                response = post_json(self.client_http, path, {"consentimiento_aceptado": True})
                self.assertIn(response.status_code, (401, 403))

    def test_manual_confirmation_still_works_under_suspension(self):
        self.login(self.admin_sucursal)
        response = post_json(
            self.client_http,
            f"/api/biometric/citas/{self.cita.id}/huella/confirm-manual/",
            {"metodo": "MANUAL"},
        )
        self.assertEqual(response.status_code, 200)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.CONFIRMADA)
        self.assertEqual(self.cita.metodo_confirmacion, CitaMedica.MetodoConfirmacion.MANUAL)
        self.assertFalse(self.cita.verif_biometria)
