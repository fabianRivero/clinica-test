from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        ADMIN_PAYMENT_PENDING_CONFIRMATION = "ADMIN_PAYMENT_PENDING_CONFIRMATION"
        ADMIN_MESSAGE_FROM_GENERAL_ADMIN = "ADMIN_MESSAGE_FROM_GENERAL_ADMIN"
        ADMIN_MESSAGE_FROM_SPECIALIST = "ADMIN_MESSAGE_FROM_SPECIALIST"
        ADMIN_MESSAGE_FROM_ADMIN = "ADMIN_MESSAGE_FROM_ADMIN"
        CLIENT_PAYMENT_CONFIRMED = "CLIENT_PAYMENT_CONFIRMED"
        CLIENT_PAYMENT_REJECTED = "CLIENT_PAYMENT_REJECTED"
        CLIENT_APPOINTMENT_CANCELLED = "CLIENT_APPOINTMENT_CANCELLED"
        CLIENT_APPOINTMENT_RESCHEDULED = "CLIENT_APPOINTMENT_RESCHEDULED"
        SPECIALIST_MESSAGE_FROM_ADMIN = "SPECIALIST_MESSAGE_FROM_ADMIN"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    branch = models.ForeignKey("catalogs.Sucursal", on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    type = models.CharField(max_length=80, choices=Type.choices)
    title = models.CharField(max_length=160)
    message = models.CharField(max_length=320)
    action_url = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    created_by_type = models.CharField(max_length=40, default="system")
    created_by_id = models.PositiveIntegerField(null=True, blank=True)
    source_event = models.CharField(max_length=80, blank=True)
    source_entity_type = models.CharField(max_length=80, blank=True)
    source_entity_id = models.PositiveIntegerField(null=True, blank=True)
    delivered_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "notifications"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["recipient", "-created_at"], name="notif_user_created_idx"),
            models.Index(fields=["recipient", "is_read", "-created_at"], name="notif_user_read_created_idx"),
            models.Index(fields=["created_at"], name="notif_created_idx"),
            models.Index(fields=["branch", "-created_at"], name="notif_branch_created_idx"),
        ]


class NotificationReadAudit(models.Model):
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="read_audits")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_read_audits")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_read_audits"
