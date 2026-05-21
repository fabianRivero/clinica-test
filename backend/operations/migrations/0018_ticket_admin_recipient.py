from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_usuario_sucursal"),
        ("operations", "0017_citamedica_verification_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ticket",
            name="especialista",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="tickets", to="staff.especialista"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="destinatario_admin",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="tickets_recibidos", to="accounts.usuario"),
        ),
    ]
