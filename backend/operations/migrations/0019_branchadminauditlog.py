from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("catalogs", "0001_initial"),
        ("operations", "0018_ticket_admin_recipient"),
    ]

    operations = [
        migrations.CreateModel(
            name="BranchAdminAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("action", models.CharField(choices=[("CHANGE_ADMIN", "Cambio administrador"), ("CREATE_BRANCH_WIZARD", "Crear sucursal wizard"), ("TOGGLE_BRANCH", "Cambiar estado sucursal"), ("TOGGLE_BRANCH_ADMIN", "Cambiar estado admin sucursal")], max_length=40)),
                ("detail", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="branch_admin_audit_logs", to="accounts.usuario")),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="admin_audit_logs", to="catalogs.sucursal")),
            ],
            options={"db_table": "branch_admin_audit_logs", "ordering": ("-created_at",)},
        ),
    ]
