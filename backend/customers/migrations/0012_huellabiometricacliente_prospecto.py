"""Add nullable prospecto FK to ``HuellaBiometricaCliente``.

Lets a fingerprint row belong to a ``Prospecto`` before the prospect
has been promoted to a ``Cliente``. The prospect-to-cliente conversion
wizard now captures the fingerprint at step 4 (where it was previously
deferred with a placeholder); the row is later re-attached to the new
``Cliente`` during ``admin_prospect_conversion_finalize``.

Rules baked in:

- ``prospecto`` is a nullable FK to ``customers.Prospecto``.
- ``CheckConstraint`` enforces **exactly one of** ``cliente`` /
  ``prospecto`` set on every row.
- ``unique_together(prospecto)`` keeps one fingerprint per prospect;
  the existing ``OneToOneField(cliente)`` already covers the cliente
  side.

The matching ``BiometricAttempt`` schema changes live in
``biometric/migrations/0003_*`` since that model is declared in the
``biometric`` app.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0011_legacy_proveedor_backfill"),
    ]

    operations = [
        # ``cliente`` is now nullable: a row may belong to a prospect
        # (and be re-attached to a cliente later during finalize).
        migrations.AlterField(
            model_name="huellabiometricacliente",
            name="cliente",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="huella_biometrica",
                to="customers.cliente",
            ),
        ),
        migrations.AddField(
            model_name="huellabiometricacliente",
            name="prospecto",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="huellas_biometricas",
                to="customers.prospecto",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="huellabiometricacliente",
            unique_together=set([("prospecto",)]),
        ),
        migrations.AddConstraint(
            model_name="huellabiometricacliente",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(
                        cliente__isnull=False,
                        prospecto__isnull=True,
                    )
                    | models.Q(
                        cliente__isnull=True,
                        prospecto__isnull=False,
                    )
                ),
                name="huella_exactly_one_owner",
            ),
        ),
    ]