# Hand-written for operation-manual-closure:
#
# Adds three nullable audit fields on ``Operacion``:
#   * ``finalized_by``     — FK to ``accounts.Usuario`` (SET_NULL so deleting
#                            a user does not cascade-delete the operation)
#   * ``finalized_at``     — DateTime (nullable on purpose: legacy rows
#                            that closed under the old auto-finalization
#                            rule have no historical admin and we do not
#                            want to invent one during this migration)
#   * ``finalization_kind``— ``MANUAL_FINALIZADA | MANUAL_SUSPENDIDA``
#                            (nullable for the same reason)
#
# Also extends ``Operacion.estado`` with a new terminal value
# ``SUSPENDIDA = "SUSPENDIDA"``. Pre-existing rows keep their state; no
# data migration runs.
#
# The migration is fully reversible: dropping it removes the new choices
# value and drops the three new columns without touching the rest of
# the schema.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("operations", "0029_citaprospecto_precio"),
    ]

    operations = [
        migrations.AddField(
            model_name="operacion",
            name="finalized_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="operaciones_finalizadas",
                to="accounts.usuario",
            ),
        ),
        migrations.AddField(
            model_name="operacion",
            name="finalized_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="operacion",
            name="finalization_kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("MANUAL_FINALIZADA", "Finalizada manualmente"),
                    ("MANUAL_SUSPENDIDA", "Suspendida manualmente"),
                ],
                max_length=24,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="operacion",
            name="estado",
            field=models.CharField(
                choices=[
                    ("BORRADOR", "Borrador"),
                    ("EN_PROCESO", "En proceso"),
                    ("FINALIZADA", "Finalizada"),
                    ("CANCELADA", "Cancelada"),
                    ("SUSPENDIDA", "Suspendida"),
                ],
                default="BORRADOR",
                max_length=20,
            ),
        ),
    ]
