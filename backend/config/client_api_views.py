import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps

from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from billing.models import ConfiguracionPagoQR, CuotaPlanPago, PagoRealizado
from clinical.models import AnalisisEstetico
from customers.models import Cliente
from operations.models import CitaMedica, DisponibilidadCita, Operacion


RESERVATION_WINDOW_DAYS = 35
BLOCKING_RESERVATION_STATES = {
    CitaMedica.Estado.PROGRAMADA,
    CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA,
    CitaMedica.Estado.CONFIRMADA,
}


def _json(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _load_payload(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _client_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return _json({"detail": "Autenticacion requerida."}, status=401)
        if not user.es_cliente:
            return _json({"detail": "No tienes permisos para acceder a esta vista."}, status=403)
        try:
            request.cliente = user.cliente
        except Cliente.DoesNotExist:
            return _json({"detail": "No existe un perfil de cliente asociado a esta cuenta."}, status=404)
        return view_func(request, *args, **kwargs)

    return wrapped


def _currency(amount):
    return f"Bs {amount:.2f}"


def _date_label(value):
    if not value:
        return "Sin fecha"
    return value.strftime("%d/%m/%Y")


def _datetime_label(value):
    if not value:
        return "Sin fecha"
    return timezone.localtime(value).strftime("%d/%m/%Y %H:%M")


def _month_label(value):
    if not value:
        return "Sin mes"
    return value.strftime("%B %Y").capitalize()


def _full_name(user):
    return user.nombre_completo or user.username


def _procedure_name(operacion):
    procedimiento = operacion.servicio_config.proc_estetico
    if procedimiento:
        return procedimiento.proceso
    return operacion.servicio_config.tipo_servicio.tipo


def _operation_specialist(operacion):
    citas = list(operacion.citas_medicas.all())
    if not citas:
        return "Por asignar"

    now = timezone.now()
    upcoming = [cita for cita in citas if cita.fecha_hora >= now]
    if upcoming:
        return _full_name(upcoming[0].medico.usuario)
    return _full_name(citas[-1].medico.usuario)


def _next_appointment(operacion):
    citas = list(operacion.citas_medicas.all())
    if not citas:
        return None

    now = timezone.now()
    upcoming = [cita for cita in citas if cita.fecha_hora >= now]
    return upcoming[0] if upcoming else None


def _quota_amount(cuota):
    operacion = cuota.operacion
    if operacion.cuotas_totales:
        return (operacion.precio_total / Decimal(operacion.cuotas_totales)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    return operacion.precio_total


def _payment_tone(payment):
    if payment.estado_verificacion == PagoRealizado.EstadoVerificacion.APROBADO:
        return "approved"
    if payment.estado_verificacion == PagoRealizado.EstadoVerificacion.RECHAZADO:
        return "observed"
    return "pending"


def _quota_tone(cuota):
    if cuota.estado == CuotaPlanPago.Estado.PAGADO:
        return "approved"
    if cuota.estado == CuotaPlanPago.Estado.VENCIDA:
        return "danger"
    return "pending"


def _appointment_tone(cita):
    if cita.estado == CitaMedica.Estado.CONFIRMADA:
        return "approved"
    if cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA:
        return "warning"
    if cita.estado == CitaMedica.Estado.CANCELADA:
        return "danger"
    if cita.estado == CitaMedica.Estado.NO_ASISTIO:
        return "observed"
    return "pending"


def _reserve_message(operacion):
    if operacion.estado != Operacion.Estado.EN_PROCESO:
        return "Solo los tratamientos en proceso pueden reservar nuevas citas."
    if operacion.puede_reservar:
        return f"Tienes {operacion.sesiones_disponibles} sesion(es) disponible(s) para reservar."
    return "Tu tratamiento ya no tiene sesiones disponibles para nuevas reservas."


def _metric(identifier, label, value, delta, tone):
    return {
        "id": identifier,
        "label": label,
        "value": str(value),
        "delta": delta,
        "tone": tone,
    }


def _operation_item(operacion):
    next_appointment = _next_appointment(operacion)
    return {
        "id": f"OP-{operacion.pk:04d}",
        "rawId": operacion.pk,
        "procedure": _procedure_name(operacion),
        "serviceType": operacion.servicio_config.tipo_servicio.tipo,
        "specialist": _operation_specialist(operacion),
        "status": operacion.get_estado_display(),
        "statusTone": (
            "success"
            if operacion.estado == Operacion.Estado.FINALIZADA
            else "danger"
            if operacion.estado == Operacion.Estado.CANCELADA
            else "warning"
            if operacion.estado == Operacion.Estado.BORRADOR
            else "primary"
        ),
        "price": _currency(operacion.precio_total),
        "zone": ", ".join(
            [value for value in [operacion.zona_general, operacion.zona_especifica] if value]
        )
        or "Sin zona registrada",
        "startedAt": _date_label(operacion.fecha_inicio),
        "endedAt": _date_label(operacion.fecha_final) if operacion.fecha_final else "En curso",
        "nextAppointment": _datetime_label(next_appointment.fecha_hora) if next_appointment else "Sin cita futura",
        "recommendations": operacion.recomendaciones or "Sin recomendaciones registradas.",
        "details": operacion.detalles_op or "Sin detalle operativo.",
        "sessions": {
            "total": operacion.sesiones_totales,
            "confirmed": operacion.sesiones_confirmadas,
            "pendingBiometric": operacion.sesiones_pendientes_confirmacion,
            "reserved": operacion.reservas_activas,
            "available": operacion.sesiones_disponibles,
        },
        "canReserve": operacion.puede_reservar,
        "reserveMessage": _reserve_message(operacion),
        "quotaSummary": (
            f"{operacion.cuotas_plan_pagos.filter(estado=CuotaPlanPago.Estado.PAGADO).count()}"
            f"/{operacion.cuotas_plan_pagos.count()} cuota(s) pagadas"
        ),
    }


def _reservation_window_for_operation(operacion):
    today = timezone.localdate()
    window_start = max(today, operacion.fecha_inicio or today)
    window_end = window_start + timedelta(days=RESERVATION_WINDOW_DAYS - 1)
    if operacion.fecha_final:
        window_end = min(window_end, operacion.fecha_final)
    return window_start, window_end


def _build_operation_slot_map(operacion):
    if not operacion.puede_reservar:
        return {
            "windowStart": None,
            "windowEnd": None,
            "monthLabel": "",
            "availableDates": [],
            "slotsByDate": {},
            "slotCount": 0,
        }

    window_start, window_end = _reservation_window_for_operation(operacion)
    if window_end < window_start:
        return {
            "windowStart": window_start.isoformat(),
            "windowEnd": window_end.isoformat(),
            "monthLabel": _month_label(window_start),
            "availableDates": [],
            "slotsByDate": {},
            "slotCount": 0,
        }

    servicio_config = operacion.servicio_config
    procedimiento = servicio_config.proc_estetico
    availability_scope = Q(tipos_servicio=servicio_config.tipo_servicio)
    if procedimiento:
        availability_scope |= Q(tipos_proc_estetico=procedimiento.tipo_p_estetico)
        availability_scope |= Q(procedimientos_esteticos=procedimiento)

    slots_qs = (
        DisponibilidadCita.objects.select_related("especialista__usuario")
        .prefetch_related(
            Prefetch(
                "citas_origen",
                queryset=CitaMedica.objects.only("id", "estado", "disponibilidad_id").order_by("-created_at"),
            )
        )
        .filter(
            activo=True,
            especialista__usuario__is_active=True,
            fecha_hora__date__gte=window_start,
            fecha_hora__date__lte=window_end,
            fecha_hora__gt=timezone.now(),
        )
        .filter(availability_scope)
        .distinct()
        .order_by("fecha_hora", "especialista__usuario__primer_nombre", "especialista__usuario__apellido_paterno")
    )

    slots_by_date = {}
    available_dates = []
    for slot in slots_qs:
        if any(cita.estado in BLOCKING_RESERVATION_STATES for cita in slot.citas_origen.all()):
            continue

        local_dt = timezone.localtime(slot.fecha_hora)
        date_key = local_dt.date().isoformat()
        slot_item = {
            "slotId": slot.pk,
            "specialistId": slot.especialista_id,
            "specialist": _full_name(slot.especialista.usuario),
            "date": date_key,
            "time": local_dt.strftime("%H:%M"),
            "dateTimeLabel": _datetime_label(slot.fecha_hora),
        }
        slots_by_date.setdefault(date_key, []).append(slot_item)

    for date_key, day_slots in sorted(slots_by_date.items()):
        day_slots.sort(key=lambda item: (item["time"], item["specialist"]))
        day_date = date.fromisoformat(date_key)
        available_dates.append(
            {
                "date": date_key,
                "label": day_date.strftime("%d/%m"),
                "slotCount": len(day_slots),
                "weekday": day_date.strftime("%A").capitalize(),
            }
        )

    return {
        "windowStart": window_start.isoformat(),
        "windowEnd": window_end.isoformat(),
        "monthLabel": _month_label(window_start),
        "availableDates": available_dates,
        "slotsByDate": slots_by_date,
        "slotCount": sum(item["slotCount"] for item in available_dates),
    }


def _get_client_operation(cliente, operation_id):
    return (
        Operacion.objects.filter(paciente=cliente, pk=operation_id)
        .select_related("servicio_config__tipo_servicio", "servicio_config__proc_estetico")
        .prefetch_related(
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.select_related("medico__usuario").order_by("fecha_hora"),
            ),
            Prefetch(
                "cuotas_plan_pagos",
                queryset=CuotaPlanPago.objects.order_by("nro_cuota"),
            ),
        )
        .first()
    )


def _quota_item(cuota):
    latest_payment = cuota.pagos_realizados.order_by("-created_at").first()
    amount_value = _quota_amount(cuota)
    return {
        "id": f"CUO-{cuota.pk:04d}",
        "rawId": cuota.pk,
        "operation": _procedure_name(cuota.operacion),
        "quotaLabel": f"Cuota {cuota.nro_cuota}",
        "amount": _currency(amount_value),
        "amountValue": f"{amount_value:.2f}",
        "dueDate": _date_label(cuota.fecha_vencimiento),
        "status": cuota.get_estado_display(),
        "statusTone": _quota_tone(cuota),
        "latestPaymentStatus": latest_payment.get_estado_verificacion_display() if latest_payment else "Sin comprobante",
        "latestPaymentTone": _payment_tone(latest_payment) if latest_payment else "neutral",
        "canUploadReceipt": cuota.estado != CuotaPlanPago.Estado.PAGADO,
    }


def _payment_item(payment):
    return {
        "id": f"PAY-{payment.pk:04d}",
        "operation": _procedure_name(payment.cuota.operacion),
        "quotaLabel": f"Cuota {payment.cuota.nro_cuota}",
        "amount": _currency(payment.monto_pagado),
        "submittedAt": _datetime_label(payment.created_at),
        "status": payment.get_estado_verificacion_display(),
        "statusTone": _payment_tone(payment),
        "dueDate": _date_label(payment.cuota.fecha_vencimiento),
        "receiptUrl": payment.comprobante_url.url if payment.comprobante_url else "",
        "verifier": _full_name(payment.verificado_por) if payment.verificado_por else "Pendiente de revision",
        "note": payment.observacion_verificacion or payment.detalles_pago or "Sin observaciones.",
    }


def _payment_qr_config_item(config):
    return {
        "hasQr": bool(config and config.imagen_qr),
        "qrImageUrl": config.imagen_qr.url if config and config.imagen_qr else "",
        "instructions": (
            config.instrucciones
            if config
            else "Escanea el QR de pago y luego adjunta tu comprobante para revision administrativa."
        ),
    }


def _appointment_item(cita):
    return {
        "id": f"CIT-{cita.pk:04d}",
        "rawId": cita.pk,
        "operation": _procedure_name(cita.operacion),
        "specialist": _full_name(cita.medico.usuario),
        "dateTime": _datetime_label(cita.fecha_hora),
        "status": cita.get_estado_display(),
        "statusTone": _appointment_tone(cita),
        "biometric": "Confirmada" if cita.verif_biometria else "Pendiente",
        "details": cita.detalles_cita or "Sin notas adicionales.",
    }


def _client_alerts(cliente, active_operations, pending_quotas, pending_payments, upcoming_appointments):
    alerts = []

    observed_payments = [
        pago
        for pago in pending_payments
        if pago.estado_verificacion == PagoRealizado.EstadoVerificacion.RECHAZADO
    ]
    if observed_payments:
        alerts.append(
            {
                "id": "client-alert-observed-payment",
                "title": "Tienes comprobantes observados",
                "description": "Uno o mas pagos necesitan un nuevo comprobante o revision administrativa.",
                "severity": "high",
                "action": "Revisar pagos",
            }
        )

    overdue_quotas = [cuota for cuota in pending_quotas if cuota.estado == CuotaPlanPago.Estado.VENCIDA]
    if overdue_quotas:
        alerts.append(
            {
                "id": "client-alert-overdue",
                "title": "Tienes cuotas vencidas",
                "description": f"Se detectaron {len(overdue_quotas)} cuota(s) vencida(s) en tu historial actual.",
                "severity": "medium",
                "action": "Ponerte al dia",
            }
        )

    no_capacity = [operacion for operacion in active_operations if not operacion.puede_reservar]
    if no_capacity:
        alerts.append(
            {
                "id": "client-alert-capacity",
                "title": "Algunos tratamientos no tienen cupos para reservar",
                "description": f"{len(no_capacity)} tratamiento(s) ya consumieron o reservaron todas sus sesiones.",
                "severity": "low",
                "action": "Ver reservas",
            }
        )

    if not alerts and upcoming_appointments:
        alerts.append(
            {
                "id": "client-alert-ok",
                "title": "Todo en orden",
                "description": "Tus tratamientos, pagos y proximas citas no muestran bloqueos importantes.",
                "severity": "low",
                "action": "Ver resumen",
            }
        )

    if not alerts and not active_operations:
        alerts.append(
            {
                "id": "client-alert-history-only",
                "title": "Tu portal muestra historial disponible",
                "description": "No tienes tratamientos activos, pero puedes revisar pagos y operaciones pasadas.",
                "severity": "low",
                "action": "Ver historial",
            }
        )

    return alerts


def _base_client_queryset(cliente):
    operations_qs = (
        Operacion.objects.filter(paciente=cliente)
        .select_related(
            "servicio_config__tipo_servicio",
            "servicio_config__proc_estetico",
        )
        .prefetch_related(
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.select_related("medico__usuario").order_by("fecha_hora"),
            ),
            Prefetch(
                "cuotas_plan_pagos",
                queryset=CuotaPlanPago.objects.prefetch_related(
                    Prefetch("pagos_realizados", queryset=PagoRealizado.objects.select_related("verificado_por").order_by("-created_at"))
                ).order_by("nro_cuota"),
            ),
        )
        .order_by("-created_at")
    )

    payments_qs = (
        PagoRealizado.objects.filter(cuota__operacion__paciente=cliente)
        .select_related(
            "cuota__operacion__servicio_config__tipo_servicio",
            "cuota__operacion__servicio_config__proc_estetico",
            "verificado_por",
        )
        .order_by("-created_at")
    )

    appointments_qs = (
        CitaMedica.objects.filter(operacion__paciente=cliente)
        .select_related(
            "operacion__servicio_config__tipo_servicio",
            "operacion__servicio_config__proc_estetico",
            "medico__usuario",
        )
        .order_by("fecha_hora")
    )

    quotas_qs = (
        CuotaPlanPago.objects.filter(operacion__paciente=cliente)
        .select_related(
            "operacion__servicio_config__tipo_servicio",
            "operacion__servicio_config__proc_estetico",
        )
        .prefetch_related(
            Prefetch("pagos_realizados", queryset=PagoRealizado.objects.select_related("verificado_por").order_by("-created_at"))
        )
        .order_by("fecha_vencimiento", "nro_cuota")
    )

    return operations_qs, payments_qs, appointments_qs, quotas_qs


@require_GET
@_client_required
def client_dashboard(request):
    cliente = request.cliente
    operations_qs, payments_qs, appointments_qs, quotas_qs = _base_client_queryset(cliente)

    active_operations = list(operations_qs.filter(estado=Operacion.Estado.EN_PROCESO))
    pending_quotas = list(quotas_qs.exclude(estado=CuotaPlanPago.Estado.PAGADO))
    upcoming_appointments = list(appointments_qs.filter(fecha_hora__gte=timezone.now()))
    latest_analysis = cliente.analisis_esteticos.order_by("-fecha_analisis").first()

    data = {
        "welcome": {
            "name": _full_name(cliente.usuario),
            "status": cliente.get_estado_cliente_display(),
            "phone": cliente.telefono or "Sin telefono",
            "ci": cliente.ci or "Sin CI registrado",
            "lastAnalysis": _date_label(latest_analysis.fecha_analisis) if latest_analysis else "Sin analisis",
            "activeOperations": len(active_operations),
            "totalOperations": operations_qs.count(),
        },
        "metrics": [
            _metric(
                "client-active-operations",
                "Tratamientos activos",
                len(active_operations),
                f"{operations_qs.filter(estado=Operacion.Estado.FINALIZADA).count()} finalizados",
                "primary",
            ),
            _metric(
                "client-pending-quotas",
                "Cuotas activas",
                len(pending_quotas),
                f"{len([cuota for cuota in pending_quotas if cuota.estado == CuotaPlanPago.Estado.VENCIDA])} vencidas",
                "warning",
            ),
            _metric(
                "client-pending-payments",
                "Pagos en revision",
                payments_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE).count(),
                f"{payments_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO).count()} aprobados",
                "success",
            ),
            _metric(
                "client-upcoming-appointments",
                "Proximas citas",
                len(upcoming_appointments),
                f"{appointments_qs.filter(estado=CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA).count()} pendientes de biometria",
                "danger" if appointments_qs.filter(estado=CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA).exists() else "primary",
            ),
        ],
        "alerts": _client_alerts(
            cliente,
            active_operations,
            pending_quotas,
            list(payments_qs[:10]),
            upcoming_appointments,
        ),
        "operations": [_operation_item(operacion) for operacion in active_operations[:4]],
        "pendingQuotas": [_quota_item(cuota) for cuota in pending_quotas[:4]],
        "recentPayments": [_payment_item(payment) for payment in payments_qs[:4]],
        "upcomingAppointments": [_appointment_item(cita) for cita in upcoming_appointments[:4]],
    }
    return _json(data)


@require_GET
@_client_required
def client_treatments(request):
    operations_qs, _, appointments_qs, _ = _base_client_queryset(request.cliente)

    data = {
        "metrics": [
            _metric(
                "client-treatments-total",
                "Tratamientos totales",
                operations_qs.count(),
                "Incluye historial y tratamientos vigentes",
                "primary",
            ),
            _metric(
                "client-treatments-active",
                "En proceso",
                operations_qs.filter(estado=Operacion.Estado.EN_PROCESO).count(),
                "Con reservas o sesiones disponibles",
                "success",
            ),
            _metric(
                "client-treatments-finished",
                "Finalizados",
                operations_qs.filter(estado=Operacion.Estado.FINALIZADA).count(),
                "Historial clinico consolidado",
                "warning",
            ),
            _metric(
                "client-treatments-sessions",
                "Sesiones confirmadas",
                appointments_qs.filter(estado=CitaMedica.Estado.CONFIRMADA, verif_biometria=True).count(),
                "Citas ya cerradas con biometria",
                "danger",
            ),
        ],
        "operations": [_operation_item(operacion) for operacion in operations_qs],
    }
    return _json(data)


@require_GET
@_client_required
def client_payments(request):
    _, payments_qs, _, quotas_qs = _base_client_queryset(request.cliente)

    data = {
        "metrics": [
            _metric(
                "client-payments-pending",
                "Pagos en revision",
                payments_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE).count(),
                "Comprobantes enviados a administracion",
                "warning",
            ),
            _metric(
                "client-payments-approved",
                "Pagos aprobados",
                payments_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO).count(),
                "Ya impactaron tus cuotas",
                "success",
            ),
            _metric(
                "client-payments-observed",
                "Pagos observados",
                payments_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.RECHAZADO).count(),
                "Necesitan correccion o nuevo comprobante",
                "danger",
            ),
            _metric(
                "client-payments-quotas",
                "Cuotas vigentes",
                quotas_qs.exclude(estado=CuotaPlanPago.Estado.PAGADO).count(),
                f"{quotas_qs.filter(estado=CuotaPlanPago.Estado.VENCIDA).count()} vencidas",
                "primary",
            ),
        ],
        "paymentQrConfig": _payment_qr_config_item(ConfiguracionPagoQR.objects.order_by("-updated_at").first()),
        "activeQuotas": [_quota_item(cuota) for cuota in quotas_qs.exclude(estado=CuotaPlanPago.Estado.PAGADO)],
        "payments": [_payment_item(payment) for payment in payments_qs],
    }
    return _json(data)


@require_POST
@_client_required
@transaction.atomic
def client_upload_payment_receipt(request, quota_id):
    cuota = (
        CuotaPlanPago.objects.select_for_update(of=("self",))
        .select_related(
            "operacion__paciente",
            "operacion__servicio_config__tipo_servicio",
        )
        .prefetch_related("pagos_realizados")
        .filter(pk=quota_id, operacion__paciente=request.cliente)
        .first()
    )
    if not cuota:
        return _json({"detail": "No encontramos la cuota solicitada."}, status=404)
    if cuota.estado == CuotaPlanPago.Estado.PAGADO:
        return _json({"detail": "Esta cuota ya fue pagada y no admite nuevos comprobantes."}, status=400)
    if cuota.pagos_realizados.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE).exists():
        return _json({"detail": "Ya tienes un comprobante pendiente de revision para esta cuota."}, status=400)

    receipt_file = request.FILES.get("receiptFile")
    if not receipt_file:
        return _json({"detail": "Debes adjuntar el comprobante del pago."}, status=400)

    amount = (request.POST.get("amount") or "").strip()
    details = (request.POST.get("details") or "").strip()
    try:
        amount_value = Decimal(amount)
    except Exception:
        return _json({"detail": "Debes indicar un monto valido para registrar el pago."}, status=400)

    payment = PagoRealizado.objects.create(
        cuota=cuota,
        monto_pagado=amount_value,
        comprobante_url=receipt_file,
        detalles_pago=details or "Comprobante enviado por el cliente desde el portal.",
    )

    cuota.refresh_from_db(fields=["estado"])

    return _json(
        {
            "detail": "El comprobante fue enviado correctamente y quedo pendiente de revision.",
            "payment": _payment_item(payment),
            "quota": _quota_item(cuota),
        },
        status=201,
    )


@require_GET
@_client_required
def client_reservations(request):
    operations_qs, _, appointments_qs, _ = _base_client_queryset(request.cliente)
    upcoming_appointments = appointments_qs.filter(fecha_hora__gte=timezone.now())
    reservable_operations = operations_qs.filter(estado=Operacion.Estado.EN_PROCESO)

    data = {
        "metrics": [
            _metric(
                "client-reservations-upcoming",
                "Citas futuras",
                upcoming_appointments.count(),
                "Reservas ya registradas para tus tratamientos",
                "primary",
            ),
            _metric(
                "client-reservations-reservable",
                "Tratamientos con cupo",
                sum(1 for operacion in reservable_operations if operacion.puede_reservar),
                "Puedes solicitar una nueva reserva en estos casos",
                "success",
            ),
            _metric(
                "client-reservations-blocked",
                "Tratamientos sin cupo",
                sum(1 for operacion in reservable_operations if not operacion.puede_reservar),
                "No permiten nuevas reservas por ahora",
                "warning",
            ),
            _metric(
                "client-reservations-biometric",
                "Pendientes de biometria",
                appointments_qs.filter(estado=CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA).count(),
                "Citas realizadas que esperan cierre final",
                "danger",
            ),
        ],
        "appointments": [_appointment_item(cita) for cita in appointments_qs],
        "operations": [_operation_item(operacion) for operacion in reservable_operations],
    }
    return _json(data)


@require_GET
@_client_required
def client_reservation_availability(request, operation_id):
    operacion = _get_client_operation(request.cliente, operation_id)
    if not operacion:
        return _json({"detail": "No encontramos la operacion solicitada."}, status=404)
    if operacion.estado != Operacion.Estado.EN_PROCESO:
        return _json({"detail": "Solo puedes reservar citas para tratamientos en proceso."}, status=400)

    data = {
        "operation": _operation_item(operacion),
        "calendar": _build_operation_slot_map(operacion),
    }
    return _json(data)


@require_POST
@_client_required
@transaction.atomic
def client_create_reservation(request, operation_id):
    operacion = _get_client_operation(request.cliente, operation_id)
    if not operacion:
        return _json({"detail": "No encontramos la operacion solicitada."}, status=404)
    if not operacion.puede_reservar:
        return _json({"detail": "Esta operacion ya no tiene sesiones disponibles para nuevas reservas."}, status=400)

    payload = _load_payload(request)
    if payload is None:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    slot_id = payload.get("slotId")
    if not slot_id:
        return _json({"detail": "Debes seleccionar un horario disponible antes de confirmar la reserva."}, status=400)

    slot = (
        DisponibilidadCita.objects.select_for_update()
        .select_related("especialista__usuario")
        .filter(pk=slot_id, activo=True, fecha_hora__gt=timezone.now())
        .first()
    )
    if not slot or not slot.coincide_con_operacion(operacion):
        return _json(
            {"detail": "El horario seleccionado ya no esta disponible para este tratamiento."},
            status=409,
        )

    if slot.citas_origen.filter(estado__in=BLOCKING_RESERVATION_STATES).exists():
        return _json(
            {"detail": "El horario seleccionado acaba de ocuparse. Actualiza el calendario e intenta de nuevo."},
            status=409,
        )

    cita = CitaMedica.objects.create(
        operacion=operacion,
        medico=slot.especialista,
        disponibilidad=slot,
        fecha_hora=slot.fecha_hora,
        estado=CitaMedica.Estado.PROGRAMADA,
        detalles_cita="Reserva web creada por el cliente desde el portal.",
    )

    return _json(
        {
            "detail": "La cita fue reservada correctamente.",
            "appointment": _appointment_item(cita),
            "operation": _operation_item(operacion),
        },
        status=201,
    )
