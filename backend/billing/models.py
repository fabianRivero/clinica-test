from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from common.models import TimeStampedModel


class CuotaPlanPago(TimeStampedModel):
    class Estado(models.TextChoices):
        PAGADO = "PAGADO", "Pagado"
        PENDIENTE = "PENDIENTE", "Pendiente"
        VENCIDA = "VENCIDA", "Vencida"

    operacion = models.ForeignKey(
        "operations.Operacion",
        on_delete=models.CASCADE,
        related_name="cuotas_plan_pagos",
    )
    nro_cuota = models.PositiveIntegerField()
    fecha_vencimiento = models.DateField()
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )

    class Meta:
        db_table = "cuotas_plan_pagos"
        ordering = ("operacion", "nro_cuota")
        constraints = [
            models.UniqueConstraint(
                fields=("operacion", "nro_cuota"),
                name="uniq_operacion_nro_cuota",
            )
        ]

    def actualizar_estado_por_pagos(self, save=True):
        if self.pagos_realizados.filter(
            estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO
        ).exists():
            nuevo_estado = self.Estado.PAGADO
        elif self.fecha_vencimiento < timezone.localdate():
            nuevo_estado = self.Estado.VENCIDA
        else:
            nuevo_estado = self.Estado.PENDIENTE

        if self.estado != nuevo_estado:
            self.estado = nuevo_estado
            if save:
                self.save(update_fields=["estado", "updated_at"])
        return self.estado

    def __str__(self):
        return f"Cuota {self.nro_cuota} - Operacion #{self.operacion_id}"


class PagoRealizado(TimeStampedModel):
    class EstadoVerificacion(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        APROBADO = "APROBADO", "Aprobado"
        RECHAZADO = "RECHAZADO", "Rechazado"

    cuota = models.ForeignKey(
        "billing.CuotaPlanPago",
        on_delete=models.CASCADE,
        related_name="pagos_realizados",
    )
    monto_pagado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    comprobante_url = models.CharField(max_length=255, blank=True)
    estado_verificacion = models.CharField(
        max_length=20,
        choices=EstadoVerificacion.choices,
        default=EstadoVerificacion.PENDIENTE,
    )
    verificado = models.BooleanField(default=False)
    verificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="pagos_verificados",
        null=True,
        blank=True,
    )
    fecha_verificacion = models.DateTimeField(null=True, blank=True)
    detalles_pago = models.TextField(blank=True)
    observacion_verificacion = models.TextField(blank=True)

    class Meta:
        db_table = "pagos_realizados"
        ordering = ("-created_at",)

    def clean(self):
        errors = {}

        if not self.comprobante_url:
            errors["comprobante_url"] = "Se requiere un comprobante para registrar el pago."

        if self.estado_verificacion in {
            self.EstadoVerificacion.APROBADO,
            self.EstadoVerificacion.RECHAZADO,
        }:
            if not self.verificado_por_id:
                errors["verificado_por"] = "Un administrador debe verificar o rechazar el pago."
            if not self.fecha_verificacion:
                errors["fecha_verificacion"] = "La fecha de verificacion es obligatoria."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.estado_verificacion == self.EstadoVerificacion.APROBADO:
            self.verificado = True
            if self.verificado_por_id and not self.fecha_verificacion:
                self.fecha_verificacion = timezone.now()
        elif self.estado_verificacion == self.EstadoVerificacion.RECHAZADO:
            self.verificado = False
            if self.verificado_por_id and not self.fecha_verificacion:
                self.fecha_verificacion = timezone.now()
        else:
            self.verificado = False
            self.verificado_por = None
            self.fecha_verificacion = None
            self.observacion_verificacion = ""

        self.full_clean()
        super().save(*args, **kwargs)
        self.cuota.actualizar_estado_por_pagos()

    def __str__(self):
        return f"Pago #{self.pk} - Cuota #{self.cuota_id}"


@receiver(post_delete, sender=PagoRealizado)
def actualizar_cuota_tras_eliminar_pago(sender, instance, **kwargs):
    instance.cuota.actualizar_estado_por_pagos()

# Create your models here.
