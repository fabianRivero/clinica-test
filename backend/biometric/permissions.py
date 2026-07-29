"""DRF permission classes for the biometric endpoints.

We avoid pulling ``rest_framework`` into this file because the rest of
the codebase uses function-based views with explicit JSON responses
(see ``config.api_views``). Instead we expose plain predicates plus a
``get_effective_user_role`` helper so both function and class views
can share the same matrix.

Roles referenced throughout (per spec requirement 13):

- ``ADMIN_PRINCIPAL``: full access, including agent token lifecycle.
- ``ADMIN_SUCURSAL``: read/list scope limited to their own ``sucursal``.
- ``TRABAJADOR``: no biometric access at all.
- ``CLIENTE``: no biometric access at all.

There is no ``RECEPCIONISTA`` role in the database yet (it's still
under design discussion; see design §16.1). PR #1 treats the
operating-of-the-reader as an admin responsibility (per the
orchestrator note) — reception is not part of the permission matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from accounts.models import Usuario


ADMIN_PRINCIPAL = "ADMIN_PRINCIPAL"
ADMIN_SUCURSAL = "ADMIN_SUCURSAL"
TRABAJADOR = "TRABAJADOR"
CLIENTE = "CLIENTE"


@dataclass
class AuthSubject:
    """Light wrapper to feed both user and agent auth into a single
    permission check.
    """

    user: Optional[Usuario]
    agent_token_id: Optional[int] = None


def _user_role(user) -> Optional[str]:
    if not user or not getattr(user, "is_authenticated", False):
        return None
    rol = getattr(user, "rol", None)
    return getattr(rol, "rol", None) if rol else None


def is_admin_principal(subject: AuthSubject) -> bool:
    return _user_role(subject.user) == ADMIN_PRINCIPAL


def is_admin_sucursal(subject: AuthSubject) -> bool:
    return _user_role(subject.user) == ADMIN_SUCURSAL


def is_admin_principal_or_sucursal(subject: AuthSubject) -> bool:
    return is_admin_principal(subject) or is_admin_sucursal(subject)


def is_admin_and_owns_sucursal(subject: AuthSubject, obj) -> bool:
    """Branch-scoped admin: ADMIN_PRINCIPAL passes; ADMIN_SUCURSAL must
    match the object's branch.

    The ``obj`` argument can be any model instance with a ``sucursal_id``
    attribute (e.g. ``AgentToken``), or a :class:`Sucursal` itself. We
    resolve the branch id through :func:`_branch_id_of` so callers can
    pass either shape.
    """
    if is_admin_principal(subject):
        return True
    if not is_admin_sucursal(subject):
        return False
    user = subject.user
    obj_branch_id = _branch_id_of(obj)
    return bool(user and user.sucursal_id == obj_branch_id)


def _branch_id_of(obj) -> Optional[int]:
    """Resolve an arbitrary object to a branch id.

    Accepts:

    - A model with ``sucursal_id`` (e.g. ``AgentToken``).
    - A ``Sucursal`` instance (use ``.id``).
    - A bare integer (returned as-is).
    - Anything else (``None``).
    """
    if obj is None:
        return None
    if isinstance(obj, int):
        return obj
    if hasattr(obj, "sucursal_id"):
        return getattr(obj, "sucursal_id", None)
    if hasattr(obj, "id"):
        return getattr(obj, "id", None)
    return None


def is_agent_token(subject: AuthSubject) -> bool:
    return bool(subject.agent_token_id)


__all__ = [
    "ADMIN_PRINCIPAL",
    "ADMIN_SUCURSAL",
    "AuthSubject",
    "is_admin_and_owns_sucursal",
    "is_admin_principal",
    "is_admin_principal_or_sucursal",
    "is_admin_sucursal",
    "is_agent_token",
]
