from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from common.models import CatalogoEditableModel, TimeStampedModel


class DiaSemana(models.IntegerChoices):
    DOMINGO = 0, "Domingo"
    LUNES = 1, "Lunes"
    MARTES = 2, "Martes"
    MIERCOLES = 3, "Miercoles"
    JUEVES = 4, "Jueves"
    VIERNES = 5, "Viernes"
    SABADO = 6, "Sabado"


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
    def primer_pago_verificado(self):
        primera_cuota = self.cuotas_plan_pagos.order_by("nro_cuota", "fecha_vencimiento").first()
        if not primera_cuota:
            return False
        return primera_cuota.pagos_realizados.filter(
            estado_verificacion="APROBADO"
        ).exists()

    @property
    def tiene_reserva_programada(self):
        return self.reservas_activas > 0

    @property
    def tiene_cierre_pendiente(self):
        return self.sesiones_pendientes_confirmacion > 0

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
        return (
            self.estado == self.Estado.EN_PROCESO
            and self.primer_pago_verificado
            and not self.tiene_reserva_programada
            and not self.tiene_cierre_pendiente
            and self.sesiones_disponibles > 0
        )

    @property
    def motivo_bloqueo_reserva(self):
        if self.estado != self.Estado.EN_PROCESO:
            return "Solo los tratamientos en proceso pueden reservar nuevas citas."
        if not self.primer_pago_verificado:
            return "Necesitas tener el primer pago verificado para poder hacer reservas."
        if self.tiene_reserva_programada:
            return (
                "Ya tienes una cita programada para este tratamiento. Debes completarla "
                "o reprogramarla antes de reservar la siguiente sesión."
            )
        if self.tiene_cierre_pendiente:
            return (
                "Tu cita anterior aún no se cerró por completo. Espera a que quede "
                "realizada y confirmada antes de reservar la siguiente sesión."
            )
        if self.sesiones_disponibles <= 0:
            return "Tu tratamiento ya no tiene sesiones disponibles para nuevas reservas."
        return ""

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
        related_name="citas_medicas", null=True, blank=True,
    )
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.CASCADE,
        related_name="citas_medicas",
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

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.estado == self.Estado.CONFIRMADA and self.verif_biometria and not self.fecha_confirmacion_biometrica:
            self.fecha_confirmacion_biometrica = timezone.now()
        if self.estado != self.Estado.CONFIRMADA:
            self.fecha_confirmacion_biometrica = None

        self.full_clean()
        super().save(*args, **kwargs)
        self.operacion.paciente.actualizar_estado_automaticamente()

    def __str__(self):
        return f"Cita #{self.pk} - {self.operacion}"


class CitaProspecto(TimeStampedModel):
    class Estado(models.TextChoices):
        PROGRAMADA = "PROGRAMADA", "Programada"
        REALIZADA = "REALIZADA", "Realizada"
        CANCELADA = "CANCELADA", "Cancelada"
        NO_ASISTIO = "NO_ASISTIO", "No asistio"

    prospecto = models.ForeignKey(
        "customers.Prospecto",
        on_delete=models.CASCADE,
        related_name="citas_medicas", null=True, blank=True,
    )
    servicio_config = models.ForeignKey(
        "catalogs.ServicioConfig",
        on_delete=models.PROTECT,
        related_name="citas_prospectos",
    )
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.CASCADE,
        related_name="citas_prospectos",
    )
    fecha_hora = models.DateTimeField()
    estado = models.CharField(
        max_length=32,
        choices=Estado.choices,
        default=Estado.PROGRAMADA,
    )
    detalles_cita = models.TextField(blank=True)

    class Meta:
        db_table = "citas_prospectos"
        ordering = ("fecha_hora",)

    def clean(self):
        errors = {}
        if self.prospecto_id and self.prospecto.estado != "PASAJERO":
            errors["prospecto"] = "Solo se pueden reservar citas para prospectos no convertidos."

        if self.servicio_config_id and self.servicio_config.proc_estetico_id:
            errors["servicio_config"] = "Las citas de prospectos solo pueden usar el servicio de cita medica."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Cita prospecto #{self.pk} - {self.prospecto}"


class CitaClienteLibre(TimeStampedModel):
    class Estado(models.TextChoices):
        PROGRAMADA = "PROGRAMADA", "Programada"
        CANCELADA = "CANCELADA", "Cancelada"
        NO_ASISTIO = "NO_ASISTIO", "No asistio"

    cliente = models.ForeignKey(
        "customers.Cliente",
        on_delete=models.CASCADE,
        related_name="citas_medicas_libres",
    )
    servicio_config = models.ForeignKey(
        "catalogs.ServicioConfig",
        on_delete=models.PROTECT,
        related_name="citas_clientes_libres",
    )
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.CASCADE,
        related_name="citas_clientes_libres",
    )
    fecha_hora = models.DateTimeField()
    estado = models.CharField(
        max_length=32,
        choices=Estado.choices,
        default=Estado.PROGRAMADA,
    )
    detalles_cita = models.TextField(blank=True)

    class Meta:
        db_table = "citas_clientes_libres"
        ordering = ("fecha_hora",)

    def clean(self):
        errors = {}
        if self.servicio_config_id and self.servicio_config.proc_estetico_id:
            errors["servicio_config"] = "Las citas medicas libres solo pueden usar servicios sin procedimiento."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Cita libre #{self.pk} - {self.cliente}"


class AgendaHabitualEspecialista(TimeStampedModel):
    especialista = models.ForeignKey(
        "staff.Especialista",
        on_delete=models.CASCADE,
        related_name="agendas_habituales",
    )
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.CASCADE,
        related_name="agendas_habituales",
    )
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    hora_inicio = models.TimeField(null=True, blank=True)
    hora_fin = models.TimeField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    detalle = models.CharField(max_length=255, blank=True)
    tipos_servicio = models.ManyToManyField(
        "catalogs.TipoServicio",
        blank=True,
        related_name="agendas_habituales",
    )
    tipos_proc_estetico = models.ManyToManyField(
        "catalogs.ProcEsteticosTipo",
        blank=True,
        related_name="agendas_habituales",
    )
    procedimientos_esteticos = models.ManyToManyField(
        "catalogs.ProcEstetico",
        blank=True,
        related_name="agendas_habituales",
    )

    class Meta:
        db_table = "agendas_habituales_especialista"
        ordering = ("especialista__usuario__primer_nombre", "fecha_inicio", "id")

    @property
    def dias_semana(self):
        return list(self.dias.values_list("dia_semana", flat=True).order_by("dia_semana"))

    def clean(self):
        if self.fecha_fin < self.fecha_inicio:
            raise ValidationError(
                {"fecha_fin": "La fecha final no puede ser anterior a la fecha inicial."}
            )

    def __str__(self):
        return f"Agenda habitual #{self.pk} - {self.especialista}"


class AgendaHabitualDia(TimeStampedModel):
    agenda = models.ForeignKey(
        "operations.AgendaHabitualEspecialista",
        on_delete=models.CASCADE,
        related_name="dias",
    )
    dia_semana = models.PositiveSmallIntegerField(choices=DiaSemana.choices)

    class Meta:
        db_table = "agendas_habituales_dias"
        ordering = ("agenda", "dia_semana")
        constraints = [
            models.UniqueConstraint(
                fields=("agenda", "dia_semana"),
                name="uniq_agenda_habitual_dia_semana",
            )
        ]

    def __str__(self):
        return f"{self.agenda} - {self.get_dia_semana_display()}"


class AgendaExcepcionEspecialista(TimeStampedModel):
    class TipoExcepcion(models.TextChoices):
        AGREGAR = "AGREGAR", "Agregar disponibilidad"
        BLOQUEAR = "BLOQUEAR", "Bloquear disponibilidad"

    especialista = models.ForeignKey(
        "staff.Especialista",
        on_delete=models.CASCADE,
        related_name="excepciones_agenda",
    )
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.CASCADE,
        related_name="excepciones_agenda",
    )
    fecha = models.DateField()
    hora_inicio = models.TimeField(null=True, blank=True)
    hora_fin = models.TimeField(null=True, blank=True)
    tipo_excepcion = models.CharField(max_length=10, choices=TipoExcepcion.choices)
    activo = models.BooleanField(default=True)
    detalle = models.CharField(max_length=255, blank=True)
    tipos_servicio = models.ManyToManyField(
        "catalogs.TipoServicio",
        blank=True,
        related_name="excepciones_agenda",
    )
    tipos_proc_estetico = models.ManyToManyField(
        "catalogs.ProcEsteticosTipo",
        blank=True,
        related_name="excepciones_agenda",
    )
    procedimientos_esteticos = models.ManyToManyField(
        "catalogs.ProcEstetico",
        blank=True,
        related_name="excepciones_agenda",
    )

    class Meta:
        db_table = "agendas_excepciones_especialista"
        ordering = ("-fecha", "especialista__usuario__primer_nombre", "id")

    def __str__(self):
        return f"{self.get_tipo_excepcion_display()} - {self.especialista} - {self.fecha}"


class DiaBloqueadoAgendaGlobal(TimeStampedModel):
    fecha = models.DateField(unique=True)
    activo = models.BooleanField(default=True)
    detalle = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "agenda_global_dias_bloqueados"
        ordering = ("fecha",)

    def __str__(self):
        return f"{self.fecha} - {'Activo' if self.activo else 'Inactivo'}"


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
