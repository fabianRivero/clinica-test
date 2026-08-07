"""App config for the backups domain.

Holds the ``BackupAuditLog`` model, the ``BackupService`` (dump,
retention, lock, audit) and the ``create_backup`` management
command. The HTTP layer is intentionally not exposed in this app
yet — endpoints arrive in a later PR.
"""

from django.apps import AppConfig


class BackupsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "backups"
    verbose_name = "Respaldos de base de datos"