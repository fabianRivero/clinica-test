"""
Serializers for operations and appointments DRF endpoints.
Domain 8 of Phase 6 — Operations + Appointments + Offline Confirmation.
"""

from decimal import Decimal

from rest_framework import serializers


class OperationUpdateDetailsSerializer(serializers.Serializer):
    """Input for updating operation details (sessions, notes, recommendations)."""
    sessionsTotal = serializers.IntegerField(required=False, min_value=1)
    details = serializers.CharField(required=False, allow_blank=True)
    recommendations = serializers.CharField(required=False, allow_blank=True)


class OperationUpdatePricePlanSerializer(serializers.Serializer):
    """Input for updating operation price/payment plan."""
    priceTotal = serializers.DecimalField(max_digits=12, decimal_places=2, required=True, min_value=0.01)
    quotaCount = serializers.IntegerField(required=True, min_value=1)
    # Edicion opcional por cuota. Si llega, cada elemento actualiza una
    # cuota individual; si falta, se aplica la redistribucion automatica
    # del saldo restante como antes. La validacion detallada de cada item
    # ocurre dentro del endpoint via ``OperationQuotaItemSerializer``.
    quotas = serializers.ListField(
        child=serializers.JSONField(),
        required=False,
        allow_empty=True,
    )


class OperationQuotaItemSerializer(serializers.Serializer):
    """Edicion individual de una cuota del plan de pagos."""
    nroCuota = serializers.IntegerField(required=True, min_value=1)
    montoProgramado = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=True, min_value=Decimal("0.00")
    )
    fechaVencimiento = serializers.DateField(required=True)


class AppointmentStatusUpdateSerializer(serializers.Serializer):
    """Input for updating appointment status."""
    status = serializers.ChoiceField(
        choices=[
            "PROGRAMADA",
            "CONFIRMADA",
            "REALIZADA_PENDIENTE_VERIFICACION",
            "CANCELADA",
            "NO_ASISTIO",
        ],
        required=True,
    )


class AppointmentRescheduleSerializer(serializers.Serializer):
    """Input for rescheduling an appointment.

    All fields beyond ``dateTime`` are optional. When present, they
    override the planning fields on the cita (matching the optional
    fields on the reservation endpoint). CitaMaquinaria/CitaEspecialista
    rows are replaced so the reschedule reads as a fresh planning round.
    """
    dateTime = serializers.CharField(required=True)
    duracionEstimadaMinutos = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=480
    )
    descripcionGeneral = serializers.CharField(
        required=False, allow_blank=True, max_length=10_000
    )
    notasPrevias = serializers.CharField(
        required=False, allow_blank=True, max_length=10_000
    )
    procedimientoPlanificado = serializers.CharField(
        required=False, allow_blank=True, max_length=10_000
    )
    zonaCuerpoPlanificada = serializers.CharField(
        required=False, allow_blank=True, max_length=200
    )
    especialistasPlanificados = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )
    maquinariaPlanificada = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )


class AppointmentBiometricConfirmSerializer(serializers.Serializer):
    """Input for confirming an appointment with biometric."""
    template = serializers.CharField(required=False, allow_blank=True)
    quality = serializers.IntegerField(required=False, default=0)
    deviceSerial = serializers.CharField(required=False, allow_blank=True)


class OfflineConflictResolveSerializer(serializers.Serializer):
    """Input for resolving an offline confirmation conflict."""
    resolution = serializers.ChoiceField(choices=["ACCEPT", "REJECT"], required=True)
    reason = serializers.CharField(required=True)
