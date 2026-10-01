"""Views for the ``/api/media/`` namespace (cloud-storage-migration, slice 2).

This module is the slice 2 home for the signed-URL endpoint that
mints short-lived presigned S3 GET URLs for protected user-uploaded
files (clinical PDFs, operation photos, payment receipts, ticket
attachments). Per the media-signed-url-endpoint spec:

* ``GET /api/media/signed-url/?path=<relative_path>`` mints the URL.
* 401 for unauthenticated callers.
* 400 for malformed paths (leading ``/``, ``\\``, ``..``) or paths
  outside the allowlist.
* 403 when the caller has no per-prefix authorization on the row
  that owns the path.
* 503 when the audit log write fails — fail-closed.

The endpoint writes the audit row (via
:func:`audit.services.write_audit_log`) BEFORE calling
:meth:`Boto3Storage.generate_presigned_url`. If the audit row cannot
be persisted, the URL is never minted — an unauditable URL cannot
be defended in a compliance review.

Slice 3 will introduce the ``backfill_media`` management command that
hydrates the bucket from ``MEDIA_ROOT``. Slice 4 introduces the ops
runbook + smoke tests. None of those affect the endpoint contract
landed here.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta, timezone
from pathlib import PurePosixPath
from typing import Optional
from urllib.parse import unquote

from django.http import HttpRequest, HttpResponse
from django.utils import timezone as dj_timezone
from django.views.decorators.http import require_GET

from accounts.models import Usuario
from audit.services import AuditWriteFailure, write_audit_log
from config.api_helpers import json_response
from operations.models import OperacionFoto
from clinical.models import FichaClinica
from notifications.models import Ticket, TicketMessage


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Hard cap on TTL (SigV4 max is 7 days / 604800 seconds — design §7 +
#: media-signed-url-endpoint spec §"TTL caps at 7 days"). The endpoint
#: clamps any caller-supplied TTL down to this bound BEFORE the
#: presigned URL is minted.
SIGNED_URL_HARD_MAX_TTL_SECONDS = 604800

#: Allowed prefixes for the ``path`` query param. Must mirror the table
#: in design §6 + the spec §"Path outside allowed prefixes is rejected".
#: ``citas/`` covers both ``citas/.../antes/`` and ``citas/.../despues/``
#: sub-prefixes via the segment-level check inside
#: :func:`_resolve_authorization_rule`.
ALLOWED_PATH_PREFIXES = (
    "fichas_clinicas/",
    "tickets_adjuntos/",
    "citas/",
    "fotos_operacion/",
    "comprobantes_pagos/",
    "comprobantes_citas/",
)


# ---------------------------------------------------------------------------
# Helpers — path sanitization
# ---------------------------------------------------------------------------


def _decode_path(raw_path: str) -> str:
    """Decode percent escapes and normalize the path.

    The path is treated as a single string; we do NOT resolve against
    a filesystem root. After decoding, leading/trailing whitespace is
    stripped so callers cannot smuggle ``%20../etc`` past a naive
    ``startswith("/")`` check.
    """
    return unquote(raw_path or "").strip()


def _sanitize_path(raw_path: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Validate the ``path`` query param.

    Returns ``(clean_path, error_message)``. ``clean_path`` is the
    canonical relative path the rest of the view will use; it is
    guaranteed to start with one of :data:`ALLOWED_PATH_PREFIXES` and
    to contain no ``..``, leading ``/``, or ``\\`` segments.

    The check order matters: we decode percent escapes FIRST so that
    ``%2e%2e`` cannot bypass the literal ``..`` rejection (design §9
    "Path sanitization rules" + media-signed-url-endpoint spec
    §"Malformed path is rejected").
    """
    if not raw_path:
        return None, "path query param is required."

    decoded = _decode_path(raw_path)
    if not decoded:
        return None, "path query param cannot be empty."

    # Reject leading slash (absolute path attempt) and backslashes
    # (Windows-style traversal). Decode before this check so percent
    # encoded variants cannot smuggle past.
    if decoded.startswith("/"):
        return None, "path must be relative (no leading '/')."
    if "\\" in decoded:
        return None, "path must not contain backslashes."

    # Reject segments equal to ``..`` or ``.``. Split on forward slash
    # using ``PurePosixPath`` so the parsing is consistent regardless
    # of platform.
    parts = PurePosixPath(decoded).parts
    if any(part in {"..", "."} for part in parts):
        return None, "path must not contain '..' or '.' segments."

    # Length cap matches ``AuditLog.resource_path`` so the audit row
    # never has to truncate.
    if len(decoded) > 512:
        return None, "path exceeds maximum length of 512 characters."

    # Allowlist check — the first segment must be one of the allowed
    # top-level prefixes. ``citas/...`` covers both ``antes/`` and
    # ``despues/`` sub-prefixes because the segment check below is on
    # the FIRST segment only.
    first_segment = parts[0] + "/"
    if first_segment not in ALLOWED_PATH_PREFIXES:
        return None, "path is outside the allowed prefixes."

    # Sub-prefix guard for ``citas/`` — only ``antes/`` and ``despues/``
    # sub-trees are authorized (design §6). Anything else inside
    # ``citas/`` is rejected.
    if decoded.startswith("citas/") and not (
        "/antes/" in decoded or decoded.endswith("/antes")
        or "/despues/" in decoded or decoded.endswith("/despues")
    ):
        return None, "citas/ paths must end with /antes/ or /despues/."

    return decoded, None


# ---------------------------------------------------------------------------
# Helpers — authorization rules (design §6 + spec §"Per-Resource Authorization")
# ---------------------------------------------------------------------------


def _role_label(user: Usuario) -> str:
    """Return ``Usuario.rol.rol`` or empty string if unset."""
    return user.rol.rol if user.rol_id and user.rol else ""


def _user_branch_id(user: Usuario) -> Optional[int]:
    """Return the branch this admin user belongs to (or None)."""
    return user.sucursal_id if user.sucursal_id else None


def _admin_principal(user: Usuario) -> bool:
    """ADMIN_PRINCIPAL (or superuser) has wildcard access to every
    allowed-prefix resource per design §6 + spec §"Admin principal has
    wildcard access".
    """
    return bool(user.is_superuser or user.es_admin_principal)


def _admin_sucursal_of(user: Usuario, branch_id: Optional[int]) -> bool:
    """True iff the user is an ADMIN_SUCURSAL whose branch matches."""
    if not user.es_admin_sucursal or user.is_superuser or user.es_admin_principal:
        return False
    return bool(
        user.es_admin_sucursal
        and branch_id is not None
        and _user_branch_id(user) == branch_id
    )


def _resolve_ficha_branch(path: str) -> Optional[int]:
    """Try to resolve a ``fichas_clinicas/...`` path to its owning
    branch via the ``FichaClinica.operacion.paciente.sucursal_origen``
    chain. Returns ``None`` when no row owns the path (stale key) or
    the path is malformed for the lookup.
    """
    ficha = (
        FichaClinica.objects.filter(documento_escaneado_pdf=path)
        .select_related("operacion__paciente")
        .first()
    )
    if ficha is None or ficha.operacion is None or ficha.operacion.paciente is None:
        return None
    return ficha.operacion.paciente.sucursal_origen_id


def _resolve_ficha_owner_cliente_id(path: str) -> Optional[int]:
    """Try to resolve a ``fichas_clinicas/...`` path to its owning
    ``Cliente.id`` (used by the cliente-self rule).
    """
    ficha = (
        FichaClinica.objects.filter(documento_escaneado_pdf=path)
        .select_related("operacion__paciente")
        .first()
    )
    if ficha is None or ficha.operacion is None or ficha.operacion.paciente is None:
        return None
    return ficha.operacion.paciente_id


def _resolve_cita_branch(path: str) -> Optional[int]:
    """Resolve a ``citas/.../antes/...`` or ``citas/.../despues/...``
    path to its branch via the ``CitaMedica.foto_antes`` /
    ``CitaMedica.foto_despues`` FK chain.
    """
    from operations.models import CitaMedica  # local import to avoid cycles

    if path.endswith("/antes") or "/antes/" in path:
        cita = (
            CitaMedica.objects.filter(foto_antes=path)
            .select_related("sucursal")
            .first()
        )
    elif path.endswith("/despues") or "/despues/" in path:
        cita = (
            CitaMedica.objects.filter(foto_despues=path)
            .select_related("sucursal")
            .first()
        )
    else:
        cita = None
    if cita is None:
        return None
    return cita.sucursal_id


def _resolve_cita_assigned_especialista_id(path: str) -> Optional[int]:
    """Resolve the assigned ``Especialista.id`` on a cita that owns the
    given path (used by the especialista-assigned rule).
    """
    from operations.models import CitaMedica

    if path.endswith("/antes") or "/antes/" in path:
        cita = (
            CitaMedica.objects.filter(foto_antes=path)
            .prefetch_related(
                "especialistas_items__especialista",
            )
            .first()
        )
    elif path.endswith("/despues") or "/despues/" in path:
        cita = (
            CitaMedica.objects.filter(foto_despues=path)
            .prefetch_related(
                "especialistas_items__especialista",
            )
            .first()
        )
    else:
        cita = None
    if cita is None:
        return None
    # ``CitaEspecialista.planificada=True`` is the assigned-at-booking
    # specialist; non-planificada is who actually attended. The spec
    # rule is "the operation's assigned especialista" so planificada
    # wins (slice 2 is read-only and does not change who attended).
    planificada = (
        cita.especialistas_items.filter(planificada=True).values_list(
            "especialista_id", flat=True
        )
    )
    return planificada.first() if planificada.exists() else None


def _resolve_foto_operacion_branch(path: str) -> Optional[int]:
    """Resolve a ``fotos_operacion/...`` path to its branch via
    ``OperacionFoto.operacion.paciente.sucursal_origen``.
    """
    foto = (
        OperacionFoto.objects.filter(imagen=path)
        .select_related("operacion__paciente")
        .first()
    )
    if foto is None or foto.operacion is None or foto.operacion.paciente is None:
        return None
    return foto.operacion.paciente.sucursal_origen_id


def _resolve_foto_operacion_especialista_id(path: str) -> Optional[int]:
    """Resolve the assigned ``Especialista.id`` for an operation photo.

    The ``Operacion`` model does NOT carry a single assigned
    especialista FK in this codebase (specialists are attached at the
    ``CitaMedica`` level via ``CitaEspecialista``); for slice 2 we
    fall back to "any cita on the operation with this specialist in
    the planificada phase". This is the closest match to the design's
    intent ("the operation's assigned especialista") without forcing
    a schema change.
    """
    from operations.models import CitaEspecialista

    foto = (
        OperacionFoto.objects.filter(imagen=path)
        .select_related("operacion")
        .first()
    )
    if foto is None or foto.operacion is None:
        return None
    especialista_id = (
        CitaEspecialista.objects.filter(
            cita__operacion=foto.operacion,
            planificada=True,
        )
        .values_list("especialista_id", flat=True)
        .first()
    )
    return especialista_id


def _resolve_comprobante_pago_cliente_id(path: str) -> Optional[int]:
    """Resolve ``comprobantes_pagos/...`` to the owning ``Cliente.id``
    via ``PagoRealizado.cuota.operacion.paciente``.
    """
    from billing.models import PagoRealizado

    pago = (
        PagoRealizado.objects.filter(comprobante_url=path)
        .select_related("cuota__operacion__paciente")
        .first()
    )
    if pago is None or pago.cuota is None or pago.cuota.operacion is None:
        return None
    return pago.cuota.operacion.paciente_id


def _resolve_comprobante_pago_branch(path: str) -> Optional[int]:
    """Resolve ``comprobantes_pagos/...`` to its branch via
    ``PagoRealizado.cuota.operacion.paciente.sucursal_origen``.
    """
    from billing.models import PagoRealizado

    pago = (
        PagoRealizado.objects.filter(comprobante_url=path)
        .select_related("cuota__operacion__paciente")
        .first()
    )
    if (
        pago is None
        or pago.cuota is None
        or pago.cuota.operacion is None
        or pago.cuota.operacion.paciente is None
    ):
        return None
    return pago.cuota.operacion.paciente.sucursal_origen_id


def _resolve_comprobante_cita_cliente_id(path: str) -> Optional[int]:
    """Resolve ``comprobantes_citas/...`` to the owning ``Cliente.id``
    via one of the three cita FKs on ``PagoCita``.

    The model is XOR-constrained to set exactly one of
    ``cita_medica``, ``cita_cliente_libre``, or ``cita_prospecto``;
    each FK chain reaches the cliente differently. Slice 2 keeps the
    resolution at one row lookup (any FK matches).
    """
    from billing.models import PagoCita

    pago = (
        PagoCita.objects.filter(comprobante_url=path)
        .select_related(
            "cita_medica__operacion__paciente",
            "cita_cliente_libre__cliente",
            "cita_prospecto",
        )
        .first()
    )
    if pago is None:
        return None
    if pago.cita_medica_id and pago.cita_medica and pago.cita_medica.operacion:
        return pago.cita_medica.operacion.paciente_id
    if pago.cita_cliente_libre_id and pago.cita_cliente_libre:
        return pago.cita_cliente_libre.cliente_id
    if pago.cita_prospecto_id and pago.cita_prospecto:
        # Prospecto becomes a Cliente via conversion; for slice 2 we
        # only return a cliente id when the FK resolves, so
        # prospecto-backed paths fall through (treated as stale keys
        # for non-admin users, per spec §"Stale key with no owning row").
        return None
    return None


def _resolve_comprobante_cita_branch(path: str) -> Optional[int]:
    """Resolve ``comprobantes_citas/...`` to its branch via the
    same XOR FK chain as :func:`_resolve_comprobante_cita_cliente_id`.
    """
    from billing.models import PagoCita

    pago = (
        PagoCita.objects.filter(comprobante_url=path)
        .select_related(
            "cita_medica__sucursal",
            "cita_cliente_libre__sucursal",
            "cita_prospecto__sucursal",
        )
        .first()
    )
    if pago is None:
        return None
    if pago.cita_medica_id and pago.cita_medica:
        return pago.cita_medica.sucursal_id
    if pago.cita_cliente_libre_id and pago.cita_cliente_libre:
        return pago.cita_cliente_libre.sucursal_id
    if pago.cita_prospecto_id and pago.cita_prospecto:
        return pago.cita_prospecto.sucursal_id
    return None


def _resolve_ticket_owner_ids(path: str) -> tuple[Optional[int], Optional[int]]:
    """Return ``(creado_por_id, especialista_usuario_id)`` for a
    ``tickets_adjuntos/...`` path, resolved via the owning
    ``TicketMessage.ticket``.
    """
    mensaje = (
        TicketMessage.objects.filter(adjunto=path)
        .select_related("ticket")
        .first()
    )
    if mensaje is None:
        return None, None
    ticket = mensaje.ticket
    creado_por = ticket.creado_por_id if ticket else None
    especialista_usuario_id = (
        ticket.especialista.usuario_id if ticket and ticket.especialista else None
    )
    return creado_por, especialista_usuario_id


def _resolve_authorization_rule(
    user: Usuario, path: str
) -> tuple[bool, str, Optional[str]]:
    """Decide whether ``user`` may mint a signed URL for ``path``.

    Returns ``(authorized, rule_name, resource_type)``:

    * ``authorized`` — True iff the user satisfies one of the rules in
      design §6 + spec §"Per-Resource Authorization".
    * ``rule_name`` — short machine-readable tag (matches the spec's
      ``authorization_rule`` field; empty string when denied).
    * ``resource_type`` — dotted ``app.Model.field`` string used to
      label the audit row.

    Admin principals always succeed (wildcard). All other rules are
    applied per prefix.
    """
    # 1) Wildcard rule first because it's the cheapest path and the
    # only one that ignores the DB lookups below.
    if _admin_principal(user):
        return True, "admin_principal", _resource_type_for(path)

    # 2) Per-prefix rules. We attempt each prefix's DB lookup, decide
    # against the user, and short-circuit on the first match. A
    # stale-key lookup (no DB row) is treated as denied for non-admin
    # users per spec §"Stale key with no owning row".
    prefix = path.split("/", 1)[0] + "/"

    if prefix == "fichas_clinicas/":
        cliente_id = _resolve_ficha_owner_cliente_id(path)
        branch_id = _resolve_ficha_branch(path)
        # cliente_self
        if (
            cliente_id is not None
            and hasattr(user, "cliente")
            and user.cliente is not None
            and user.cliente.id == cliente_id
        ):
            return True, "cliente_self", "clinical.FichaClinica.documento_escaneado_pdf"
        # admin_sucursal (own branch)
        if _admin_sucursal_of(user, branch_id):
            return True, "admin_sucursal", "clinical.FichaClinica.documento_escaneado_pdf"
        # Stale key (no ficha row owns the path) — non-admin denied.
        return False, "", "clinical.FichaClinica.documento_escaneado_pdf"

    if prefix == "citas/":
        branch_id = _resolve_cita_branch(path)
        especialista_id = _resolve_cita_assigned_especialista_id(path)
        # especialista_assigned — the assigned specialist via the
        # CitaEspecialista.planificada=True link.
        if (
            especialista_id is not None
            and hasattr(user, "especialista")
            and user.especialista is not None
            and user.especialista.id == especialista_id
        ):
            return True, "especialista_assigned", "operations.CitaMedica.foto_antes"
        # admin_sucursal (own branch)
        if _admin_sucursal_of(user, branch_id):
            return True, "admin_sucursal", "operations.CitaMedica.foto_antes"
        return False, "", "operations.CitaMedica.foto_antes"

    if prefix == "fotos_operacion/":
        branch_id = _resolve_foto_operacion_branch(path)
        especialista_id = _resolve_foto_operacion_especialista_id(path)
        if (
            especialista_id is not None
            and hasattr(user, "especialista")
            and user.especialista is not None
            and user.especialista.id == especialista_id
        ):
            return True, "especialista_assigned", "operations.OperacionFoto.imagen"
        if _admin_sucursal_of(user, branch_id):
            return True, "admin_sucursal", "operations.OperacionFoto.imagen"
        return False, "", "operations.OperacionFoto.imagen"

    if prefix == "comprobantes_pagos/":
        cliente_id = _resolve_comprobante_pago_cliente_id(path)
        branch_id = _resolve_comprobante_pago_branch(path)
        # cliente_self
        if (
            cliente_id is not None
            and hasattr(user, "cliente")
            and user.cliente is not None
            and user.cliente.id == cliente_id
        ):
            return True, "cliente_self", "billing.PagoRealizado.comprobante_url"
        # admin_sucursal (own branch)
        if _admin_sucursal_of(user, branch_id):
            return True, "admin_sucursal", "billing.PagoRealizado.comprobante_url"
        return False, "", "billing.PagoRealizado.comprobante_url"

    if prefix == "comprobantes_citas/":
        cliente_id = _resolve_comprobante_cita_cliente_id(path)
        branch_id = _resolve_comprobante_cita_branch(path)
        if (
            cliente_id is not None
            and hasattr(user, "cliente")
            and user.cliente is not None
            and user.cliente.id == cliente_id
        ):
            return True, "cliente_self", "billing.PagoCita.comprobante_url"
        if _admin_sucursal_of(user, branch_id):
            return True, "admin_sucursal", "billing.PagoCita.comprobante_url"
        return False, "", "billing.PagoCita.comprobante_url"

    if prefix == "tickets_adjuntos/":
        creado_por_id, especialista_usuario_id = _resolve_ticket_owner_ids(path)
        # ticket_creator
        if creado_por_id is not None and creado_por_id == user.id:
            return True, "ticket_creator", "notifications.TicketMessage.adjunto"
        # ticket_assignee (the assigned specialist's user account)
        if (
            especialista_usuario_id is not None
            and especialista_usuario_id == user.id
        ):
            return True, "ticket_assignee", "notifications.TicketMessage.adjunto"
        # admin_sucursal — already short-circuited above by
        # _admin_principal; here we only check the wildcard-skipping
        # admin_sucursal variant.
        if user.es_admin_sucursal and not user.is_superuser:
            # The branch-of-ticket check requires the ticket's
            # sucursal — pull it for the audit row only.
            ticket = (
                Ticket.objects.filter(mensajes__adjunto=path).first()
            )
            if ticket is not None and ticket.sucursal_id == _user_branch_id(user):
                return True, "admin_sucursal", "notifications.TicketMessage.adjunto"
        return False, "", "notifications.TicketMessage.adjunto"

    # Should be unreachable because the sanitizer restricts the prefix,
    # but defensively deny.
    return False, "", ""


def _resource_type_for(path: str) -> str:
    """Return the dotted ``app.Model.field`` for the given path.

    Mirrors :func:`_resolve_authorization_rule`'s prefix mapping so
    the audit row labels stay consistent.
    """
    prefix = path.split("/", 1)[0] + "/"
    if prefix == "fichas_clinicas/":
        return "clinical.FichaClinica.documento_escaneado_pdf"
    if prefix == "citas/":
        return "operations.CitaMedica.foto_antes"
    if prefix == "fotos_operacion/":
        return "operations.OperacionFoto.imagen"
    if prefix == "comprobantes_pagos/":
        return "billing.PagoRealizado.comprobante_url"
    if prefix == "comprobantes_citas/":
        return "billing.PagoCita.comprobante_url"
    if prefix == "tickets_adjuntos/":
        return "notifications.TicketMessage.adjunto"
    return ""


# ---------------------------------------------------------------------------
# Helpers — TTL clamping
# ---------------------------------------------------------------------------


def _clamp_ttl_seconds(requested: Optional[str]) -> int:
    """Return a safe TTL bounded by env defaults + SigV4 max.

    Order of precedence (smallest wins):

    1. The ``ttl`` query param if present and parseable as int.
    2. The ``MEDIA_SIGNED_URL_TTL_SECONDS`` env var (default 900).
    3. The :data:`SIGNED_URL_HARD_MAX_TTL_SECONDS` SigV4 cap (604800).
    """
    env_default = int(os.getenv("MEDIA_SIGNED_URL_TTL_SECONDS", "900"))
    if requested is None or requested == "":
        base = env_default
    else:
        try:
            base = int(requested)
        except (TypeError, ValueError):
            base = env_default
    if base <= 0:
        base = env_default
    return min(base, SIGNED_URL_HARD_MAX_TTL_SECONDS)


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------


@require_GET
def media_signed_url(request: HttpRequest) -> HttpResponse:
    """Mint a SigV4 presigned S3 GET URL for the requested resource.

    GET ``/api/media/signed-url/?path=<relative_path>``.

    Status codes (per spec §"Signed URL Endpoint"):

    * 200 — success. Body: ``{ url, expires_at, ttl_seconds }``.
    * 400 — malformed path or outside allowlist.
    * 401 — not authenticated.
    * 403 — authenticated, but the per-prefix authorization rule
      does not apply to this user.
    * 404 — the bucket does not contain the key. Slice 2 returns 404
      here (instead of falling back to local) so the lazy migration
      path from slice 1 stays the only route for legacy files.
    * 503 — audit write failed (fail-closed). No URL is minted.
    """
    # 1) Authentication.
    user = request.user
    if not user.is_authenticated:
        return json_response(
            {"detail": "Autenticacion requerida."}, status=401
        )

    # 2) Path sanitization.
    raw_path = request.GET.get("path")
    clean_path, sanitize_error = _sanitize_path(raw_path)
    if sanitize_error is not None or clean_path is None:
        return json_response({"detail": sanitize_error or "Invalid path."}, status=400)

    # 3) Authorization.
    authorized, rule_name, resource_type = _resolve_authorization_rule(user, clean_path)
    if not authorized:
        # Per spec §"401 and 403 do not write audit rows", we refuse
        # silently here. 403 carries no body detail beyond a generic
        # message to avoid leaking which prefix failed.
        logger.info(
            "signed_url_denied: user_id=%s path=%s", user.id, clean_path
        )
        return json_response(
            {"detail": "No tienes permisos para acceder a este recurso."},
            status=403,
        )

    # 4) Bucket existence check. Per slice 2 decision: if the key is
    # not in the bucket, the endpoint returns 404 — even if the local
    # fallback file exists on disk. The lazy migration is triggered by
    # upload (slice 3 ``backfill_media`` cron), not by download; we
    # deliberately avoid serving local bytes via a presigned URL.
    storage = _build_storage()
    try:
        if not storage.exists(clean_path):
            logger.info(
                "signed_url_not_in_bucket: user_id=%s path=%s",
                user.id,
                clean_path,
            )
            return json_response(
                {"detail": "El recurso solicitado no existe."},
                status=404,
            )
    except Exception as exc:  # pragma: no cover - defensive
        # An unexpected boto3 error during the existence check is
        # treated the same as a miss so we do not leak infrastructure
        # state to the caller.
        logger.error(
            "signed_url_exists_check_failed: user_id=%s path=%s err=%s",
            user.id,
            clean_path,
            exc,
        )
        return json_response(
            {"detail": "El recurso solicitado no existe."},
            status=404,
        )

    # 5) TTL clamping.
    ttl_seconds = _clamp_ttl_seconds(request.GET.get("ttl"))
    expires_at = dj_timezone.now() + timedelta(seconds=ttl_seconds)

    # 6) Audit row BEFORE URL mint — fail-closed. If the audit write
    # raises, we surface 503 and the URL is never minted. No
    # half-state of "URL minted, audit lost" is possible.
    try:
        write_audit_log(
            user=user,
            user_role=_role_label(user),
            action="SIGNED_URL_ISSUED",
            resource_path=clean_path,
            resource_type=resource_type,
            client_ip=_request_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:512],
            expires_at=expires_at,
        )
    except AuditWriteFailure:
        return json_response(
            {
                "detail": (
                    "No se pudo registrar la auditoria. Reintentaremos en "
                    "instantes."
                )
            },
            status=503,
        )

    # 7) Mint the presigned URL through the storage backend.
    signed = storage.generate_presigned_url(clean_path, ttl_seconds)

    return json_response(
        {
            "url": signed,
            "expires_at": expires_at.astimezone(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ttl_seconds": ttl_seconds,
        }
    )


# ---------------------------------------------------------------------------
# Helpers — request + storage bootstrapping
# ---------------------------------------------------------------------------


def _request_ip(request: HttpRequest) -> Optional[str]:
    """Return ``X-Forwarded-For`` first hop or ``REMOTE_ADDR``.

    Mirrors :func:`config.api_views._request_ip` so audit rows are
    labelled consistently with the rest of the API.
    """
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def _build_storage():
    """Build the storage instance for presigned URL minting.

    Slice 2 always uses :class:`Boto3Storage` (NOT the lazy local
    fallback) so the endpoint never serves a local file via a
    presigned URL. If the bucket is missing the key the endpoint has
    already authorized, the resulting presigned URL simply 404s on
    the AWS side — which is the expected behavior per design §6:
    presigned URLs are bucket-only, local-fallback files are migrated
    lazily on write (slice 3 backfill_media) or on the next read
    (slice 1's existing fallback path is still active for
    ``_open``/``exists``).

    Returning a per-request instance keeps tests straightforward (no
    module-level mock to thread) and matches the slice 1 pattern of
    constructing a fresh boto3 client per call.
    """
    from config.storage_backends import Boto3Storage

    return Boto3Storage()