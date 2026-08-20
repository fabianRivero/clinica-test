"""Assign canonical sector FKs to the three baseline ServicioConfig rows.

Before this migration, the historical ``clean_baseline.seed_aesthetic_catalog``
created the three treatment ServicioConfig rows (Depilacion definitiva,
Tratamiento de manchas, Borrado de tatuajes) with ``sector=NULL``. The
ficha medica was resolved via ``proc_estetico`` only.

The new contract assigns each procedure to its own sector so a service
that picks an existing sector via the admin UI reuses the canonical
fields for that sector:

* "Depilacion definitiva" -> DEP
* "Tratamiento de manchas" -> MAN
* "Borrado de tatuajes" -> TAT

The Cita de consulta ServicioConfig keeps ``sector=NULL`` and
``proc_estetico=NULL`` (no ficha).
"""

from django.db import migrations


PROC_TO_SECTOR = {
    "Depilacion definitiva": "DEP",
    "Tratamiento de manchas": "MAN",
    "Borrado de tatuajes": "TAT",
}


def forwards(apps, schema_editor):
    servicio_model = apps.get_model("catalogs", "ServicioConfig")
    sector_model = apps.get_model("catalogs", "Sector")

    sectors_by_codigo = {
        s.codigo: s for s in sector_model.objects.filter(
            codigo__in=PROC_TO_SECTOR.values()
        )
    }
    for proceso, sector_codigo in PROC_TO_SECTOR.items():
        sector = sectors_by_codigo.get(sector_codigo)
        if sector is None:
            # Sectors not seeded yet; the seed will create the rows
            # with the correct assignment.
            continue
        # Only update rows that target the canonical procedure
        # (``proc_estetico__proceso``) and currently have a
        # different (or null) sector. Re-stamping on every row
        # would clobber services the operator added later that
        # intentionally point to a different procedure + sector.
        servicio_model.objects.filter(
            proc_estetico__proceso=proceso,
        ).exclude(sector=sector).update(sector=sector)


def backwards(apps, schema_editor):
    servicio_model = apps.get_model("catalogs", "ServicioConfig")
    servicio_model.objects.filter(
        proc_estetico__proceso__in=PROC_TO_SECTOR.keys(),
    ).exclude(proc_estetico__isnull=True).update(sector=None)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0008_reassign_manchas_punto_d_to_man_sector"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
