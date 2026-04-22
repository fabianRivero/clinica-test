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
    datos_usuario = models.JSONField(default=dict, blank=True)
    datos_operacion = models.JSONField(default=dict, blank=True)
    datos_ficha = models.JSONField(default=dict, blank=True)

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
    ci = models.CharField(max_length=30, blank=True)
    estado_cliente = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.INACTIVO,
    )
    cod_biometrico = models.CharField(max_length=255, blank=True, null=True, unique=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    nro_hijos = models.PositiveIntegerField(default=0)
    direccion_domicilio = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    ocupacion = models.CharField(max_length=120, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        db_table = "clientes"
        ordering = ("usuario__primer_nombre", "usuario__apellido_paterno")

    def actualizar_estado_automaticamente(self, save=True):
        nuevo_estado = (
            self.Estado.ACTIVO
            if self.operaciones.filter(estado="EN_PROCESO").exists()
            else self.Estado.INACTIVO
        )
        if self.estado_cliente != nuevo_estado:
            self.estado_cliente = nuevo_estado
            if save:
                self.save(update_fields=["estado_cliente", "updated_at"])
        return self.estado_cliente

    def __str__(self):
        return self.usuario.nombre_completo

# Create your models here.
