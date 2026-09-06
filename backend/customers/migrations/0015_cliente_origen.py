"""Add Cliente.origen with default ``NUEVO`` and backfill existing rows.

The column is non-null. We add it with ``db_default="NUEVO"`` so the
backfill happens at the DB layer; every pre-existing ``clientes`` row
gets the literal ``"NUEVO"`` value on apply, AND every subsequent
INSERT (including ``bulk_create`` paths that bypass the model-level
default) inherits the SQL-level default. This protects both the
production rollout and the test suite's ``bulk_create`` graph
construction.

``default="NUEVO"`` on the model itself keeps the Python-side
``Cliente()`` / ``Cliente.objects.create()`` path covered too, and is
the value the serializer sees when reading an unset field.

Reverse path drops the column outright; the existing draft / finalize
payloads already stop serialising ``origen`` for prospects and
reactivations, so the rollback is data-clean.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0014_cliente_cliente_codigo"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
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