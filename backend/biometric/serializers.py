"""Serializers for biometric endpoints.

We hand-roll tiny serializers instead of pulling in ``djangorestframework``
serializers here to keep the surface small and to match the rest of
the codebase which uses function-based views with JSON responses.
"""

from __future__ import annotations

from typing import Any


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


__all__ = ["agent_token_payload", "huella_payload", "attempt_payload"]
