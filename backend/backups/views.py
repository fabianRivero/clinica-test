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

from config.api_helpers import json_response

from .decorators import require_admin_principal


@require_admin_principal
def admin_backup_trigger(request):
    """Create a fresh dump and stream it back as an attachment.

    Implemented in PR #2 commit 2 (trigger + list).
    """
    return json_response({"detail": "No implementado."}, status=501)


@require_admin_principal
def admin_backup_list(request):
    """Return JSON listing of dumps in ``BACKUPS_DIR``.

    Implemented in PR #2 commit 2 (trigger + list).
    """
    return json_response({"detail": "No implementado."}, status=501)


@require_admin_principal
def admin_backup_download(request, filename: str):
    """Stream the dump file as an attachment.

    Implemented in PR #2 commit 3 (download + delete).
    """
    return json_response({"detail": "No implementado."}, status=501)


@require_admin_principal
def admin_backup_delete(request, filename: str):
    """Remove a dump from ``BACKUPS_DIR``.

    Implemented in PR #2 commit 3 (download + delete).
    """
    return json_response({"detail": "No implementado."}, status=501)