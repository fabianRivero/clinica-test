"""HTTP endpoints for the biometric app.

Match the existing project style: function-based views decorated with
``@require_POST`` / ``@require_GET`` / ``@require_http_methods``,
returning :func:`config.api_helpers.json_response`. Permissions are
enforced inline via helpers from ``biometric.permissions``.

URL routing lives in ``biometric.urls``; this module is concerned only
with the request/response logic. Tests live in
``biometric.tests.test_endpoints``.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from accounts.models import Usuario
from biometric.log_filters import BiometricOnlyLogScrubber  # noqa: F401  (used in log config)
from biometric.models import AgentToken, BiometricAttempt
from biometric.permissions import (
    ADMIN_PRINCIPAL,
    AuthSubject,
    is_admin_and_owns_sucursal,
    is_admin_principal,
    is_admin_principal_or_sucursal,
    is_agent_token,
)
from biometric.serializers import agent_token_payload, attempt_payload, huella_payload
from biometric.services.agent_client import AgentOperationError, AgentUnavailableError
from biometric.services.capture_tokens import capture_token_store
from biometric.services.encryption import InvalidToken, decrypt_template, encrypt_template
from biometric.services.factory import get_agent_client
from biometric.services.threshold import decide_match, get_threshold
from catalogs.models import Sucursal
from config.api_helpers import json_response, load_payload
from customers.models import Cliente, HuellaBiometricaCliente, Prospecto
from operations.models import CitaMedica


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _subject_from_request(request) -> AuthSubject:
    """Build an :class:`AuthSubject` for the incoming request.

    Falls through to (None, None) when the request is anonymous or the
    user has no role row.
    """
    user = request.user if getattr(request, "user", None) else None
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    agent_id = _resolve_agent_token(request)
    return AuthSubject(user=user, agent_token_id=agent_id)


def _resolve_agent_token(request) -> Optional[int]:
    """Read ``Authorization: Bearer <raw>`` and return the matching
    ``AgentToken.id`` if the row exists and is active.

    Returns ``None`` for unauthenticated requests. Bearer parsing is
    case-insensitive on the scheme, matching RFC 7235.
    """
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    raw = parts[1].strip()
    if not raw:
        return None
    token_hash = AgentToken.hash_token(raw)
    return (
        AgentToken.objects.filter(token_hash=token_hash, is_active=True)
        .values_list("id", flat=True)
        .first()
    )


def _require_admin_principal(request):
    subject = _subject_from_request(request)
    if subject.user is None or not subject.user.is_authenticated:
        return subject, json_response({"detail": "Autenticacion requerida.", "code": "UNAUTHENTICATED"}, status=401)
    if not is_admin_principal(subject):
        return subject, json_response({"detail": "Acceso restringido a administradores principales.", "code": "FORBIDDEN"}, status=403)
    return subject, None


def _require_admin_principal_or_sucursal(request):
    subject = _subject_from_request(request)
    if subject.user is None or not subject.user.is_authenticated:
        return subject, json_response({"detail": "Autenticacion requerida.", "code": "UNAUTHENTICATED"}, status=401)
    if not is_admin_principal_or_sucursal(subject):
        return subject, json_response({"detail": "Acceso restringido a administradores.", "code": "FORBIDDEN"}, status=403)
    return subject, None


def _require_agent_token(request):
    subject = _subject_from_request(request)
    if not is_agent_token(subject):
        return subject, json_response({"detail": "Bearer token required.", "code": "UNAUTHENTICATED"}, status=401)
    return subject, None


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
def enroll_init(request, cliente_id: int):
    """Start enrollment for a client.

    Pseudocode:

    1. Auth gate (admin principal/sucursal).
    2. Validate ``consentimiento_aceptado``.
    3. Generate a short-lived ``capture_token``.
    4. Invoke the agent client (PR #1: mock).
    5. Encrypt the template and persist to ``HuellaBiometricaCliente``.
    6. Write ``BiometricAttempt(operation=ENROLL, success=True)``.
    """
    subject, err = _require_admin_principal_or_sucursal(request)
    if err is not None:
        return err

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido.", "code": "INVALID_JSON"}, status=400)

    if not payload.get("consentimiento_aceptado"):
        return json_response(
            {"detail": "El consentimiento del cliente es obligatorio.", "code": "CONSENT_REQUIRED"},
            status=400,
        )

    cliente = Cliente.objects.filter(pk=cliente_id).first()
    if cliente is None:
        return json_response({"detail": "Cliente no encontrado.", "code": "CLIENTE_NOT_FOUND"}, status=404)

    capture_token = capture_token_store.create(
        {"kind": "enroll", "cliente_id": cliente_id, "user_id": subject.user.id},
    )

    # Pick an active agent. PR #2 honours the same first-by-id rule
    # as PR #1; the most-recently-seen tiebreaker is deferred to PR #3.
    active_agent = (
        AgentToken.objects.filter(is_active=True)
        .order_by("id")
        .first()
    )
    if active_agent is None:
        BiometricAttempt.objects.create(
            cliente=cliente,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.ENROLL,
            success=False,
            failure_reason=BiometricAttempt.FailureReason.NO_IMAGE,
        )
        return json_response(
            {
                "detail": "No hay ningun lector de huellas configurado en esta sede.",
                "code": "NO_AGENT",
            },
            status=503,
        )

    try:
        agent_client = get_agent_client()
        capture = agent_client.capture(
            active_agent, capture_token=capture_token, finger_name="any"
        )
    except AgentUnavailableError as exc:
        # Log a BiometricAttempt with NO_IMAGE/AGENT_OFFLINE so the audit
        # log is complete even when nothing was persisted.
        BiometricAttempt.objects.create(
            cliente=cliente,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.ENROLL,
            success=False,
            failure_reason=BiometricAttempt.FailureReason.NO_IMAGE,
        )
        return json_response(
            {"detail": "El lector de huellas no esta disponible.", "code": str(exc)},
            status=503,
        )
    except AgentOperationError as exc:
        # The agent rejected the capture operationally (low quality,
        # no finger detected, etc.). Return 400 so the frontend can
        # surface a clear retry instruction instead of "service unavailable".
        BiometricAttempt.objects.create(
            cliente=cliente,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.ENROLL,
            success=False,
            failure_reason=BiometricAttempt.FailureReason.LOW_QUALITY,
        )
        return json_response(
            {"detail": "La calidad de la huella capturada es insuficiente. Reintente.", "code": exc.code},
            status=400,
        )

    if capture.quality_score < 50:
        BiometricAttempt.objects.create(
            cliente=cliente,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.ENROLL,
            success=False,
            score=Decimal(capture.quality_score) / Decimal(100),
            failure_reason=BiometricAttempt.FailureReason.LOW_QUALITY,
        )
        return json_response(
            {"detail": "La calidad de captura es insuficiente.", "code": "LOW_QUALITY"},
            status=400,
        )

    try:
        template_bytes = bytes.fromhex(capture.template_b64)
    except ValueError:
        return json_response(
            {"detail": "La plantilla recibida del lector es invalida.", "code": "INVALID_TEMPLATE"},
            status=400,
        )

    ciphertext = encrypt_template(template_bytes)

    with transaction.atomic():
        huella, created = HuellaBiometricaCliente.objects.update_or_create(
            cliente=cliente,
            defaults={
                "proveedor": HuellaBiometricaCliente.Proveedor.DIGITAL_PERSONA,
                "template_biometrico": ciphertext,
                "template_format": capture.template_format or "DP_PROPRIETARY",
                "device_serial": capture.device_serial,
                "calidad_captura": capture.quality_score,
                "consentimiento_aceptado": True,
                "activo": True,
                "registrado_por": subject.user,
                "fecha_registro": timezone.now(),
            },
        )
        attempt = BiometricAttempt.objects.create(
            cliente=cliente,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.ENROLL,
            success=True,
            score=Decimal(capture.quality_score) / Decimal(100),
        )

    return json_response(
        {
            "ok": True,
            "cliente_id": cliente.id,
            "huella_id": huella.id,
            "device_serial": huella.device_serial,
            "template_format": huella.template_format,
            "calidad_captura": huella.calidad_captura,
            "proveedor": huella.proveedor,
            "created": created,
            "attempt": attempt_payload(attempt),
        },
        status=201,
    )


@csrf_exempt
@require_POST
def enroll_finalize(request, cliente_id: int):
    """Async finalize (PR #1 keeps this as a thin spec-compliant alias).

    PR #1 already captures the template inside ``enroll_init`` using the
    mock agent. This endpoint exists for spec parity with the design
    and to keep the door open for an async capture flow in PR #2/3.

    It accepts ``{capture_token, template_b64, quality_score,
    device_serial, template_format}`` and does the same encryption +
    persistence as the init path. It is idempotent for a single
    ``capture_token``: replaying the same token after it was popped
    returns 422.
    """
    subject, err = _require_admin_principal_or_sucursal(request)
    if err is not None:
        return err

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido.", "code": "INVALID_JSON"}, status=400)

    capture_token = (payload.get("capture_token") or "").strip()
    if not capture_token:
        return json_response({"detail": "capture_token es obligatorio.", "code": "MISSING_TOKEN"}, status=400)

    entry = capture_token_store.pop(capture_token)
    if entry is None:
        return json_response({"detail": "capture_token invalido o expirado.", "code": "INVALID_TOKEN"}, status=422)
    if entry.get("cliente_id") != cliente_id:
        return json_response({"detail": "capture_token no corresponde al cliente.", "code": "TOKEN_CLIENT_MISMATCH"}, status=422)

    try:
        template_bytes = bytes.fromhex(str(payload.get("template_b64") or ""))
    except ValueError:
        return json_response({"detail": "template_b64 invalido.", "code": "INVALID_TEMPLATE"}, status=400)

    try:
        quality = int(payload.get("quality_score") or 0)
    except (TypeError, ValueError):
        quality = 0
    if quality < 50:
        cliente = Cliente.objects.filter(pk=cliente_id).first()
        if cliente:
            BiometricAttempt.objects.create(
                cliente=cliente,
                usuario=subject.user,
                operation=BiometricAttempt.Operation.ENROLL,
                success=False,
                score=Decimal(quality) / Decimal(100),
                failure_reason=BiometricAttempt.FailureReason.LOW_QUALITY,
            )
        return json_response({"detail": "La calidad de captura es insuficiente.", "code": "LOW_QUALITY"}, status=400)

    cliente = Cliente.objects.filter(pk=cliente_id).first()
    if cliente is None:
        return json_response({"detail": "Cliente no encontrado.", "code": "CLIENTE_NOT_FOUND"}, status=404)

    ciphertext = encrypt_template(template_bytes)
    with transaction.atomic():
        huella, _ = HuellaBiometricaCliente.objects.update_or_create(
            cliente=cliente,
            defaults={
                "proveedor": HuellaBiometricaCliente.Proveedor.DIGITAL_PERSONA,
                "template_biometrico": ciphertext,
                "template_format": payload.get("template_format") or "DP_PROPRIETARY",
                "device_serial": payload.get("device_serial") or "",
                "calidad_captura": quality,
                "consentimiento_aceptado": True,
                "activo": True,
                "registrado_por": subject.user,
                "fecha_registro": timezone.now(),
            },
        )
        attempt = BiometricAttempt.objects.create(
            cliente=cliente,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.ENROLL,
            success=True,
            score=Decimal(quality) / Decimal(100),
        )
    return json_response(
        {
            "ok": True,
            "cliente_id": cliente.id,
            "huella_id": huella.id,
            "attempt": attempt_payload(attempt),
        },
        status=200,
    )


# ---------------------------------------------------------------------------
# Prospect enrollment (no Cliente yet)
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
def prospect_enroll_init(request, prospect_id: int):
    """Real fingerprint enrollment for a prospect (no cliente yet).

    Mirrors :func:`enroll_init` but persists
    ``HuellaBiometricaCliente`` with ``prospecto`` set and ``cliente=None``.
    The finalize endpoint (:func:`config.prospect_conversion_views.admin_prospect_conversion_finalize`)
    re-attaches the row to the newly-created ``Cliente`` atomically.

    The view follows the same auth + quality + encryption pipeline as
    :func:`enroll_init`. The only differences are:

    - Looks up a ``Prospecto`` (not a ``Cliente``).
    - Persists the huella with ``prospecto=<id>`` and ``cliente=None``.
    - Returns ``prospecto_id`` (and ``cliente_id: None``) instead of
      ``cliente_id`` so the frontend can identify the row.
    """
    subject, err = _require_admin_principal_or_sucursal(request)
    if err is not None:
        return err

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido.", "code": "INVALID_JSON"}, status=400)

    if not payload.get("consentimiento_aceptado"):
        return json_response(
            {"detail": "El consentimiento del cliente es obligatorio.", "code": "CONSENT_REQUIRED"},
            status=400,
        )

    prospect = Prospecto.objects.filter(pk=prospect_id).first()
    if prospect is None:
        return json_response({"detail": "Prospecto no encontrado.", "code": "PROSPECTO_NOT_FOUND"}, status=404)

    capture_token = capture_token_store.create(
        {"kind": "prospect_enroll", "prospect_id": prospect_id, "user_id": subject.user.id},
    )

    active_agent = (
        AgentToken.objects.filter(is_active=True)
        .order_by("id")
        .first()
    )
    if active_agent is None:
        BiometricAttempt.objects.create(
            prospecto=prospect,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.ENROLL,
            success=False,
            failure_reason=BiometricAttempt.FailureReason.NO_IMAGE,
        )
        return json_response(
            {
                "detail": "No hay ningun lector de huellas configurado en esta sede.",
                "code": "NO_AGENT",
            },
            status=503,
        )

    try:
        agent_client = get_agent_client()
        capture = agent_client.capture(
            active_agent, capture_token=capture_token, finger_name="any"
        )
    except AgentUnavailableError as exc:
        BiometricAttempt.objects.create(
            prospecto=prospect,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.ENROLL,
            success=False,
            failure_reason=BiometricAttempt.FailureReason.NO_IMAGE,
        )
        return json_response(
            {"detail": "El lector de huellas no esta disponible.", "code": str(exc)},
            status=503,
        )
    except AgentOperationError as exc:
        BiometricAttempt.objects.create(
            prospecto=prospect,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.ENROLL,
            success=False,
            failure_reason=BiometricAttempt.FailureReason.LOW_QUALITY,
        )
        return json_response(
            {"detail": "La calidad de la huella capturada es insuficiente. Reintente con el dedo mas limpio y plano sobre el cristal.", "code": exc.code},
            status=400,
        )

    if capture.quality_score < 50:
        BiometricAttempt.objects.create(
            prospecto=prospect,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.ENROLL,
            success=False,
            score=Decimal(capture.quality_score) / Decimal(100),
            failure_reason=BiometricAttempt.FailureReason.LOW_QUALITY,
        )
        return json_response(
            {"detail": "La calidad de captura es insuficiente.", "code": "LOW_QUALITY"},
            status=400,
        )

    try:
        template_bytes = bytes.fromhex(capture.template_b64)
    except ValueError:
        return json_response(
            {"detail": "La plantilla recibida del lector es invalida.", "code": "INVALID_TEMPLATE"},
            status=400,
        )

    ciphertext = encrypt_template(template_bytes)

    with transaction.atomic():
        huella, _created = HuellaBiometricaCliente.objects.update_or_create(
            prospecto=prospect,
            defaults={
                "cliente": None,
                "proveedor": HuellaBiometricaCliente.Proveedor.DIGITAL_PERSONA,
                "template_biometrico": ciphertext,
                "template_format": capture.template_format or "DP_PROPRIETARY",
                "device_serial": capture.device_serial,
                "calidad_captura": capture.quality_score,
                "consentimiento_aceptado": True,
                "activo": True,
                "registrado_por": subject.user,
                "fecha_registro": timezone.now(),
            },
        )
        attempt = BiometricAttempt.objects.create(
            prospecto=prospect,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.ENROLL,
            success=True,
            score=Decimal(capture.quality_score) / Decimal(100),
            agent_pc=active_agent,
        )

    return json_response(
        {
            "ok": True,
            "cliente_id": None,
            "prospecto_id": prospect.id,
            "huella_id": huella.id,
            "device_serial": huella.device_serial,
            "template_format": huella.template_format,
            "calidad_captura": huella.calidad_captura,
            "proveedor": huella.proveedor,
            "attempt_id": attempt.id,
        },
        status=201,
    )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _pick_active_agent() -> Optional[AgentToken]:
    """Pick the first active agent row.

    PR #1 picks the first active row by ``id`` (a deterministic,
    simplest definition). When the spec's most-recently-seen logic
    lands in PR #3 the order will switch to ``-last_seen_at``.
    """
    return (
        AgentToken.objects.filter(is_active=True)
        .order_by("id")
        .first()
    )


@csrf_exempt
@require_POST
def verify_init(request, cita_id: int):
    """Trigger a biometric verification for a cita.

    Orchestrates the capture directly: the backend decrypts the
    client's stored template, calls the agent's ``/match`` endpoint
    with that template, and stores the resulting ``score`` against the
    capture_token. The frontend then only has to poll or call
    :func:`verify_confirm` once capture is complete.

    If the client has no ``HuellaBiometricaCliente`` row, returns
    ``{has_fingerprint:false, manual_only:true}`` so the UI can render
    only the manual path (spec requirement 8).
    """
    subject, err = _require_admin_principal_or_sucursal(request)
    if err is not None:
        return err

    cita = CitaMedica.objects.select_related("operacion__paciente", "sucursal").filter(pk=cita_id).first()
    if cita is None:
        return json_response({"detail": "Cita no encontrada.", "code": "CITA_NOT_FOUND"}, status=404)

    if cita.estado != CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
        return json_response(
            {"detail": "La cita debe estar en estado pendiente de verificacion.", "code": "INVALID_STATE"},
            status=400,
        )

    cliente = getattr(cita.operacion, "paciente", None) if cita.operacion_id else None
    if cliente is None:
        return json_response(
            {"detail": "La cita no tiene un paciente asociado.", "code": "NO_CLIENTE"},
            status=422,
        )

    # Cross-sucursal lookup: filter by cliente_id only, regardless of the
    # sucursal that owns the cita. This is the requirement that lets a
    # client enrolled in branch A be verified at branch B.
    huella = (
        HuellaBiometricaCliente.objects.filter(cliente=cliente, activo=True).first()
    )
    if huella is None or not huella.template_biometrico:
        return json_response(
            {"has_fingerprint": False, "manual_only": True},
            status=200,
        )

    agent = _pick_active_agent()
    if agent is None:
        return json_response(
            {"detail": "No hay ningun lector de huellas configurado en esta sede.", "code": "NO_AGENT"},
            status=503,
        )

    # Decrypt the stored template so the agent can use it as the
    # reference for the 1:1 match.
    try:
        stored_template = decrypt_template(bytes(huella.template_biometrico))
    except (InvalidToken, ValueError) as exc:
        BiometricAttempt.objects.create(
            cita=cita,
            cliente=cliente,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.VERIFY,
            success=False,
            failure_reason=BiometricAttempt.FailureReason.DECRYPT_FAILED,
        )
        logger.exception("verify_init: stored template could not be decrypted")
        return json_response(
            {"detail": "La plantilla almacenada no se puede desencriptar. Reenrole al cliente.", "code": "DECRYPT_FAILED"},
            status=500,
        )

    capture_token = capture_token_store.create(
        {
            "kind": "verify",
            "cita_id": cita_id,
            "cliente_id": cliente.id,
            "agent_id": agent.id,
            "user_id": subject.user.id,
        },
    )

    # Run the match synchronously against the agent. The score is
    # stored on the capture_token entry so verify_confirm can read
    # it without touching the agent again.
    try:
        agent_client = get_agent_client()
        match_response = agent_client.match(
            agent,
            template_bytes=stored_template,
            capture_token=capture_token,
        )
    except AgentUnavailableError as exc:
        BiometricAttempt.objects.create(
            cita=cita,
            cliente=cliente,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.VERIFY,
            success=False,
            failure_reason=BiometricAttempt.FailureReason.NO_IMAGE,
        )
        return json_response(
            {"detail": "El lector de huellas no esta disponible.", "code": str(exc)},
            status=503,
        )
    except AgentOperationError as exc:
        BiometricAttempt.objects.create(
            cita=cita,
            cliente=cliente,
            usuario=subject.user,
            operation=BiometricAttempt.Operation.VERIFY,
            success=False,
            failure_reason=BiometricAttempt.FailureReason.LOW_QUALITY,
        )
        return json_response(
            {"detail": "No se pudo verificar la huella. Reintente.", "code": exc.code},
            status=400,
        )

    # Persist the score on the capture_token entry so verify_confirm
    # can read it without re-calling the agent.
    capture_token_store.set_score(capture_token, float(match_response.score))

    return json_response(
        {
            "has_fingerprint": True,
            "capture_token": capture_token,
            "threshold": str(get_threshold()),
            "score": float(match_response.score),
            "cliente_id": cliente.id,
            "cita_id": cita_id,
        },
        status=200,
    )


@csrf_exempt
@require_POST
def verify_confirm(request, cita_id: int):
    """Decide a match against the configured threshold.

    On success: transition the cita to ``CONFIRMADA`` with
    ``metodo_confirmacion=BIOMETRICO``, set ``verif_biometria=True``,
    update ``fecha_confirmacion_biometrica`` and ``HuellaBiometricaCliente
    .last_match_*``.

    Always writes a ``BiometricAttempt(operation=VERIFY, success=...)``
    row regardless of outcome (spec requirement 12: no retry cap).
    """
    subject, err = _require_admin_principal_or_sucursal(request)
    if err is not None:
        return err

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido.", "code": "INVALID_JSON"}, status=400)

    capture_token = (payload.get("capture_token") or "").strip()
    raw_score = payload.get("score")
    if not capture_token or raw_score is None:
        return json_response(
            {"detail": "capture_token y score son obligatorios.", "code": "MISSING_FIELDS"},
            status=400,
        )

    try:
        score = Decimal(str(raw_score))
    except (InvalidOperation, TypeError, ValueError):
        return json_response({"detail": "score invalido.", "code": "INVALID_SCORE"}, status=400)

    entry = capture_token_store.pop(capture_token)
    if entry is None:
        return json_response(
            {"detail": "capture_token invalido o expirado.", "code": "INVALID_TOKEN"},
            status=422,
        )
    if entry.get("cita_id") != cita_id:
        return json_response(
            {"detail": "capture_token no corresponde a la cita.", "code": "TOKEN_CITA_MISMATCH"},
            status=422,
        )

    cita = CitaMedica.objects.select_related("operacion__paciente", "sucursal").filter(pk=cita_id).first()
    if cita is None:
        return json_response({"detail": "Cita no encontrada.", "code": "CITA_NOT_FOUND"}, status=404)
    if cita.estado != CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
        return json_response(
            {"detail": "La cita debe estar pendiente de verificacion.", "code": "INVALID_STATE"},
            status=400,
        )

    cliente = getattr(cita.operacion, "paciente", None) if cita.operacion_id else None
    if cliente is None:
        return json_response({"detail": "La cita no tiene cliente.", "code": "NO_CLIENTE"}, status=422)

    agent_id = entry.get("agent_id")
    matched, reason = decide_match(score)

    if matched:
        # Try decrypting the stored template just to confirm we can read
        # it; we don't propagate the bytes anywhere, but a wrong key is a
        # fail-closed condition (spec requirement 1, "Wrong key fails
        # closed"). On mismatch we treat it as a failed attempt and the
        # cita stays pending.
        huella = (
            HuellaBiometricaCliente.objects.filter(cliente=cliente, activo=True).first()
        )
        if huella is None or not huella.template_biometrico:
            matched = False
            reason = "NO_TEMPLATE"
        else:
            try:
                decrypt_template(bytes(huella.template_biometrico))
            except InvalidToken:
                logger.error(
                    "Stored template could not be decrypted with current key; "
                    "treating verify as failure (re-enrollment required)."
                )
                matched = False
                reason = "DECRYPT_FAILED"

    attempt = BiometricAttempt.objects.create(
        cita=cita,
        cliente=cliente,
        usuario=subject.user,
        operation=BiometricAttempt.Operation.VERIFY,
        success=matched,
        score=score,
        failure_reason="" if matched else (
            BiometricAttempt.FailureReason.BELOW_THRESHOLD
            if reason == "score_below_threshold"
            else reason
        ),
        agent_pc_id=agent_id,
    )

    if matched:
        cita.estado = CitaMedica.Estado.CONFIRMADA
        cita.verif_biometria = True
        cita.metodo_confirmacion = CitaMedica.MetodoConfirmacion.BIOMETRICO
        # ``fecha_confirmacion_biometrica`` is set automatically by
        # ``CitaMedica.save`` when the new state has ``verif_biometria``
        # set and the field is empty.
        cita.save()
        HuellaBiometricaCliente.objects.filter(cliente=cliente).update(
            last_match_at=timezone.now(),
            last_match_score=score,
        )

    return json_response(
        {
            "matched": matched,
            "score": str(score),
            "threshold": str(get_threshold()),
            "attempt": attempt_payload(attempt),
            "cita_id": cita_id,
            "message": (
                "La huella coincide con la registrada."
                if matched
                else "La huella no coincide con la registrada. La cita sigue pendiente."
            ),
            "code": "" if matched else reason,
        },
        status=200,
    )


# ---------------------------------------------------------------------------
# Agent lifecycle
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
def agent_create(request):
    """Create a new AgentToken. ADMIN_PRINCIPAL only. Returns the raw
    secret exactly once.
    """
    subject, err = _require_admin_principal(request)
    if err is not None:
        return err

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido.", "code": "INVALID_JSON"}, status=400)

    name = (payload.get("name") or "").strip()
    public_url = (payload.get("public_url") or "").strip()
    sucursal_id = payload.get("sucursal_id")

    if not name or not public_url or sucursal_id is None:
        return json_response(
            {"detail": "name, sucursal_id y public_url son obligatorios.", "code": "MISSING_FIELDS"},
            status=400,
        )

    sucursal = Sucursal.objects.filter(pk=sucursal_id, activa=True).first()
    if sucursal is None:
        return json_response({"detail": "Sucursal invalida o inactiva.", "code": "SUCURSAL_NOT_FOUND"}, status=404)

    duplicate = (
        AgentToken.objects.filter(public_url=public_url, is_active=True).exists()
    )
    if duplicate:
        return json_response(
            {"detail": "Ya existe un agente activo con esa public_url.", "code": "DUPLICATE_URL"},
            status=422,
        )

    raw_token = secrets.token_urlsafe(32)
    token_hash_value = AgentToken.hash_token(raw_token)
    # Fernet-encrypt the raw token so the backend can perform OUTBOUND
    # calls to the agent (HttpAgentClient). The same Fernet key used
    # for templates is used here.
    try:
        token_encrypted = encrypt_template(raw_token.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - propagate as 500
        return json_response(
            {
                "detail": "No se pudo cifrar el token del agente. "
                "Verifica BIOMETRIC_FERNET_KEY.",
                "code": "ENCRYPTION_FAILED",
            },
            status=500,
        )

    agent = AgentToken.objects.create(
        name=name,
        sucursal=sucursal,
        token_hash=token_hash_value,
        public_url=public_url,
        is_active=True,
        created_by=subject.user,
        token_encrypted=token_encrypted,
    )

    body = agent_token_payload(agent, include_raw=True, raw=raw_token)
    body["raw_token"] = raw_token  # expose verbatim in PR #1 for clarity
    return json_response(body, status=201)


@csrf_exempt
@require_GET
def agent_list(request):
    """List AgentTokens.

    ADMIN_PRINCIPAL sees all; ADMIN_SUCURSAL sees only their branch.
    Never returns ``token_hash`` or the raw token.
    """
    subject, err = _require_admin_principal_or_sucursal(request)
    if err is not None:
        return err

    qs = AgentToken.objects.select_related("sucursal").order_by("sucursal__nombre", "name")
    if subject.user.is_superuser or is_admin_principal(subject):
        tokens = list(qs)
    else:
        tokens = list(qs.filter(sucursal_id=subject.user.sucursal_id))
    return json_response(
        {"results": [agent_token_payload(t) for t in tokens]},
        status=200,
    )


@csrf_exempt
@require_POST
def agent_heartbeat(request, agent_id: int):
    """Update ``last_seen_at`` for an active agent. Bearer-only."""
    subject, err = _require_agent_token(request)
    if err is not None:
        return err

    if subject.agent_token_id != agent_id:
        # Token does not belong to this agent.
        return json_response({"detail": "Token does not match agent id.", "code": "AGENT_MISMATCH"}, status=401)

    AgentToken.objects.filter(pk=agent_id).update(last_seen_at=timezone.now())
    # Per spec requirement 11 the heartbeat endpoint always returns 204.
    from django.http import HttpResponse

    return HttpResponse(status=204)


@csrf_exempt
@require_http_methods(["DELETE"])
def agent_delete(request, agent_id: int):
    """Soft-delete: ``is_active = False``. ADMIN_PRINCIPAL only."""
    subject, err = _require_admin_principal(request)
    if err is not None:
        return err

    agent = AgentToken.objects.filter(pk=agent_id).first()
    if agent is None:
        return json_response({"detail": "Agente no encontrado.", "code": "AGENT_NOT_FOUND"}, status=404)

    # Branch admins are blocked outright at the auth gate so we don't
    # need an explicit ownership check here.
    if not is_admin_and_owns_sucursal(subject, agent):
        # ADMIN_PRINCIPAL passes this; ADMIN_SUCURSAL should never reach
        # here because the gate above already blocks them. Defensive:
        return json_response({"detail": "Acceso restringido al administrador principal.", "code": "FORBIDDEN"}, status=403)

    agent.is_active = False
    agent.save(update_fields=["is_active", "updated_at"])
    from django.http import HttpResponse

    return HttpResponse(status=204)


# ---------------------------------------------------------------------------
# Manual confirmation (audit completeness)
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
def confirm_manual(request, cita_id: int):
    """Manual fallback for spec requirement 12.

    Admins can always confirm manually regardless of biometric
    attempts. We accept ``{metodo: "MANUAL" | "TABLET"}`` for
    forward-compatibility.
    """
    subject, err = _require_admin_principal_or_sucursal(request)
    if err is not None:
        return err

    cita = CitaMedica.objects.select_related("operacion__paciente").filter(pk=cita_id).first()
    if cita is None:
        return json_response({"detail": "Cita no encontrada.", "code": "CITA_NOT_FOUND"}, status=404)

    if cita.estado != CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
        return json_response(
            {"detail": "Solo se pueden confirmar citas pendientes de verificacion.", "code": "INVALID_STATE"},
            status=400,
        )

    payload = load_payload(request) or {}
    requested_metodo = (payload.get("metodo") or "MANUAL").upper()

    cita.estado = CitaMedica.Estado.CONFIRMADA
    cita.verif_biometria = False
    cita.metodo_confirmacion = requested_metodo if requested_metodo in {
        CitaMedica.MetodoConfirmacion.MANUAL,
        CitaMedica.MetodoConfirmacion.TABLET,
    } else CitaMedica.MetodoConfirmacion.MANUAL
    cita.save()

    return json_response(
        {
            "ok": True,
            "cita_id": cita.id,
            "estado": cita.estado,
            "metodo_confirmacion": cita.metodo_confirmacion,
        },
        status=200,
    )


__all__ = [
    "agent_create",
    "agent_delete",
    "agent_heartbeat",
    "agent_list",
    "confirm_manual",
    "enroll_finalize",
    "enroll_init",
    "prospect_enroll_init",
    "verify_confirm",
    "verify_init",
]
