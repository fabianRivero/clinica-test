from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from common.models import TimeStampedModel


class Operacion(TimeStampedModel):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        EN_PROCESO = "EN_PROCESO", "En proceso"
        FINALIZADA = "FINALIZADA", "Finalizada"
        CANCELADA = "CANCELADA", "Cancelada"

    paciente = models.ForeignKey(
        "customers.Cliente",
        on_delete=models.PROTECT,
        related_name="operaciones",
    )
    servicio_config = models.ForeignKey(
        "catalogs.ServicioConfig",
        on_delete=models.PROTECT,
        related_name="operaciones",
    )
    zona_general = models.CharField(max_length=120, blank=True)
    zona_especifica = models.CharField(max_length=255, blank=True)
    precio_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    cuotas_totales = models.PositiveIntegerField(default=1)
    sesiones_totales = models.PositiveIntegerField(default=1)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_final = models.DateField(null=True, blank=True)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.BORRADOR,
    )
    detalles_op = models.TextField(blank=True)
    recomendaciones = models.TextField(blank=True)

    class Meta:
        db_table = "operaciones"
        ordering = ("-created_at",)

    @property
    def sesiones_confirmadas(self):
        return self.citas_medicas.filter(
            estado=CitaMedica.Estado.CONFIRMADA,
            verif_biometria=True,
        ).count()

    @property
    def sesiones_pendientes_confirmacion(self):
        return self.citas_medicas.filter(
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA,
        ).count()

    @property
    def reservas_activas(self):
        return self.citas_medicas.filter(estado=CitaMedica.Estado.PROGRAMADA).count()

    @property
    def sesiones_disponibles(self):
        disponibles = (
            self.sesiones_totales
            - self.sesiones_confirmadas
            - self.sesiones_pendientes_confirmacion
            - self.reservas_activas
        )
        return max(disponibles, 0)

    @property
    def puede_reservar(self):
        return self.estado == self.Estado.EN_PROCESO and self.sesiones_disponibles > 0

    def __str__(self):
        return f"Operacion #{self.pk} - {self.paciente}"


class CitaMedica(TimeStampedModel):
    class Estado(models.TextChoices):
        PROGRAMADA = "PROGRAMADA", "Programada"
        REALIZADA_PENDIENTE_BIOMETRIA = (
            "REALIZADA_PENDIENTE_BIOMETRIA",
            "Realizada pendiente biometria",
        )
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        CANCELADA = "CANCELADA", "Cancelada"
        NO_ASISTIO = "NO_ASISTIO", "No asistio"

    operacion = models.ForeignKey(
        "operations.Operacion",
        on_delete=models.CASCADE,
        related_name="citas_medicas",
    )
    medico = models.ForeignKey(
        "staff.Especialista",
        on_delete=models.PROTECT,
        related_name="citas_medicas",
    )
    disponibilidad = models.ForeignKey(
        "operations.DisponibilidadCita",
        on_delete=models.SET_NULL,
        related_name="citas_origen",
        null=True,
        blank=True,
    )
    fecha_hora = models.DateTimeField()
    estado = models.CharField(
        max_length=32,
        choices=Estado.choices,
        default=Estado.PROGRAMADA,
    )
    verif_biometria = models.BooleanField(default=False)
    fecha_confirmacion_biometrica = models.DateTimeField(null=True, blank=True)
    detalles_cita = models.TextField(blank=True)

    class Meta:
        db_table = "citas_medicas"
        ordering = ("fecha_hora",)

    def clean(self):
        errors = {}

        if self.estado == self.Estado.CONFIRMADA and not self.verif_biometria:
            errors["verif_biometria"] = "Una cita confirmada requiere verificacion biometrica."

        if self.operacion_id:
            otras_citas = self.operacion.citas_medicas.exclude(pk=self.pk)
            sesiones_consumidas = otras_citas.filter(
                models.Q(estado=self.Estado.PROGRAMADA)
                | models.Q(estado=self.Estado.REALIZADA_PENDIENTE_BIOMETRIA)
                | models.Q(estado=self.Estado.CONFIRMADA, verif_biometria=True)
            ).count()

            estado_consume_sesion = self.estado in {
                self.Estado.PROGRAMADA,
                self.Estado.REALIZADA_PENDIENTE_BIOMETRIA,
                self.Estado.CONFIRMADA,
            }
            total_consumido = sesiones_consumidas + (1 if estado_consume_sesion else 0)

            if total_consumido > self.operacion.sesiones_totales:
                errors["estado"] = "La operacion ya no tiene sesiones disponibles para nuevas reservas."

        if self.disponibilidad_id:
            if self.medico_id and self.disponibilidad.especialista_id != self.medico_id:
                errors["disponibilidad"] = (
                    "La disponibilidad seleccionada pertenece a un especialista diferente."
                )
            if self.fecha_hora and self.disponibilidad.fecha_hora != self.fecha_hora:
                errors["fecha_hora"] = (
                    "La fecha y hora de la cita deben coincidir con la disponibilidad asignada."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.estado == self.Estado.CONFIRMADA and self.verif_biometria and not self.fecha_confirmacion_biometrica:
            self.fecha_confirmacion_biometrica = timezone.now()
        if self.estado != self.Estado.CONFIRMADA:
            self.fecha_confirmacion_biometrica = None

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Cita #{self.pk} - {self.operacion}"


class DisponibilidadCita(TimeStampedModel):
    especialista = models.ForeignKey(
        "staff.Especialista",
        on_delete=models.PROTECT,
        related_name="disponibilidades_cita",
    )
    fecha_hora = models.DateTimeField()
    activo = models.BooleanField(default=True)
    detalle = models.CharField(max_length=255, blank=True)
    tipos_servicio = models.ManyToManyField(
        "catalogs.TipoServicio",
        blank=True,
        related_name="disponibilidades_cita",
    )
    tipos_proc_estetico = models.ManyToManyField(
        "catalogs.ProcEsteticosTipo",
        blank=True,
        related_name="disponibilidades_cita",
    )
    procedimientos_esteticos = models.ManyToManyField(
        "catalogs.ProcEstetico",
        blank=True,
        related_name="disponibilidades_cita",
    )

    class Meta:
        db_table = "disponibilidad_citas"
        ordering = ("fecha_hora", "especialista__usuario__primer_nombre")
        constraints = [
            models.UniqueConstraint(
                fields=("especialista", "fecha_hora"),
                name="uniq_disponibilidad_especialista_fecha_hora",
            )
        ]

    @property
    def tiene_reserva_activa(self):
        return self.citas_origen.filter(
            estado__in={
                CitaMedica.Estado.PROGRAMADA,
                CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA,
                CitaMedica.Estado.CONFIRMADA,
            }
        ).exists()

    @property
    def estado_resumen(self):
        if not self.activo:
            return "INACTIVO"
        if self.fecha_hora <= timezone.now():
            return "EXPIRADO"
        if self.tiene_reserva_activa:
            return "RESERVADO"
        return "DISPONIBLE"

    def coincide_con_operacion(self, operacion):
        servicio_config = operacion.servicio_config
        procedimiento = servicio_config.proc_estetico

        if self.tipos_servicio.filter(pk=servicio_config.tipo_servicio_id).exists():
            return True
        if procedimiento and self.tipos_proc_estetico.filter(pk=procedimiento.tipo_p_estetico_id).exists():
            return True
        if procedimiento and self.procedimientos_esteticos.filter(pk=procedimiento.pk).exists():
            return True
        return False

    def __str__(self):
        return f"{self.especialista} - {timezone.localtime(self.fecha_hora).strftime('%d/%m/%Y %H:%M')}"


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
        "operations.FichaClinica",
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
        "operations.FichaClinica",
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
        "operations.FichaClinica",
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
        return f"{self.proc_estetico} - {self.nombre}"


class FichaCampo(TimeStampedModel):
    class TipoCampo(models.TextChoices):
        TEXTO = "TEXTO", "Texto"
        NUMERO = "NUMERO", "Numero"
        FECHA = "FECHA", "Fecha"
        BOOLEANO = "BOOLEANO", "Booleano"
        SELECCION = "SELECCION", "Seleccion unica"
        MULTISELECCION = "MULTISELECCION", "Seleccion multiple"

    seccion = models.ForeignKey(
        "operations.FichaSeccion",
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
        "operations.FichaClinica",
        on_delete=models.CASCADE,
        related_name="respuestas_campos",
    )
    campo = models.ForeignKey(
        "operations.FichaCampo",
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
        "operations.FichaRespuestaCampo",
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


@receiver(post_save, sender=Operacion)
@receiver(post_delete, sender=Operacion)
def sincronizar_estado_cliente(sender, instance, **kwargs):
    instance.paciente.actualizar_estado_automaticamente()

# Create your models here.
