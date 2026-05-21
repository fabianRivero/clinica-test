from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0005_alter_pagorealizado_estado_verificacion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cuotaplanpago",
            name="estado",
            field=models.CharField(
                choices=[
                    ("PAGADO", "Pagado"),
                    ("PENDIENTE", "Pendiente"),
                    ("VENCIDA", "Vencida"),
                    ("NO_PAGADA", "No pagada"),
                ],
                default="PENDIENTE",
                max_length=20,
            ),
        ),
    ]
