"""
Expense serializers for DRF migration.
Domain 2 of Phase 6.
"""

from decimal import Decimal
from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from rest_framework import serializers

from billing.models import CategoriaGasto, GastoSucursal
from catalogs.models import Sucursal


class CategoriaGastoListSerializer(serializers.ModelSerializer):
    """Used in category list endpoint."""

    class Meta:
        model = CategoriaGasto
        fields = ["id", "nombre", "descripcion", "activo"]


class GastoSucursalSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source="categoria.nombre", read_only=True)
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", read_only=True)
    registrado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = GastoSucursal
        fields = [
            "id", "fecha", "concepto", "unidades", "costo_unidad",
            "gasto_total", "proveedor", "detalles",
            "categoria", "categoria_nombre",
            "sucursal", "sucursal_nombre",
            "registrado_por", "registrado_por_nombre",
            "factura_url",
            "created_at", "updated_at",
        ]
        read_only_fields = ["gasto_total", "registrado_por"]

    def get_registrado_por_nombre(self, obj):
        if obj.registrado_por:
            return f"{obj.registrado_por.primer_nombre} {obj.registrado_por.apellido_paterno}"
        return "—"

    def get_factura_url(self, obj):
        if obj.factura:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.factura.url)
            return obj.factura.url
        return None


class GastoSucursalCreateSerializer(serializers.Serializer):
    """Serializer for creating/updating GastoSucursal via DRF."""

    fecha = serializers.DateField()
    concepto = serializers.CharField(max_length=180)
    unidades = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))
    costo_unidad = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))
    categoria_id = serializers.IntegerField()
    proveedor = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    detalles = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_categoria_id(self, value):
        if not CategoriaGasto.objects.filter(pk=value, activo=True).exists():
            raise serializers.ValidationError("Categoria no encontrada o inactiva.")
        return value

    def validate_unidades(self, value):
        if value <= 0:
            raise serializers.ValidationError("Las unidades deben ser mayores a 0.")
        return value

    def validate_costo_unidad(self, value):
        if value < 0:
            raise serializers.ValidationError("El costo no puede ser negativo.")
        return value

    def create(self, validated_data):
        categoria_id = validated_data.pop("categoria_id")
        categoria = CategoriaGasto.objects.get(pk=categoria_id)

        gasto_total = validated_data["unidades"] * validated_data["costo_unidad"]

        # branch and registrado_por come from the view via context
        branch = self.context.get("branch")
        user = self.context.get("user")

        return GastoSucursal.objects.create(
            sucursal=branch,
            categoria=categoria,
            registrado_por=user,
            gasto_total=gasto_total,
            **validated_data,
        )

    def update(self, instance, validated_data):
        categoria_id = validated_data.pop("categoria_id", None)
        if categoria_id is not None:
            instance.categoria_id = categoria_id

        for field in ["fecha", "concepto", "unidades", "costo_unidad", "proveedor", "detalles"]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])

        instance.gasto_total = instance.unidades * instance.costo_unidad
        instance.full_clean()
        instance.save()
        return instance


class ExpenseMetricsSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    value = serializers.CharField()
    delta = serializers.CharField()
    tone = serializers.CharField()