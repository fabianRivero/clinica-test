"""``audit_log_retention`` management command (slice 4).

Deletes ``AuditLog`` rows older than ``--days`` (default 90). Wired to a
cron job (see ``docs/runbooks/aws-cloud-storage-setup.md`` ops
follow-ups) to satisfy proposal Gate 6 + design §4 retention note.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from audit.models import AuditLog

logger = __import__("logging").getLogger(__name__)


class Command(BaseCommand):
    help = "Delete AuditLog rows older than --days (default 90)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90)

    def handle(self, *args, **options):
        days = options["days"]
        cutoff = timezone.now() - timedelta(days=days)
        with transaction.atomic():
            qs = AuditLog.objects.filter(created_at__lt=cutoff)
            count = qs.count()
            qs.delete()
        logger.info("audit_log_retention: deleted=%d cutoff=%s days=%d", count, cutoff.isoformat(), days)
        self.stdout.write(f"audit_log_retention: deleted={count} days={days}")
