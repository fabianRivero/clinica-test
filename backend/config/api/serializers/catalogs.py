"""
Catalog serializers for DRF migration.
Domain 1 of Phase 6.
"""

from rest_framework import serializers

from catalogs.models import (
    TipoServicio,
    ProcEstetico,
    ProcEsteticosTipo,
    ServicioConfig,
    GrupoOpciones,
    OpcionCatalogo,
)
from billing.models import CategoriaGasto
from staff.models import Especialidad
from clinical.models import FichaCampo, FichaSeccion


# ---------------------------------------------------------------------------
# Shared base serializers
# ---------------------------------------------------------------------------

class CatalogoEditableSerializer(serializers.ModelSerializer):
    """Base serializer for models using CatalogoEditableModel (descripcion, orden, activo)."""

    class Meta:
        abstract = True


class TimeStampedSerializer(serializers.ModelSerializer):
    """Base serializer for models using TimeStampedModel."""

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# TipoServicio
# ---------------------------------------------------------------------------

class TipoServicioSerializer(CatalogoEditableSerializer):
    class Meta:
        model = TipoServicio
        fields = ["id", "tipo", "descripcion", "orden", "activo"]


class TipoServicioCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoServicio
        fields = ["tipo", "descripcion", "orden"]

    def validate_tipo(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("El tipo debe tener al menos 2 caracteres.")
        return value


# ---------------------------------------------------------------------------
# ProcEsteticosTipo
# ---------------------------------------------------------------------------

class ProcEsteticosTipoSerializer(CatalogoEditableSerializer):
    class Meta:
        model = ProcEsteticosTipo
        fields = ["id", "tipo", "descripcion", "orden", "activo"]


# ---------------------------------------------------------------------------
# ProcEstetico
# ---------------------------------------------------------------------------

class ProcEsteticoSerializer(CatalogoEditableSerializer):
    tipo_p_estetico_nombre = serializers.CharField(source="tipo_p_estetico.tipo", read_only=True)

    class Meta:
        model = ProcEstetico
        fields = ["id", "proceso", "tipo_p_estetico", "tipo_p_estetico_nombre", "descripcion", "orden", "activo"]


class ProcEsteticoCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcEstetico
        fields = ["proceso", "tipo_p_estetico", "descripcion", "orden"]

    def validate_proceso(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("El proceso debe tener al menos 2 caracteres.")
        return value


# ---------------------------------------------------------------------------
# ServicioConfig
# ---------------------------------------------------------------------------

class ServicioConfigSerializer(serializers.ModelSerializer):
    tipo_servicio_tipo = serializers.CharField(source="tipo_servicio.tipo", read_only=True)
    proc_estetico_proceso = serializers.CharField(source="proc_estetico.proceso", read_only=True)
    proc_estetico_tipo = serializers.CharField(source="proc_estetico.tipo_p_estetico.tipo", read_only=True)
    operaciones_count = serializers.IntegerField(source="operaciones.count", read_only=True)

    class Meta:
        model = ServicioConfig
        fields = [
            "id", "tipo_servicio", "tipo_servicio_tipo",
            "proc_estetico", "proc_estetico_proceso", "proc_estetico_tipo",
            "precio_base", "activo", "operaciones_count",
            "created_at", "updated_at",
        ]


class ServicioConfigCreateSerializer(serializers.ModelSerializer):
    serviceTypeId = serializers.IntegerField(write_only=True)
    procedureId = serializers.IntegerField(required=False, allow_null=True)
    basePrice = serializers.DecimalField(max_digits=10, decimal_places=2, write_only=True)

    class Meta:
        model = ServicioConfig
        fields = ["serviceTypeId", "procedureId", "basePrice"]

    def validate_serviceTypeId(self, value):
        if not TipoServicio.objects.filter(pk=value, activo=True).exists():
            raise serializers.ValidationError("Tipo de servicio no encontrado o inactivo.")
        return value

    def validate_procedureId(self, value):
        if value is not None and not ProcEstetico.objects.filter(pk=value, activo=True).exists():
            raise serializers.ValidationError("Procedimiento no encontrado o inactivo.")
        return value

    def validate_basePrice(self, value):
        if value < 0:
            raise serializers.ValidationError("El precio base no puede ser negativo.")
        return value

    def create(self, validated_data):
        tipo_servicio_id = validated_data.pop("serviceTypeId")
        proc_estetico_id = validated_data.pop("procedureId", None)
        precio_base = validated_data.pop("basePrice")

        tipo_servicio = TipoServicio.objects.get(pk=tipo_servicio_id)
        proc_estetico = ProcEstetico.objects.get(pk=proc_estetico_id) if proc_estetico_id else None

        return ServicioConfig.objects.create(
            tipo_servicio=tipo_servicio,
            proc_estetico=proc_estetico,
            precio_base=precio_base,
        )


# ---------------------------------------------------------------------------
# Especialidad
# ---------------------------------------------------------------------------

class EspecialidadSerializer(CatalogoEditableSerializer):
    especialistas_count = serializers.SerializerMethodField()

    class Meta:
        model = Especialidad
        fields = ["id", "nombre", "descripcion", "orden", "activo", "especialistas_count"]

    def get_especialistas_count(self, obj):
        return obj.especialistas_rel.count()


class EspecialidadCreateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(write_only=True)
    description = serializers.CharField(required=False, allow_blank=True, write_only=True)
    order = serializers.IntegerField(required=False, write_only=True)

    class Meta:
        model = Especialidad
        fields = ["name", "description", "order"]

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("El nombre debe tener al menos 2 caracteres.")
        return value

    def create(self, validated_data):
        return Especialidad.objects.create(
            nombre=validated_data["name"],
            descripcion=validated_data.get("description", ""),
            orden=validated_data.get("order", 0),
        )


# ---------------------------------------------------------------------------
# GrupoOpciones
# ---------------------------------------------------------------------------

class OpcionCatalogoSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpcionCatalogo
        fields = ["id", "codigo", "nombre", "valor", "orden", "activo"]


class GrupoOpcionesSerializer(serializers.ModelSerializer):
    opciones_activas = serializers.IntegerField(source="opciones.filter(activo=True).count", read_only=True)
    opciones_total = serializers.IntegerField(source="opciones.count", read_only=True)

    class Meta:
        model = GrupoOpciones
        fields = ["id", "codigo", "nombre", "descripcion", "activo", "opciones_activas", "opciones_total"]


class GrupoOpcionesCreateSerializer(serializers.ModelSerializer):
    code = serializers.CharField(write_only=True)
    name = serializers.CharField(write_only=True)
    description = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = GrupoOpciones
        fields = ["code", "name", "description"]

    def validate_code(self, value):
        value = value.strip().upper()
        if len(value) < 2:
            raise serializers.ValidationError("El codigo debe tener al menos 2 caracteres.")
        return value

    def create(self, validated_data):
        return GrupoOpciones.objects.create(
            codigo=validated_data["code"],
            nombre=validated_data["name"],
            descripcion=validated_data.get("description", ""),
        )


# ---------------------------------------------------------------------------
# CategoriaGasto
# ---------------------------------------------------------------------------

class CategoriaGastoSerializer(CatalogoEditableSerializer):
    gastos_count = serializers.IntegerField(source="gastos.count", read_only=True)

    class Meta:
        model = CategoriaGasto
        fields = ["id", "nombre", "descripcion", "orden", "activo", "gastos_count"]


class CategoriaGastoCreateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(write_only=True)
    description = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = CategoriaGasto
        fields = ["name", "description"]

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("El nombre debe tener al menos 2 caracteres.")
        return value

    def create(self, validated_data):
        return CategoriaGasto.objects.create(
            nombre=validated_data["name"],
            descripcion=validated_data.get("description", ""),
        )