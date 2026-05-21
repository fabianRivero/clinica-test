from django.db import migrations, models


def backfill_verification_fields(apps, schema_editor):
    CitaMedica = apps.get_model("operations", "CitaMedica")

    for cita in CitaMedica.objects.all().iterator():
        if cita.estado == "CONFIRMADA":
            cita.estado_verificacion = "VERIFICADA"
        elif cita.estado == "REALIZADA_PENDIENTE_BIOMETRIA":
            cita.estado_verificacion = "PENDIENTE"
        else:
            cita.estado_verificacion = "NO_REQUERIDA"

        if cita.metodo_confirmacion == "BIOMETRICO":
            cita.metodo_verificacion = "BIOMETRIA"
        elif cita.metodo_confirmacion == "TABLET":
            cita.metodo_verificacion = "QR"
        elif cita.metodo_confirmacion == "MANUAL":
            cita.metodo_verificacion = "MANUAL"
        else:
            cita.metodo_verificacion = ""

        cita.save(update_fields=["estado_verificacion", "metodo_verificacion"])


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0016_tabletkiosko"),
    ]

    operations = [
        migrations.AddField(
            model_name="citamedica",
            name="estado_verificacion",
            field=models.CharField(
                choices=[
                    ("PENDIENTE", "Pendiente"),
                    ("VERIFICADA", "Verificada"),
                    ("NO_REQUERIDA", "No requerida"),
                ],
                default="NO_REQUERIDA",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="citamedica",
            name="metodo_verificacion",
            field=models.CharField(
                blank=True,
                choices=[
                    ("BIOMETRIA", "Biometria"),
                    ("QR", "QR"),
                    ("MANUAL", "Manual"),
                    ("OTRO", "Otro"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.RunPython(backfill_verification_fields, migrations.RunPython.noop),
    ]

