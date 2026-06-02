import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0006_alter_cuotaplanpago_estado"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracionpagoqr",
            name="sucursal",
            field=models.ForeignKey(
                "catalogs.Sucursal",
                on_delete=models.SET_NULL,
                null=True,
                blank=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="configuracionpagoqr",
            constraint=models.UniqueConstraint(
                fields=["sucursal"],
                name="uniq_config_qr_sucursal",
            ),
        ),
    ]