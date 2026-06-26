from django.core.validators import FileExtensionValidator
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


class FichaClinica(TimeStampedModel):
    operacion = models.OneToOneField(
        "operations.Operacion",
        on_delete=models.CASCADE,
        related_name="ficha_clinica",
    )
    fecha_ficha = models.DateField(default=timezone.localdate)
    motivo_consulta = models.TextField(blank=True)
    observaciones = models.TextField(blank=True)
    firma_paciente_ci = models.CharField(max_length=120, blank=True)
    firma_paciente_url = models.CharField(max_length=255, blank=True)
    documento_escaneado_pdf = models.FileField(
        upload_to="fichas_clinicas/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(["pdf"])],
    )
    consentimiento_aceptado = models.BooleanField(default=False)

    class Meta:
        db_table = "ficha_clinica"
        ordering = ("-fecha_ficha",)

    def __str__(self):
        return f"Ficha clinica - Operacion #{self.operacion_id}"


class FichaAntecedenteMedico(TimeStampedModel):
    class TipoAntecedente(models.TextChoices):
        FAMILIAR = "FAMILIAR", "Familiar"
        PERSONAL = "PERSONAL", "Personal"

    ficha = models.ForeignKey(
        "clinical.FichaClinica",
        on_delete=models.CASCADE,
        related_name="antecedentes",
    )
    antecedente = models.ForeignKey(
        "catalogs.AntecedenteMedico",
        on_delete=models.PROTECT,
        related_name="fichas_rel",
    )
    tipo_antecedente = models.CharField(max_length=10, choices=TipoAntecedente.choices)
    detalle = models.TextField(blank=True)

    class Meta:
        db_table = "ficha_antecedentes_medicos"
        constraints = [
            models.UniqueConstraint(
                fields=("ficha", "antecedente", "tipo_antecedente"),
                name="uniq_ficha_antecedente_tipo",
            )
        ]

    def __str__(self):
        return f"{self.tipo_antecedente} - {self.antecedente}"


class FichaImplanteInjerto(TimeStampedModel):
    ficha = models.ForeignKey(
        "clinical.FichaClinica",
        on_delete=models.CASCADE,
        related_name="implantes",
    )
    implante = models.ForeignKey(
        "catalogs.ImplanteInjerto",
        on_delete=models.PROTECT,
        related_name="fichas_rel",
    )
    detalle = models.TextField(blank=True)

    class Meta:
        db_table = "ficha_implantes_injertos"
        constraints = [
            models.UniqueConstraint(
                fields=("ficha", "implante"),
                name="uniq_ficha_implante",
            )
        ]

    def __str__(self):
        return f"{self.implante} - Ficha #{self.ficha_id}"


class FichaCirugiaEstetica(TimeStampedModel):
    ficha = models.ForeignKey(
        "clinical.FichaClinica",
        on_delete=models.CASCADE,
        related_name="cirugias",
    )
    cirugia = models.ForeignKey(
        "catalogs.CirugiaEstetica",
        on_delete=models.PROTECT,
        related_name="fichas_rel",
    )
    hace_cuanto_tiempo = models.CharField(max_length=120, blank=True)
    detalle = models.TextField(blank=True)

    class Meta:
        db_table = "ficha_cirugias_esteticas"
        constraints = [
            models.UniqueConstraint(
                fields=("ficha", "cirugia"),
                name="uniq_ficha_cirugia",
            )
        ]

    def __str__(self):
        return f"{self.cirugia} - Ficha #{self.ficha_id}"


class FichaSeccion(TimeStampedModel):
    proc_estetico = models.ForeignKey(
        "catalogs.ProcEstetico",
        on_delete=models.CASCADE,
        related_name="secciones_ficha",
        null=True,
        blank=True,
    )
    sector = models.ForeignKey(
        "catalogs.Sector",
        on_delete=models.SET_NULL,
        related_name="ficha_secciones",
        null=True,
        blank=True,
    )
    codigo = models.CharField(max_length=80)
    nombre = models.CharField(max_length=120)
    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "ficha_secciones"
        ordering = ("proc_estetico", "orden", "nombre")
        constraints = [
            models.UniqueConstraint(
                fields=("proc_estetico", "codigo"),
                name="uniq_proc_codigo_seccion",
            )
        ]

    def __str__(self):
        scope = self.proc_estetico or self.sector
        return f"{scope} - {self.nombre}"


class FichaCampo(TimeStampedModel):
    class TipoCampo(models.TextChoices):
        TEXTO = "TEXTO", "Texto"
        NUMERO = "NUMERO", "Numero"
        FECHA = "FECHA", "Fecha"
        BOOLEANO = "BOOLEANO", "Booleano"
        SELECCION = "SELECCION", "Seleccion unica"
        MULTISELECCION = "MULTISELECCION", "Seleccion multiple"

    seccion = models.ForeignKey(
        "clinical.FichaSeccion",
        on_delete=models.CASCADE,
        related_name="campos",
    )
    codigo = models.CharField(max_length=80)
    etiqueta = models.CharField(max_length=150)
    tipo_campo = models.CharField(max_length=20, choices=TipoCampo.choices)
    grupo_opciones = models.ForeignKey(
        "catalogs.GrupoOpciones",
        on_delete=models.PROTECT,
        related_name="campos",
        null=True,
        blank=True,
    )
    es_multiple = models.BooleanField(default=False)
    permite_detalle = models.BooleanField(default=False)
    requerido = models.BooleanField(default=False)
    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "ficha_campos"
        ordering = ("seccion", "orden", "etiqueta")
        constraints = [
            models.UniqueConstraint(
                fields=("seccion", "codigo"),
                name="uniq_seccion_codigo_campo",
            )
        ]

    def __str__(self):
        return self.etiqueta


class FichaRespuestaCampo(TimeStampedModel):
    ficha = models.ForeignKey(
        "clinical.FichaClinica",
        on_delete=models.CASCADE,
        related_name="respuestas_campos",
    )
    campo = models.ForeignKey(
        "clinical.FichaCampo",
        on_delete=models.PROTECT,
        related_name="respuestas",
    )
    valor_texto = models.TextField(blank=True)
    valor_numero = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    valor_fecha = models.DateField(null=True, blank=True)
    valor_booleano = models.BooleanField(null=True, blank=True)
    detalle = models.TextField(blank=True)

    class Meta:
        db_table = "ficha_respuestas_campos"
        constraints = [
            models.UniqueConstraint(
                fields=("ficha", "campo"),
                name="uniq_ficha_campo_respuesta",
            )
        ]

    def __str__(self):
        return f"Ficha #{self.ficha_id} - {self.campo}"


class FichaRespuestaOpcion(TimeStampedModel):
    respuesta = models.ForeignKey(
        "clinical.FichaRespuestaCampo",
        on_delete=models.CASCADE,
        related_name="opciones_seleccionadas",
    )
    opcion = models.ForeignKey(
        "catalogs.OpcionCatalogo",
        on_delete=models.PROTECT,
        related_name="respuestas",
    )

    class Meta:
        db_table = "ficha_respuestas_opciones"
        constraints = [
            models.UniqueConstraint(
                fields=("respuesta", "opcion"),
                name="uniq_respuesta_opcion",
            )
        ]

    def __str__(self):
        return f"{self.respuesta} - {self.opcion}"
