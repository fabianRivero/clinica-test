"""Seed the three baseline Sector records and reassign existing FichaSeccion
records to use the new Sector FK.

Mapping (per design ADR-3 and proposal A3):
- DEP (Depilacion) receives sections whose ProcEstetico is either
  "Depilacion definitiva" or "Tratamiento de manchas" (PUNTO_D).
- TAT (Tatuajes) receives sections whose ProcEstetico is "Borrado de tatuajes"
  (PUNTO_E).
- MAN (Manchas) is seeded for completeness; no existing section maps to it.

The migration is idempotent so it can run safely on databases that already
have sectors seeded by `seed_pdf_baseline` or a previous run.
"""

from django.db import migrations


DEP_PROC_NAMES = ("Depilacion definitiva", "Tratamiento de manchas")
TAT_PROC_NAME = "Borrado de tatuajes"


def _get_or_create_sector(sector_model, codigo, nombre, descripcion, orden):
    sector = sector_model.objects.filter(codigo__iexact=codigo).first()
    if sector is None:
        sector = sector_model.objects.create(
            codigo=codigo,
            nombre=nombre,
            descripcion=descripcion,
            activo=True,
            orden=orden,
        )
    else:
        updates = []
        if sector.nombre != nombre:
            sector.nombre = nombre
            updates.append("nombre")
        if not sector.descripcion:
            sector.descripcion = descripcion
            updates.append("descripcion")
        if sector.orden != orden:
            sector.orden = orden
            updates.append("orden")
        if updates:
            sector.save(update_fields=updates)
    return sector


def seed_sectores_and_reassign(apps, schema_editor):
    Sector = apps.get_model("catalogs", "Sector")
    ProcEstetico = apps.get_model("catalogs", "ProcEstetico")
    FichaSeccion = apps.get_model("clinical", "FichaSeccion")

    dep_sector = _get_or_create_sector(
        Sector,
        codigo="DEP",
        nombre="Depilacion",
        descripcion="Secciones de ficha clinica para servicios de depilacion y manchas.",
        orden=1,
    )
    man_sector = _get_or_create_sector(
        Sector,
        codigo="MAN",
        nombre="Manchas",
        descripcion="Secciones de ficha clinica para servicios especializados en manchas.",
        orden=2,
    )
    tat_sector = _get_or_create_sector(
        Sector,
        codigo="TAT",
        nombre="Tatuajes",
        descripcion="Secciones de ficha clinica para servicios de borrado de tatuajes.",
        orden=3,
    )

    dep_procs = list(ProcEstetico.objects.filter(proceso__in=DEP_PROC_NAMES))
    tat_procs = list(ProcEstetico.objects.filter(proceso=TAT_PROC_NAME))

    FichaSeccion.objects.filter(
        proc_estetico__in=dep_procs, sector__isnull=True
    ).update(sector=dep_sector)
    FichaSeccion.objects.filter(
        proc_estetico__in=tat_procs, sector__isnull=True
    ).update(sector=tat_sector)

    # Silence "unused variable" for the seeded-but-unassigned sector.
    _ = man_sector


def remove_sector_seed_and_unassign(apps, schema_editor):
    """Reverse migration: clear sector FKs and delete seeded sector records.

    The reverse operation is only safe on databases where the three seed
    sectors were not modified by users. We restrict deletion to the exact
    codigos created by the forward path.
    """
    Sector = apps.get_model("catalogs", "Sector")
    FichaSeccion = apps.get_model("clinical", "FichaSeccion")

    seed_codigos = ["DEP", "MAN", "TAT"]
    FichaSeccion.objects.filter(sector__codigo__in=seed_codigos).update(sector=None)
    Sector.objects.filter(codigo__in=seed_codigos).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0005_sector_servicioconfig_sector"),
        ("clinical", "0003_fichaseccion_sector_alter_fichaseccion_proc_estetico"),
    ]

    operations = [
        migrations.RunPython(seed_sectores_and_reassign, remove_sector_seed_and_unassign),
    ]
