# Hand-written for citas-pagos (PR 1: backend data layer).
#
# Adds ``precio`` (DecimalField default 0) to ``CitaMedica`` and
# ``CitaClienteLibre``. ``precio=0`` is the natural disable for legacy
# appointments — admins set the price via the existing edit flows
# before the first APROBADO PagoCita can be registered.

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0027_operacionfoto'),
    ]

    operations = [
        migrations.AddField(
            model_name='citamedica',
            name='precio',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
        migrations.AddField(
            model_name='citaclientelibre',
            name='precio',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]