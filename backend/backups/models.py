"""Audit model for admin database backups.

Every trigger, download, delete, retention prune and rate-limit
denial MUST write a row here. The model is append-only at the
application layer (no UPDATE/DELETE endpoints) and MUST NOT
store dump contents — only metadata about who did what, when,
from where, and which filename was involved.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class BackupAuditLog(TimeStampedModel):
    """Append-only audit row for admin backup actions."""

    class Action(models.TextChoices):
        TRIGGER_DOWNLOAD = "trigger_download", "Descarga manual"
        DOWNLOAD_SERVER_BACKUP = "download_server_backup", "Descargar respaldo"
        DELETE_SERVER_BACKUP = "delete_server_backup", "Eliminar respaldo"
        RETENTION_PRUNE = "retention_prune", "Retencion"
        RATE_LIMIT_DENIED = "rate_limit_denied", "Limite de velocidad"
        DOWNLOAD_DENIED = "download_denied", "Descarga rechazada"
        DELETE_DENIED = "delete_denied", "Eliminacion rechazada"
        TRIGGER_FAILED = "trigger_failed", "Creacion fallida"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backup_audit_logs",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    filename = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "backup_audit_logs"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["-created_at"], name="backup_audit_created_idx"),
            models.Index(fields=["action", "-created_at"], name="backup_audit_action_idx"),
        ]

    def __str__(self) -> str:
        user_label = getattr(self.user, "username", None) or "system"
        return f"{user_label} {self.action} {self.filename or ''}".strip()