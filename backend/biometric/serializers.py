"""Serializers for biometric endpoints.

We hand-roll tiny serializers instead of pulling in ``djangorestframework``
serializers here to keep the surface small and to match the rest of
the codebase which uses function-based views with JSON responses.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Suspension contracts (change `suspend-fingerprint-integration`).
#
# When the ``BIOMETRIC_SUSPENDED`` flag is on, the backend must emit a
# stable response family for every gated endpoint so legacy clients
# keep receiving a recognisable payload instead of an exception. The
# bodies below are the *only* accepted shapes for suspended responses;
# view-level adapters (``json_response`` and DRF ``Response``) layer
# the HTTP status (503) on top.
# ---------------------------------------------------------------------------

BIOMETRIC_SUSPENDED_CODE = "BIOMETRIC_SUSPENDED"

# Human-readable message shared by every suspended body. Views MAY
# override ``detail`` when a more specific explanation is useful (e.g.
# agent lifecycle), but the ``code`` field is always this constant so
# clients can switch on it.
BIOMETRIC_SUSPENDED_DETAIL = (
    "La verificación biométrica está suspendida temporalmente. "
    "Use la confirmación manual."
)


def enrollment_suspended_payload() -> dict[str, Any]:
    """Body for suspended enrollment / re-enrollment / finalize /
    prospect-enrollment responses.

    Shape (always HTTP 503): ``{detail, code, enrollment_available:false}``.
    The ``enrollment_available`` flag is explicit so legacy clients can
    distinguish "service unavailable" from "biometric disabled" without
    parsing strings.
    """
    return {
        "detail": BIOMETRIC_SUSPENDED_DETAIL,
        "code": BIOMETRIC_SUSPENDED_CODE,
        "enrollment_available": False,
    }


def verification_suspended_payload() -> dict[str, Any]:
    """Body for suspended verification / canonical and legacy biometric
    confirmation responses.

    Shape (always HTTP 503): ``{detail, code, manual_only:true, matched:false}``.
    ``manual_only`` mirrors the existing "no fingerprint registered"
    response so the frontend already renders the manual confirmation
    path; ``matched:false`` prevents any stale code path from
    interpreting a suspended response as a successful match.
    """
    return {
        "detail": BIOMETRIC_SUSPENDED_DETAIL,
        "code": BIOMETRIC_SUSPENDED_CODE,
        "manual_only": True,
        "matched": False,
    }


def agent_suspended_payload() -> dict[str, Any]:
    """Body for suspended agent create / heartbeat / delete responses.

    Shape (always HTTP 503): ``{detail, code}``. Reads (list / detail)
    are NOT gated here — the spec keeps authorized history visible.
    """
    return {
        "detail": BIOMETRIC_SUSPENDED_DETAIL,
        "code": BIOMETRIC_SUSPENDED_CODE,
    }


def agent_token_payload(token, *, include_raw: bool = False, raw: str = "") -> dict[str, Any]:
    """Serialize an :class:`AgentToken` for API responses.

    ``include_raw=True`` is used **only** on the create response so the
    caller can copy the token once and paste it into the agent's
    ``config.ini``. Subsequent requests expose ``token_fingerprint``
    (first 8 chars of the SHA-256 hash) and never the raw secret.
    """
    data = {
        "id": token.id,
        "name": token.name,
        "sucursal_id": token.sucursal_id,
        "public_url": token.public_url,
        "is_active": token.is_active,
        "last_seen_at": token.last_seen_at.isoformat() if token.last_seen_at else None,
        "created_at": token.created_at.isoformat() if token.created_at else None,
        "token_fingerprint": token.token_fingerprint,
    }
    if include_raw:
        data["token"] = raw
        data["token_hint"] = raw[:4] + "…" + raw[-4:] if len(raw) >= 8 else raw
    return data


def huella_payload(huella) -> dict[str, Any]:
    """Serialize :class:`HuellaBiometricaCliente` for API responses.

    Note we deliberately omit ``template_biometrico`` (ciphertext).
    Only metadata is exposed.
    """
    return {
        "id": huella.id,
        "cliente_id": huella.cliente_id,
        "proveedor": huella.proveedor,
        "template_format": huella.template_format,
        "device_serial": huella.device_serial,
        "calidad_captura": huella.calidad_captura,
        "activo": huella.activo,
        "consentimiento_aceptado": huella.consentimiento_aceptado,
        "last_match_at": huella.last_match_at.isoformat() if huella.last_match_at else None,
        "last_match_score": str(huella.last_match_score) if huella.last_match_score is not None else None,
        "updated_at": huella.updated_at.isoformat() if getattr(huella, "updated_at", None) else None,
    }


def attempt_payload(attempt) -> dict[str, Any]:
    """Serialize a :class:`BiometricAttempt` row."""
    return {
        "id": attempt.id,
        "cita_id": attempt.cita_id,
        "usuario_id": attempt.usuario_id,
        "cliente_id": attempt.cliente_id,
        "operation": attempt.operation,
        "success": attempt.success,
        "score": str(attempt.score) if attempt.score is not None else None,
        "failure_reason": attempt.failure_reason or None,
        "agent_pc_id": attempt.agent_pc_id,
        "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
    }


__all__ = [
    "BIOMETRIC_SUSPENDED_CODE",
    "BIOMETRIC_SUSPENDED_DETAIL",
    "agent_suspended_payload",
    "agent_token_payload",
    "attempt_payload",
    "enrollment_suspended_payload",
    "huella_payload",
    "verification_suspended_payload",
]
