# Hand-written for citas-pagos follow-on: add ``precio`` to
# ``CitaProspecto`` so admin cobro on prospecto appointments can land on
# a non-zero amount. Mirrors the 0028 migration that did the same for
# ``CitaMedica`` and ``CitaClienteLibre``.
#
# ``precio=0`` is the natural disable for legacy rows — admins set
# the price (either at booking time or via the new PATCH endpoint)
# before the first APROBADO PagoCita can be registered.

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0028_citamedica_precio_citaclientelibre_precio'),
        ('billing', '0011_pago_cita_cita_prospecto'),
    ]

    operations = [
        migrations.AddField(
            model_name='citaprospecto',
            name='precio',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]