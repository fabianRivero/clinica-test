from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0019_branchadminauditlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventoconfirmacioncita",
            name="confirmed_at_server",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eventoconfirmacioncita",
            name="conflict_reason",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="eventoconfirmacioncita",
            name="device_id",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="eventoconfirmacioncita",
            name="event_id",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="eventoconfirmacioncita",
            name="origin_mode",
            field=models.CharField(choices=[("ONLINE", "Online"), ("OFFLINE", "Offline")], default="ONLINE", max_length=16),
        ),
        migrations.AddField(
            model_name="eventoconfirmacioncita",
            name="recorded_at_device",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eventoconfirmacioncita",
            name="sync_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pendiente"),
                    ("ACCEPTED", "Aceptado"),
                    ("DUPLICATE", "Duplicado"),
                    ("CONFLICT", "Conflicto"),
                    ("REJECTED", "Rechazado"),
                ],
                default="ACCEPTED",
                max_length=16,
            ),
        ),
    ]
