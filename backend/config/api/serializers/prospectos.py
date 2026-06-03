"""
Serializers for prospect-related DRF endpoints.
Domain 7 of Phase 6 — Prospects + Conversion Wizard.
"""

from rest_framework import serializers

from customers.models import Prospecto, ProspectoConversionBorrador
from operations.models import CitaProspecto


# =============================================================================
# Prospect List / Search
# =============================================================================

class ProspectListSerializer(serializers.Serializer):
    """Serializer for a prospect item in list."""
    id = serializers.IntegerField(source="pk")
    name = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()
    registeredAt = serializers.SerializerMethodField()
    branchName = serializers.SerializerMethodField()
    registeredBy = serializers.SerializerMethodField()

    def get_name(self, obj):
        parts = [obj.primer_nombre, obj.segundo_nombre, obj.apellido_paterno, obj.apellido_materno]
        return " ".join(p for p in parts if p)

    def get_phone(self, obj):
        return obj.telefono or "Sin teléfono"

    def get_state(self, obj):
        return obj.get_estado_display()

    def get_registeredAt(self, obj):
        return obj.created_at.isoformat() if obj.created_at else ""

    def get_branchName(self, obj):
        return obj.sucursal_registro.nombre if obj.sucursal_registro else "Sin sucursal"

    def get_registeredBy(self, obj):
        return obj.registrado_por.nombre_completo if obj.registrado_por else "Sistema"


# =============================================================================
# Prospect Create / Update
# =============================================================================

class ProspectCreateSerializer(serializers.Serializer):
    """Input for creating a new prospect."""
    primerNombre = serializers.CharField(max_length=60, required=True)
    segundoNombre = serializers.CharField(max_length=60, required=False, default="")
    apellidoPaterno = serializers.CharField(max_length=60, required=True)
    apellidoMaterno = serializers.CharField(max_length=60, required=False, default="")
    telefono = serializers.CharField(max_length=20, required=False, default="")
    observaciones = serializers.CharField(required=False, default="")
    estado = serializers.CharField(required=False, default="PASAJERO")

    def validate_estado(self, value):
        valid = {Prospecto.Estado.PASAJERO, Prospecto.Estado.DESCARTADO}
        if value not in valid:
            raise serializers.ValidationError("Solo puedes crear prospectos en estado pasajero o descartado.")
        return value


class ProspectUpdateSerializer(serializers.Serializer):
    """Input for updating a prospect."""
    primerNombre = serializers.CharField(max_length=60, required=False)
    segundoNombre = serializers.CharField(max_length=60, required=False)
    apellidoPaterno = serializers.CharField(max_length=60, required=False)
    apellidoMaterno = serializers.CharField(max_length=60, required=False)
    telefono = serializers.CharField(max_length=20, required=False)
    observaciones = serializers.CharField(required=False)
    estado = serializers.CharField(required=False)

    def validate_estado(self, value):
        if value and value not in {Prospecto.Estado.PASAJERO, Prospecto.Estado.DESCARTADO}:
            raise serializers.ValidationError("El estado seleccionado no es valido para este prospecto.")
        return value


class ProspectMigrateSerializer(serializers.Serializer):
    """Input for migrating a prospect to a different branch."""
    branchId = serializers.IntegerField(required=True)

    def validate_branchId(self, value):
        from catalogs.models import Sucursal
        if not Sucursal.objects.filter(pk=value).exists():
            raise serializers.ValidationError("La sucursal no existe.")
        return value


# =============================================================================
# Prospect Duplicate Check
# =============================================================================

class ProspectDuplicateCheckSerializer(serializers.Serializer):
    """Input for checking duplicate prospects."""
    primerNombre = serializers.CharField(max_length=60, required=True)
    segundoNombre = serializers.CharField(max_length=60, required=False, default="")
    apellidoPaterno = serializers.CharField(max_length=60, required=True)
    apellidoMaterno = serializers.CharField(max_length=60, required=False, default="")
    telefono = serializers.CharField(max_length=20, required=False, default="")


# =============================================================================
# Prospect Medical Appointment
# =============================================================================

class ProspectMedicalAvailabilitySerializer(serializers.Serializer):
    """Output for prospect medical appointment availability."""
    prospect = ProspectListSerializer()
    service = serializers.DictField()
    calendar = serializers.DictField()


class ProspectMedicalAppointmentCreateSerializer(serializers.Serializer):
    """Input for creating a medical appointment for a prospect."""
    branchId = serializers.IntegerField(required=True)
    dateTime = serializers.CharField(required=True)

    def validate_dateTime(self, value):
        from django.utils import dateparse
        from django.utils.timezone import is_naive
        fecha_hora = dateparse.parse_datetime(value)
        if fecha_hora and is_naive(fecha_hora):
            fecha_hora = timezone.make_aware(fecha_hora)
        if not fecha_hora:
            raise serializers.ValidationError("Formato de fecha/hora invalido.")
        return value


class ProspectAppointmentUpdateSerializer(serializers.Serializer):
    """Input for updating a prospect appointment status."""
    status = serializers.CharField(required=True)

    def validate_status(self, value):
        if value not in CitaProspecto.Estado.values:
            raise serializers.ValidationError("Estado de cita invalido.")
        return value
