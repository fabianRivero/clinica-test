from django.db import migrations, models


def split_name_fields(apps, schema_editor):
    Prospecto = apps.get_model('customers', 'Prospecto')
    for prospecto in Prospecto.objects.all().iterator():
        nombres = (getattr(prospecto, 'nombres', '') or '').strip().split()
        apellidos = (getattr(prospecto, 'apellidos', '') or '').strip().split()
        prospecto.primer_nombre = nombres[0] if nombres else ''
        prospecto.segundo_nombre = ' '.join(nombres[1:]) if len(nombres) > 1 else ''
        prospecto.apellido_paterno = apellidos[0] if apellidos else ''
        prospecto.apellido_materno = ' '.join(apellidos[1:]) if len(apellidos) > 1 else ''
        prospecto.save(update_fields=['primer_nombre', 'segundo_nombre', 'apellido_paterno', 'apellido_materno'])


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0007_prospectoconversionborrador_documento_pdf_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='prospecto',
            name='apellido_materno',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='prospecto',
            name='apellido_paterno',
            field=models.CharField(default='', max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='prospecto',
            name='primer_nombre',
            field=models.CharField(default='', max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='prospecto',
            name='segundo_nombre',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.RunPython(split_name_fields, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='prospecto',
            name='apellidos',
        ),
        migrations.RemoveField(
            model_name='prospecto',
            name='nombres',
        ),
    ]
