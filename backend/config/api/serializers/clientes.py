"""
Serializers for client-related DRF endpoints.
Domain 6 of Phase 6 — Clientes, Operaciones (reservations), CitasMedicasLibres.
"""

from rest_framework import serializers
from django.db.models import Prefetch
from django.utils import timezone

from customers.models import Cliente, Prospecto
from operations.models import CitaMedica, CitaClienteLibre, Operacion
from operations.scheduling import mark_expired_programmed_appointments_as_no_show
from config.client_api_views import (
    _operation_item,
    _appointment_item,
    _payment_item,
    _quota_item,
    _build_operation_slot_map,
)
from config.api_helpers import full_name, currency, date_label, datetime_label, metric, procedure_name


# =============================================================================
# Client Search
# =============================================================================

class ClientSearchSerializer(serializers.Serializer):
    """Lightweight serializer for global client search results."""
    id = serializers.IntegerField(source="pk")
    name = serializers.SerializerMethodField()
    ci = serializers.CharField()
    phone = serializers.SerializerMethodField()
    branchId = serializers.IntegerField(source="usuario.sucursal_id")
    branchName = serializers.SerializerMethodField()
    cityName = serializers.SerializerMethodField()

    def get_name(self, obj):
        return full_name(obj.usuario)

    def get_phone(self, obj):
        return obj.telefono or "Sin teléfono"

    def get_branchName(self, obj):
        return obj.usuario.sucursal.nombre if obj.usuario.sucursal else "Sin sucursal"

    def get_cityName(self, obj):
        return obj.usuario.sucursal.ciudad if obj.usuario.sucursal else "Sin ciudad"


# =============================================================================
# Client Detail
# =============================================================================

class ClientAppointmentSerializer(serializers.Serializer):
    """Serializer for a client's medical appointment (CitaMedica or CitaClienteLibre)."""
    id = serializers.CharField()
    rawId = serializers.IntegerField()
    dateTime = serializers.CharField()
    operation = serializers.CharField()
    specialist = serializers.CharField()
    status = serializers.CharField()


class ClientOperationSerializer(serializers.Serializer):
    """Serializer for a client's operation using existing _operation_item helper."""
    id = serializers.CharField()
    rawId = serializers.IntegerField()
    procedure = serializers.CharField()
    serviceType = serializers.CharField()
    branch = serializers.CharField()
    status = serializers.CharField()
    statusTone = serializers.CharField()
    price = serializers.CharField()
    zone = serializers.CharField()
    startedAt = serializers.CharField()
    endedAt = serializers.CharField()
    nextAppointment = serializers.CharField()
    recommendations = serializers.CharField()
    details = serializers.CharField()
    sessions = serializers.DictField()
    canReserve = serializers.BooleanField()
    firstPaymentVerified = serializers.BooleanField()
    reserveMessage = serializers.CharField()
    quotaSummary = serializers.CharField()


class ClientPaymentSerializer(serializers.Serializer):
    """Serializer for a client's payment using existing _payment_item helper."""
    id = serializers.CharField()
    rawId = serializers.IntegerField()
    patient = serializers.CharField()
    operation = serializers.CharField()
    amount = serializers.CharField()
    submittedAt = serializers.CharField()
    bank = serializers.CharField()
    status = serializers.CharField()
    quota = serializers.CharField()
    dueDate = serializers.CharField()
    verifier = serializers.CharField()
    receiptUrl = serializers.CharField()
    note = serializers.CharField()


class ClientQuotaSerializer(serializers.Serializer):
    """Serializer for a client's pending quota using existing _quota_item helper."""
    id = serializers.CharField()
    rawId = serializers.IntegerField()
    patient = serializers.CharField()
    operation = serializers.CharField()
    quotaNumber = serializers.IntegerField()
    amount = serializers.CharField()
    dueDate = serializers.CharField()
    status = serializers.CharField()
    paymentsCount = serializers.IntegerField()


class ClientMetricSerializer(serializers.Serializer):
    """Serializer for a client metric (used in detail view)."""
    key = serializers.CharField()
    label = serializers.CharField()
    value = serializers.IntegerField()
    description = serializers.CharField()
    tone = serializers.CharField()


class ClientDetailSerializer(serializers.Serializer):
    """Full client detail with metrics, operations, appointments, payments, quotas."""
    client = ClientSearchSerializer()
    metrics = ClientMetricSerializer(many=True)
    operations = ClientOperationSerializer(many=True)
    appointments = ClientAppointmentSerializer(many=True)
    sessions = ClientAppointmentSerializer(many=True)
    payments = ClientPaymentSerializer(many=True)
    pendingQuotas = ClientQuotaSerializer(many=True)


# =============================================================================
# Client Toggle (Inactivate)
# =============================================================================

class ClientInactivateSerializer(serializers.Serializer):
    """No input needed for inactivate — just confirmation."""
    pass


# =============================================================================
# Client Migrate
# =============================================================================

class ClientMigrateSerializer(serializers.Serializer):
    """Input for migrating a client to a different branch."""
    branchId = serializers.IntegerField()

    def validate_branchId(self, value):
        from catalogs.models import Sucursal
        if not Sucursal.objects.filter(pk=value).exists():
            raise serializers.ValidationError("La sucursal no existe.")
        return value


# =============================================================================
# Operation Reservation
# =============================================================================

class OperationReservationAvailabilitySerializer(serializers.Serializer):
    """Output serializer for operation reservation availability."""
    operation = ClientOperationSerializer()


class OperationReservationCreateSerializer(serializers.Serializer):
    """Input for creating a reservation on an operation."""
    branchId = serializers.IntegerField()
    dateTime = serializers.CharField()  # ISO datetime string

    def validate_dateTime(self, value):
        from django.utils import dateparse
        from django.utils.timezone import is_naive
        fecha_hora = dateparse.parse_datetime(value)
        if fecha_hora and is_naive(fecha_hora):
            fecha_hora = timezone.make_aware(fecha_hora)
        if not fecha_hora:
            raise serializers.ValidationError("Formato de fecha/hora inválido.")
        return value


# =============================================================================
# Free Medical Appointment
# =============================================================================

class FreeMedicalAvailabilitySerializer(serializers.Serializer):
    """Output for free medical appointment availability."""
    client = ClientSearchSerializer()
    service = serializers.DictField()


class FreeMedicalAppointmentCreateSerializer(serializers.Serializer):
    """Input for creating a free medical appointment."""
    branchId = serializers.IntegerField()
    dateTime = serializers.CharField()

    def validate_dateTime(self, value):
        from django.utils import dateparse
        from django.utils.timezone import is_naive
        fecha_hora = dateparse.parse_datetime(value)
        if fecha_hora and is_naive(fecha_hora):
            fecha_hora = timezone.make_aware(fecha_hora)
        if not fecha_hora:
            raise serializers.ValidationError("Formato de fecha/hora inválido.")
        return value
