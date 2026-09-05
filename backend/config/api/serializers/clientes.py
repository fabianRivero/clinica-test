"""
Serializers for client-related DRF endpoints.
Domain 6 of Phase 6 — Clientes, Operaciones (reservations), CitasMedicasLibres.
"""

from rest_framework import serializers
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Prefetch
from django.utils import timezone

from accounts.models import Usuario
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
    email = serializers.CharField(source="usuario.email", default="")
    clienteCodigo = serializers.CharField(default="")
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
    patientId = serializers.IntegerField()
    procedure = serializers.CharField()
    serviceType = serializers.CharField()
    branch = serializers.CharField()
    status = serializers.CharField()
    statusTone = serializers.CharField()
    price = serializers.CharField()
    zone = serializers.CharField()
    startedAt = serializers.CharField()
    startedAtIso = serializers.CharField(allow_null=True, required=False)
    endedAt = serializers.CharField()
    nextAppointment = serializers.CharField()
    recommendations = serializers.CharField()
    details = serializers.CharField()
    sessions = serializers.DictField()
    availableAppointments = serializers.IntegerField()
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
    # ISO timestamp of the payment creation — used by the date-range
    # filter on the client detail payments blocks. ``submittedAt`` is
    # the human-readable label and is shown in the table; this is the
    # only field the filter can compare against.
    createdAt = serializers.CharField()
    bank = serializers.CharField()
    status = serializers.CharField()
    statusTone = serializers.CharField()
    quota = serializers.CharField()
    quotaLabel = serializers.CharField()
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
    """Input for creating a reservation on an operation.

    All fields beyond ``branchId`` and ``dateTime`` are optional — see the
    appointment-reservation-redesign spec. The reservation MUST succeed even
    when none of the new fields are provided.
    """
    branchId = serializers.IntegerField()
    dateTime = serializers.CharField()  # ISO datetime string

    # Planning fields (all optional).
    duracionEstimadaMinutos = serializers.IntegerField(
        required=False,
        allow_null=True,
        validators=[
            MinValueValidator(1, message="La duracion estimada debe ser al menos 1 minuto."),
            MaxValueValidator(480, message="La duracion estimada no puede superar los 480 minutos (8 horas)."),
        ],
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

    def validate_dateTime(self, value):
        from django.utils import dateparse
        from django.utils.timezone import is_naive
        fecha_hora = dateparse.parse_datetime(value)
        if fecha_hora and is_naive(fecha_hora):
            fecha_hora = timezone.make_aware(fecha_hora)
        if not fecha_hora:
            raise serializers.ValidationError("Formato de fecha/hora inválido.")
        return value

    def validate_maquinariaPlanificada(self, value):
        cleaned = []
        for idx, item in enumerate(value or []):
            if not isinstance(item, dict):
                raise serializers.ValidationError(
                    f"maquinariaPlanificada[{idx}] debe ser un objeto."
                )
            mid = item.get("maquinariaId")
            cant = item.get("cantidad", 1)
            try:
                mid = int(mid) if mid is not None else None
            except (TypeError, ValueError):
                raise serializers.ValidationError(
                    f"maquinariaPlanificada[{idx}].maquinariaId invalido."
                )
            try:
                cant = int(cant)
            except (TypeError, ValueError):
                raise serializers.ValidationError(
                    f"maquinariaPlanificada[{idx}].cantidad invalida."
                )
            if mid is None:
                raise serializers.ValidationError(
                    f"maquinariaPlanificada[{idx}].maquinariaId es obligatorio."
                )
            if cant < 1:
                raise serializers.ValidationError(
                    f"maquinariaPlanificada[{idx}].cantidad debe ser >= 1."
                )
            cleaned.append({"maquinariaId": mid, "cantidad": cant})
        return cleaned


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


# =============================================================================
# Admin Client Profile Editing (Slice 1 — backend foundation)
# =============================================================================
#
# Change: reactivacion-perfil-cliente
#
# This serializer is the single source of truth for the 13 contract fields
# the modal can PATCH against ``/api/admin/clientes/<id>/perfil/``. The
# response envelope is built by ``config.prospect_conversion_views._build_initial_client_user_data``
# so the modal and the reactivation wizard share one camelCase shape; the
# field set here intentionally mirrors that shape (plus ``hasPassword``)
# for reviewers reading the contract.
#
# Field ownership (see design.md / proposal.md for the full rationale):
#
#   primerNombre, segundoNombre, apellidoPaterno, apellidoMaterno, username,
#   email -> instance.usuario (OneToOne, always present)
#   telefono                            -> instance.usuario.telefono AND
#                                         instance.telefono (sync, both saved)
#   fechaNacimiento                     -> instance.fecha_nacimiento ONLY
#                                         (Usuario.fecha_nacimiento is intentionally
#                                          not mirrored; finalize never wrote it,
#                                          the serializer keeps parity)
#   ci, nroHijos, direccionDomicilio,
#   ocupacion, observacionesCliente     -> instance
#
# PATCH semantics: every field is optional; omitted fields keep their value.
# ``password`` is NOT a field on the serializer, so any payload that includes
# it is rejected by the explicit ``validate()`` guard below.
# -----------------------------------------------------------------------------


class AdminClientProfileWriteSerializer(serializers.Serializer):
    """Partial-update serializer for the admin live-client-profile endpoint.

    Mirrors ``_build_initial_client_user_data(cliente)`` keys so the modal can
    hydrate from one source of truth (``hasPassword`` is added by the helper,
    not by this serializer — see ``ClientesViewSet.perfil``).
    """

    primerNombre = serializers.CharField(max_length=80, required=False, allow_blank=True)
    segundoNombre = serializers.CharField(max_length=80, required=False, allow_blank=True)
    apellidoPaterno = serializers.CharField(max_length=80, required=False, allow_blank=True)
    apellidoMaterno = serializers.CharField(max_length=80, required=False, allow_blank=True)
    ci = serializers.CharField(max_length=30, required=False, allow_blank=True)
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    telefono = serializers.CharField(max_length=30, required=False, allow_blank=True)
    fechaNacimiento = serializers.DateField(required=False, allow_null=True)
    nroHijos = serializers.IntegerField(required=False, min_value=0, default=0)
    ocupacion = serializers.CharField(max_length=120, required=False, allow_blank=True)
    direccionDomicilio = serializers.CharField(max_length=255, required=False, allow_blank=True)
    observacionesCliente = serializers.CharField(required=False, allow_blank=True)

    # Map of camelCase input -> snake_case Usuario attribute.
    # Kept as a class attribute so reviewers can see the field-ownership
    # contract without reading update().
    USER_FIELDS = {
        "primerNombre": "primer_nombre",
        "segundoNombre": "segundo_nombre",
        "apellidoPaterno": "apellido_paterno",
        "apellidoMaterno": "apellido_materno",
        "username": "username",
        "email": "email",
    }
    # Map of camelCase input -> snake_case Cliente attribute.
    CLIENTE_FIELDS = {
        "ci": "ci",
        "fechaNacimiento": "fecha_nacimiento",
        "nroHijos": "nro_hijos",
        "direccionDomicilio": "direccion_domicilio",
        "ocupacion": "ocupacion",
        "observacionesCliente": "observaciones",
    }

    def validate(self, attrs):
        # Belt-and-braces: ``password`` is intentionally not declared as a
        # field, so DRF would otherwise silently drop it. Explicit reject
        # returns a clear 400 instead.
        if "password" in self.initial_data:
            raise serializers.ValidationError(
                {"password": "password is not editable through this endpoint"}
            )
        # Reject any key that is not one of the 13 declared contract fields.
        # DRF's default Serializer.run_validation silently drops unknown
        # keys; the spec requires a 400 instead so misbehaving clients get
        # loud feedback. ``hasPassword`` is intentionally tolerated because
        # the modal may send it back from the response shape and it is
        # informational only (no live side effect).
        declared = set(self.fields.keys())
        allowed_extras = {"hasPassword"}
        for key in self.initial_data.keys():
            if key in declared or key in allowed_extras:
                continue
            raise serializers.ValidationError(
                {key: f"Unknown field '{key}'. Only the 13 declared profile fields are editable."}
            )
        return attrs

    def validate_username(self, value):
        # Empty string is allowed (the field is optional + allow_blank), but
        # when present the username must be unique across all Usuario rows
        # except the one attached to the current Cliente.
        if not value:
            return value
        instance = self.instance
        qs = Usuario.objects.filter(username=value)
        if instance is not None and getattr(instance, "usuario_id", None) is not None:
            qs = qs.exclude(pk=instance.usuario_id)
        if qs.exists():
            raise serializers.ValidationError(
                "El nombre de usuario ya esta en uso."
            )
        return value

    def validate_ci(self, value):
        # CI uniqueness check excludes the current row. Empty CI is allowed
        # (matches the existing model convention — ``Cliente.ci`` is
        # ``blank=True`` and not ``unique=True``; we only protect against
        # collisions when the admin explicitly types a value).
        if not value:
            return value
        instance = self.instance
        qs = Cliente.objects.filter(ci=value)
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Ya existe otro cliente con ese CI."
            )
        return value

    def update(self, instance, validated_data):
        """Dispatch each accepted field to its owning row.

        Wrapped in ``transaction.atomic`` at the view layer so any
        failure (e.g. an unexpected DB constraint) rolls back the whole
        write — the modal must never see a half-applied profile.
        """
        user = instance.usuario  # OneToOne, always present on Cliente.

        for camel, snake in self.USER_FIELDS.items():
            if camel in validated_data:
                setattr(user, snake, validated_data[camel])

        if "telefono" in validated_data:
            value = validated_data["telefono"] or ""
            user.telefono = value
            instance.telefono = value

        for camel, snake in self.CLIENTE_FIELDS.items():
            if camel in validated_data:
                setattr(instance, snake, validated_data[camel])

        user.save()
        instance.save()
        return instance

