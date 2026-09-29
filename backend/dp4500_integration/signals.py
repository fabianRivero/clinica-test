"""post_delete signal handler for the dp4500_integration cascade.

Phase 2 of dp4500-host-app-integration-phase2. When a ``Usuario`` is
deleted, synchronously record a ``PendingCascade`` row (so retries
survive worker crashes that lose the Celery queue) and asynchronously
enqueue the ``cascade_revoke_template`` task.

Both operations are best-effort. If either raises, the local User
delete still commits (the operator's intent is honored regardless of
DP4500's reachability). Recovery is the
``reconcile_pending_cascades`` management command.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from accounts.models import Usuario
from dp4500_integration.models import PendingCascade
from dp4500_integration.tasks import cascade_revoke_template


logger = logging.getLogger(__name__)


@receiver(post_delete, sender=Usuario)
def cascade_revoke_on_user_delete(sender, instance, **kwargs):
    """Synchronously record PendingCascade; asynchronously enqueue task."""
    if not instance.biometric_external_id:
        return

    user_external_id = str(instance.biometric_external_id)
    sucursal_id = instance.sucursal_id

    # Sync insert: source of truth for retries. If this fails, the
    # management command can recover. The Celery enqueue is then
    # best-effort.
    try:
        with transaction.atomic():
            pending = PendingCascade.objects.create(
                user_external_id=instance.biometric_external_id,
                sucursal_id=sucursal_id or 0,
                status=PendingCascade.STATUS_PENDING,
            )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to record PendingCascade for user_external_id=%s "
            "after User.delete(): %s. Cascade will not run; run "
            "reconcile_pending_cascades manually.",
            user_external_id, exc,
        )
        return

    try:
        cascade_revoke_template.delay(user_external_id, sucursal_id or 0)
    except Exception as exc:  # noqa: BLE001
        # Common in tests (no broker / CELERY_TASK_ALWAYS_EAGER=False in
        # some environments) — log and rely on the PendingCascade row.
        logger.error(
            "Failed to enqueue cascade_revoke_template for %s: %s. "
            "PendingCascade row exists; management command will retry.",
            user_external_id, exc,
        )
