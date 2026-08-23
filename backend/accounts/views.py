"""
Admin-assisted user recovery views.

Search and detail endpoints used by /cms/equipo/recuperar to find any
user (cliente, trabajador, admin de sucursal, admin principal) by
username, name, email, phone, or CI, and to inspect their account
context before the reset-password flow (commit 3).

Branch scoping mirrors the rest of the admin area: a main/principal
admin can see every user; a branch admin only sees users whose
``Usuario.sucursal`` matches their own. The branch check is enforced
inside each view rather than relying on ``AdminRequired`` alone so the
403 is a clear cross-branch violation when applicable.

The actual password reset lives in commit 3. We deliberately keep
this commit read-only.
"""

import logging
import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from django.views.decorators.http import require_GET, require_POST

from config.api_helpers import admin_required, json_response
from config.api_views import _invalidate_user_sessions

logger = logging.getLogger(__name__)

MAX_SEARCH_RESULTS = 25

# Temporary password must satisfy Django's AUTH_PASSWORD_VALIDATORS
# (MinimumLengthValidator default 8, plus the common-password and
# numeric-only restrictions). We build 16 chars from a letter+digit
# pool so the password has enough entropy to pass the CommonPassword
# blacklist while staying legible for an admin who has to dictate
# it over the phone.
_TEMP_PWD_ALPHABET = string.ascii_letters + string.digits
_TEMP_PWD_LENGTH = 16


def _generate_temporary_password():
    """Build a cryptographically-random password that clears every
    validator configured in settings.AUTH_PASSWORD_VALIDATORS.

    We reserve one slot for a digit so the output is guaranteed to
    mix letters and digits (helps legibility when an admin dictates
    it over the phone and avoids the rare all-letter draw). The
    remaining 15 slots are drawn from the full letter+digit pool,
    then the position of the guaranteed digit is randomised to
    avoid positional bias. On the rare blacklist hit we roll again.
    """

    while True:
        guaranteed_digit = secrets.choice(string.digits)
        body = "".join(
            secrets.choice(_TEMP_PWD_ALPHABET)
            for _ in range(_TEMP_PWD_LENGTH - 1)
        )
        digit_position = secrets.randbelow(_TEMP_PWD_LENGTH)
        candidate = (
            body[:digit_position] + guaranteed_digit + body[digit_position:]
        )
        try:
            validate_password(candidate)
        except Exception:
            continue
        return candidate


def _resolve_kind(user):
    """Map a Usuario to a frontend-friendly role tag.

    Order matters: superuser and ADMIN_PRINCIPAL win over plain role
    names because they encode operational authority, not just label.
    """

    if user.is_superuser:
        return "admin_principal"
    if user.es_admin_principal:
        return "admin_principal"
    if user.es_admin_sucursal:
        return "admin_sucursal"
    if user.es_trabajador:
        return "trabajador"
    if user.es_cliente:
        return "cliente"
    return "otro"


def _resolve_ci(user):
    """CI lives on Cliente or Especialista, not on Usuario.

    Returns an empty string when the user has no profile attached yet.
    """

    if hasattr(user, "cliente") and user.cliente.ci:
        return user.cliente.ci
    if hasattr(user, "especialista") and user.especialista.ci:
        return user.especialista.ci
    return ""


def _serialize_recovery_user(user):
    return {
        "id": user.id,
        "username": user.username,
        "fullName": user.nombre_completo or user.username,
        "rol": (user.rol.rol if user.rol else ""),
        "kind": _resolve_kind(user),
        "email": user.email or "",
        "telefono": user.telefono or "",
        "ci": _resolve_ci(user),
        "sucursal": (user.sucursal.nombre if user.sucursal else ""),
        "sucursalId": user.sucursal_id,
        "isActive": user.is_active,
        "mustChangePassword": user.must_change_password,
    }


def _scoped_queryset(request):
    """Return the base Usuario queryset visible to the current admin.

    Main/principal admins see every row. Branch admins are restricted
    to users whose ``sucursal_id`` matches their own. Active flag is
    preserved so admins can find deactivated accounts too.
    """

    User = get_user_model()
    qs = User.objects.select_related("rol", "sucursal")
    request_user = request.user
    if not (request_user.is_superuser or request_user.es_admin_principal):
        qs = qs.filter(sucursal_id=request_user.sucursal_id)
    return qs


def _branch_violation(request_user, target):
    """Return True when a branch admin tries to reach a target outside
    their own branch.
    """

    if request_user.is_superuser or request_user.es_admin_principal:
        return False
    return target.sucursal_id != request_user.sucursal_id


@require_GET
@admin_required
def usuario_recovery_search(request):
    """Search users by username, name, email, phone, or CI.

    Returns up to 25 matches. Empty ``q`` returns an empty list (the
    frontend uses this to reset the result panel when the operator
    clears the search box).

    Query interpretation:
    - A single token (no spaces) keeps the original OR semantics:
      match any field that contains the token. ``fabian`` matches a
      user whose ``primer_nombre`` contains "Fabian".
    - Multiple tokens (whitespace-separated) switch to AND semantics
      over the user's full name only. Each token must appear, in any
      order, in the concatenation of ``primer_nombre``,
      ``segundo_nombre``, ``apellido_paterno``, ``apellido_materno``
      (case-insensitive). ``fabian rivero`` matches "Fabian Rivero
      Lopez"; ``rivero fabian`` matches the same row. This matches
      how an admin types a name into Google.

    We don't try to combine per-field OR with per-token AND: a query
    with spaces is treated as a name query (a "fabian r" looking for
    the email is rare enough that we don't lose much by being strict).
    """

    q = (request.GET.get("q") or "").strip()
    if not q:
        return json_response({"users": []})

    base = _scoped_queryset(request)

    tokens = q.split()
    if len(tokens) >= 2:
        # AND across tokens on the full name (case-insensitive).
        # Concatenate the name fields and require every token to be
        # present. We use ``__icontains`` on each field individually so
        # the query stays portable across the SQLite test backend
        # and PostgreSQL in production.
        for token in tokens:
            base = base.filter(
                Q(primer_nombre__icontains=token)
                | Q(segundo_nombre__icontains=token)
                | Q(apellido_paterno__icontains=token)
                | Q(apellido_materno__icontains=token)
            )
    else:
        # Single-token OR across every searchable field (original
        # behaviour). CI lives on Cliente/Especialista.
        ci_q = Q(cliente__ci__icontains=q) | Q(especialista__ci__icontains=q)
        text_match = (
            Q(username__icontains=q)
            | Q(primer_nombre__icontains=q)
            | Q(segundo_nombre__icontains=q)
            | Q(apellido_paterno__icontains=q)
            | Q(apellido_materno__icontains=q)
            | Q(email__icontains=q)
            | Q(telefono__icontains=q)
            | ci_q
        )
        base = base.filter(text_match)

    matches = base.distinct().order_by("username")[:MAX_SEARCH_RESULTS]
    return json_response({"users": [_serialize_recovery_user(u) for u in matches]})


@require_GET
@admin_required
def usuario_recovery_detail(request, user_id):
    """Return full account context for a single user.

    Branch admins that try to peek at a user outside their own branch
    get a 403 with a clear cross-branch message rather than an empty
    payload (the search endpoint already filters, but the detail one
    is reachable by direct URL and we want explicit feedback).
    """

    User = get_user_model()
    target = (
        User.objects.select_related("rol", "sucursal")
        .filter(pk=user_id)
        .first()
    )
    if not target:
        return json_response({"detail": "No encontramos al usuario solicitado."}, status=404)

    if _branch_violation(request.user, target):
        return json_response(
            {"detail": "Este usuario pertenece a otra sucursal."},
            status=403,
        )

    payload = _serialize_recovery_user(target)
    payload["createdAt"] = target.date_joined.isoformat() if target.date_joined else None
    last_login = target.last_login
    payload["lastLogin"] = last_login.isoformat() if last_login else None
    return json_response(payload)


@require_POST
@admin_required
def usuario_recovery_reset(request, user_id):
    """Issue a temporary password for a user account.

    The system generates a random password that satisfies every
    AUTH_PASSWORD_VALIDATORS, marks the account with
    ``must_change_password=True`` so the user is forced to pick a
    real password on next login, and invalidates every active
    session for that user. The temporary password is returned in
    the response exactly once; the admin is expected to deliver it
    out-of-band to the user.

    Branch scoping: a branch admin cannot reset users in another
    branch. Self-resets are blocked to prevent admins from locking
    themselves out (the AuthProvider layer is the right path for
    self-service password changes).
    """

    request_user = request.user
    if int(user_id) == request_user.id:
        return json_response(
            {"detail": "No puedes resetear tu propia contraseña desde aqui."},
            status=400,
        )

    User = get_user_model()
    target = (
        User.objects.select_related("rol", "sucursal")
        .filter(pk=user_id)
        .first()
    )
    if not target:
        return json_response({"detail": "No encontramos al usuario solicitado."}, status=404)

    if _branch_violation(request_user, target):
        return json_response(
            {"detail": "Este usuario pertenece a otra sucursal."},
            status=403,
        )

    temporary_password = _generate_temporary_password()
    target.set_password(temporary_password)
    target.must_change_password = True
    target.save(update_fields=["password", "must_change_password"])

    _invalidate_user_sessions([target.id])

    logger.warning(
        "user_recovery_reset actor=%s target=%s target_username=%s target_branch=%s",
        request_user.id,
        target.id,
        target.username,
        target.sucursal_id,
    )

    return json_response(
        {
            "detail": (
                "Contrasena temporal generada. La cuenta fue marcada para "
                "forzar cambio en el proximo inicio de sesion."
            ),
            "user": {
                "id": target.id,
                "username": target.username,
                "fullName": target.nombre_completo or target.username,
            },
            "temporaryPassword": temporary_password,
            "mustChangePassword": True,
            "sessionInvalidated": True,
        }
    )