# Hand-written for citas-pagos follow-on: extend ``PagoCita`` to cover
# ``CitaProspecto`` (third FK). The XOR CheckConstraint becomes 3-way
# so exactly one of ``cita_medica`` / ``cita_cliente_libre`` /
# ``cita_prospecto`` is set per row.
#
# Additive only:
#   * AddField cita_prospecto (nullable, indexed).
#   * AddIndex for the new FK + created_at composite.
#   * RemoveConstraint + AddConstraint to swap the 2-way XOR for the
#     3-way version (CheckConstraint names are immutable).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0010_cita_precio_and_pago_cita'),
        ('operations', '0028_citamedica_precio_citaclientelibre_precio'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagocita',
            name='cita_prospecto',
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='pagos_cita',
                to='operations.citaprospecto',
            ),
        ),
        migrations.AddIndex(
            model_name='pagocita',
            index=models.Index(
                fields=['cita_prospecto', '-created_at'],
                name='pagos_citas_cita_pr_2c1aba_idx',
            ),
        ),
        # Drop the 2-way XOR and add the 3-way XOR. The constraint
        # ``name`` is the immutable identifier; you cannot mutate a
        # CheckConstraint in place, so we remove + re-add.
        migrations.RemoveConstraint(
            model_name='pagocita',
            name='pago_cita_xor_cita_fk',
        ),
        migrations.AddConstraint(
            model_name='pagocita',
            constraint=models.CheckConstraint(
                check=(
                    # cita_medica set, the other two null
                    models.Q(
                        cita_medica__isnull=False,
                        cita_cliente_libre__isnull=True,
                        cita_prospecto__isnull=True,
                    )
                    # cita_cliente_libre set, the other two null
                    | models.Q(
                        cita_medica__isnull=True,
                        cita_cliente_libre__isnull=False,
                        cita_prospecto__isnull=True,
                    )
                    # cita_prospecto set, the other two null
                    | models.Q(
                        cita_medica__isnull=True,
                        cita_cliente_libre__isnull=True,
                        cita_prospecto__isnull=False,
                    )
                ),
                name='pago_cita_xor_cita_fk',
            ),
        ),
    ]