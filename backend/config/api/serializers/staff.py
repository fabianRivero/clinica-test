"""
Staff serializers for DRF migration.
Domain 4 of Phase 6.
"""

from datetime import date

from django.db import IntegrityError
from django.core.exceptions import ValidationError

from rest_framework import serializers

from accounts.models import Usuario, Rol
from staff.models import Especialista, Especialidad, EspecialistaEspecialidad
from catalogs.models import Sucursal


# ---------------------------------------------------------------------------
# Branch Admin serializers
# ---------------------------------------------------------------------------

class BranchAdminSerializer(serializers.ModelSerializer):
    """Read serializer for branch admin users."""
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", read_only=True)
    rol_nombre = serializers.CharField(source="rol.rol", read_only=True)

    class Meta:
        model = Usuario
        fields = [
            "id", "username", "email", "primer_nombre", "segundo_nombre",
            "apellido_paterno", "apellido_materno", "telefono",
            "fecha_nacimiento", "is_active",
            "sucursal", "sucursal_nombre", "rol_nombre",
        ]


class BranchAdminCreateSerializer(serializers.Serializer):
    """Serializer for creating a branch admin user."""
    username = serializers.CharField(max_length=150)
    primerNombre = serializers.CharField(max_length=80)
    segundoNombre = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    apellidoPaterno = serializers.CharField(max_length=80)
    apellidoMaterno = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    password = serializers.CharField(max_length=128, write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    telefono = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    fechaNacimiento = serializers.DateField(required=False, allow_null=True)

    def validate_username(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("El username debe tener al menos 3 caracteres.")
        if Usuario.objects.filter(username=value).exists():
            raise serializers.ValidationError("Este nombre de usuario ya existe.")
        return value

    def validate_password(self, value):
        if len(value) < 6:
            raise serializers.ValidationError("La password debe tener al menos 6 caracteres.")
        return value

    def _capitalize(self, value):
        if not value:
            return ""
        return value.strip().capitalize()

    def create(self, validated_data):
        password = validated_data.pop("password")
        fecha_nacimiento = validated_data.pop("fechaNacimiento", None)

        user = Usuario(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            primer_nombre=self._capitalize(validated_data["primerNombre"]),
            segundo_nombre=self._capitalize(validated_data.get("segundoNombre", "")),
            apellido_paterno=self._capitalize(validated_data["apellidoPaterno"]),
            apellido_materno=self._capitalize(validated_data.get("apellidoMaterno", "")),
            telefono=validated_data.get("telefono", ""),
            fecha_nacimiento=fecha_nacimiento,
            rol=_get_branch_admin_role(),
            is_active=False,
            sucursal=None,
        )
        user.set_password(password)
        user.save()
        return user


class BranchAdminUpdateSerializer(serializers.Serializer):
    """Serializer for updating a branch admin."""
    username = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    telefono = serializers.CharField(max_length=30, required=False, allow_blank=True)
    fechaNacimiento = serializers.DateField(required=False, allow_null=True)
    password = serializers.CharField(max_length=128, write_only=True, required=False)

    def update(self, instance, validated_data):
        for field in ("username", "email", "telefono"):
            if field in validated_data:
                setattr(instance, field, (validated_data.get(field) or "").strip())

        if validated_data.get("fechaNacimiento") is not None:
            instance.fecha_nacimiento = validated_data["fechaNacimiento"]

        new_password = validated_data.get("password")
        if new_password:
            instance.set_password(new_password)

        instance.save()
        return instance


class BranchAdminToggleSerializer(serializers.Serializer):
    """Serializer for toggling branch admin active state."""
    active = serializers.BooleanField()

    def validate_active(self, value):
        return value


# ---------------------------------------------------------------------------
# Specialist/Staff serializers
# ---------------------------------------------------------------------------

class EspecialidadSerializer(serializers.ModelSerializer):
    """Read serializer for Especialidad catalog."""
    especialistas_count = serializers.IntegerField(source="especialistas_rel.count", read_only=True)

    class Meta:
        model = Especialidad
        fields = ["id", "nombre", "descripcion", "orden", "activo", "especialistas_count"]


class EspecialistaSerializer(serializers.ModelSerializer):
    """Read serializer for Especialista with nested user and specialties."""
    usuario_nombre = serializers.SerializerMethodField()
    especialidades = serializers.SerializerMethodField()
    sucursal_nombre = serializers.CharField(source="sucursal_base.nombre", read_only=True)
    is_active = serializers.BooleanField(source="usuario.is_active", read_only=True)

    class Meta:
        model = Especialista
        fields = [
            "id", "ci", "telefono", "observaciones", "puede_abrir_fichas",
            "is_active", "usuario_nombre", "sucursal_nombre", "especialidades",
        ]

    def get_usuario_nombre(self, obj):
        return obj.usuario.nombre_completo

    def get_especialidades(self, obj):
        return [rel.especialidad.nombre for rel in obj.especialidades_rel.all()]


class SpecialistCreateSerializer(serializers.Serializer):
    """Serializer for creating a specialist + user."""
    username = serializers.CharField(max_length=150)
    primerNombre = serializers.CharField(max_length=80)
    segundoNombre = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    apellidoPaterno = serializers.CharField(max_length=80)
    apellidoMaterno = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    telefono = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    fechaNacimiento = serializers.DateField(required=False, allow_null=True)
    ci = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")
    puedeAbrirFichas = serializers.BooleanField(default=True)
    specialtyIds = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    branchId = serializers.IntegerField(required=False, allow_null=True)

    def validate_username(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("El username debe tener al menos 3 caracteres.")
        if Usuario.objects.filter(username=value).exists():
            raise serializers.ValidationError("Este nombre de usuario ya existe.")
        return value

    def _capitalize(self, value):
        return value.strip().capitalize() if value else ""

    def create(self, validated_data):
        specialty_ids = validated_data.pop("specialtyIds", [])
        branch_id = validated_data.pop("branchId", None)

        user = Usuario(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            primer_nombre=self._capitalize(validated_data["primerNombre"]),
            segundo_nombre=self._capitalize(validated_data.get("segundoNombre", "")),
            apellido_paterno=self._capitalize(validated_data["apellidoPaterno"]),
            apellido_materno=self._capitalize(validated_data.get("apellidoMaterno", "")),
            telefono=validated_data.get("telefono", ""),
            fecha_nacimiento=validated_data.get("fechaNacimiento"),
            rol=_get_worker_role(),
            is_active=True,
        )
        user.set_password(validated_data["username"])  # Default password = username
        user.save()

        especialista = Especialista(
            usuario=user,
            ci=validated_data.get("ci", ""),
            telefono=validated_data.get("telefono", ""),
            observaciones=validated_data.get("observaciones", ""),
            puede_abrir_fichas=validated_data.get("puedeAbrirFichas", True),
            sucursal_base_id=branch_id,
        )
        especialista.save()

        if specialty_ids:
            EspecialistaEspecialidad.objects.bulk_create([
                EspecialistaEspecialidad(especialista=especialista, especialidad_id=sid)
                for sid in specialty_ids
            ])

        return especialista


class SpecialistUpdateSerializer(serializers.Serializer):
    """Serializer for updating a specialist."""
    telefono = serializers.CharField(max_length=30, required=False, allow_blank=True)
    observaciones = serializers.CharField(required=False, allow_blank=True)
    puedeAbrirFichas = serializers.BooleanField(required=False)
    specialtyIds = serializers.ListField(child=serializers.IntegerField(), required=False)
    branchId = serializers.IntegerField(required=False, allow_null=True)

    def update(self, instance, validated_data):
        for field in ("telefono", "observaciones"):
            if field in validated_data:
                setattr(instance, field, validated_data[field])

        if "puedeAbrirFichas" in validated_data:
            instance.puede_abrir_fichas = validated_data["puedeAbrirFichas"]

        if "branchId" in validated_data:
            instance.sucursal_base_id = validated_data["branchId"]

        instance.save()

        if "specialtyIds" in validated_data:
            instance.especialidades_rel.all().delete()
            EspecialistaEspecialidad.objects.bulk_create([
                EspecialistaEspecialidad(especialista=instance, especialidad_id=sid)
                for sid in validated_data["specialtyIds"]
            ])

        return instance


class SpecialistToggleSerializer(serializers.Serializer):
    """Serializer for toggling specialist active state."""
    active = serializers.BooleanField()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_branch_admin_role():
    return Rol.objects.get_or_create(rol="ADMIN_SUCURSAL")[0]


def _get_worker_role():
    return Rol.objects.get_or_create(rol="TRABAJADOR")[0]