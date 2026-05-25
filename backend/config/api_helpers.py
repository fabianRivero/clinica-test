"""
Shared helper functions extracted from config view modules.

These functions were duplicated across two or more view files and are now
centralised here to avoid repetition.  When adding new helpers, keep them
grouped under the appropriate comment header.
"""

import json
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps

from django.http import JsonResponse
from django.utils import timezone


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def json_response(data, status=200):
    """Return a JsonResponse with UTF-8-safe serialisation."""
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

def load_payload(request):
    """Parse the request body as JSON.

    Returns a dict, or ``None`` when the body is not valid JSON.
    Empty bodies are treated as ``{}`` so callers always receive a dict
    (unless the JSON is malformed, in which case ``None`` is returned).
    """
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def admin_required(view_func):
    """Decorator: require an authenticated admin user.

    - 401 if not authenticated.
    - 403 if not an admin (superuser or ``es_administrador``).
    - 403 if the admin's branch is inactive (branch admins only).
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return json_response({"detail": "Autenticacion requerida."}, status=401)
        if not (user.is_superuser or user.es_administrador):
            return json_response({"detail": "No tienes permisos para acceder a esta vista."}, status=403)
        if not (user.is_superuser or user.es_admin_principal):
            if not user.sucursal or not user.sucursal.activa:
                return json_response(
                    {"detail": "Tu sucursal esta inactiva. Contacta al administrador principal."},
                    status=403,
                )
        return view_func(request, *args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# Branch helpers
# ---------------------------------------------------------------------------

def get_user_branch(request):
    """Return the effective branch for the current user.

    - Branch admins always get their assigned branch.
    - Main/super admins get the branch from ``X-Selected-Branch-Id`` header,
      ``branchId`` query/post param, or session; falling back to the main branch.
    """
    from catalogs.models import Sucursal

    user = request.user
    if not (user.is_superuser or user.es_admin_principal):
        return user.sucursal

    branch_id = (
        request.headers.get("X-Selected-Branch-Id")
        or request.GET.get("branchId")
        or request.POST.get("branchId")
    )
    if branch_id:
        try:
            branch = Sucursal.objects.filter(pk=int(branch_id), activa=True).first()
            if branch:
                request.session["selected_branch_id"] = branch.pk
                return branch
        except (ValueError, TypeError):
            pass

    session_branch_id = request.session.get("selected_branch_id")
    if session_branch_id:
        branch = Sucursal.objects.filter(pk=session_branch_id, activa=True).first()
        if branch:
            return branch

    main_branch = Sucursal.objects.filter(es_principal=True, activa=True).first()
    if main_branch:
        request.session["selected_branch_id"] = main_branch.pk
    return main_branch


# ---------------------------------------------------------------------------
# Display / format helpers
# ---------------------------------------------------------------------------

def currency(amount):
    """Format a numeric amount as a Boliviano string, e.g. ``Bs 1234.56``."""
    return f"Bs {amount:.2f}"


def date_label(value):
    """Format a date as ``dd/mm/yyyy`` or return *Sin fecha* for falsy values."""
    if not value:
        return "Sin fecha"
    return value.strftime("%d/%m/%Y")


def full_name(user):
    """Return the user's ``nombre_completo``, falling back to ``username``.

    Returns *Sin asignar* when *user* is falsy (e.g. ``None``).
    """
    if not user:
        return "Sin asignar"
    return user.nombre_completo or user.username


def procedure_name(operacion):
    """Return the procedure name for an operation.

    Prefers the cosmetic procedure name; falls back to the service type.
    """
    procedimiento = operacion.servicio_config.proc_estetico
    if procedimiento:
        return procedimiento.proceso
    return operacion.servicio_config.tipo_servicio.tipo


def metric(identifier, label, value, delta, tone):
    """Build a normalised metric dict for API responses."""
    return {
        "id": identifier,
        "label": label,
        "value": str(value),
        "delta": delta,
        "tone": tone,
    }


def split_amount(total, count):
    """Split *total* into *count* equal decimal parts, remainder in the last.

    Uses ``ROUND_HALF_UP`` rounding.
    """
    if count <= 0:
        return []
    base = (total / Decimal(count)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    amounts = [base for _ in range(count)]
    amounts[-1] = (total - sum(amounts[:-1])).quantize(Decimal("0.01"))
    return amounts