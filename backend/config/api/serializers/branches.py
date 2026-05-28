"""
Branch serializers for DRF migration.
Domain 5 of Phase 6.
"""

from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError

from rest_framework import serializers

from catalogs.models import Sucursal
from accounts.models import Usuario, Rol
from operations.models import BranchAdminAuditLog, TabletKiosko


# ---------------------------------------------------------------------------
# Branch serializers
# ---------------------------------------------------------------------------

class BranchSerializer(serializers.ModelSerializer):
    """Read serializer for Sucursal."""
    admin = serializers.SerializerMethodField()

    class Meta:
        model = Sucursal
        fields = [
            "id", "nombre", "ciudad", "direccion", "es_principal", "activa",
            "especialistas_pueden_abrir_fichas",
        ]

    def get_admin(self, obj):
        admin = Usuario.objects.filter(
            rol__rol="ADMIN_SUCURSAL",
            is_active=True,
            sucursal=obj,
        ).first()
        if admin:
            return {
                "id": admin.pk,
                "nombre": admin.nombre_completo,
                "username": admin.username,
            }
        return None


class BranchCreateSerializer(serializers.Serializer):
    """Serializer for creating a branch (simple form)."""
    nombre = serializers.CharField(max_length=120)
    ciudad = serializers.CharField(max_length=100, required=False, default="")
    direccion = serializers.CharField(max_length=255, required=False, default="")
    esPrincipal = serializers.BooleanField(default=False)
    especialistasPuedenAbrirFichas = serializers.BooleanField(default=True)

    def validate_nombre(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("El nombre debe tener al menos 2 caracteres.")
        return value

    def create(self, validated_data):
        return Sucursal.objects.create(
            nombre=validated_data["nombre"],
            ciudad=validated_data.get("ciudad", ""),
            direccion=validated_data.get("direccion", ""),
            es_principal=validated_data.get("esPrincipal", False),
            especialistas_pueden_abrir_fichas=validated_data.get("especialistasPuedenAbrirFichas", True),
            activa=True,
        )


class BranchUpdateSerializer(serializers.Serializer):
    """Serializer for updating a branch."""
    nombre = serializers.CharField(max_length=120, required=False)
    ciudad = serializers.CharField(max_length=100, required=False)
    direccion = serializers.CharField(max_length=255, required=False)
    esPrincipal = serializers.BooleanField(required=False)
    especialistasPuedenAbrirFichas = serializers.BooleanField(required=False)

    def update(self, instance, validated_data):
        for field in ("nombre", "ciudad", "direccion"):
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        if "esPrincipal" in validated_data:
            instance.es_principal = validated_data["esPrincipal"]
        if "especialistasPuedenAbrirFichas" in validated_data:
            instance.especialistas_pueden_abrir_fichas = validated_data["especialistasPuedenAbrirFichas"]
        instance.save()
        return instance


class BranchToggleSerializer(serializers.Serializer):
    """Serializer for toggling branch active state."""
    active = serializers.BooleanField()
    force = serializers.BooleanField(default=False)


class BranchDeactivationImpactSerializer(serializers.Serializer):
    """Serializer for deactivation impact response."""
    pendingAppointments = serializers.IntegerField()
    pendingOperations = serializers.IntegerField()
    pendingProspectAppointments = serializers.IntegerField()
    pendingPayments = serializers.IntegerField()


# ---------------------------------------------------------------------------
# Branch Admin Change serializers
# ---------------------------------------------------------------------------

class BranchChangeAdminSerializer(serializers.Serializer):
    """Serializer for changing branch admin."""
    newAdminUserId = serializers.IntegerField()

    def validate_newAdminUserId(self, value):
        try:
            user = Usuario.objects.get(pk=value)
        except Usuario.DoesNotExist:
            raise serializers.ValidationError("Usuario no encontrado.")
        if not (user.rol and user.rol.rol == "ADMIN_SUCURSAL"):
            raise serializers.ValidationError("El usuario seleccionado no es admin de sucursal.")
        return value


# ---------------------------------------------------------------------------
# Branch Wizard serializers
# ---------------------------------------------------------------------------

class BranchWizardStep1Serializer(serializers.Serializer):
    """Serializer for wizard step 1 — branch data."""
    nombre = serializers.CharField(max_length=120)
    ciudad = serializers.CharField(max_length=100, required=False, default="")
    direccion = serializers.CharField(max_length=255, required=False, default="")
    esPrincipal = serializers.BooleanField(default=False)
    especialistasPuedenAbrirFichas = serializers.BooleanField(default=True)

    def validate_nombre(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("El nombre debe tener al menos 2 caracteres.")
        if Sucursal.objects.filter(nombre__iexact=value).exists():
            raise serializers.ValidationError("Ya existe una sucursal con este nombre.")
        return value


class BranchWizardStep2Serializer(serializers.Serializer):
    """Serializer for wizard step 2 — admin assignment."""
    mode = serializers.ChoiceField(choices=["existing_inactive", "create_new"])

    # For existing_inactive mode
    adminUserId = serializers.IntegerField(required=False)

    # For create_new mode
    username = serializers.CharField(max_length=150, required=False)
    primerNombre = serializers.CharField(max_length=80, required=False)
    segundoNombre = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    apellidoPaterno = serializers.CharField(max_length=80, required=False)
    apellidoMaterno = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    ci = serializers.CharField(max_length=30, required=False)
    telefono = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(max_length=128, required=False)

    def validate(self, data):
        mode = data.get("mode")
        if mode == "existing_inactive":
            if not data.get("adminUserId"):
                raise serializers.ValidationError({"adminUserId": "Obligatorio para existing_inactive."})
            try:
                user = Usuario.objects.get(pk=data["adminUserId"])
                if not (user.rol and user.rol.rol == "ADMIN_SUCURSAL"):
                    raise serializers.ValidationError({"adminUserId": "El usuario no es admin de sucursal."})
                if user.is_active or user.sucursal_id is not None:
                    raise serializers.ValidationError({"adminUserId": "El admin debe estar inactivo y sin sucursal."})
            except Usuario.DoesNotExist:
                raise serializers.ValidationError({"adminUserId": "Usuario no encontrado."})
        elif mode == "create_new":
            required = ["username", "primerNombre", "apellidoPaterno", "ci", "password"]
            for field in required:
                if not data.get(field):
                    raise serializers.ValidationError({field: "Este campo es obligatorio."})
            if Usuario.objects.filter(username=data["username"]).exists():
                raise serializers.ValidationError({"username": "Este nombre de usuario ya existe."})
        return data


class BranchWizardFinalizeSerializer(serializers.Serializer):
    """Serializer for wizard finalize."""
    nombre = serializers.CharField(max_length=120)
    clave = serializers.CharField(max_length=50)


# ---------------------------------------------------------------------------
# Audit log serializer
# ---------------------------------------------------------------------------

class BranchAuditLogSerializer(serializers.ModelSerializer):
    """Read serializer for BranchAdminAuditLog."""
    branch_nombre = serializers.CharField(source="branch.nombre", read_only=True)
    actor_nombre = serializers.SerializerMethodField()

    class Meta:
        model = BranchAdminAuditLog
        fields = ["id", "created_at", "action", "detail", "branch_id", "branch_nombre", "actor", "actor_nombre", "metadata"]

    def get_actor_nombre(self, obj):
        return obj.actor.nombre_completo if obj.actor else "Sistema"