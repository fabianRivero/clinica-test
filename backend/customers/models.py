from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel


class Prospecto(TimeStampedModel):
    class Estado(models.TextChoices):
        PASAJERO = "PASAJERO", "Pasajero"
        CONVERTIDO = "CONVERTIDO", "Convertido"
        DESCARTADO = "DESCARTADO", "Descartado"

    nombres = models.CharField(max_length=120)
    apellidos = models.CharField(max_length=160)
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
        return f"{self.nombres} {self.apellidos}".strip()


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

    fecha_nacimiento = models.DateField(null=True, blank=True)
    nro_hijos = models.PositiveIntegerField(default=0)
    direccion_domicilio = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    ocupacion = models.CharField(max_length=120, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        db_table = "clientes"
        ordering = ("usuario__primer_nombre", "usuario__apellido_paterno")

    def cambiar_estado(self, nuevo_estado, save=True):
        if nuevo_estado not in {choice[0] for choice in self.Estado.choices}:
            raise ValueError("Estado de cliente no valido.")
        if self.estado_cliente != nuevo_estado:
            self.estado_cliente = nuevo_estado
            if save:
                self.save(update_fields=["estado_cliente", "updated_at"])
        return self.estado_cliente

    def procedimiento_tiene_pendientes(self, operacion):
        if operacion.estado in {"CANCELADA", "FINALIZADA"}:
            return False
        sesiones_pendientes = operacion.sesiones_confirmadas < operacion.sesiones_totales
        pagos_pendientes = operacion.cuotas_plan_pagos.exclude(estado="PAGADO").exists()
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
                operacion.cuotas_plan_pagos.exclude(estado="PAGADO").count()
                for operacion in operaciones_con_pendientes
            ),
        }

    def actualizar_estado_automaticamente(self, save=True):
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
    class Proveedor(models.TextChoices):
        MOCK = "MOCK", "Simulador"
        SECU_GEN = "SECU_GEN", "SecuGen"

    cliente = models.OneToOneField(
        "customers.Cliente",
        on_delete=models.CASCADE,
        related_name="huella_biometrica",
    )
    proveedor = models.CharField(
        max_length=20,
        choices=Proveedor.choices,
        default=Proveedor.MOCK,
    )
    template_biometrico = models.TextField()
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

    class Meta:
        db_table = "clientes_huellas_biometricas"
        ordering = ("-fecha_registro",)

    def __str__(self):
        return f"Huella biometrica - {self.cliente}"

# Create your models here.
