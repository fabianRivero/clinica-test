from django.db import migrations


def rename_pending_biometria_to_verificacion(apps, schema_editor):
    """
    Patch all existing rows that have estado='REALIZADA_PENDIENTE_BIOMETRIA'
    to 'REALIZADA_PENDIENTE_VERIFICACION' before the schema alter runs.
    """
    CitaMedica = apps.get_model('operations', 'CitaMedica')
    CitaMedica.objects.filter(
        estado='REALIZADA_PENDIENTE_BIOMETRIA'
    ).update(estado='REALIZADA_PENDIENTE_VERIFICACION')


def reverse_rename(apps, schema_editor):
    """Reverse: revert rows back to old enum value (for migration rollback)."""
    CitaMedica = apps.get_model('operations', 'CitaMedica')
    CitaMedica.objects.filter(
        estado='REALIZADA_PENDIENTE_VERIFICACION'
    ).update(estado='REALIZADA_PENDIENTE_BIOMETRIA')


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0021_remove_fichacampo_grupo_opciones_and_more'),
    ]

    operations = [
        migrations.RunPython(
            rename_pending_biometria_to_verificacion,
            reverse_code=reverse_rename,
        ),
    ]
