"""Service layer for the ``audit`` app.

The signed-URL endpoint MUST write an audit row BEFORE issuing the
presigned URL (media-signed-url-endpoint spec §"Audit Log
(Fail-Closed)"). This module exposes:

* :class:`AuditWriteFailure` — translated DB error so callers can
  catch a single exception regardless of which database driver is in
  use (Postgres ``IntegrityError`` vs SQLite ``OperationalError`` vs
  Postgres connection-dropped ``OperationalError``).
* :func:`write_audit_log` — thin wrapper around
  ``AuditLog.objects.create`` that swallows the underlying driver
  exception and re-raises :class:`AuditWriteFailure`. The endpoint
  catches ``AuditWriteFailure`` and returns 503; no URL is minted.

The function signature accepts keyword-only arguments matching the
AuditLog fields. ``user`` is the ``accounts.Usuario`` instance (or
``None`` for system actions); ``expires_at`` is a tz-aware
``datetime`` matching the presigned URL expiry.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from django.db import DatabaseError

from .models import AuditLog


logger = logging.getLogger(__name__)


class AuditWriteFailure(Exception):
    """Raised when the audit log row cannot be persisted.

    The signed-URL endpoint catches this exception and returns HTTP
    503 (no URL is minted). We deliberately surface a domain-level
    exception rather than letting the raw driver error escape — the
    view code should not have to know which database backend is
    configured.
    """


def write_audit_log(
    *,
    user: Optional[object],
    user_role: str,
    action: str,
    resource_path: str,
    resource_type: str,
    client_ip: Optional[str],
    user_agent: str,
    expires_at: Optional[datetime],
    denial_reason: str = "",
) -> AuditLog:
    """Persist one audit row, translating DB errors into
    :class:`AuditWriteFailure`.

    The endpoint calls this function BEFORE minting a presigned URL.
    Any DB-side failure (connection drop, integrity error, disk full)
    surfaces here as :class:`AuditWriteFailure` so the view layer can
    return 503 and refuse to mint the URL.
    """
    user_id = getattr(user, "id", None) if user is not None else None
    try:
        return AuditLog.objects.create(
            user=user if user_id is not None else None,
            user_role=user_role or "",
            action=action,
            resource_path=resource_path,
            resource_type=resource_type,
            client_ip=client_ip or None,
            user_agent=user_agent or "",
            expires_at=expires_at,
            denial_reason=denial_reason or "",
        )
    except DatabaseError as exc:
        logger.error(
            "audit_log_write_failed: action=%s user_id=%s resource=%s err=%s",
            action,
            user_id,
            resource_path,
            exc,
        )
        raise AuditWriteFailure(str(exc)) from exc