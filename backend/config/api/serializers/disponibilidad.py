"""
Serializers for availability-related DRF endpoints.
Domain 9 of Phase 6 — Disponibilidad (Availability Management).
"""

from rest_framework import serializers


class HabitualScheduleCreateSerializer(serializers.Serializer):
    """Input for creating a habitual schedule rule."""
    specialistIds = serializers.ListField(
        child=serializers.IntegerField(), required=False
    )
    specialistId = serializers.IntegerField(required=False)
    branchId = serializers.IntegerField(required=True)
    startDate = serializers.CharField(required=True)
    endDate = serializers.CharField(required=False, allow_blank=True, default="")
    startTime = serializers.CharField(required=True)
    endTime = serializers.CharField(required=True)
    detail = serializers.CharField(required=False, default="")
    weekdayCodes = serializers.ListField(
        child=serializers.IntegerField(), required=True
    )


class HabitualScheduleUpdateSerializer(serializers.Serializer):
    """Input for updating a habitual schedule rule."""
    branchId = serializers.IntegerField(required=False)
    startDate = serializers.CharField(required=False)
    endDate = serializers.CharField(required=False, allow_blank=True)
    startTime = serializers.CharField(required=False)
    endTime = serializers.CharField(required=False)
    detail = serializers.CharField(required=False, allow_blank=True)
    active = serializers.BooleanField(required=False)
    weekdayCodes = serializers.ListField(
        child=serializers.IntegerField(), required=False
    )


class SpecialistExceptionCreateSerializer(serializers.Serializer):
    """Input for creating specialist exceptions (block or extra hours)."""
    specialistIds = serializers.ListField(
        child=serializers.IntegerField(), required=False
    )
    specialistId = serializers.IntegerField(required=False)
    branchId = serializers.IntegerField(required=True)
    type = serializers.ChoiceField(
        choices=["BLOQUEAR", "HORA_EXTRA"], required=True
    )
    dates = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    rangeStartDate = serializers.CharField(required=False, allow_blank=True)
    rangeEndDate = serializers.CharField(required=False, allow_blank=True)
    weekdayCodes = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    startTime = serializers.CharField(required=False, allow_blank=True)
    endTime = serializers.CharField(required=False, allow_blank=True)
    detail = serializers.CharField(required=False, default="")


class GlobalDayManageSerializer(serializers.Serializer):
    """Input for managing a global branch closure day."""
    action = serializers.ChoiceField(choices=["BLOQUEAR", "DESBLOQUEAR"], required=True)
    date = serializers.CharField(required=True)
    detail = serializers.CharField(required=False, default="")


class ConcurrencyCheckSerializer(serializers.Serializer):
    """Input for checking appointment concurrency at a specific time."""
    sucursal_id = serializers.IntegerField(required=True)
    fecha = serializers.CharField(required=True)
    hora_inicio = serializers.CharField(required=True)
