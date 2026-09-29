"""E2E smoke tests for dp4500_integration.

Phase 2 of dp4500-host-app-integration-phase2. Drives the wizard
step 4 endpoint via Django's test client.

Cita verify view tests live elsewhere — full Operacion + Cliente +
ServicioConfig fixture setup is more complex than warranted for a
Phase 2 smoke. The view-level classification logic is covered by
``test_client.py`` (status mapping) and ``test_cascade.py`` (cascade
signal + Celery task). The e2e URL wiring is verified here.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from accounts.models import Rol
from dp4500_integration.models import BiometricEnrollmentRecord


class WizardStep4ViewE2ETests(TestCase):
    def setUp(self):
        User = get_user_model()
        rol, _ = Rol.objects.get_or_create(rol="ADMIN_PRINCIPAL")
        self.user = User.objects.create_user(
            username="wizard_admin",
            password="Sup3rSecret!",
            primer_nombre="Wizard",
            apellido_paterno="Admin",
            rol=rol,
        )

    def test_get_step_4_renders_capture_pending(self):
        """GET the URL: returns 200 with the capture_pending.html template."""
        client = Client()
        client.force_login(self.user)
        resp = client.get(
            "/api/integration/dp4500/wizard/prospecto/42/step-4/",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("Paso 4", body)
        self.assertIn("Phase 2 stub", body)
        self.assertIn("Continuar sin captura", body)

    def test_post_advance_writes_biometric_enrollment_record(self):
        """POST with ``advance=1`` redirects and writes a Phase 2 stub record."""
        client = Client()
        client.force_login(self.user)
        resp = client.post(
            "/api/integration/dp4500/wizard/prospecto/42/step-4/",
            data={"advance": "1"},
        )
        # Redirect to "/" (Phase 2 stub landing).
        self.assertEqual(resp.status_code, 302)
        rec = BiometricEnrollmentRecord.objects.get(wizard_id="prospect-42")
        self.assertEqual(
            rec.enrollment_strategy,
            BiometricEnrollmentRecord.STRATEGY_PENDING,
        )
        self.assertIsNotNone(rec.advanced_at)

    def test_post_cancel_marks_cancelled_at(self):
        """POST with ``cancel=1`` marks the open record's cancelled_at."""
        client = Client()
        client.force_login(self.user)
        client.post(
            "/api/integration/dp4500/wizard/prospecto/42/step-4/",
            data={"advance": "1"},
        )
        client.post(
            "/api/integration/dp4500/wizard/prospecto/42/step-4/",
            data={"cancel": "1"},
        )
        rec = BiometricEnrollmentRecord.objects.get(wizard_id="prospect-42")
        self.assertIsNotNone(rec.cancelled_at)
        self.assertIsNotNone(rec.advanced_at)
