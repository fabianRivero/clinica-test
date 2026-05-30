from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0022_rename_pending_biometria_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='citamedica',
            name='estado',
            field=models.CharField(
                choices=[
                    ('PROGRAMADA', 'Programada'),
                    ('REALIZADA_PENDIENTE_VERIFICACION', 'Realizada Pendiente de Verificación'),
                    ('CONFIRMADA', 'Confirmada'),
                    ('CANCELADA', 'Cancelada'),
                    ('NO_ASISTIO', 'No asistio'),
                ],
                default='PROGRAMADA',
                max_length=32,
            ),
        ),
    ]