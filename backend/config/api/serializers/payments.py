"""
Payment serializers for DRF migration.
Domain 3 of Phase 6.
"""

from decimal import Decimal

from rest_framework import serializers

from billing.models import CuotaPlanPago, PagoRealizado, ConfiguracionPagoQR
from operations.models import Operacion


class PagoRealizadoCreateSerializer(serializers.Serializer):
    """Write serializer for both client and admin payment creation.

    ``clean()`` on the model is the authoritative validator; this
    serializer only catches shape errors early and derives
    ``monto_fisico`` / ``monto_virtual`` from ``monto_pagado`` when the
    method is ``VIRTUAL`` or ``FISICO``.

    The serializer is intentionally NOT a ``ModelSerializer``: write-side
    field requirements differ from the read shape (camelCase input keys,
    optional breakdown, optional receipt) and decoupling keeps the
    existing read serializer untouched.
    """
    paymentMethod = serializers.ChoiceField(choices=PagoRealizado.MetodoPago.choices)
    monto_pagado = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01")
    )
    montoFisico = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    montoVirtual = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    receiptFile = serializers.FileField(required=False, allow_null=True)
    details = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        method = attrs["paymentMethod"]
        fisico = attrs.get("montoFisico")
        virtual = attrs.get("montoVirtual")
        total = attrs["monto_pagado"]
        receipt = attrs.get("receiptFile")

        if method == PagoRealizado.MetodoPago.VIRTUAL:
            if not receipt:
                raise serializers.ValidationError(
                    {"receiptFile": "Debes adjuntar el comprobante."}
                )
            attrs["montoVirtual"] = total
            attrs["montoFisico"] = Decimal("0")
        elif method == PagoRealizado.MetodoPago.FISICO:
            attrs["montoFisico"] = total
            attrs["montoVirtual"] = Decimal("0")
        else:  # MIXTO
            if not fisico or not virtual or fisico <= 0 or virtual <= 0:
                raise serializers.ValidationError(
                    "Para pagos MIXTO debes indicar montoFisico y montoVirtual mayores a 0."
                )
            if fisico + virtual != total:
                raise serializers.ValidationError(
                    "montoFisico + montoVirtual debe ser igual a monto_pagado."
                )
        return attrs


class PagoRealizadoSerializer(serializers.ModelSerializer):
    """Read serializer for PagoRealizado with nested relations."""
    cliente_nombre = serializers.SerializerMethodField()
    procedimiento = serializers.CharField(source="cuota.operacion.servicio_config.proc_estetico.proceso", read_only=True)
    verificado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = PagoRealizado
        fields = [
            "id", "monto_pagado", "metodo_pago", "monto_fisico", "monto_virtual",
            "comprobante_url", "estado_verificacion",
            "verificado", "verificado_por", "verificado_por_nombre",
            "fecha_verificacion", "detalles_pago", "observacion_verificacion",
            "cliente_nombre", "procedimiento",
            "created_at",
        ]

    def get_cliente_nombre(self, obj):
        if obj.cuota and obj.cuota.operacion and obj.cuota.operacion.paciente:
            u = obj.cuota.operacion.paciente.usuario
            return f"{u.primer_nombre} {u.apellido_paterno}"
        return "—"

    def get_verificado_por_nombre(self, obj):
        if obj.verificado_por:
            return f"{obj.verificado_por.primer_nombre} {obj.verificado_por.apellido_paterno}"
        return None


class CuotaPlanPagoSerializer(serializers.ModelSerializer):
    """Read serializer for CuotaPlanPago with nested relations."""
    paciente_nombre = serializers.SerializerMethodField()
    procedimiento = serializers.CharField(source="operacion.servicio_config.proc_estetico.proceso", read_only=True)
    pagos_count = serializers.IntegerField(source="pagos_realizados.count", read_only=True)

    class Meta:
        model = CuotaPlanPago
        fields = [
            "id", "nro_cuota", "fecha_vencimiento", "monto_programado", "estado",
            "paciente_nombre", "procedimiento", "pagos_count",
            "created_at", "updated_at",
        ]

    def get_paciente_nombre(self, obj):
        if obj.operacion and obj.operacion.paciente and obj.operacion.paciente.usuario:
            u = obj.operacion.paciente.usuario
            return f"{u.primer_nombre} {u.apellido_paterno}"
        return "—"


class ConfiguracionPagoQRSerializer(serializers.ModelSerializer):
    """Read serializer for QR config."""
    sucursal = serializers.PrimaryKeyRelatedField(read_only=True)
    imagen_qr_url = serializers.SerializerMethodField()

    class Meta:
        model = ConfiguracionPagoQR
        fields = ["id", "sucursal", "instrucciones", "imagen_qr_url", "updated_at"]

    def get_imagen_qr_url(self, obj):
        if obj.imagen_qr:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.imagen_qr.url)
            return obj.imagen_qr.url
        return None


class PaymentStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating payment verification status."""
    status = serializers.ChoiceField(choices=PagoRealizado.EstadoVerificacion.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_status(self, value):
        if value not in {choice[0] for choice in PagoRealizado.EstadoVerificacion.choices}:
            raise serializers.ValidationError("Estado no valido.")
        return value