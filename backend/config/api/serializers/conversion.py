"""
Serializers for prospect conversion wizard.
Domain 7 of Phase 6 — Conversion Wizard (Prospect → Client).

These serializers handle the 5-step wizard:
- paso-1: User/client data
- paso-2: Operation/treatment plan
- paso-3: Medical form (ficha médica)
- paso-4: Biometric data
- finalize: Complete conversion

The validation logic lives in config.prospect_conversion_views helpers.
These serializers are thin: they accept the payload and let the existing
validation functions handle the details.
"""

from rest_framework import serializers


class WizardStep1UserSerializer(serializers.Serializer):
    """Serializer for conversion wizard step 1 — user/client data."""
    primerNombre = serializers.CharField(max_length=60, required=True)
    segundoNombre = serializers.CharField(max_length=60, required=False, default="")
    apellidoPaterno = serializers.CharField(max_length=60, required=True)
    apellidoMaterno = serializers.CharField(max_length=60, required=False, default="")
    username = serializers.CharField(max_length=30, required=True)
    password = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    telefono = serializers.CharField(max_length=20, required=False, default="")
    ci = serializers.CharField(max_length=20, required=False, default="")
    fechaNacimiento = serializers.CharField(required=False, default="")
    nroHijos = serializers.IntegerField(required=False, default=0)
    direccionDomicilio = serializers.CharField(required=False, default="")
    ocupacion = serializers.CharField(required=False, default="")
    observacionesCliente = serializers.CharField(required=False, default="")


class WizardStep2OperationSerializer(serializers.Serializer):
    """Serializer for conversion wizard step 2 — operation/treatment plan."""
    serviceConfigId = serializers.IntegerField(required=True, min_value=1)
    precioTotal = serializers.DecimalField(max_digits=12, decimal_places=2, required=True, min_value=0.01)
    cuotasTotales = serializers.IntegerField(required=True, min_value=1)
    sesionesTotales = serializers.IntegerField(required=True, min_value=1)
    fechaInicio = serializers.CharField(required=True)
    fechaFinal = serializers.CharField(required=False, default="")
    estado = serializers.CharField(required=False, default="EN_PROCESO")
    zonaGeneral = serializers.CharField(required=True)
    zonaEspecifica = serializers.CharField(required=True)
    detallesOperacion = serializers.CharField(required=False, default="")
    recomendaciones = serializers.CharField(required=False, default="")
    fechasVencimientoCuotas = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )


class WizardStep3MedicalSerializer(serializers.Serializer):
    """Serializer for conversion wizard step 3 — medical form (ficha médica)."""
    fechaFicha = serializers.CharField(required=True)
    motivoConsulta = serializers.CharField(required=False, default="")
    observaciones = serializers.CharField(required=False, default="")
    consentimientoAceptado = serializers.BooleanField(required=False, default=False)
    firmaPacienteCi = serializers.CharField(required=False, default="")
    # Nested analysis data
    tipoPielId = serializers.IntegerField(required=False, allow_null=True)
    gradoDeshidratacionId = serializers.IntegerField(required=False, allow_null=True)
    grosorPielId = serializers.IntegerField(required=False, allow_null=True)
    patologiaIds = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    # Response fields (dynamic, based on procedure config)
    fieldResponses = serializers.DictField(required=False, default=dict)


class WizardStep4BiometricSerializer(serializers.Serializer):
    """Serializer for conversion wizard step 4 — biometric enrollment."""
    provider = serializers.CharField(required=False, default="MOCK")
    template = serializers.CharField(required=False, default="")
    quality = serializers.IntegerField(required=False, default=0)
    deviceSerial = serializers.CharField(required=False, default="")
    consentAccepted = serializers.BooleanField(required=False, default=True)


class ConversionFinalizeSerializer(serializers.Serializer):
    """
    Serializer for conversion finalize — no extra input needed.
    The draft already contains all step data. Finalize just needs
    the request with the PDF file attached.
    """
    pass
