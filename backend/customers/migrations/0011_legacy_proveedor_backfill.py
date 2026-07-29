"""Data migration for the biometric integration.

Backfills legacy ``MOCK`` and ``SECU_GEN`` rows so:

- ``proveedor`` becomes ``MOCK_LEGACY`` / ``SECU_GEN_LEGACY``.
- ``activo`` flips to ``False`` (re-enrollment required under
  DigitalPersona).
- ``template_biometrico`` becomes ``NULL`` (the old TextField data is
  not Fernet ciphertext; keeping it would be misleading).
- ``template_format`` becomes ``UNKNOWN``.

The reverse migration is a no-op: those rows stay legacy and inactive
once we move forward. Operators who want to restore them must re-enroll
manually.
"""

from django.db import migrations


def backfill_legacy_proveedor(apps, schema_editor):
    HuellaBiometricaCliente = apps.get_model(
        "customers", "HuellaBiometricaCliente"
    )

    # MOCK -> MOCK_LEGACY
    HuellaBiometricaCliente.objects.filter(proveedor="MOCK").update(
        proveedor="MOCK_LEGACY",
        activo=False,
        template_biometrico=None,
        template_format="UNKNOWN",
    )
    # SECU_GEN -> SECU_GEN_LEGACY
    HuellaBiometricaCliente.objects.filter(proveedor="SECU_GEN").update(
        proveedor="SECU_GEN_LEGACY",
        activo=False,
        template_biometrico=None,
        template_format="UNKNOWN",
    )


def noop_reverse(apps, schema_editor):
    # Forward-only: we never resurrect legacy plaintext templates.
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0010_huellabiometricacliente_encrypted_template_key_id_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_legacy_proveedor, noop_reverse),
    ]
