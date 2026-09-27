"""Views for dp4500_integration.

Phase 2 of dp4500-host-app-integration-phase2. Two views:

  - ``ConversionStepBiometricView``: wizard step 4 stub. Renders the
    capture_pending.html template; accepts POST to advance the
    wizard or cancel. Real capture client is Phase 4.

  - ``CitaBiometricVerifyView``: POST /api/integration/dp4500/citas/<id>/verificar/.
    Runs the challenge/verify dance against DP4500; on success,
    transitions the cita to CONFIRMADA inside a transaction with
    select_for_update(); on failure, leaves the cita unchanged.
"""
from __future__ import annotations

import logging
import uuid as _uuidlib
from decimal import Decimal
from typing import Any

from django.conf import settings as _s
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from dp4500_integration.client import HTTPClient
from dp4500_integration.exceptions import (
    BiometricMismatch,
    BiometricUnavailable,
    BiometricVerifyFailed,
)
from dp4500_integration.key_resolver import env_key_resolver
from dp4500_integration.models import BiometricEnrollmentRecord
from operations.models import CitaMedica


logger = logging.getLogger(__name__)


# Phase 2 stub: the prospect -> User transition has not happened yet at
# step 4 of the wizard. Use the nil-UUID as a placeholder so the
# BiometricEnrollmentRecord row is valid; Phase 4 removes this once
# the wizard commits to the User before step 4.
ZERO_UUID = _uuidlib.UUID("00000000-0000-0000-0000-000000000000")


def _decimal4(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0001"))


# --------------------------------------------------------------------------
# Wizard step 4 view (stub for Phase 4)
# --------------------------------------------------------------------------


class ConversionStepBiometricView(View):
    """GET renders capture_pending.html; POST advances the wizard."""

    template_name = "integration/capture_pending.html"

    def get(self, request: Request, prospect_id: int) -> Any:
        # Phase 2 stub: render with a placeholder. Phase 4 will look
        # up the User associated with the prospect and pass
        # ``biometric_external_id`` as the user-visible identifier.
        context = {
            "prospect_id": prospect_id,
            "biometric_external_id": None,
            "biometric_available": True,
            "wizard_step": 4,
        }
        return render(request, self.template_name, context)

    def post(self, request: Request, prospect_id: int) -> Any:
        if "cancel" in request.POST:
            BiometricEnrollmentRecord.objects.filter(
                wizard_id=f"prospect-{prospect_id}",
                cancelled_at__isnull=True,
            ).update(cancelled_at=timezone.now())
            return self._back_to_step3(prospect_id)
        # Default: advance.
        BiometricEnrollmentRecord.objects.create(
            user=request.user,
            user_external_id=getattr(
                request.user, "biometric_external_id", None,
            ) or ZERO_UUID,
            wizard_id=f"prospect-{prospect_id}",
            enrollment_strategy=BiometricEnrollmentRecord.STRATEGY_PENDING,
            advanced_at=timezone.now(),
            advanced_by=request.user,
        )
        return self._to_step5(prospect_id)

    def _to_step5(self, prospect_id: int) -> Any:
        # The wizard's existing step-5 URL lives in the host-app's
        # prospect-convert namespace. Phase 2 just redirects to "/";
        # Phase 4 wires the real reverse().
        return redirect("/")

    def _back_to_step3(self, prospect_id: int) -> Any:
        return redirect("/")


# --------------------------------------------------------------------------
# Cita biometric verify view
# --------------------------------------------------------------------------


class CitaBiometricVerifyView(APIView):
    """POST /api/integration/dp4500/citas/<cita_id>/verificar/.

    Phase 2 of dp4500-host-app-integration-phase2. Runs the
    challenge+verify dance against DP4500 and, on success, transitions
    the cita to CONFIRMADA inside a ``select_for_update`` transaction.
    On failure, leaves the cita unchanged.

    Concurrency: two concurrent calls for the same cita serialize on
    the cita row's ``select_for_update`` lock; the loser sees the new
    estado and returns 409 ``cita_no_longer_pending``.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request: Request, cita_id: int, *args: Any, **kwargs: Any) -> Response:
        client = HTTPClient(
            base_url=_s.DP4500_BASE_URL,
            timeout_seconds=_s.DP4500_TIMEOUT_SECONDS,
            key_resolver=env_key_resolver,
        )
        try:
            with transaction.atomic():
                cita = (
                    CitaMedica.objects
                    .select_for_update()
                    .filter(pk=cita_id)
                    .first()
                )
                if cita is None:
                    return Response(
                        {"detail": "Cita no encontrada.", "code": "CITA_NOT_FOUND"},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                if cita.sucursal_id is None:
                    return Response(
                        {
                            "detail": "La cita no tiene sucursal; no hay service key.",
                            "code": "NO_SERVICE_KEY",
                        },
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                        headers={"Retry-After": "60"},
                    )
                if cita.estado != CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
                    return Response(
                        {
                            "detail": "La cita no está pendiente de verificación.",
                            "code": "cita_no_longer_pending",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                # Resolve the host-app user's biometric_external_id. The
                # ``operacion.paciente.usuario`` path mirrors the clinic's
                # existing user-relationship chain.
                user_external_id = ""
                if cita.operacion_id:
                    cliente = getattr(cita.operacion, "paciente", None)
                    usuario = getattr(cliente, "usuario", None) if cliente else None
                    user_external_id = str(
                        getattr(usuario, "biometric_external_id", "") or ""
                    )
                if not user_external_id:
                    return Response(
                        {
                            "detail": "El cliente no tiene UUID biométrico asignado.",
                            "code": "no_biometric_external_id",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Step 1: challenge.
                try:
                    challenge = client.identity_challenge(
                        user_external_id=user_external_id,
                        sucursal_id=cita.sucursal_id,
                    )
                except BiometricUnavailable as exc:
                    return self._dp4500_unavailable(exc)

                # Step 2: verify. Phase 2 passes "phase2-stub" as the
                # signature; Phase 4 wires real Ed25519 sign.
                try:
                    result = client.identity_verify(
                        user_external_id=user_external_id,
                        challenge_id=challenge.capture_token,
                        signature_b64="phase2-stub",
                        timestamp=timezone.now().isoformat(),
                        sucursal_id=cita.sucursal_id,
                    )
                except (BiometricMismatch, BiometricVerifyFailed) as exc:
                    return Response(
                        {
                            "detail": type(exc).__name__ + ": " + str(exc),
                            "code": "biometric_failure",
                        },
                        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )
                except BiometricUnavailable as exc:
                    return self._dp4500_unavailable(exc)

                if not result.matched:
                    return Response(
                        {"detail": "La huella no coincide.", "code": "biometric_mismatch"},
                        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )

                # Match: write all three biometric fields atomically.
                cita.estado = CitaMedica.Estado.CONFIRMADA
                cita.metodo_confirmacion = CitaMedica.MetodoConfirmacion.BIOMETRICO
                cita.biometric_challenge_id = challenge.capture_token
                # ``match.confidence`` is the match score; Phase 1's
                # response does not include it in the verify response,
                # so we leave None here. Phase 4 reads it from the
                # response payload.
                cita.biometric_verified_at = timezone.now()
                cita.save()
                return Response(
                    {"ok": True, "audit_hash": result.audit_hash},
                    status=status.HTTP_200_OK,
                )
        finally:
            client.close()

    @staticmethod
    def _dp4500_unavailable(exc: Exception) -> Response:
        return Response(
            {
                "detail": f"DP4500 no responde: {exc}",
                "code": "dp4500_unavailable",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": "60"},
        )
