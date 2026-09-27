"""reconcile_pending_cascades — manual override for the cascade Celery task.

Phase 2 of dp4500-host-app-integration-phase2. When Celery is
unavailable for an extended period, the operator runs this command
to manually iterate over every ``PendingCascade(status='pending')``
row and run the cascade inline.

Idempotent: re-running on rows already processed is a no-op (their
status is not 'pending' anymore).

Behavior:
  - Default mode: processes every pending row synchronously, using
    the same classification logic as the Celery task.
  - ``--dry-run``: prints what would be processed without touching
    anything.
  - ``--limit N``: processes at most N rows (for staged rollouts).
"""
from __future__ import annotations

import sys
from typing import Any

from django.core.management.base import BaseCommand

from dp4500_integration.models import PendingCascade
from dp4500_integration.tasks import _do_cascade


class Command(BaseCommand):
    help = (
        "Manually process every PendingCascade(status='pending') row. "
        "Use when Celery is unavailable; otherwise the Celery worker "
        "picks them up automatically."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run", action="store_true",
            help="List rows that would be processed; do not touch them.",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Process at most N rows (for staged rollouts).",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        qs = PendingCascade.objects.filter(status=PendingCascade.STATUS_PENDING)
        if opts["limit"]:
            qs = qs[:opts["limit"]]

        processed = 0
        failed = 0
        for row in qs:
            if opts["dry_run"]:
                self.stdout.write(
                    f"[dry-run] would reconcile pk={row.pk} "
                    f"user_external_id={row.user_external_id} "
                    f"sucursal_id={row.sucursal_id}"
                )
                processed += 1
                continue

            try:
                new_status = _do_cascade(
                    str(row.user_external_id), row.sucursal_id,
                )
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(
                    f"row {row.pk}: {type(exc).__name__}: {exc}"
                )
                failed += 1
                continue

            row.status = new_status
            if new_status == PendingCascade.STATUS_COMPLETED:
                from django.utils.timezone import now
                row.completed_at = now()
            row.save()
            processed += 1

        if failed:
            self.stderr.write(f"reconcile processed={processed} failed={failed}")
            sys.exit(1)
        self.stdout.write(f"reconcile processed={processed}")
