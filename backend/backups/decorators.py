"""Decorators and helpers used by the backups HTTP layer.

Kept in their own module so PR #2 (views + tests) does not depend on
``config.api_views`` — every backup view imports its authz / rate
limit helpers from here.
"""

from __future__ import annotations

from functools import wraps
from typing import Callable, Optional, Tuple

from django.core.cache import cache
from django.http import HttpResponse

from config.api_helpers import json_response


def get_client_ip(request) -> Optional[str]:
    """Best-effort client IP extraction (honours ``X-Forwarded-For``)."""
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.META.get("REMOTE_ADDR") or None


def require_admin_principal(view_func: Callable) -> Callable:
    """Gate a view behind the principal-only authz check.

    Returns 401 for anonymous callers and 403 for any authenticated
    user that is not a superuser or ``es_admin_principal``. Mirrors
    the existing ``@_admin_principal_required`` decorator in
    ``config.api_views`` but is local to the ``backups`` app so the
    new endpoints have a single, named dependency to import.
    """

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return json_response(
                {"detail": "Autenticacion requerida."}, status=401
            )
        if not (
            getattr(user, "is_superuser", False)
            or getattr(user, "es_admin_principal", False)
        ):
            return json_response(
                {
                    "detail": "Esta accion requiere permisos de administrador principal."
                },
                status=403,
            )
        return view_func(request, *args, **kwargs)

    return wrapped


def check_rate_limit(scope: str, user_id: int, seconds: int) -> Tuple[bool, Optional[HttpResponse]]:
    """Programmatic rate-limit probe returning ``(allowed, denial_response)``.

    Uses the default Django cache. Returns ``(True, None)`` when
    allowed; on denial, returns ``(False, denial_response)`` where
    *denial_response* is a 429 JSON response the caller must return.

    Views call this directly so they can attach a ``RATE_LIMIT_DENIED``
    audit row with action-specific metadata (scope, filename).
    """
    key = f"backup_ratelimit:{scope}:{user_id}"
    if cache.get(key):
        return False, json_response(
            {
                "detail": "Limite de velocidad excedido. Intenta nuevamente en unos segundos."
            },
            status=429,
        )
    cache.set(key, 1, seconds)
    return True, None


__all__ = [
    "check_rate_limit",
    "get_client_ip",
    "require_admin_principal",
]