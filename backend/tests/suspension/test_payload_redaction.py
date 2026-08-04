"""Task 2.4 — payload affordances redact the stored template under suspension.

The two response builders that surface MOCK_LEGACY templates are:

- ``config.api_views._operation_detail`` (admin operation detail, used
  by ``/api/admin/operaciones/<id>/``).
- ``config.client_api_views._appointment_item`` (client portal
  appointment row).

Both must report ``canConfirmBiometric=false`` and
``biometricMockTemplate=""`` while ``BIOMETRIC_SUSPENDED`` is on, and
the on-disk ciphertext row in ``HuellaBiometricaCliente`` must stay
byte-for-byte unchanged.
"""

from __future__ import annotations

from django.test import override_settings

from biometric.services.encryption import encrypt_template
from customers.models import HuellaBiometricaCliente

from ._base import SuspensionGateTestBase


SUSPENDED = override_settings(BIOMETRIC_SUSPENDED=True)


@SUSPENDED
class PayloadRedactionTests(SuspensionGateTestBase):
    def setUp(self):
        super().setUp()
        # Use a real Fernet-encrypted payload so legacy code paths that
        # pass `template_biometrico` through a base64 codec stay
        # serializable.
        self.ciphertext = encrypt_template(b"REDACT-THIS-CIPHERTEXT")
        self.huella = HuellaBiometricaCliente.objects.create(
            cliente=self.cliente,
            proveedor=HuellaBiometricaCliente.Proveedor.MOCK_LEGACY,
            template_biometrico=self.ciphertext,
            activo=True,
            calidad_captura=80,
            device_serial="dev-1",
        )

    def test_operation_detail_redacts_template_and_disables_can_confirm(self):
        from config.api_views import _operation_detail

        payload = _operation_detail(self.operacion)
        self.assertEqual(payload["biometricMockTemplate"], "")
        for appointment in payload["appointments"]:
            self.assertFalse(appointment["canConfirmBiometric"])

    def test_client_appointment_item_redacts_template_and_disables_can_confirm(self):
        from config.client_api_views import _appointment_item

        item = _appointment_item(self.cita)
        self.assertEqual(item["biometricMockTemplate"], "")
        self.assertFalse(item["canConfirmBiometric"])

    def test_existing_history_template_remains_unchanged_on_disk(self):
        self.huella.refresh_from_db()
        self.assertEqual(bytes(self.huella.template_biometrico), self.ciphertext)
