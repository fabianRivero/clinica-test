"""Audit app (cloud-storage-migration, slice 2 of 4).

Persists an append-only log of every successful signed-URL mint so
HIPAA compliance reviews can answer "who was issued, from which IP, for
which resource, by which rule" without relying on bucket access logs
alone. The audit write is fail-closed: if the row cannot be persisted,
the signed-URL mint is refused (HTTP 503) — an unauditable URL cannot
be defended in a compliance review (media-signed-url-endpoint spec
§"Audit Log (Fail-Closed)").

The app is intentionally minimal for slice 2:

* :class:`audit.models.AuditLog` — the table the endpoint writes to.
* :func:`audit.services.write_audit_log` — the writer the endpoint
  calls. Wraps ``AuditLog.objects.create`` and translates any DB
  exception into :class:`audit.services.AuditWriteFailure`.

Slice 3+ can add retention enforcement (90-day purge, design §4 +
proposal Gate 6), structured-log emission alongside the DB row, and
admin integration. None of those block the endpoint landing.
"""