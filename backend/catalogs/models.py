from django.core.validators import MinValueValidator
from django.db import models

from common.models import CatalogoEditableModel, TimeStampedModel


class TipoServicio(CatalogoEditableModel):
    tipo = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "tipo_servicio"
        ordering = ("orden", "tipo")

    def __str__(self):
        return self.tipo


class ProcEsteticosTipo(CatalogoEditableModel):
    tipo = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "proc_esteticos_tipo"
        ordering = ("orden", "tipo")

    def __str__(self):
        return self.tipo


class ProcEstetico(CatalogoEditableModel):
    tipo_p_estetico = models.ForeignKey(
        "catalogs.ProcEsteticosTipo",
        on_delete=models.PROTECT,
        related_name="procedimientos",
    )
    proceso = models.CharField(max_length=150)

    class Meta:
        db_table = "proc_esteticos"
        ordering = ("orden", "proceso")
        constraints = [
            models.UniqueConstraint(
                fields=("tipo_p_estetico", "proceso"),
                name="uniq_tipo_proceso_estetico",
            )
        ]

    def __str__(self):
        return self.proceso


class ServicioConfig(TimeStampedModel):
    tipo_servicio = models.ForeignKey(
        "catalogs.TipoServicio",
        on_delete=models.PROTECT,
        related_name="servicios_config",
    )
    proc_estetico = models.ForeignKey(
        "catalogs.ProcEstetico",
        on_delete=models.PROTECT,
        related_name="servicios_config",
        null=True,
        blank=True,
    )
    precio_base = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "servicios_config"
        ordering = ("tipo_servicio__tipo", "proc_estetico__proceso")
        constraints = [
            models.UniqueConstraint(
                fields=("tipo_servicio", "proc_estetico"),
                name="uniq_tipo_servicio_proc",
            )
        ]

    def __str__(self):
        if self.proc_estetico:
            return f"{self.tipo_servicio} - {self.proc_estetico}"
        return str(self.tipo_servicio)


class AntecedenteMedico(CatalogoEditableModel):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "antecedentes_medicos"
        ordering = ("orden", "nombre")

    def __str__(self):
        return self.nombre


class ImplanteInjerto(CatalogoEditableModel):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "implantes_injertos"
        ordering = ("orden", "nombre")

    def __str__(self):
        return self.nombre


class CirugiaEstetica(CatalogoEditableModel):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "cirugias_esteticas"
        ordering = ("orden", "nombre")

    def __str__(self):
        return self.nombre


class GrupoOpciones(TimeStampedModel):
    codigo = models.CharField(max_length=80, unique=True)
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "grupos_opciones"
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class OpcionCatalogo(TimeStampedModel):
    grupo = models.ForeignKey(
        "catalogs.GrupoOpciones",
        on_delete=models.CASCADE,
        related_name="opciones",
    )
    codigo = models.CharField(max_length=80)
    nombre = models.CharField(max_length=120)
    valor = models.CharField(max_length=120)
    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "opciones_catalogo"
        ordering = ("grupo", "orden", "nombre")
        constraints = [
            models.UniqueConstraint(
                fields=("grupo", "codigo"),
                name="uniq_grupo_codigo_opcion",
            )
        ]

    def __str__(self):
        return f"{self.grupo} - {self.nombre}"


class TipoPiel(CatalogoEditableModel):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "tipos_piel"
        ordering = ("orden", "nombre")

    def __str__(self):
        return self.nombre


class GradoDeshidratacion(CatalogoEditableModel):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "grados_deshidratacion"
        ordering = ("orden", "nombre")

    def __str__(self):
        return self.nombre


class GrosorPiel(CatalogoEditableModel):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "grosores_piel"
        ordering = ("orden", "nombre")

    def __str__(self):
        return self.nombre


class PatologiaCutanea(CatalogoEditableModel):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "patologias_cutaneas"
        ordering = ("orden", "nombre")

    def __str__(self):
        return self.nombre


class ProductoAlergia(CatalogoEditableModel):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "productos_alergia"
        ordering = ("orden", "nombre")

    def __str__(self):
        return self.nombre


class TipoAlergia(CatalogoEditableModel):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "tipos_alergia"
        ordering = ("orden", "nombre")

    def __str__(self):
        return self.nombre


class GravedadAlergia(CatalogoEditableModel):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "gravedades_alergia"
        ordering = ("orden", "nombre")

    def __str__(self):
        return self.nombre

# Create your models here.
