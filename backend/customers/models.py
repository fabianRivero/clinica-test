from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel


class Prospecto(TimeStampedModel):
    class Estado(models.TextChoices):
        PASAJERO = "PASAJERO", "Pasajero"
        CONVERTIDO = "CONVERTIDO", "Convertido"
        DESCARTADO = "DESCARTADO", "Descartado"

    primer_nombre = models.CharField(max_length=120)
    segundo_nombre = models.CharField(max_length=120, blank=True, default="")
    apellido_paterno = models.CharField(max_length=120)
    apellido_materno = models.CharField(max_length=120, blank=True, default="")
    telefono = models.CharField(max_length=30, blank=True)

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PASAJERO,
    )
    observaciones = models.TextField(blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="prospectos_registrados",
        null=True,
        blank=True,
    )
    sucursal_registro = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.SET_NULL,
        related_name="prospectos_registrados",
        null=True,
        blank=True,
    )
    convertido_a_cliente = models.OneToOneField(
        "customers.Cliente",
        on_delete=models.SET_NULL,
        related_name="prospecto_origen",
        null=True,
        blank=True,
    )
    fecha_conversion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "prospectos"
        ordering = ("-created_at",)

    def marcar_como_convertido(self, cliente, save=True):
        self.estado = self.Estado.CONVERTIDO
        self.convertido_a_cliente = cliente
        self.fecha_conversion = timezone.now()
        if save:
            self.save(
                update_fields=[
                    "estado",
                    "convertido_a_cliente",
                    "fecha_conversion",
                    "updated_at",
                ]
            )

    def __str__(self):
        parts = [
            self.primer_nombre,
            self.segundo_nombre,
            self.apellido_paterno,
            self.apellido_materno,
        ]
        return " ".join(part for part in parts if part).strip()


class ProspectoConversionBorrador(TimeStampedModel):
    class Paso(models.IntegerChoices):
        DATOS_USUARIO = 1, "Datos de usuario"
        OPERACION = 2, "Operacion"
        FICHA_MEDICA = 3, "Ficha medica"
        BIOMETRIA = 4, "Biometria"

    prospecto = models.OneToOneField(
        "customers.Prospecto",
        on_delete=models.CASCADE,
        related_name="borrador_conversion",
        null=True,
        blank=True,
    )
    cliente = models.OneToOneField(
        "customers.Cliente",
        on_delete=models.CASCADE,
        related_name="borrador_reactivacion",
        null=True,
        blank=True,
    )
    iniciado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="conversiones_prospecto_iniciadas",
        null=True,
        blank=True,
    )
    paso_actual = models.PositiveSmallIntegerField(
        choices=Paso.choices,
        default=Paso.DATOS_USUARIO,
    )
    paso_usuario_completado = models.BooleanField(default=False)
    paso_operacion_completado = models.BooleanField(default=False)
    paso_ficha_completado = models.BooleanField(default=False)
    paso_biometria_completado = models.BooleanField(default=False)
    datos_usuario = models.JSONField(default=dict, blank=True)
    datos_operacion = models.JSONField(default=dict, blank=True)
    datos_ficha = models.JSONField(default=dict, blank=True)
    datos_biometria = models.JSONField(default=dict, blank=True)
    documento_pdf = models.FileField(upload_to="conversiones/borradores/", null=True, blank=True)

    class Meta:
        db_table = "prospectos_conversion_borrador"

    def __str__(self):
        return f"Borrador conversion - {self.prospecto}"


class Cliente(TimeStampedModel):
    class Estado(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        INACTIVO = "INACTIVO", "Inactivo"

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cliente",
    )
    sucursal_registro = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.SET_NULL,
        related_name="clientes_registrados",
        null=True,
        blank=True,
    )
    ci = models.CharField(max_length=30, blank=True)
    estado_cliente = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.INACTIVO,
    )
    bloqueo_reactivacion_automatica = models.BooleanField(default=False)

    fecha_nacimiento = models.DateField()
    nro_hijos = models.PositiveIntegerField(default=0)
    direccion_domicilio = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    ocupacion = models.CharField(max_length=120, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        db_table = "clientes"
        ordering = ("usuario__primer_nombre", "usuario__apellido_paterno")

    def cambiar_estado(self, nuevo_estado, save=True, manual=False):
        if nuevo_estado not in {choice[0] for choice in self.Estado.choices}:
            raise ValueError("Estado de cliente no valido.")

        if manual:
            self.bloqueo_reactivacion_automatica = nuevo_estado == self.Estado.INACTIVO
        elif nuevo_estado == self.Estado.ACTIVO:
            self.bloqueo_reactivacion_automatica = False

        if self.estado_cliente != nuevo_estado:
            self.estado_cliente = nuevo_estado
            if save:
                self.save(update_fields=["estado_cliente", "bloqueo_reactivacion_automatica", "updated_at"])
        elif save and manual:
            self.save(update_fields=["bloqueo_reactivacion_automatica", "updated_at"])
        return self.estado_cliente

    def procedimiento_tiene_pendientes(self, operacion):
        if operacion.estado in {"CANCELADA", "FINALIZADA"}:
            return False
        sesiones_pendientes = operacion.sesiones_confirmadas < operacion.sesiones_totales
        pagos_pendientes = operacion.cuotas_plan_pagos.exclude(
            estado__in={"PAGADO", "NO_PAGADA"}
        ).exists()
        return sesiones_pendientes or pagos_pendientes

    def pendientes_operativos(self):
        operaciones = self.operaciones.prefetch_related("cuotas_plan_pagos", "citas_medicas")
        operaciones_con_pendientes = [
            operacion
            for operacion in operaciones
            if self.procedimiento_tiene_pendientes(operacion)
        ]
        return {
            "operaciones_pendientes": len(operaciones_con_pendientes),
            "sesiones_pendientes": sum(
                max(operacion.sesiones_totales - operacion.sesiones_confirmadas, 0)
                for operacion in operaciones_con_pendientes
            ),
            "cuotas_pendientes": sum(
                operacion.cuotas_plan_pagos.exclude(estado__in={"PAGADO", "NO_PAGADA"}).count()
                for operacion in operaciones_con_pendientes
            ),
        }

    def actualizar_estado_automaticamente(self, save=True):
        if self.estado_cliente == self.Estado.INACTIVO and self.bloqueo_reactivacion_automatica:
            return self.estado_cliente

        tiene_pendientes = False
        for operacion in self.operaciones.prefetch_related("cuotas_plan_pagos", "citas_medicas"):
            if self.procedimiento_tiene_pendientes(operacion):
                tiene_pendientes = True
                continue
            if operacion.estado == "EN_PROCESO":
                operacion.estado = "FINALIZADA"
                operacion.save(update_fields=["estado", "updated_at"])

        nuevo_estado = self.Estado.ACTIVO if tiene_pendientes else self.Estado.INACTIVO
        return self.cambiar_estado(nuevo_estado, save=save)

    def __str__(self):
        return self.usuario.nombre_completo


class HuellaBiometricaCliente(TimeStampedModel):
    """Stored fingerprint template per client.

    The model is intentionally cross-sucursal: there is no ``sucursal_id``
    and no ``dedo`` field. ``OneToOneField`` on ``cliente`` already
    satisfies spec requirement "one fingerprint per client" and the
    design's per-cliente uniqueness constraint. ``updated_at``
    comes from ``TimeStampedModel``.

    A row may belong to a ``Cliente`` *or* a ``Prospecto`` — never both,
    never neither (see the ``huella_exactly_one_owner`` check
    constraint). The prospect-to-cliente conversion wizard captures the
    fingerprint at step 4 and persists the row against the prospect;
    finalize re-attaches it to the newly-created cliente.

    The ``template_biometrico`` column is now a ``BinaryField`` storing
    a Fernet ciphertext. Existing TextField rows are migrated to
    ``NULL`` with ``activo=False`` and ``proveedor=MOCK_LEGACY`` so
    re-enrollment under DigitalPersona is required.
    """

    class Proveedor(models.TextChoices):
        MOCK_LEGACY = "MOCK_LEGACY", "Simulador (legacy, inactivo)"
        SECU_GEN_LEGACY = "SECU_GEN_LEGACY", "SecuGen (legacy, inactivo)"
        DIGITAL_PERSONA = "DIGITAL_PERSONA", "DigitalPersona 4500"

    class TemplateFormat(models.TextChoices):
        DP_PROPRIETARY = "DP_PROPRIETARY", "DigitalPersona proprietary"
        ANSI_378 = "ANSI_378", "ANSI 378"
        ISO_19794_2 = "ISO_19794_2", "ISO 19794-2"
        UNKNOWN = "UNKNOWN", "Desconocido"

    cliente = models.OneToOneField(
        "customers.Cliente",
        on_delete=models.CASCADE,
        related_name="huella_biometrica",
        null=True,
        blank=True,
    )
    # Nullable FK to ``Prospecto``: the prospect-to-cliente conversion
    # wizard captures the fingerprint at step 4, before the prospect has
    # been promoted to a ``Cliente``. The finalize handler re-attaches
    # the row to the new cliente. Enforces "exactly one of cliente /
    # prospecto" via the ``huella_exactly_one_owner`` check constraint.
    prospecto = models.ForeignKey(
        "customers.Prospecto",
        on_delete=models.CASCADE,
        related_name="huellas_biometricas",
        null=True,
        blank=True,
    )
    proveedor = models.CharField(
        max_length=24,
        choices=Proveedor.choices,
        default=Proveedor.DIGITAL_PERSONA,
    )
    template_biometrico = models.BinaryField(null=True, blank=True)
    template_format = models.CharField(
        max_length=24,
        choices=TemplateFormat.choices,
        default=TemplateFormat.UNKNOWN,
    )
    encrypted_template_key_id = models.CharField(max_length=40, blank=True, default="")
    device_serial = models.CharField(max_length=120, blank=True)
    calidad_captura = models.PositiveSmallIntegerField(default=0)
    consentimiento_aceptado = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="huellas_biometricas_registradas",
        null=True,
        blank=True,
    )
    fecha_registro = models.DateTimeField(default=timezone.now)
    last_match_at = models.DateTimeField(null=True, blank=True)
    last_match_score = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )

    class Meta:
        db_table = "clientes_huellas_biometricas"
        ordering = ("-fecha_registro",)
        unique_together = (("prospecto",),)
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(
                        cliente__isnull=False,
                        prospecto__isnull=True,
                    )
                    | models.Q(
                        cliente__isnull=True,
                        prospecto__isnull=False,
                    )
                ),
                name="huella_exactly_one_owner",
            ),
        ]

    def __str__(self):
        return f"Huella biometrica - {self.cliente}"

# Create your models here.
