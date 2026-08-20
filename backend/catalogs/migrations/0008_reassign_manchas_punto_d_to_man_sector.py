"""Move the PUNTO_D section of "Tratamiento de manchas" from sector DEP to sector MAN.

Before this migration, the historical ``clean_baseline.seed_form_configuration``
created two PUNTO_D sections under the same DEP sector: one for
"Depilacion definitiva" and one for "Tratamiento de manchas". This was
intentional while the ficha medica rendering prioritized ``sector`` over
``proc_estetico`` and both procedures were meant to share a single ficha
form.

The new contract assigns each procedure to its own sector so a service
that picks an existing sector via the admin UI reuses the canonical
fields for that sector:

* "Depilacion definitiva" -> DEP
* "Tratamiento de manchas" -> MAN
* "Borrado de tatuajes" -> TAT

The PUNTO_D section of "Tratamiento de manchas" therefore moves from
sector=DEP to sector=MAN. The PUNTO_D of "Depilacion definitiva" stays
under DEP. The PUNTO_E of "Borrado de tatuajes" stays under TAT (no
move required, but we re-stamp it for safety).

The data migration is idempotent: it queries by natural key (sector
codigo + FichaSeccion.proc_estetico__proceso) so re-running it on a
DB where the rows are already in the target state is a no-op.
"""

from django.db import migrations


DEPILACION_PROC = "Depilacion definitiva"
MANCHAS_PROC = "Tratamiento de manchas"
TATUAJES_PROC = "Borrado de tatuajes"


def _section_for_procedure(ficha_seccion_model, proceso):
    return ficha_seccion_model.objects.filter(
        proc_estetico__proceso=proceso,
        codigo="PUNTO_D" if proceso != TATUAJES_PROC else "PUNTO_E",
    ).first()


def forwards(apps, schema_editor):
    sector_model = apps.get_model("catalogs", "Sector")
    ficha_seccion_model = apps.get_model("clinical", "FichaSeccion")

    man_sector = sector_model.objects.filter(codigo="MAN").first()
    dep_sector = sector_model.objects.filter(codigo="DEP").first()
    if man_sector is None or dep_sector is None:
        # Sector catalog not seeded yet; nothing to migrate. The
        # seed will create the rows with the correct assignment.
        return

    manchas_section = _section_for_procedure(ficha_seccion_model, MANCHAS_PROC)
    if manchas_section is not None and manchas_section.sector_id == dep_sector.pk:
        manchas_section.sector = man_sector
        manchas_section.save(update_fields=["sector", "updated_at"])

    # Belt-and-suspenders: also re-stamp the depilacion PUNTO_D under
    # DEP and the tatuajes PUNTO_E under TAT in case they drifted
    # from prior seed runs. These are no-ops when the rows are
    # already correct.
    depilacion_section = _section_for_procedure(ficha_seccion_model, DEPILACION_PROC)
    if depilacion_section is not None and depilacion_section.sector_id != dep_sector.pk:
        depilacion_section.sector = dep_sector
        depilacion_section.save(update_fields=["sector", "updated_at"])

    tatuajes_section = _section_for_procedure(ficha_seccion_model, TATUAJES_PROC)
    if tatuajes_section is not None:
        tat_sector = sector_model.objects.filter(codigo="TAT").first()
        if tat_sector is not None and tatuajes_section.sector_id != tat_sector.pk:
            tatuajes_section.sector = tat_sector
            tatuajes_section.save(update_fields=["sector", "updated_at"])


def backwards(apps, schema_editor):
    sector_model = apps.get_model("catalogs", "Sector")
    ficha_seccion_model = apps.get_model("clinical", "FichaSeccion")

    dep_sector = sector_model.objects.filter(codigo="DEP").first()
    if dep_sector is None:
        return
    # Roll back the manchas PUNTO_D to sector DEP (legacy layout).
    manchas_section = _section_for_procedure(ficha_seccion_model, MANCHAS_PROC)
    if manchas_section is not None and manchas_section.sector_id != dep_sector.pk:
        manchas_section.sector = dep_sector
        manchas_section.save(update_fields=["sector", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0007_normalize_tipo_servicio_estetico"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
