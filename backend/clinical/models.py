from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel


class AnalisisEstetico(TimeStampedModel):
    paciente = models.ForeignKey(
        "customers.Cliente",
        on_delete=models.CASCADE,
        related_name="analisis_esteticos",
    )
    fecha_analisis = models.DateField(default=timezone.localdate)
    tipo_piel = models.ForeignKey(
        "catalogs.TipoPiel",
        on_delete=models.PROTECT,
        related_name="analisis_esteticos",
    )
    grado_deshidratacion = models.ForeignKey(
        "catalogs.GradoDeshidratacion",
        on_delete=models.PROTECT,
        related_name="analisis_esteticos",
    )
    grosor_piel = models.ForeignKey(
        "catalogs.GrosorPiel",
        on_delete=models.PROTECT,
        related_name="analisis_esteticos",
    )
    observaciones = models.TextField(blank=True)

    class Meta:
        db_table = "analisis_estetico"
        ordering = ("-fecha_analisis",)

    def __str__(self):
        return f"Analisis #{self.pk} - {self.paciente}"


class PatologiaPorAnalisis(TimeStampedModel):
    analisis = models.ForeignKey(
        "clinical.AnalisisEstetico",
        on_delete=models.CASCADE,
        related_name="patologias_rel",
    )
    patologia = models.ForeignKey(
        "catalogs.PatologiaCutanea",
        on_delete=models.PROTECT,
        related_name="analisis_rel",
    )

    class Meta:
        db_table = "patologias_por_analisis"
        constraints = [
            models.UniqueConstraint(
                fields=("analisis", "patologia"),
                name="uniq_patologia_por_analisis",
            )
        ]

    def __str__(self):
        return f"{self.analisis} - {self.patologia}"


class AnalisisEsteticoAlergia(TimeStampedModel):
    analisis = models.ForeignKey(
        "clinical.AnalisisEstetico",
        on_delete=models.CASCADE,
        related_name="alergias",
    )
    producto_alergia = models.ForeignKey(
        "catalogs.ProductoAlergia",
        on_delete=models.PROTECT,
        related_name="analisis_rel",
    )
    tipo_alergia = models.ForeignKey(
        "catalogs.TipoAlergia",
        on_delete=models.PROTECT,
        related_name="analisis_rel",
    )
    gravedad = models.ForeignKey(
        "catalogs.GravedadAlergia",
        on_delete=models.PROTECT,
        related_name="analisis_rel",
    )
    detalle_reaccion = models.TextField(blank=True)

    class Meta:
        db_table = "analisis_estetico_alergias"
        constraints = [
            models.UniqueConstraint(
                fields=("analisis", "producto_alergia", "tipo_alergia", "gravedad"),
                name="uniq_analisis_producto_tipo_gravedad",
            )
        ]

    def __str__(self):
        return f"{self.analisis} - {self.producto_alergia}"

# Create your models here.
