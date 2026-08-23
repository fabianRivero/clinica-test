import django.db.models.deletion
from django.db import migrations, models


def _get_principal_branch_id(apps, schema_editor):
    Sucursal = apps.get_model("catalogs", "Sucursal")
    principal = (
        Sucursal.objects.filter(es_principal=True, activa=True)
        .order_by("id")
        .first()
    )
    return principal.id if principal else None


def _backfill_sucursal_origen(apps, schema_editor):
    """Copy values from the old sucursal_registro column into the new
    sucursal_origen column, then fill any remaining NULLs with the
    principal branch so no Cliente row is left without an origin.

    Until this data migration runs, both columns coexist; we update
    the new one (nullable) freely. The operations after this one
    remove the old column. The new column stays nullable because the
    field uses on_delete=SET_NULL: deleting a Sucursal would
    otherwise leave a Cliente pointing to a non-existent row. The
    application layer enforces that a new Cliente always has an
    origin branch (admin form / serializer validation).
    """
    Cliente = apps.get_model("customers", "Cliente")
    principal_id = _get_principal_branch_id(apps, schema_editor)

    Cliente.objects.filter(sucursal_registro__isnull=False).update(
        sucursal_origen=models.F("sucursal_registro")
    )

    if principal_id is not None:
        Cliente.objects.filter(sucursal_origen__isnull=True).update(
            sucursal_origen_id=principal_id
        )


def _noop_reverse(apps, schema_editor):
    pass


_SUCURSAL_ORIGEN_FIELD = models.ForeignKey(
    to="catalogs.sucursal",
    on_delete=django.db.models.deletion.SET_NULL,
    related_name="clientes_origen",
    null=True,
    blank=False,
    help_text="Sucursal donde el cliente fue dado de alta originalmente. No se modifica al migrar al cliente entre sucursales; el branch operativo actual vive en Usuario.sucursal_id.",
)


class Migration(migrations.Migration):
    """Rename Cliente.sucursal_registro -> Cliente.sucursal_origen.

    SQLite cannot rename a column with data preservation, so we go
    through AddField + data copy + RemoveField. Django emits the same
    SQL it would emit for a RenameField on backends that support it.

    The new field keeps null=True at the DB level (so deleting the
    origin Sucursal doesn't crash with an integrity error) but
    blank=False at the form/serializer level so application code
    can rely on it being non-null for any newly created Cliente.
    """

    dependencies = [
        ("catalogs", "0009_assign_sector_to_baseline_servicios"),
        ("customers", "0012_huellabiometricacliente_prospecto"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="sucursal_origen",
            field=_SUCURSAL_ORIGEN_FIELD,
        ),
        migrations.RunPython(_backfill_sucursal_origen, _noop_reverse),
        migrations.RemoveField(
            model_name="cliente",
            name="sucursal_registro",
        ),
    ]