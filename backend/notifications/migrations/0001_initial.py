from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalogs", "0004_sucursal_especialistas_pueden_abrir_fichas"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("type", models.CharField(choices=[("ADMIN_PAYMENT_PENDING_CONFIRMATION", "Admin Payment Pending Confirmation"), ("ADMIN_MESSAGE_FROM_GENERAL_ADMIN", "Admin Message From General Admin"), ("ADMIN_MESSAGE_FROM_SPECIALIST", "Admin Message From Specialist"), ("ADMIN_MESSAGE_FROM_ADMIN", "Admin Message From Admin"), ("CLIENT_PAYMENT_CONFIRMED", "Client Payment Confirmed"), ("CLIENT_PAYMENT_REJECTED", "Client Payment Rejected"), ("CLIENT_APPOINTMENT_CANCELLED", "Client Appointment Cancelled"), ("CLIENT_APPOINTMENT_RESCHEDULED", "Client Appointment Rescheduled"), ("SPECIALIST_MESSAGE_FROM_ADMIN", "Specialist Message From Admin")], max_length=80)),
                ("title", models.CharField(max_length=160)),
                ("message", models.CharField(max_length=320)),
                ("action_url", models.CharField(blank=True, max_length=255)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("is_read", models.BooleanField(default=False)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by_type", models.CharField(default="system", max_length=40)),
                ("created_by_id", models.PositiveIntegerField(blank=True, null=True)),
                ("source_event", models.CharField(blank=True, max_length=80)),
                ("source_entity_type", models.CharField(blank=True, max_length=80)),
                ("source_entity_id", models.PositiveIntegerField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(auto_now_add=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("branch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notifications", to="catalogs.sucursal")),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "notifications", "ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="NotificationReadAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("read_at", models.DateTimeField(auto_now_add=True)),
                ("notification", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="read_audits", to="notifications.notification")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notification_read_audits", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "notification_read_audits"},
        ),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["recipient", "-created_at"], name="notif_user_created_idx")),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["recipient", "is_read", "-created_at"], name="notif_user_read_created_idx")),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["created_at"], name="notif_created_idx")),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["branch", "-created_at"], name="notif_branch_created_idx")),
        migrations.RunSQL(
            sql="CREATE INDEX notif_unread_partial_idx ON notifications (recipient_id, created_at DESC) WHERE is_read = false;",
            reverse_sql="DROP INDEX IF EXISTS notif_unread_partial_idx;",
        ),
    ]
