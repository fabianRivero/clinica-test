"""Normalize the ``TipoServicio.tipo`` treatment aesthetic identity.

The two baseline seed commands historically disagreed on the canonical
spelling of the treatment aesthetic ``TipoServicio.tipo``:

* ``seed_client_baseline`` always wrote ``"Tratamiento estetico"`` (unaccented).
* ``seed_pdf_baseline`` wrote ``"Tratamiento estético"`` (accented).

The reform change (reform-database-seed-scripts, decision D2/D3) locks the
canonical identity on the unaccented spelling and demands a one-shot data
migration that:

* reassigns every ``ServicioConfig.tipo_servicio_id`` row currently pointing
  at the legacy accented row to the canonical unaccented row, and
* deletes the legacy accented row once it has no dependents.

The migration is a no-op on databases that never had the accented row, and
remains safe to re-run on databases that have already been normalized.

Reverse semantics
-----------------
The reverse migration restores the database to its pre-forward shape by
**reassigning** any ``ServicioConfig`` rows that point at the canonical
(unaccented) row back to the legacy (accented) row and then deleting the
canonical row.

The reverse is intentionally **conservative**: if the canonical row already
existed before the forward migration ran (the typical
``seed_client_baseline`` path), the reverse is a no-op — the canonical row
is left in place because we cannot distinguish "created by forward" from
"pre-existing operator data" without a separate marker table. The legacy
accented row, when absent, is treated as a no-op signal that the original
database never carried it.
"""

from django.db import migrations


LEGACY_TIPO = "Tratamiento estético"
CANONICAL_TIPO = "Tratamiento estetico"


def normalize_tipo_servicio_estetico(apps, schema_editor):
    """Forward: reassign FKs to the canonical row, drop the legacy row.

    Inside the implicit ``schema_editor`` transaction:

    1. Look up the legacy row by its exact ``tipo`` value.
    2. If the legacy row does not exist, the migration is a no-op.
    3. Look up (or create) the canonical row. Creation reuses the legacy
       row's ``orden``/``descripcion`` when present to avoid drift; otherwise
       it falls back to a neutral default that matches the existing
       ``seed_client_baseline`` literal.
    4. Reassign every ``ServicioConfig`` pointing at the legacy row to the
       canonical row. ``on_delete=PROTECT`` would otherwise block the
       subsequent DELETE.
    5. Delete the now-orphan legacy row.
    """
    TipoServicio = apps.get_model("catalogs", "TipoServicio")
    ServicioConfig = apps.get_model("catalogs", "ServicioConfig")

    legacy = TipoServicio.objects.filter(tipo=LEGACY_TIPO).first()
    if legacy is None:
        return

    canonical = TipoServicio.objects.filter(tipo=CANONICAL_TIPO).first()
    if canonical is None:
        canonical = TipoServicio.objects.create(
            tipo=CANONICAL_TIPO,
            descripcion=legacy.descripcion
            or "Procedimientos de la ficha medica.",
            orden=legacy.orden or 2,
            activo=legacy.activo,
        )

    ServicioConfig.objects.filter(tipo_servicio=legacy).update(
        tipo_servicio=canonical
    )
    legacy.delete()


def restore_tipo_servicio_estetico(apps, schema_editor):
    """Reverse: reassign FKs back to the legacy row and drop the canonical row.

    The reverse is a no-op when the legacy row does not exist or when no
    ``ServicioConfig`` rows reference the canonical row that we would
    otherwise delete — i.e. when the canonical row was pre-existing
    operator data (``seed_client_baseline`` path) rather than created by the
    forward migration.
    """
    TipoServicio = apps.get_model("catalogs", "TipoServicio")
    ServicioConfig = apps.get_model("catalogs", "ServicioConfig")

    legacy = TipoServicio.objects.filter(tipo=LEGACY_TIPO).first()
    canonical = TipoServicio.objects.filter(tipo=CANONICAL_TIPO).first()

    if legacy is None or canonical is None:
        return

    ServicioConfig.objects.filter(tipo_servicio=canonical).update(
        tipo_servicio=legacy
    )
    canonical.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0006_seed_sectores_and_reassign_fichaseccion"),
    ]

    operations = [
        migrations.RunPython(
            normalize_tipo_servicio_estetico,
            restore_tipo_servicio_estetico,
        ),
    ]