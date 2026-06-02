from django.db import migrations


def migrate_global_qr_to_principal_branch(apps, schema_editor):
    ConfiguracionPagoQR = apps.get_model("billing", "ConfiguracionPagoQR")
    Sucursal = apps.get_model("catalogs", "Sucursal")

    # Find existing QR config records
    existing_configs = ConfiguracionPagoQR.objects.all()
    if not existing_configs.exists():
        return

    # Find principal branch
    principal_branch = Sucursal.objects.filter(es_principal=True).first()
    if not principal_branch:
        # No principal branch exists, leave sucursal=null
        return

    # Assign existing QR config(s) to principal branch
    # Use first() since we want to migrate the most recent global config
    # If there are multiple, assign all to principal branch
    for config in existing_configs:
        config.sucursal = principal_branch
        config.save(update_fields=["sucursal"])


def reverse_migration(apps, schema_editor):
    # Set all QR configs back to null (global state)
    ConfiguracionPagoQR = apps.get_model("billing", "ConfiguracionPagoQR")
    ConfiguracionPagoQR.objects.all().update(sucursal=None)


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0007_add_sucursal_to_configuracion_pago_qr"),
    ]

    operations = [
        migrations.RunPython(
            migrate_global_qr_to_principal_branch,
            reverse_code=reverse_migration,
        ),
    ]