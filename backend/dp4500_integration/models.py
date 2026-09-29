"""Models for the dp4500_integration app.

Phase 2 of dp4500-host-app-integration-phase2. Two models:

  - ``PendingCascade``: per-user delete-cascade queue. Synchronously
    inserted by the post_delete signal on Usuario. The Celery task
    ``cascade_revoke_template`` reads the row, calls DP4500's
    DELETE /service/templates/<external_id>/, classifies the outcome
    (204/404 -> completed, 503 BIOMETRIC_SUSPENDED -> suspended,
    transient -> retry), and updates the row.
  - ``BiometricEnrollmentRecord``: per-wizard-step-4 local audit
    trail. Captured when the operator advances the wizard; carries
    the enrollment_strategy (Phase 2: always "pending").

No cross-project FKs. ``sucursal_id`` is a plain IntegerField per
design §6.1 — branch renames must NOT cascade-delete pending rows.
"""
from __future__ import annotations

from django.db import models


class PendingCascade(models.Model):
    """Per-user delete-cascade queue entry.

    Synchronously inserted by the ``post_delete`` signal on Usuario.
    Updated by the Celery ``cascade_revoke_template`` task.
    """

    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_SUSPENDED = "suspended"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending cascade"),
        (STATUS_COMPLETED, "DP4500 returned 204 or 404"),
        (STATUS_SUSPENDED, "DP4500 returned 503 BIOMETRIC_SUSPENDED; not retryable"),
        (STATUS_FAILED, "Exhausted retries"),
    )

    user_external_id = models.UUIDField()
    # Intentionally NOT FK to Sucursal: branch renames must not cascade-
    # delete pending rows. See design §1.4 invariant 3.
    sucursal_id = models.IntegerField()

    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error_code = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dp4500_integration_pending_cascade"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["user_external_id"]),
        ]


class BiometricEnrollmentRecord(models.Model):
    """Per-wizard-step-4 local audit trail.

    Captured when the operator advances the prospect-convert wizard to
    step 5. Phase 2 always sets ``enrollment_strategy='pending'``; Phase 4
    adds the ``'websdk'`` and ``'electron'`` values when the real capture
    client is wired in.
    """

    STRATEGY_PENDING = "pending"
    STRATEGY_MOCK = "mock"
    STRATEGY_WEBSDK = "websdk"
    STRATEGY_ELECTRON = "electron"
    STRATEGY_CHOICES = (
        (STRATEGY_PENDING, "Phase 2 stub: capture not yet wired"),
        (STRATEGY_MOCK, "Phase 2 dev: dev-only mock capture"),
        (STRATEGY_WEBSDK, "Phase 4: browser Web SDK"),
        (STRATEGY_ELECTRON, "Phase 4: Electron child process"),
    )

    user = models.ForeignKey(
        "accounts.Usuario", on_delete=models.CASCADE,
        related_name="biometric_enrollment_records",
    )
    user_external_id = models.UUIDField()
    wizard_id = models.CharField(max_length=64)
    enrollment_strategy = models.CharField(
        max_length=16, choices=STRATEGY_CHOICES, default=STRATEGY_PENDING,
    )
    advanced_at = models.DateTimeField(null=True, blank=True)
    advanced_by = models.ForeignKey(
        "accounts.Usuario",
        null=True, blank=True, on_delete=models.SET_NULL,
        related_name="enrollment_advances",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dp4500_integration_enrollment_record"
        indexes = [
            models.Index(fields=["user", "wizard_id"]),
            models.Index(fields=["enrollment_strategy", "advanced_at"]),
        ]


__all__ = ["PendingCascade", "BiometricEnrollmentRecord"]
