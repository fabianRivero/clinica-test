from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinical", "0003_fichaseccion_sector_alter_fichaseccion_proc_estetico"),
    ]

    operations = [
        migrations.AddField(
            model_name="analisisestetico",
            name="alergias_productos_texto",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
