"""Domain models for the ``audit`` app.

Slice 2 ships :class:`AuditLog` to back the fail-closed audit write the
signed-URL endpoint requires (media-signed-url-endpoint spec §"Audit
Log (Fail-Closed)"). The model is deliberately close to the schema in
design §4 + the spec table:

* ``id`` — ``BigAutoField`` primary key (consistent with
  ``DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"``).
* ``user`` — nullable FK to ``accounts.Usuario`` (kept via
  ``SET_NULL`` so deleting a user does not destroy the audit trail).
* ``user_role`` — snapshot of ``Usuario.rol.rol`` at mint time, so the
  audit row survives a user being promoted/demoted between mints.
* ``action`` — coarse-grained ``SIGNED_URL_ISSUED`` vs
  ``SIGNED_URL_DENIED`` enum. The endpoint only writes the
  ``SIGNED_URL_ISSUED`` row (spec §"401 and 403 do not write audit
  rows"), but the model keeps the denied branch so future enforcement
  actions (e.g. explicit ``SUSPENDED_DENIED`` write at the API edge)
  can reuse the same table.
* ``resource_path`` — bucket-relative path the URL was minted for;
  matches the ``path`` query param exactly (after sanitization) so
  ops can ``grep`` from the access log into the audit table.
* ``resource_type`` — dotted ``app_label.Model.field`` string (per
  spec) so a single row answers "which model owns this object".
* ``client_ip`` — respects ``X-Forwarded-For`` via
  :func:`config.api_views._request_ip` (slice 2 wires the endpoint to
  the same helper the existing API uses).
* ``user_agent`` — truncated client UA.
* ``expires_at`` — when the presigned URL itself expires; supports
  "show me everything that was mintable in window X" queries.
* ``created_at`` — ``auto_now_add`` timestamp; db-indexed for the
  spec's ``timestamp`` range queries.
* ``denial_reason`` — short machine-readable reason for the
  ``SIGNED_URL_DENIED`` action (e.g. ``stale_key``, ``expired``);
  empty for ``SIGNED_URL_ISSUED``.

Indexes target the documented query patterns from the spec
(``user_id``, ``resource_path``, ``timestamp``). 90-day retention
(proposal Gate 6, design §4) is left to a future cron; it is not
blocking the endpoint landing.
"""

from __future__ import annotations

from django.db import models


class AuditLog(models.Model):
    """Append-only audit trail for signed-URL mints.

    The endpoint calls :func:`audit.services.write_audit_log` BEFORE
    issuing a presigned URL. If the audit write raises, the endpoint
    returns 503 and the URL is never minted — an unauditable URL
    cannot be defended in a compliance review.
    """

    class Action(models.TextChoices):
        SIGNED_URL_ISSUED = "SIGNED_URL_ISSUED", "Signed URL issued"
        SIGNED_URL_DENIED = "SIGNED_URL_DENIED", "Signed URL denied"

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_audit_logs",
    )
    user_role = models.CharField(max_length=64, blank=True)
    action = models.CharField(max_length=32, choices=Action.choices)
    resource_path = models.CharField(max_length=512)
    resource_type = models.CharField(max_length=128)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    denial_reason = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "audit_log"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "action", "-created_at"]),
            models.Index(fields=["resource_path", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"AuditLog<{self.action} user={self.user_id} path={self.resource_path}>"