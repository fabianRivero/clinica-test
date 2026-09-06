"""Add Prospecto.origen with default ``NUEVO`` and backfill existing rows.

Mirrors ``0015_cliente_origen``: the column is non-null and ships with
``db_default="NUEVO"`` so the backfill happens at the DB layer — every
pre-existing ``prospectos`` row gets the literal ``"NUEVO"`` value on
apply, AND every subsequent ``INSERT`` (including ``bulk_create`` paths
that bypass the model-level default) inherits the SQL-level default.

``default="NUEVO"`` on the model itself keeps the Python-side
``Prospecto()`` / ``Prospecto.objects.create()`` path covered too, and
is the value the serializer sees when reading an unset field.

Reverse path drops the column outright; ``Cliente.origen`` semantics
and the direct-path finalize remain untouched.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0015_cliente_origen"),
    ]

    operations = [
        migrations.AddField(
            model_name="prospecto",
            name="origen",
            field=models.CharField(
                max_length=32,
                choices=[
                    ("NUEVO", "Nuevo"),
                    ("RECURRENTE_PRE_SISTEMA", "Recurrente pre-sistema"),
                ],
                default="NUEVO",
                db_default="NUEVO",
            ),
        ),
    ]
