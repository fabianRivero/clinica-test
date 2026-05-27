from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.contrib.auth.hashers import check_password, identify_hasher, make_password
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
        return self.citas_medicas.filter(estado=CitaMedica.Estado.CONFIRMADA).count()

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
            and not self.tiene_reserva_programada
            and not self.tiene_cierre_pendiente
            and self.sesiones_disponibles > 0
        )

    @property
    def motivo_bloqueo_reserva(self):
        if self.estado != self.Estado.EN_PROCESO:
            return "Solo los tratamientos en proceso pueden reservar nuevas citas."
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
    class EstadoVerificacion(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        VERIFICADA = "VERIFICADA", "Verificada"
        NO_REQUERIDA = "NO_REQUERIDA", "No requerida"

    class MetodoVerificacion(models.TextChoices):
        BIOMETRIA = "BIOMETRIA", "Biometria"
        QR = "QR", "QR"
        MANUAL = "MANUAL", "Manual"
        OTRO = "OTRO", "Otro"

    class MetodoConfirmacion(models.TextChoices):
        BIOMETRICO = "BIOMETRICO", "Biometrico"
        TABLET = "TABLET", "Tablet"
        MANUAL = "MANUAL", "Manual"

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
    metodo_confirmacion = models.CharField(
        max_length=16,
        choices=MetodoConfirmacion.choices,
        blank=True,
        default="",
    )
    estado_verificacion = models.CharField(
        max_length=16,
        choices=EstadoVerificacion.choices,
        default=EstadoVerificacion.NO_REQUERIDA,
    )
    metodo_verificacion = models.CharField(
        max_length=16,
        choices=MetodoVerificacion.choices,
        blank=True,
        default="",
    )
    detalles_cita = models.TextField(blank=True)

    class Meta:
        db_table = "citas_medicas"
        ordering = ("fecha_hora",)

    def clean(self):
        errors = {}

        if self.estado == self.Estado.CONFIRMADA:
            if self.metodo_confirmacion == self.MetodoConfirmacion.BIOMETRICO and not self.verif_biometria:
                errors["verif_biometria"] = "Una cita confirmada por biometria requiere verificacion biometrica."
            if not self.metodo_confirmacion:
                errors["metodo_confirmacion"] = "Debes especificar el metodo de confirmacion para una cita confirmada."

        if self.operacion_id:
            otras_citas = self.operacion.citas_medicas.exclude(pk=self.pk)
            sesiones_consumidas = otras_citas.filter(
                models.Q(estado=self.Estado.PROGRAMADA)
                | models.Q(estado=self.Estado.REALIZADA_PENDIENTE_BIOMETRIA)
                | models.Q(estado=self.Estado.CONFIRMADA)
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
        previous_status = None
        if self.pk:
            previous_status = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("estado", flat=True)
                .first()
            )

        # Compatibilidad temporal: derivamos campos nuevos desde el modelo legacy.
        if self.estado == self.Estado.CONFIRMADA:
            self.estado_verificacion = self.EstadoVerificacion.VERIFICADA
        elif self.estado == self.Estado.REALIZADA_PENDIENTE_BIOMETRIA:
            self.estado_verificacion = self.EstadoVerificacion.PENDIENTE
        elif (
            self.estado == self.Estado.PROGRAMADA
            and previous_status == self.Estado.NO_ASISTIO
        ):
            self.estado_verificacion = self.EstadoVerificacion.PENDIENTE
        else:
            self.estado_verificacion = self.EstadoVerificacion.NO_REQUERIDA

        if self.metodo_confirmacion == self.MetodoConfirmacion.BIOMETRICO:
            self.metodo_verificacion = self.MetodoVerificacion.BIOMETRIA
        elif self.metodo_confirmacion == self.MetodoConfirmacion.TABLET:
            self.metodo_verificacion = self.MetodoVerificacion.QR
        elif self.metodo_confirmacion == self.MetodoConfirmacion.MANUAL:
            self.metodo_verificacion = self.MetodoVerificacion.MANUAL
        else:
            self.metodo_verificacion = ""

        if self.estado == self.Estado.CONFIRMADA and self.verif_biometria and not self.fecha_confirmacion_biometrica:
            self.fecha_confirmacion_biometrica = timezone.now()
        if self.estado != self.Estado.CONFIRMADA:
            self.fecha_confirmacion_biometrica = None
            self.metodo_confirmacion = ""

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


class EventoConfirmacionCita(TimeStampedModel):
    class Metodo(models.TextChoices):
        BIOMETRICO = "BIOMETRICO", "Biometrico"
        TABLET = "TABLET", "Tablet"
        MANUAL = "MANUAL", "Manual"

    class ModoOrigen(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        OFFLINE = "OFFLINE", "Offline"

    class EstadoSync(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        ACCEPTED = "ACCEPTED", "Aceptado"
        DUPLICATE = "DUPLICATE", "Duplicado"
        CONFLICT = "CONFLICT", "Conflicto"
        REJECTED = "REJECTED", "Rechazado"

    cita = models.ForeignKey(
        "operations.CitaMedica",
        on_delete=models.CASCADE,
        related_name="eventos_confirmacion",
    )
    paciente = models.ForeignKey(
        "customers.Cliente",
        on_delete=models.PROTECT,
        related_name="eventos_confirmacion_citas",
    )
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.PROTECT,
        related_name="eventos_confirmacion_citas",
    )
    metodo = models.CharField(max_length=16, choices=Metodo.choices)
    confirmado_en = models.DateTimeField(default=timezone.now)
    ip_origen = models.GenericIPAddressField(null=True, blank=True)
    event_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    origin_mode = models.CharField(max_length=16, choices=ModoOrigen.choices, default=ModoOrigen.ONLINE)
    device_id = models.CharField(max_length=80, blank=True, default="")
    recorded_at_device = models.DateTimeField(null=True, blank=True)
    confirmed_at_server = models.DateTimeField(null=True, blank=True)
    sync_status = models.CharField(max_length=16, choices=EstadoSync.choices, default=EstadoSync.ACCEPTED)
    conflict_reason = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        db_table = "eventos_confirmacion_citas"
        ordering = ("-confirmado_en", "-id")

    def __str__(self):
        return f"Evento confirmacion cita #{self.cita_id} - {self.metodo}"


class TabletKiosko(TimeStampedModel):
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=120)
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.PROTECT,
        related_name="kioskos_tablet",
    )
    clave = models.CharField(max_length=255)
    activo = models.BooleanField(default=True)
    ultimo_acceso = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tablet_kioskos"
        ordering = ("nombre",)

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"

    def set_clave(self, raw_clave: str):
        self.clave = make_password(raw_clave)

    def check_clave(self, raw_clave: str) -> bool:
        return check_password(raw_clave, self.clave)

    def save(self, *args, **kwargs):
        if self.clave:
            try:
                identify_hasher(self.clave)
            except Exception:
                self.clave = make_password(self.clave)
        super().save(*args, **kwargs)


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


@receiver(post_save, sender=Operacion)
@receiver(post_delete, sender=Operacion)
def sincronizar_estado_cliente(sender, instance, **kwargs):
    instance.paciente.actualizar_estado_automaticamente()


class BranchAdminAuditLog(TimeStampedModel):
    class Action(models.TextChoices):
        CHANGE_ADMIN = "CHANGE_ADMIN", "Cambio administrador"
        CREATE_BRANCH_WIZARD = "CREATE_BRANCH_WIZARD", "Crear sucursal wizard"
        TOGGLE_BRANCH = "TOGGLE_BRANCH", "Cambiar estado sucursal"
        TOGGLE_BRANCH_ADMIN = "TOGGLE_BRANCH_ADMIN", "Cambiar estado admin sucursal"

    branch = models.ForeignKey("catalogs.Sucursal", on_delete=models.CASCADE, related_name="admin_audit_logs")
    actor = models.ForeignKey("accounts.Usuario", on_delete=models.SET_NULL, null=True, blank=True, related_name="branch_admin_audit_logs")
    action = models.CharField(max_length=40, choices=Action.choices)
    detail = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "branch_admin_audit_logs"
        ordering = ("-created_at",)
