"""Management command: create a server-side database backup.

Cron / systemd-timer entry point. The command intentionally has no
positional arguments: the operator controls ``BACKUPS_DIR`` (and the
optional ``--backups-dir`` override for ad-hoc runs) via settings.
``--actor-label`` lets operators distinguish custom invocations
from the default ``system:cron`` audit label.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from backups.models import BackupAuditLog
from backups.services import (
    BackupAlreadyRunningError,
    BackupService,
    BackupServiceError,
    log_backup_audit,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate a database backup and apply retention."

    def add_arguments(self, parser):
        parser.add_argument(
            "--backups-dir",
            default=None,
            help="Override BACKUPS_DIR for this invocation (operator convenience).",
        )
        parser.add_argument(
            "--actor-label",
            default="system:cron",
            help="Audit-row actor label (defaults to 'system:cron').",
        )

    def handle(self, *args, **options):
        backups_dir = options.get("backups_dir")
        actor = options.get("actor_label") or "system:cron"

        service_kwargs = {}
        if backups_dir:
            service_kwargs["backups_dir"] = Path(backups_dir)

        service = BackupService(**service_kwargs)
        try:
            target = service.create_backup(actor=actor)
        except BackupAlreadyRunningError as exc:
            log_backup_audit(
                action=BackupAuditLog.Action.TRIGGER_FAILED,
                filename="",
                metadata={"actor": actor, "reason": "already_running"},
            )
            self.stderr.write(self.style.ERROR(str(exc)))
            raise CommandError("Backup already in progress.") from exc
        except BackupServiceError as exc:
            log_backup_audit(
                action=BackupAuditLog.Action.TRIGGER_FAILED,
                filename="",
                metadata={"actor": actor, "reason": "service_error"},
            )
            self.stderr.write(self.style.ERROR(f"Backup failed: {exc}"))
            raise CommandError("Backup failed.") from exc
        except Exception as exc:  # pragma: no cover - defensive
            log_backup_audit(
                action=BackupAuditLog.Action.TRIGGER_FAILED,
                filename="",
                metadata={"actor": actor, "reason": "unexpected"},
            )
            logger.exception("Unexpected error during backup")
            self.stderr.write(self.style.ERROR(f"Backup failed: {exc}"))
            raise CommandError("Backup failed.") from exc

        self.stdout.write(self.style.SUCCESS(str(target)))