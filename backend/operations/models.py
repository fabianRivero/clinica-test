import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from common.models import CatalogoEditableModel, TimeStampedModel


class OperacionPrecondicionNoCumplida(Exception):
    """Raised when ``Operacion.cerrar_como_finalizada`` cannot transition
    the operation because one of its preconditions failed.

    Carries the structured ``preconditions`` report (sesiones / cuotas /
    monto) so the DRF viewset can surface it verbatim as a 409 response
    body. Source-state rejections (``Operacion`` not in ``EN_PROCESO``)
    raise a plain ``ValidationError`` instead — they are NOT precondition
    failures and must not be wrapped in this exception.
    """

    def __init__(self, operacion, report):
        self.operacion = operacion
        self.report = report
        super().__init__(
            "Precondiciones de cierre no cumplidas para la operacion "
            f"#{operacion.pk}."
        )


class DiaSemana(models.IntegerChoices):
    DOMINGO = 0, "Domingo"
    LUNES = 1, "Lunes"
    MARTES = 2, "Martes"
    MIERCOLES = 3, "Miércoles"
    JUEVES = 4, "Jueves"
    VIERNES = 5, "Viernes"
    SABADO = 6, "Sábado"


class Operacion(TimeStampedModel):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        EN_PROCESO = "EN_PROCESO", "En proceso"
        FINALIZADA = "FINALIZADA", "Finalizada"
        CANCELADA = "CANCELADA", "Cancelada"
        SUSPENDIDA = "SUSPENDIDA", "Suspendida"

    class FinalizationKind(models.TextChoices):
        MANUAL_FINALIZADA = "MANUAL_FINALIZADA", "Finalizada manualmente"
        MANUAL_SUSPENDIDA = "MANUAL_SUSPENDIDA", "Suspendida manualmente"

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

    # --- Manual closure audit trail (operation-manual-closure) ----------
    # Nullable on purpose: legacy ``Operacion`` rows that closed under the
    # old auto-finalization rule have no historical admin and we don't
    # want to invent one during the migration.
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="operaciones_finalizadas",
        null=True,
        blank=True,
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalization_kind = models.CharField(
        max_length=24,
        choices=FinalizationKind.choices,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "operaciones"
        ordering = ("-created_at",)

    @property
    def sesiones_confirmadas(self):
        return self.citas_medicas.filter(estado=CitaMedica.Estado.CONFIRMADA).count()

    @property
    def sesiones_pendientes_confirmacion(self):
        return self.citas_medicas.filter(
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
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
                "Hay una cita que debe confirmarse antes de hacer una reserva en este procedimiento."
            )
        if self.tiene_cierre_pendiente:
            return (
                "Hay una cita pendiente de cierre antes de hacer una reserva en este procedimiento."
            )
        if self.sesiones_disponibles <= 0:
            return "Tu tratamiento ya no tiene sesiones disponibles para nuevas reservas."
        return ""

    # ------------------------------------------------------------------ #
    # Manual closure (operation-manual-closure)                           #
    # ------------------------------------------------------------------ #
    #
    # ``puede_cerrar`` is the single source of truth for "is this
    # operation ready to be finalized". It powers the server's 409
    # response AND the frontend's disabled-state + modal preview, so both
    # consumers always agree on the same precondition shape.
    #
    # The shape is deliberately kept minimal and quantised:
    #   * boolean ``ok`` is the global gate (True iff every precondition
    #     section is True)
    #   * each section exposes enough detail to render the modal without a
    #     second round-trip
    #   * monetary fields are 2dp DECIMAL STRINGS (NOT Decimals or
    #     floats) so the JSON payload survives float round-trip in
    #     JavaScript without precision loss
    _CENT = Decimal("0.01")

    def puede_cerrar(self):
        """Return ``(ok, preconditions)``.

        ``preconditions`` mirrors the contract documented in the
        ``operation-manual-closure`` design doc:

        ```
        {
          "ok": false,
          "sesiones": {
            "ok": false,
            "expected": 5,
            "confirmed": 3,
            "reserved": 1,    # diagnostico only (PROGRAMADA)
            "pending": 1,     # diagnostico only (REALIZADA_PENDIENTE_VERIFICACION)
            "missing": 2      # expected - confirmed
          },
          "cuotas": {
            "ok": false,
            "pending": [{"nroCuota": 2, "estado": "PENDIENTE"}]
          },
          "monto": {
            "ok": false,
            "precioTotal": "100.00",
            "sumaMontoProgramado": "95.00",
            "diff": "-5.00"
          }
        }
        ```

        ``diff = precioTotal - sumaMontoProgramado`` (2dp quantised).
        Negative means sumaMontoProgramado > precioTotal.

        Sesion "realizada" semantics: ONLY ``CitaMedica.Estado.CONFIRMADA``
        counts towards ``consumed``. A reservation in ``PROGRAMADA`` or a
        session the specialist marked as attended but the client has not
        yet approved in the tablet (``REALIZADA_PENDIENTE_VERIFICACION``)
        do NOT count as realized sessions and BLOCK closure. The
        ``reserved`` and ``pending`` counts remain in the report so the
        admin can see exactly what's pending in the diagnostic UI.
        """
        # ----- sesiones -----
        # Only CONFIRMADA counts as a realized session. PROGRAMADA
        # (just reserved, not yet performed) and
        # REALIZADA_PENDIENTE_VERIFICACION (performed but not yet
        # client-approved) both BLOCK closure.
        confirmed = self.citas_medicas.filter(
            estado=CitaMedica.Estado.CONFIRMADA
        ).count()
        # Diagnostic counts (do NOT contribute to consumed).
        reserved = self.citas_medicas.filter(
            estado=CitaMedica.Estado.PROGRAMADA
        ).count()
        pending = self.citas_medicas.filter(
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION
        ).count()
        expected = int(self.sesiones_totales or 0)
        consumed = confirmed  # only CONFIRMADA counts.
        missing = max(expected - consumed, 0)
        sesiones_ok = missing == 0 and expected > 0

        # ----- cuotas -----
        qs_cuotas = self.cuotas_plan_pagos.exclude(
            estado__in={"PAGADO", "NO_PAGADA"}
        ).order_by("nro_cuota")
        cuotas_pending = [
            {"nroCuota": c.nro_cuota, "estado": c.estado}
            for c in qs_cuotas
        ]
        cuotas_ok = not cuotas_pending

        # ----- monto -----
        precio_total = (self.precio_total or Decimal("0")).quantize(self._CENT)
        suma_monto = sum(
            (c.monto_programado or Decimal("0"))
            for c in self.cuotas_plan_pagos.all()
        ).quantize(self._CENT)
        diff = (precio_total - suma_monto).quantize(self._CENT)
        monto_ok = diff == Decimal("0.00")

        report = {
            "ok": sesiones_ok and cuotas_ok and monto_ok,
            "sesiones": {
                "ok": sesiones_ok,
                "expected": expected,
                "confirmed": confirmed,
                "reserved": reserved,
                "pending": pending,
                "missing": missing,
            },
            "cuotas": {
                "ok": cuotas_ok,
                "pending": cuotas_pending,
            },
            "monto": {
                "ok": monto_ok,
                "precioTotal": str(precio_total),
                "sumaMontoProgramado": str(suma_monto),
                "diff": str(diff),
            },
        }
        return report["ok"], report

    def cerrar_como_finalizada(self, user):
        """Transition ``self`` ``EN_PROCESO -> FINALIZADA`` atomically.

        Writes the three audit fields (``finalized_by``, ``finalized_at``,
        ``finalization_kind``) inside the same ``save()`` so partial
        writes are impossible — readers will either see ``EN_PROCESO``
        with audit fields null or ``FINALIZADA`` with the full audit
        trail.

        Raises ``OperacionPrecondicionNoCumplida`` when the precondition
        report is not OK. Raises ``ValidationError`` when the source
        state is not ``EN_PROCESO``.
        """
        from django.core.exceptions import ValidationError

        if self.estado != self.Estado.EN_PROCESO:
            raise ValidationError(
                f"Solo se pueden finalizar operaciones en proceso "
                f"(estado actual: {self.get_estado_display()})."
            )

        ok, report = self.puede_cerrar()
        if not ok:
            raise OperacionPrecondicionNoCumplida(self, report)

        now = timezone.now()
        self.estado = self.Estado.FINALIZADA
        self.finalized_by = user
        self.finalized_at = now
        self.finalization_kind = self.FinalizationKind.MANUAL_FINALIZADA
        self.save(update_fields=[
            "estado",
            "finalized_by",
            "finalized_at",
            "finalization_kind",
            "updated_at",
        ])

    def cerrar_como_suspendida(self, user):
        """Transition ``self`` ``EN_PROCESO -> SUSPENDIDA`` unconditionally.

        No precondition check — the admin explicitly chose to suspend the
        treatment even when sesiones/cuotas/monto don't reconcile.

        Raises ``ValidationError`` when the source state is not
        ``EN_PROCESO``. (Same shape as ``cerrar_como_finalizada``.)
        """
        from django.core.exceptions import ValidationError

        if self.estado != self.Estado.EN_PROCESO:
            raise ValidationError(
                f"Solo se pueden suspender operaciones en proceso "
                f"(estado actual: {self.get_estado_display()})."
            )

        now = timezone.now()
        self.estado = self.Estado.SUSPENDIDA
        self.finalized_by = user
        self.finalized_at = now
        self.finalization_kind = self.FinalizationKind.MANUAL_SUSPENDIDA
        self.save(update_fields=[
            "estado",
            "finalized_by",
            "finalized_at",
            "finalization_kind",
            "updated_at",
        ])

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
        REALIZADA_PENDIENTE_VERIFICACION = (
            "REALIZADA_PENDIENTE_VERIFICACION",
            "Realizada Pendiente de Verificación",
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

    # --- Appointment payment (citas-pagos) ---------------------------------
    # Default 0 so legacy rows stay non-billable. Admins set this before
    # registering the first APROBADO PagoCita via the cobrar endpoint.
    precio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
    )

    # --- Appointment reservation redesign (planning fields) -----------------
    # Captured at reservation time. All optional so legacy rows keep working.
    duracion_estimada_minutos = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(480)],
        help_text="Duracion estimada en minutos (1..480).",
    )
    descripcion_general = models.TextField(blank=True, default="")
    notas_previas = models.TextField(blank=True, default="")
    notas_post = models.TextField(blank=True, default="")
    foto_antes = models.ImageField(
        upload_to="citas/%Y/%m/%d/antes/",
        null=True,
        blank=True,
    )
    foto_despues = models.ImageField(
        upload_to="citas/%Y/%m/%d/despues/",
        null=True,
        blank=True,
    )
    procedimiento_planificado = models.TextField(blank=True, default="")
    zona_cuerpo_planificada = models.CharField(max_length=200, blank=True, default="")

    # --- Appointment reservation redesign (real-time fields) ----------------
    # Captured at close time, when the cita transitions to
    # REALIZADA_PENDIENTE_VERIFICACION.
    hora_real_inicio = models.DateTimeField(null=True, blank=True)
    hora_real_fin = models.DateTimeField(null=True, blank=True)
    procedimiento_realizado = models.TextField(blank=True, default="")
    zona_cuerpo_realizada = models.CharField(max_length=200, blank=True, default="")

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
                | models.Q(estado=self.Estado.REALIZADA_PENDIENTE_VERIFICACION)
                | models.Q(estado=self.Estado.CONFIRMADA)
            ).count()

            estado_consume_sesion = self.estado in {
                self.Estado.PROGRAMADA,
                self.Estado.REALIZADA_PENDIENTE_VERIFICACION,
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
        elif self.estado == self.Estado.REALIZADA_PENDIENTE_VERIFICACION:
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


def _operacion_foto_upload_to(instance, filename):
    """Callable ``upload_to`` for ``OperacionFoto.imagen``.

    Returns ``operaciones/<YYYY>/<MM>/<DD>/<kind>/<uuid-prefix>-``
    so that same-day uploads do not collide and the path stays organised by
    date AND kind. Django invokes this once per save, after the row's PK
    exists; the FK is set by the endpoint before ``save()``, so
    ``instance.kind`` is available.
    """
    stamp = timezone.now().strftime("%Y/%m/%d")
    prefix = uuid.uuid4().hex[:12]
    return f"operaciones/{stamp}/{instance.kind}/{prefix}-{filename}"


class OperacionFoto(models.Model):
    """Persistent before/after photos attached to an ``Operacion``.

    Inherits directly from ``models.Model`` (NOT ``TimeStampedModel``) per
    the spec, which forbids an ``updated_at`` column on this table.
    """

    class Kind(models.TextChoices):
        ANTES = "antes", "Antes"
        DESPUES = "despues", "Despues"

    operacion = models.ForeignKey(
        "operations.Operacion",
        on_delete=models.CASCADE,
        related_name="fotos_operacion",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    imagen = models.ImageField(upload_to=_operacion_foto_upload_to)
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "operaciones_fotos"
        ordering = ("uploaded_at", "id")
        indexes = [
            models.Index(fields=["operacion", "kind", "uploaded_at", "id"]),
        ]

    def __str__(self):
        return f"OperacionFoto #{self.pk} - {self.operacion_id} ({self.kind})"


class CitaMaquinaria(TimeStampedModel):
    """Many-to-many between CitaMedica and Maquinaria with payload.

    `planificada=True` rows are reserved at booking time; `planificada=False`
    rows record the equipment actually used at close time. The UniqueConstraint
    on (cita, maquinaria, planificada) prevents the same machinery row being
    added twice in the same phase.
    """

    cita = models.ForeignKey(
        "operations.CitaMedica",
        on_delete=models.CASCADE,
        related_name="maquinaria_items",
    )
    maquinaria = models.ForeignKey(
        "catalogs.Maquinaria",
        on_delete=models.PROTECT,
        related_name="citas_items",
    )
    cantidad = models.PositiveIntegerField(default=1)
    planificada = models.BooleanField(default=True)

    class Meta:
        db_table = "citas_maquinaria"
        ordering = ("cita", "maquinaria")
        constraints = [
            models.UniqueConstraint(
                fields=("cita", "maquinaria", "planificada"),
                name="uniq_cita_maquinaria_planificada",
            ),
        ]

    def __str__(self):
        fase = "planificada" if self.planificada else "usada"
        return f"Cita #{self.cita_id} - {self.maquinaria} ({fase}, x{self.cantidad})"


class CitaEspecialista(TimeStampedModel):
    """Many-to-many between CitaMedica and Especialista with payload.

    `planificada=True` rows are the specialists expected to attend;
    `planificada=False` rows record who actually attended at close time.
    """

    cita = models.ForeignKey(
        "operations.CitaMedica",
        on_delete=models.CASCADE,
        related_name="especialistas_items",
    )
    especialista = models.ForeignKey(
        "staff.Especialista",
        on_delete=models.PROTECT,
        related_name="citas_items",
    )
    planificada = models.BooleanField(default=True)

    class Meta:
        db_table = "citas_especialistas"
        ordering = ("cita", "especialista")
        constraints = [
            models.UniqueConstraint(
                fields=("cita", "especialista", "planificada"),
                name="uniq_cita_especialista_planificada",
            ),
        ]

    def __str__(self):
        fase = "planificada" if self.planificada else "atendida"
        return f"Cita #{self.cita_id} - {self.especialista} ({fase})"


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
    # --- citas-pagos follow-on: precio editable hasta el primer APROBADO ---
    # Default 0 keeps legacy prospect rows non-billable until the admin sets
    # a price. Mirrors ``CitaMedica.precio`` and ``CitaClienteLibre.precio``.
    precio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
    )

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
        REALIZADA = "REALIZADA", "Realizada"
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

    # --- Appointment payment (citas-pagos) ---------------------------------
    # Default 0 so legacy rows stay non-billable. Admins set this before
    # registering the first APROBADO PagoCita via the cobrar endpoint.
    precio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
    )

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
        return f"Evento confirmación cita #{self.cita_id} - {self.metodo}"


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
    fecha_fin = models.DateField(null=True, blank=True)
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
        if self.fecha_fin is not None and self.fecha_fin < self.fecha_inicio:
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
