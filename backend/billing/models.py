import logging
from decimal import Decimal

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from common.models import CatalogoEditableModel, TimeStampedModel

logger = logging.getLogger(__name__)


def _safe_delete_file(file_name):
    if not file_name:
        return
    try:
        default_storage.delete(file_name)
    except (FileNotFoundError, PermissionError, OSError):
        pass


class CuotaPlanPago(TimeStampedModel):
    class Estado(models.TextChoices):
        PAGADO = "PAGADO", "Pagado"
        PENDIENTE = "PENDIENTE", "Pendiente"
        VENCIDA = "VENCIDA", "Vencida"
        NO_PAGADA = "NO_PAGADA", "No pagada"

    operacion = models.ForeignKey(
        "operations.Operacion",
        on_delete=models.CASCADE,
        related_name="cuotas_plan_pagos",
    )
    nro_cuota = models.PositiveIntegerField()
    fecha_vencimiento = models.DateField()
    monto_programado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
    )
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
        # PAGADO only when the sum of approved payments actually covers the
        # scheduled amount. With mixed/partial payments a single approved
        # row no longer marks the quota as fully paid.
        approved_sum = (
            self.pagos_realizados.filter(
                estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO
            ).aggregate(s=Sum("monto_pagado"))["s"]
            or Decimal("0")
        )
        if approved_sum >= self.monto_programado:
            nuevo_estado = self.Estado.PAGADO
        elif self.pagos_realizados.filter(
            estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE
        ).exists():
            nuevo_estado = self.Estado.PENDIENTE
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
        CANCELADO = "CANCELADO", "Cancelado"

    class MetodoPago(models.TextChoices):
        VIRTUAL = "VIRTUAL", "Virtual"
        FISICO = "FISICO", "Físico"
        MIXTO = "MIXTO", "Mixto"

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
    metodo_pago = models.CharField(
        max_length=10,
        choices=MetodoPago.choices,
        default=MetodoPago.VIRTUAL,
    )
    monto_fisico = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
    )
    monto_virtual = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
    )
    comprobante_url = models.FileField(
        upload_to="comprobantes_pagos/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "webp", "pdf"])],
    )
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

        # ---- Method-driven rules (NEW) ----
        # VIRTUAL: receipt required, monto_virtual == monto_pagado, monto_fisico == 0.
        # FISICO: receipt optional, monto_fisico == monto_pagado, monto_virtual == 0.
        # MIXTO: receipt optional, both breakdown amounts strictly > 0 and sum to monto_pagado.
        if self.metodo_pago == self.MetodoPago.VIRTUAL:
            if not self.comprobante_url:
                errors["comprobante_url"] = "Se requiere un comprobante para registrar el pago."
            if self.monto_virtual != self.monto_pagado:
                errors["monto_virtual"] = "monto_virtual debe ser igual a monto_pagado para pagos virtuales."
            if self.monto_fisico != 0:
                errors["monto_fisico"] = "monto_fisico debe ser 0 para pagos virtuales."
        elif self.metodo_pago == self.MetodoPago.FISICO:
            if self.monto_fisico != self.monto_pagado:
                errors["monto_fisico"] = "monto_fisico debe ser igual a monto_pagado para pagos fisicos."
            if self.monto_virtual != 0:
                errors["monto_virtual"] = "monto_virtual debe ser 0 para pagos fisicos."
        elif self.metodo_pago == self.MetodoPago.MIXTO:
            if self.monto_fisico <= 0 or self.monto_virtual <= 0:
                errors["monto_pagado"] = "Ambos montos (fisico y virtual) deben ser mayores a 0."
            if (self.monto_fisico + self.monto_virtual) != self.monto_pagado:
                errors["monto_pagado"] = "monto_fisico + monto_virtual debe ser igual a monto_pagado."

        # ---- Existing rules (unchanged) ----
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
        previous_file_name = None
        if self.pk:
            previous_file_name = (
                PagoRealizado.objects.filter(pk=self.pk)
                .values_list("comprobante_url", flat=True)
                .first()
            )

        if self.estado_verificacion == self.EstadoVerificacion.APROBADO:
            self.verificado = True
            if self.verificado_por_id and not self.fecha_verificacion:
                self.fecha_verificacion = timezone.now()
        elif self.estado_verificacion in {
            self.EstadoVerificacion.RECHAZADO,
            self.EstadoVerificacion.CANCELADO,
        }:
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
        logger.warning(
            "payment_save payment=%s cuota=%s operacion=%s status=%s verificado=%s verificado_por=%s fecha_verificacion=%s",
            self.pk,
            self.cuota_id,
            self.cuota.operacion_id if self.cuota_id else None,
            self.estado_verificacion,
            self.verificado,
            self.verificado_por_id,
            self.fecha_verificacion.isoformat() if self.fecha_verificacion else None,
        )
        if previous_file_name and previous_file_name != self.comprobante_url.name:
            _safe_delete_file(previous_file_name)
        self.cuota.actualizar_estado_por_pagos()
        self.cuota.operacion.paciente.actualizar_estado_automaticamente()

    def __str__(self):
        return f"Pago #{self.pk} - Cuota #{self.cuota_id}"


class PagoCita(TimeStampedModel):
    """Sibling payment table for ``CitaMedica`` / ``CitaClienteLibre`` /
    ``CitaProspecto``.

    Mirrors ``PagoRealizado`` (VIRTUAL / FISICO / MIXTO with breakdown
    amounts, optional receipt, ``estado_verificacion``) but lives on a
    separate table so the admin cobro flow for citas cannot accidentally
    feed the cuota ``actualizar_estado_por_pagos`` aggregator.

    Exactly one of ``cita_medica`` / ``cita_cliente_libre`` /
    ``cita_prospecto`` MUST be set (XOR enforced in ``clean()`` AND as a
    ``CheckConstraint`` so the database also rejects it). Each FK gets
    an index so admin detail payloads can prefetch the related cita in
    a single query.
    """

    MetodoPago = PagoRealizado.MetodoPago
    EstadoVerificacion = PagoRealizado.EstadoVerificacion

    cita_medica = models.ForeignKey(
        "operations.CitaMedica",
        on_delete=models.CASCADE,
        related_name="pagos_cita",
        null=True,
        blank=True,
        db_index=True,
    )
    cita_cliente_libre = models.ForeignKey(
        "operations.CitaClienteLibre",
        on_delete=models.CASCADE,
        related_name="pagos_cita",
        null=True,
        blank=True,
        db_index=True,
    )
    cita_prospecto = models.ForeignKey(
        "operations.CitaProspecto",
        on_delete=models.CASCADE,
        related_name="pagos_cita",
        null=True,
        blank=True,
        db_index=True,
    )
    monto_pagado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    metodo_pago = models.CharField(
        max_length=10,
        choices=MetodoPago.choices,
        default=MetodoPago.VIRTUAL,
    )
    monto_fisico = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
    )
    monto_virtual = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
    )
    comprobante_url = models.FileField(
        upload_to="comprobantes_citas/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "webp", "pdf"])],
    )
    estado_verificacion = models.CharField(
        max_length=20,
        choices=EstadoVerificacion.choices,
        default=EstadoVerificacion.PENDIENTE,
    )
    verificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="pagos_cita_verificados",
        null=True,
        blank=True,
    )
    fecha_verificacion = models.DateTimeField(null=True, blank=True)
    detalles_pago = models.TextField(blank=True)

    class Meta:
        db_table = "pagos_citas"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["cita_medica", "-created_at"]),
            models.Index(fields=["cita_cliente_libre", "-created_at"]),
            models.Index(fields=["cita_prospecto", "-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    # cita_medica set, others null
                    (
                        models.Q(
                            cita_medica__isnull=False,
                            cita_cliente_libre__isnull=True,
                            cita_prospecto__isnull=True,
                        )
                    )
                    # cita_cliente_libre set, others null
                    | (
                        models.Q(
                            cita_medica__isnull=True,
                            cita_cliente_libre__isnull=False,
                            cita_prospecto__isnull=True,
                        )
                    )
                    # cita_prospecto set, others null
                    | (
                        models.Q(
                            cita_medica__isnull=True,
                            cita_cliente_libre__isnull=True,
                            cita_prospecto__isnull=False,
                        )
                    )
                ),
                name="pago_cita_xor_cita_fk",
            ),
        ]

    def clean(self):
        errors = {}

        # ---- XOR: exactly one of three cita FKs must be set ----
        flags = (
            bool(self.cita_medica_id),
            bool(self.cita_cliente_libre_id),
            bool(self.cita_prospecto_id),
        )
        if sum(flags) != 1:
            errors["__all__"] = (
                "PagoCita requiere exactamente una cita asociada "
                "(cita_medica XOR cita_cliente_libre XOR cita_prospecto)."
            )

        # ---- Method-driven amount rules (shared helper) ----
        amount_errors = _validate_metodo_pago_amounts(self)
        errors.update(amount_errors)

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        target = (
            self.cita_medica_id
            or self.cita_cliente_libre_id
            or self.cita_prospecto_id
        )
        return f"PagoCita #{self.pk} - Cita #{target}"


class CategoriaGasto(CatalogoEditableModel):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "categorias_gasto"
        ordering = ("orden", "nombre")

    def __str__(self):
        return self.nombre


class GastoSucursal(TimeStampedModel):
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.PROTECT,
        related_name="gastos",
    )
    categoria = models.ForeignKey(
        "billing.CategoriaGasto",
        on_delete=models.PROTECT,
        related_name="gastos",
    )
    fecha = models.DateField()
    concepto = models.CharField(max_length=180)
    unidades = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    costo_unidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    gasto_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    proveedor = models.CharField(max_length=160, blank=True)
    factura = models.FileField(
        upload_to="facturas_gastos/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "webp", "pdf"])],
    )
    detalles = models.TextField(blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="gastos_registrados",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "gastos_sucursal"
        ordering = ("-fecha", "-created_at")

    def save(self, *args, **kwargs):
        previous_file_name = None
        if self.pk:
            previous_file_name = (
                GastoSucursal.objects.filter(pk=self.pk)
                .values_list("factura", flat=True)
                .first()
            )

        self.full_clean()
        super().save(*args, **kwargs)
        if previous_file_name and previous_file_name != self.factura.name:
            _safe_delete_file(previous_file_name)

    def __str__(self):
        return f"{self.concepto} - {self.sucursal}"


class ConfiguracionPagoQR(TimeStampedModel):
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    instrucciones = models.TextField(
        blank=True,
        default=(
            "Escanea este QR para pagar a la cuenta bancaria de la clinica. "
            "Luego adjunta el comprobante para que administracion valide tu pago."
        ),
    )
    imagen_qr = models.FileField(
        upload_to="pagos_qr/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "webp"])],
    )

    class Meta:
        db_table = "configuracion_pago_qr"
        verbose_name = "Configuración de pago QR"
        verbose_name_plural = "Configuración de pago QR"
        constraints = [
            models.UniqueConstraint(
                fields=["sucursal"],
                name="uniq_config_qr_sucursal",
            )
        ]

    def save(self, *args, **kwargs):
        previous_file_name = None
        if self.pk:
            previous_file_name = (
                ConfiguracionPagoQR.objects.filter(pk=self.pk)
                .values_list("imagen_qr", flat=True)
                .first()
            )

        super().save(*args, **kwargs)
        if previous_file_name and previous_file_name != self.imagen_qr.name:
            _safe_delete_file(previous_file_name)

    def __str__(self):
        return "Configuración QR de pagos"


@receiver(post_delete, sender=PagoRealizado)
def actualizar_cuota_tras_eliminar_pago(sender, instance, **kwargs):
    if instance.comprobante_url:
        _safe_delete_file(instance.comprobante_url.name)
    instance.cuota.actualizar_estado_por_pagos()
    instance.cuota.operacion.paciente.actualizar_estado_automaticamente()


@receiver(post_delete, sender=GastoSucursal)
def eliminar_factura_gasto(sender, instance, **kwargs):
    if instance.factura:
        _safe_delete_file(instance.factura.name)


@receiver(post_delete, sender=ConfiguracionPagoQR)
def eliminar_archivo_qr_al_borrar_configuracion(sender, instance, **kwargs):
    if instance.imagen_qr:
        _safe_delete_file(instance.imagen_qr.name)

# Create your models here.


def _validate_metodo_pago_amounts(payment):
    """Validate the VIRTUAL / FISICO / MIXTO breakdown rules shared by
    ``PagoRealizado`` and ``PagoCita``.

    The helper checks ONLY the amount fields (``monto_pagado``,
    ``monto_fisico``, ``monto_virtual``) so it can be reused by both
    models — the receipt-required rule is ``PagoRealizado``-specific
    (client portal uploads) and stays in that model's ``clean()``.

    Return value is a ``dict`` suitable for merging into a
    ``ValidationError({...})``. Empty dict means the breakdown is valid.

    Rules (mirror of the spec table for ``appointment-payment`` / the
    existing rules in ``PagoRealizado.clean()``):

    * ``VIRTUAL``: ``monto_virtual == monto_pagado`` AND ``monto_fisico == 0``.
    * ``FISICO``:  ``monto_fisico  == monto_pagado`` AND ``monto_virtual == 0``.
    * ``MIXTO``:   ``monto_fisico > 0`` AND ``monto_virtual > 0`` AND
      ``monto_fisico + monto_virtual == monto_pagado``.
    """
    errors = {}

    if payment.metodo_pago == PagoRealizado.MetodoPago.VIRTUAL:
        if payment.monto_virtual != payment.monto_pagado:
            errors["monto_virtual"] = (
                "monto_virtual debe ser igual a monto_pagado para pagos virtuales."
            )
        if payment.monto_fisico != 0:
            errors["monto_fisico"] = (
                "monto_fisico debe ser 0 para pagos virtuales."
            )
    elif payment.metodo_pago == PagoRealizado.MetodoPago.FISICO:
        if payment.monto_fisico != payment.monto_pagado:
            errors["monto_fisico"] = (
                "monto_fisico debe ser igual a monto_pagado para pagos fisicos."
            )
        if payment.monto_virtual != 0:
            errors["monto_virtual"] = (
                "monto_virtual debe ser 0 para pagos fisicos."
            )
    elif payment.metodo_pago == PagoRealizado.MetodoPago.MIXTO:
        if payment.monto_fisico <= 0 or payment.monto_virtual <= 0:
            errors["monto_pagado"] = (
                "Ambos montos (fisico y virtual) deben ser mayores a 0."
            )
        if (payment.monto_fisico + payment.monto_virtual) != payment.monto_pagado:
            errors["monto_pagado"] = (
                "monto_fisico + monto_virtual debe ser igual a monto_pagado."
            )

    return errors
