from django.db import migrations


def backfill_confirmation_method(apps, schema_editor):
    CitaMedica = apps.get_model("operations", "CitaMedica")

    CitaMedica.objects.filter(
        estado="CONFIRMADA",
        verif_biometria=True,
        metodo_confirmacion="",
    ).update(metodo_confirmacion="BIOMETRICO")

    CitaMedica.objects.filter(
        estado="CONFIRMADA",
        verif_biometria=False,
        metodo_confirmacion="",
    ).update(metodo_confirmacion="TABLET")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0013_citamedica_metodo_confirmacion_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_confirmation_method, noop_reverse),
    ]
