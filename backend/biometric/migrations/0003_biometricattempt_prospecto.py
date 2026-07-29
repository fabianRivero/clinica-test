"""Add nullable prospecto FK to biometric-owned rows.

This migration lifts the constraint that forced every
``HuellaBiometricaCliente`` and ``BiometricAttempt`` to belong to an
existing ``Cliente``. The prospect-to-cliente conversion wizard now
captures the fingerprint at step 4 (where previously the capture was
deferred with a placeholder), so the row has to exist *before* the
``Cliente`` row does.

Rules baked in:

- ``HuellaBiometricaCliente.prospecto`` and
  ``BiometricAttempt.prospecto`` are nullable FKs to
  ``customers.Prospecto``.
- ``BiometricAttempt.cliente`` is also nullable now (prospect-attempts
  have no cliente yet).
- ``HuellaBiometricaCliente`` enforces **exactly one of**
  ``cliente`` / ``prospecto`` via a ``CheckConstraint``.
- ``HuellaBiometricaCliente`` gains ``unique_together(prospecto)``
  so each prospect can only own one fingerprint row. The existing
  ``OneToOneField(cliente)`` already covers the cliente side.

``HuellaBiometricaCliente`` is declared in ``customers.models`` so its
schema changes are tracked in a separate, app-local migration under
``customers/migrations/0012_*``. This migration in ``biometric/`` only
owns ``BiometricAttempt``-level changes and uses
``SeparateDatabaseAndState`` to add a database state row for the FK on
``HuellaBiometricaCliente`` (so the ``BiometricAttempt.prospecto``
index doesn't get generated against a missing app state).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("biometric", "0002_agenttoken_token_encrypted"),
        ("customers", "0012_huellabiometricacliente_prospecto"),
    ]

    operations = [
        # ---- BiometricAttempt -------------------------------------------------
        migrations.AlterField(
            model_name="biometricattempt",
            name="cliente",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="biometric_attempts",
                to="customers.cliente",
            ),
        ),
        migrations.AddField(
            model_name="biometricattempt",
            name="prospecto",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="biometric_attempts",
                to="customers.prospecto",
            ),
        ),
        # Index by prospecto+operation so the prospect-attempt dashboard
        # query stays cheap (mirrors biometric_atts_cliente_op).
        migrations.AddIndex(
            model_name="biometricattempt",
            index=models.Index(
                fields=("prospecto", "operation"),
                name="biometric_atts_prospecto_op",
            ),
        ),
    ]