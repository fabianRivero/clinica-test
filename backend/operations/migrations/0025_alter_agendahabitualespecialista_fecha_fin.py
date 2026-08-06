# Generated for: permitir fecha_fin NULL en agendas habituales (bugfix)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0024_alter_citaclientelibre_estado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agendahabitualespecialista',
            name='fecha_fin',
            field=models.DateField(blank=True, null=True),
        ),
    ]