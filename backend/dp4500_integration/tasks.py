"""Celery tasks for dp4500_integration.

Phase 2 of dp4500-host-app-integration-phase2. Single task:
``cascade_revoke_template``. Retries up to 5x with 30s default
delay on transient ``BiometricUnavailable``; treats
``BiometricSuspended`` as non-retryable.
"""
from __future__ import annotations

import logging

from celery import shared_task

from dp4500_integration.client import HTTPClient
from dp4500_integration.exceptions import (
    BiometricSuspended,
    BiometricUnavailable,
)
from dp4500_integration.models import PendingCascade


logger = logging.getLogger(__name__)


def _resolve_key_resolver():
    """Return a callable(sucursal_id) -> raw_token | None.

    Reads DP4500_SERVICE_KEY_SUCURSAL_<id> from os.environ. Mirrors
    ``dp4500_integration.key_resolver.env_key_resolver`` but imported
    lazily so Celery task discovery does not require the client module
    to load at import time.
    """
    import os
    return lambda sucursal_id: os.environ.get(
        f"DP4500_SERVICE_KEY_SUCURSAL_{sucursal_id}",
    )


def _do_cascade(user_external_id: str, sucursal_id: int) -> str:
    """Run one cascade attempt; return the outcome code.

    Returns one of: ``"completed"``, ``"suspended"``, ``"failed"``.
    Raises ``BiometricUnavailable`` (caller catches and retries) or
    ``BiometricSuspended`` (caller treats as terminal).
    """
    from django.conf import settings

    client = HTTPClient(
        base_url=settings.DP4500_BASE_URL,
        timeout_seconds=settings.DP4500_TIMEOUT_SECONDS,
        key_resolver=_resolve_key_resolver(),
    )
    try:
        client.delete_template(
            user_external_id=user_external_id,
            sucursal_id=sucursal_id,
        )
    except BiometricSuspended:
        return PendingCascade.STATUS_SUSPENDED
    except BiometricUnavailable as exc:
        # Transient: caller catches this and calls self.retry(...).
        raise
    finally:
        client.close()
    return PendingCascade.STATUS_COMPLETED


@shared_task(bind=True, max_retries=5, default_retry_delay=30, ignore_result=True)
def cascade_revoke_template(self, user_external_id: str, sucursal_id: int):
    """Issue DELETE /service/templates/<external_id>/ for the given user.

    Outcome classification per design §6.3:
      - 204 / 404 from DP4500     -> status='completed'
      - 503 BIOMETRIC_SUSPENDED   -> status='suspended' (non-retryable)
      - BiometricUnavailable       -> Celery auto-retry (5x, 30s delay)
      - Anything else              -> status='failed' after retries exhausted

    Test settings set ``CELERY_TASK_ALWAYS_EAGER=True`` so this runs
    synchronously during tests; ``self.retry()`` raises a synchronous
    ``Retry`` exception that the test fixture catches.
    """
    pending = PendingCascade.objects.filter(
        user_external_id=user_external_id,
        sucursal_id=sucursal_id,
        status=PendingCascade.STATUS_PENDING,
    ).first()
    if pending is None:
        # Already completed by a previous attempt / reconciliation.
        return

    pending.attempts = (pending.attempts or 0) + 1
    pending.last_attempt_at = __import__("django.utils.timezone", fromlist=["now"]).now()

    try:
        new_status = _do_cascade(user_external_id, sucursal_id)
    except BiometricUnavailable as exc:
        pending.last_error_code = str(exc)[:64]
        pending.save()
        # Retry with the configured backoff. After max_retries the
        # task moves to FAILED via the on_failure hook below.
        raise self.retry(exc=exc)
    except Exception as exc:  # noqa: BLE001
        pending.last_error_code = f"unexpected:{type(exc).__name__}"[:64]
        pending.save()
        raise self.retry(exc=exc)

    pending.status = new_status
    if new_status == PendingCascade.STATUS_COMPLETED:
        pending.completed_at = __import__("django.utils.timezone", fromlist=["now"]).now()
    pending.save()


def _cascade_revoke_template_on_failure(self, exc, task_id, args, kwargs, einfo):
    """Mark the row FAILED when Celery exhausts retries.

    Celery 5.x dropped the ``@on_failure`` decorator; assign the
    hook to the Task class manually after the task is defined.
    """
    user_external_id = kwargs.get("user_external_id") if kwargs else None
    sucursal_id = kwargs.get("sucursal_id") if kwargs else None
    PendingCascade.objects.filter(
        user_external_id=user_external_id,
        sucursal_id=sucursal_id,
        status=PendingCascade.STATUS_PENDING,
    ).update(
        status=PendingCascade.STATUS_FAILED,
        last_error_code=f"celery:{type(exc).__name__}"[:64],
    )


# Wire the on_failure hook onto the underlying Task class.
cascade_revoke_template.on_failure = _cascade_revoke_template_on_failure
