"""HTTP views for the backups domain.

Four principal-only endpoints:

* ``POST /api/admin/backups/trigger/`` — create a fresh dump and stream it
* ``GET  /api/admin/backups/``          — list existing server-side dumps
* ``GET  /api/admin/backups/<file>/download/`` — stream a dump as attachment
* ``DELETE /api/admin/backups/<file>/`` — remove a dump

All views are gated by :func:`backups.decorators.require_admin_principal`
and stream responses use :class:`django.http.FileResponse`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from config.api_helpers import json_response

from . import services
from .decorators import check_rate_limit, require_admin_principal
from .models import BackupAuditLog


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _audit(*, request, action: str, filename: str = "", metadata: dict | None = None):
    """Write an audit row, swallowing errors so views never crash on audit."""
    try:
        user = (
            request.user
            if getattr(request, "user", None) and request.user.is_authenticated
            else None
        )
        services.log_backup_audit(
            action=action,
            filename=filename[:255],
            request=request,
            user=user,
            metadata=metadata,
        )
    except Exception:  # pragma: no cover - audit must never crash
        pass


def _resolve_target(filename: str) -> Path | None:
    """Return the safe ``Path`` for *filename* or ``None`` if it fails."""
    try:
        return services._safe_path(Path(settings.BACKUPS_DIR), filename)
    except (ValueError, TypeError):
        return None


def _serialize_entry(path: Path) -> dict[str, Any]:
    """Build the JSON shape returned by the list endpoint."""
    try:
        stat = path.stat()
    except OSError:
        stat = None
    if stat is None:
        return {
            "id": path.name,
            "name": path.name,
            "size": 0,
            "modified_at": "",
            "is_weekly": path.name.endswith(".weekly.dump"),
        }
    return {
        "id": path.name,
        "name": path.name,
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "is_weekly": path.name.endswith(".weekly.dump"),
    }


# ---------------------------------------------------------------------------
# POST /api/admin/backups/trigger/
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
@require_admin_principal
def admin_backup_trigger(request):
    """Create a fresh dump and stream it back as an attachment."""
    allowed, denial = check_rate_limit(
        "trigger",
        request.user.pk,
        settings.BACKUP_RATE_LIMIT_TRIGGER_SECONDS,
    )
    if not allowed:
        _audit(
            request=request,
            action=BackupAuditLog.Action.RATE_LIMIT_DENIED,
            metadata={"scope": "trigger"},
        )
        return denial

    try:
        target = services.BackupService().create_backup(
            actor=f"user:{request.user.pk}",
            request=request,
            user=request.user,
        )
    except services.BackupAlreadyRunningError:
        _audit(
            request=request,
            action=BackupAuditLog.Action.RATE_LIMIT_DENIED,
            metadata={"scope": "trigger", "reason": "backup_busy"},
        )
        return json_response(
            {"detail": "Ya hay un respaldo en curso."}, status=409
        )
    except services.BackupServiceError:
        _audit(
            request=request,
            action=BackupAuditLog.Action.TRIGGER_FAILED,
            metadata={"reason": "service_error"},
        )
        return json_response(
            {"detail": "No se pudo generar el respaldo."}, status=500
        )

    response = FileResponse(
        open(target, "rb"),
        as_attachment=True,
        filename=target.name,
        content_type="application/octet-stream",
    )
    return response


# ---------------------------------------------------------------------------
# GET /api/admin/backups/
# ---------------------------------------------------------------------------


@require_GET
@require_admin_principal
def admin_backup_list(request):
    """Return JSON listing of dumps in ``BACKUPS_DIR``."""
    backups_dir = Path(settings.BACKUPS_DIR)
    if not backups_dir.exists():
        return json_response({"results": []})

    entries: list[dict[str, Any]] = []
    for p in backups_dir.glob("clinica_*.dump"):
        entries.append(_serialize_entry(p))

    entries.sort(key=lambda e: e["modified_at"], reverse=True)
    return json_response({"results": entries})


# ---------------------------------------------------------------------------
# GET /api/admin/backups/<str:filename>/download/
# ---------------------------------------------------------------------------


@require_GET
@require_admin_principal
def admin_backup_download(request, filename: str):
    """Stream the dump file as an attachment."""
    allowed, denial = check_rate_limit(
        "download",
        request.user.pk,
        settings.BACKUP_RATE_LIMIT_DOWNLOAD_SECONDS,
    )
    if not allowed:
        return denial

    if not services.validate_filename(filename):
        _audit(
            request=request,
            action=BackupAuditLog.Action.DOWNLOAD_DENIED,
            filename=filename[:255],
            metadata={"reason": "invalid_filename"},
        )
        return json_response({"detail": "No encontrado."}, status=404)

    target = _resolve_target(filename)
    if target is None or not target.exists() or not target.is_file():
        _audit(
            request=request,
            action=BackupAuditLog.Action.DOWNLOAD_DENIED,
            filename=filename[:255],
            metadata={"reason": "not_found_or_escape"},
        )
        return json_response({"detail": "No encontrado."}, status=404)

    _audit(
        request=request,
        action=BackupAuditLog.Action.DOWNLOAD_SERVER_BACKUP,
        filename=filename,
        metadata={"size_bytes": target.stat().st_size},
    )
    response = FileResponse(
        open(target, "rb"),
        as_attachment=True,
        filename=target.name,
        content_type="application/octet-stream",
    )
    return response


# ---------------------------------------------------------------------------
# DELETE /api/admin/backups/<str:filename>/
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["DELETE"])
@require_admin_principal
def admin_backup_delete(request, filename: str):
    """Remove a dump from ``BACKUPS_DIR``."""
    allowed, denial = check_rate_limit(
        "delete",
        request.user.pk,
        settings.BACKUP_RATE_LIMIT_DELETE_SECONDS,
    )
    if not allowed:
        _audit(
            request=request,
            action=BackupAuditLog.Action.RATE_LIMIT_DENIED,
            filename=filename[:255],
            metadata={"scope": "delete"},
        )
        return denial

    if not services.validate_filename(filename):
        _audit(
            request=request,
            action=BackupAuditLog.Action.DELETE_DENIED,
            filename=filename[:255],
            metadata={"reason": "invalid_filename"},
        )
        return json_response({"detail": "No encontrado."}, status=404)

    target = _resolve_target(filename)
    if target is None or not target.exists() or not target.is_file():
        _audit(
            request=request,
            action=BackupAuditLog.Action.DELETE_DENIED,
            filename=filename[:255],
            metadata={"reason": "not_found_or_escape"},
        )
        return json_response({"detail": "No encontrado."}, status=404)

    try:
        target.unlink()
    except OSError:
        return json_response(
            {"detail": "No se pudo eliminar el respaldo."}, status=500
        )

    _audit(
        request=request,
        action=BackupAuditLog.Action.DELETE_SERVER_BACKUP,
        filename=filename,
    )
    return HttpResponse(status=204)