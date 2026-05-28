"""
Serializers for operations and appointments DRF endpoints.
Domain 8 of Phase 6 — Operations + Appointments + Offline Confirmation.
"""

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


class AppointmentStatusUpdateSerializer(serializers.Serializer):
    """Input for updating appointment status."""
    status = serializers.ChoiceField(
        choices=[
            "PROGRAMADA",
            "CONFIRMADA",
            "REALIZADA_PENDIENTE_BIOMETRIA",
            "CANCELADA",
            "NO_ASISTIO",
        ],
        required=True,
    )


class AppointmentRescheduleSerializer(serializers.Serializer):
    """Input for rescheduling an appointment."""
    dateTime = serializers.CharField(required=True)


class AppointmentBiometricConfirmSerializer(serializers.Serializer):
    """Input for confirming an appointment with biometric."""
    template = serializers.CharField(required=False, allow_blank=True)
    quality = serializers.IntegerField(required=False, default=0)
    deviceSerial = serializers.CharField(required=False, allow_blank=True)


class OfflineConflictResolveSerializer(serializers.Serializer):
    """Input for resolving an offline confirmation conflict."""
    resolution = serializers.ChoiceField(choices=["ACCEPT", "REJECT"], required=True)
    reason = serializers.CharField(required=True)
