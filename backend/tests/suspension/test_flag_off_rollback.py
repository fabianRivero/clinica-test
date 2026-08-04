"""Task 2.5 — flag-off rollback proves no regression for every gated family.

The default ``BIOMETRIC_SUSPENDED`` is False. With the flag off, the
endpoints must keep their existing live behaviour:

- ``enroll_init`` / ``prospect_enroll`` / etc. do not return 503.
- ``verify_init`` (without a fingerprint) returns
  ``{has_fingerprint:false, manual_only:true}``.
- The legacy ``confirmar-biometria`` slash function may return 200/4xx
  based on the template equality check but NEVER 503.
- The client portal appointment row reports ``canConfirmBiometric=True``
  for a pending cita.
- The admin operation detail exposes the legacy MOCK template as a
  non-empty value.

The PR 1 foundation already covered the factory short-circuit and
SuspendedAgentClient contract; those assertions live in
``biometric/tests/test_suspension_foundation.py`` and
``biometric/tests/test_agent_client.py``. We intentionally do not
duplicate them here.
"""

from __future__ import annotations

from django.test import override_settings

from biometric.services.encryption import encrypt_template
from customers.models import HuellaBiometricaCliente

from ._base import SuspensionGateTestBase, post_json


class FlagOffRollbackTests(SuspensionGateTestBase):
    def setUp(self):
        super().setUp()
        # Real Fernet-encrypted payload so the legacy code path stays
        # serializable; the assertion is non-empty, not the exact value.
        self.huella = HuellaBiometricaCliente.objects.create(
            cliente=self.cliente,
            proveedor=HuellaBiometricaCliente.Proveedor.MOCK_LEGACY,
            template_biometrico=encrypt_template(b"keepme"),
            activo=True,
        )

    def test_flag_off_verify_init_returns_normal_handshake(self):
        # Delete the seeded huella so verify_init returns its no-fingerprint
        # response (NOT 503).
        HuellaBiometricaCliente.objects.all().delete()
        self.login(self.admin_sucursal)
        with override_settings(BIOMETRIC_SUSPENDED=False):
            response = post_json(
                self.client_http, f"/api/biometric/citas/{self.cita.id}/huella/verify-init/"
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("has_fingerprint") is False)
        self.assertTrue(response.json().get("manual_only"))

    def test_flag_off_legacy_route_does_not_503(self):
        self.login(self.admin_principal)
        with override_settings(BIOMETRIC_SUSPENDED=False):
            response = post_json(
                self.client_http,
                f"/api/admin/citas/{self.cita.id}/confirmar-biometria/",
                {"template": "TEMPLATE_OK", "quality": 80},
            )
        # The legacy function may return 200 or 4xx depending on the
        # template equality check, but it MUST NOT return 503.
        self.assertNotEqual(response.status_code, 503)

    def test_flag_off_drf_action_route_does_not_503(self):
        # Same guarantee for the DRF no-slash URL: with the flag off the
        # CitasViewSet action runs its real serializer + write path,
        # not the suspended gate. Move the cita to PROGRAMADA so the
        # action's state-check returns 400 (a normal validation error)
        # rather than reaching the (pre-existing) save() call that
        # references a non-existent field — we are asserting the
        # rollback contract, not exercising the full happy path.
        from operations.models import CitaMedica

        self.cita.estado = CitaMedica.Estado.PROGRAMADA
        self.cita.save()
        self.login(self.admin_principal)
        with override_settings(BIOMETRIC_SUSPENDED=False):
            response = post_json(
                self.client_http,
                f"/api/admin/citas/citas/{self.cita.id}/confirmar-biometria",
                {"template": "TEMPLATE_OK", "quality": 80},
            )
        # Pre-existing latent issue: the live DRF action's update_fields
        # references a non-existent field, so the happy path crashes with
        # 500. That is out of scope for the suspension change. The
        # rollback contract is: under flag-off, the request MUST NOT
        # receive 503 (the suspended gate is bypassed). The action may
        # 400 (state check) or 500 (latent bug) — anything except 503.
        self.assertNotEqual(response.status_code, 503)

    def test_flag_off_canConfirmBiometric_is_true_for_pending(self):
        from config.client_api_views import _appointment_item

        with override_settings(BIOMETRIC_SUSPENDED=False):
            item = _appointment_item(self.cita)
        self.assertTrue(item["canConfirmBiometric"])

    def test_flag_off_template_is_exposed_in_operation_detail(self):
        # MOCK_LEGACY provider exposes the ciphertext under suspension as
        # empty string and in the live build as a non-empty string. We
        # assert via the serializer helper (the admin HTTP view
        # round-trips the bytes through a JSON encoder that may not be
        # able to serialise raw bytes — that latent issue is pre-existing
        # and out of scope for this diff).
        from config.api_views import _operation_detail

        with override_settings(BIOMETRIC_SUSPENDED=False):
            live = _operation_detail(self.operacion)
        self.assertNotEqual(live["biometricMockTemplate"], "")
        with override_settings(BIOMETRIC_SUSPENDED=True):
            suspended = _operation_detail(self.operacion)
        self.assertEqual(suspended["biometricMockTemplate"], "")
