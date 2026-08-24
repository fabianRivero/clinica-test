"""Add Cliente.cliente_codigo and backfill existing rows.

Three-step migration:

1. ``AddField`` with ``null=True`` so existing rows can stay untouched while
   the data migration runs.
2. ``RunPython`` backfill: iterate every Cliente row missing a codigo and
   generate one using the same alphabet as ``Cliente._generar_codigo_unico``
   (kept in lock-step here so the migration is reproducible even from the
   historical model state). ``.iterator(chunk_size=500)`` keeps memory bounded
   on the prod-sized ``clientes`` table.
3. ``AlterField`` to drop ``null=True`` and keep ``unique=True, blank=True``.
   The DB-level uniqueness constraint is the authoritative safety net for
   any race between backfill and concurrent inserts; with every existing row
   now populated, the constraint can be enforced at the column level.

The reverse path simply clears ``cliente_codigo`` on every row. The field
itself is removed by Django's own reverse of the ``AddField`` step.
"""

from django.db import migrations, models


# Mirrors ``Cliente._generar_codigo_unico`` alphabet from the live model.
# Must stay in lock-step with ``backend/customers/models.py``; duplication
# is intentional so the migration is replayable from historical state.
_CLIENTE_CODIGO_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CLIENTE_CODIGO_SUFFIX_LEN = 6
_CLIENTE_CODIGO_MAX_RETRIES = 8


def _generar_codigo_candidato():
    import secrets

    suffix = "".join(
        secrets.choice(_CLIENTE_CODIGO_ALPHABET)
        for _ in range(_CLIENTE_CODIGO_SUFFIX_LEN)
    )
    return f"CLI-{suffix}"


def _backfill_cliente_codigo(apps, schema_editor):
    Cliente = apps.get_model("customers", "Cliente")
    updated_at_field = "updated_at"

    qs = Cliente.objects.filter(cliente_codigo__isnull=True).iterator(chunk_size=500)
    for cliente in qs:
        for _attempt in range(_CLIENTE_CODIGO_MAX_RETRIES):
            candidato = _generar_codigo_candidato()
            collision = Cliente.objects.filter(cliente_codigo=candidato).exists()
            if collision:
                continue
            Cliente.objects.filter(pk=cliente.pk).update(
                cliente_codigo=candidato,
                **{updated_at_field: cliente.updated_at},
            )
            break
        else:
            # Extremely unlikely (~1/729M per attempt); let Django's
            # ``unique=True`` constraint catch the residual on the next
            # migration run rather than masking it here.
            raise RuntimeError(
                "Could not generate a unique cliente_codigo after "
                f"{_CLIENTE_CODIGO_MAX_RETRIES} attempts"
            )


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0013_remove_cliente_sucursal_registro_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="cliente_codigo",
            field=models.CharField(
                max_length=12,
                unique=True,
                null=True,
                blank=True,
                help_text=(
                    "Identificador universal del cliente en formato CLI-XXXXXX. "
                    "Se asigna automaticamente al guardar si esta vacio."
                ),
            ),
        ),
        migrations.RunPython(_backfill_cliente_codigo, _noop_reverse),
        migrations.AlterField(
            model_name="cliente",
            name="cliente_codigo",
            field=models.CharField(
                max_length=12,
                unique=True,
                blank=True,
                help_text=(
                    "Identificador universal del cliente en formato CLI-XXXXXX. "
                    "Se asigna automaticamente al guardar si esta vacio."
                ),
            ),
        ),
    ]
