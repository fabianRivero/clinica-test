import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps

from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST
from django.conf import settings

from billing.models import ConfiguracionPagoQR, CuotaPlanPago, PagoRealizado
from clinical.models import AnalisisEstetico
from notifications.models import Notification
from notifications.services import create_notification, admins_for_specialist_branch
from config.api_helpers import (
    currency,
    date_label,
    datetime_label,
    full_name,
    json_response,
    metric,
    procedure_name,
)
from customers.models import Cliente
from operations.models import CitaClienteLibre, CitaMedica, CitaProspecto, EventoConfirmacionCita, Operacion, TabletKiosko
from operations.scheduling import mark_expired_programmed_appointments_as_no_show


RESERVATION_WINDOW_DAYS = 35
BLOCKING_RESERVATION_STATES = {
    CitaMedica.Estado.PROGRAMADA,
    CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
    CitaMedica.Estado.CONFIRMADA,
}


def _load_payload(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _client_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return json_response({"detail": "Autenticacion requerida."}, status=401)
        if not user.es_cliente:
            return json_response({"detail": "No tienes permisos para acceder a esta vista."}, status=403)
        try:
            request.cliente = user.cliente
        except Cliente.DoesNotExist:
            return json_response({"detail": "No existe un perfil de cliente asociado a esta cuenta."}, status=404)
        return view_func(request, *args, **kwargs)

    return wrapped


def _tablet_kiosk_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        kiosk_id = request.session.get("tablet_kiosk_id")
        if not kiosk_id:
            return json_response({"detail": "Sesion de tablet requerida."}, status=401)
        kiosk = TabletKiosko.objects.filter(pk=kiosk_id, activo=True).select_related("sucursal").first()
        if not kiosk:
            request.session.pop("tablet_kiosk_id", None)
            return json_response({"detail": "La sesion de tablet no es valida."}, status=401)
        request.tablet_kiosk = kiosk
        return view_func(request, *args, **kwargs)

    return wrapped


def _tablet_client_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        client_id = request.session.get("tablet_client_id")
        if not client_id:
            return json_response({"detail": "Debes identificar al cliente en la tablet."}, status=401)
        cliente = Cliente.objects.filter(pk=client_id).select_related("usuario").first()
        if not cliente:
            request.session.pop("tablet_client_id", None)
            return json_response({"detail": "No se encontro el cliente de la sesion actual."}, status=401)
        request.cliente = cliente
        return view_func(request, *args, **kwargs)

    return wrapped


def _month_label(value):
    if not value:
        return "Sin mes"
    return value.strftime("%B %Y").capitalize()


def _operation_branch(operacion):
    citas = list(operacion.citas_medicas.all())
    if citas:
        now = timezone.now()
        upcoming = [cita for cita in citas if cita.fecha_hora >= now]
        cita = upcoming[0] if upcoming else citas[-1]
        return f"Sede: {cita.sucursal.nombre}"

    # Sin citas reservadas todavia (caso normal en operaciones recien
    # creadas por el wizard de conversion): caemos a la sede de origen del
    # cliente, que el wizard ya persiste al crear el Cliente. Solo si el
    # cliente tampoco tiene sede asignada mostramos "Por asignar".
    cliente = getattr(operacion, "paciente", None)
    sucursal_origen = getattr(cliente, "sucursal_origen", None) if cliente else None
    if sucursal_origen is not None:
        return f"Sede: {sucursal_origen.nombre}"
    return "Por asignar"


def _next_appointment(operacion):
    citas = list(operacion.citas_medicas.all())
    if not citas:
        return None

    now = timezone.now()
    upcoming = [cita for cita in citas if cita.fecha_hora >= now]
    return upcoming[0] if upcoming else None


def _quota_amount(cuota):
    if cuota.monto_programado:
        return cuota.monto_programado
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
    if cuota.estado == CuotaPlanPago.Estado.NO_PAGADA:
        return "observed"
    if cuota.estado == CuotaPlanPago.Estado.VENCIDA:
        return "danger"
    return "pending"


def _appointment_tone(cita):
    if cita.estado == CitaMedica.Estado.CONFIRMADA:
        return "approved"
    if cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
        return "warning"
    if cita.estado == CitaMedica.Estado.CANCELADA:
        return "danger"
    if cita.estado == CitaMedica.Estado.NO_ASISTIO:
        return "observed"
    return "pending"


def _reserve_message(operacion):
    if operacion.puede_reservar:
        return f"Tienes {operacion.sesiones_disponibles} sesion(es) disponible(s) para reservar."
    return operacion.motivo_bloqueo_reserva or "Tu tratamiento ya no tiene sesiones disponibles para nuevas reservas."


def _operation_item(operacion):
    next_appointment = _next_appointment(operacion)
    zone = ", ".join(
        [value for value in [operacion.zona_general, operacion.zona_especifica] if value]
    ) or "Sin zona registrada"
    sessions_confirmed = operacion.sesiones_confirmadas
    sessions_total = operacion.sesiones_totales
    # Label for operation select: "#ID - Procedure | Zone | sessions (X/Y) | Status"
    select_label = (
        f"#{operacion.pk} - {procedure_name(operacion)} | {zone} | "
        f"{sessions_confirmed}/{sessions_total} ses. | {operacion.get_estado_display()}"
    )
    return {
        "id": f"OP-{operacion.pk:04d}",
        "rawId": operacion.pk,
        "patientId": operacion.paciente_id,
        "procedure": procedure_name(operacion),
        "serviceType": operacion.servicio_config.tipo_servicio.tipo,
        "branch": _operation_branch(operacion),
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
        "price": currency(operacion.precio_total),
        "zone": zone,
        "startedAt": date_label(operacion.fecha_inicio),
        # Version ISO (`YYYY-MM-DD`) de la fecha de inicio para que el front
        # pueda filtrar la lista por mes/anio sin parsear el label
        # localizado. `None` cuando la operacion aun no tiene fecha.
        "startedAtIso": operacion.fecha_inicio.isoformat() if operacion.fecha_inicio else None,
        "endedAt": date_label(operacion.fecha_final) if operacion.fecha_final else "En curso",
        "nextAppointment": datetime_label(next_appointment.fecha_hora) if next_appointment else "Sin cita futura",
        "recommendations": operacion.recomendaciones or "Sin recomendaciones registradas.",
        "details": operacion.detalles_op or "Sin detalle operativo.",
        "sessions": {
            "total": sessions_total,
            "confirmed": sessions_confirmed,
            "pendingBiometric": operacion.sesiones_pendientes_confirmacion,
            "reserved": operacion.reservas_activas,
            "available": operacion.sesiones_disponibles,
        },
        # Cupos que quedan para una nueva reserva. Tambien viene
        # anidado en ``sessions.available``; lo exponemos al nivel raiz
        # para que el frontend pueda bloquear el formulario "Reservar
        # nueva cita" sin parsear el string localizado.
        "availableAppointments": operacion.sesiones_disponibles,
        "canReserve": operacion.puede_reservar,
        "firstPaymentVerified": operacion.primer_pago_verificado,
        "reserveMessage": _reserve_message(operacion),
        "quotaSummary": (
            f"{operacion.cuotas_plan_pagos.filter(estado=CuotaPlanPago.Estado.PAGADO).count()}"
            f"/{operacion.cuotas_plan_pagos.count()} cuota(s) pagadas"
        ),
        "selectLabel": select_label,
    }


def _reservation_window_for_operation(operacion):
    today = timezone.localdate()
    window_start = max(today, operacion.fecha_inicio or today)
    window_end = window_start + timedelta(days=RESERVATION_WINDOW_DAYS - 1)
    if operacion.fecha_final:
        window_end = min(window_end, operacion.fecha_final)
    return window_start, window_end


def _build_operation_slot_map(operacion, editing_appointment=None):
    return {
        "windowStart": None,
        "windowEnd": None,
        "monthLabel": "",
        "availableDates": [],
        "slotsByDate": {},
        "slotCount": 0,
    }
def _get_client_operation(cliente, operation_id):
    mark_expired_programmed_appointments_as_no_show()
    return (
        Operacion.objects.filter(paciente=cliente, pk=operation_id)
        .select_related("servicio_config__tipo_servicio", "servicio_config__proc_estetico")
        .prefetch_related(
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.select_related().order_by("fecha_hora"),
            ),
            Prefetch(
                "cuotas_plan_pagos",
                queryset=CuotaPlanPago.objects.order_by("nro_cuota"),
            ),
        )
        .first()
    )


def _get_client_appointment(cliente, appointment_id):
    mark_expired_programmed_appointments_as_no_show()
    return (
        CitaMedica.objects.filter(operacion__paciente=cliente, pk=appointment_id)
        .select_related(
            "operacion__servicio_config__tipo_servicio",
            "operacion__servicio_config__proc_estetico",
            
            "disponibilidad",
        )
        .prefetch_related("disponibilidad__citas_origen")
        .first()
    )


def _quota_item(cuota):
    latest_payment = cuota.pagos_realizados.order_by("-created_at").first()
    amount_value = (
        latest_payment.monto_pagado
        if latest_payment and latest_payment.estado_verificacion in {
            PagoRealizado.EstadoVerificacion.PENDIENTE,
            PagoRealizado.EstadoVerificacion.RECHAZADO,
        }
        else _quota_amount(cuota)
    )
    if cuota.estado == CuotaPlanPago.Estado.PAGADO:
        status = cuota.get_estado_display()
        status_tone = "approved"
    elif latest_payment and latest_payment.estado_verificacion == PagoRealizado.EstadoVerificacion.PENDIENTE:
        status = "Pendiente de revisión"
        status_tone = "pending"
    elif latest_payment and latest_payment.estado_verificacion == PagoRealizado.EstadoVerificacion.RECHAZADO:
        status = "Comprobante observado"
        status_tone = "observed"
    else:
        status = cuota.get_estado_display()
        status_tone = _quota_tone(cuota)

    latest_payment_status = (
        "Pendiente de revisión"
        if latest_payment and latest_payment.estado_verificacion == PagoRealizado.EstadoVerificacion.PENDIENTE
        else "Comprobante observado"
        if latest_payment and latest_payment.estado_verificacion == PagoRealizado.EstadoVerificacion.RECHAZADO
        else latest_payment.get_estado_verificacion_display()
        if latest_payment
        else "Sin comprobante"
    )
    can_replace_receipt = bool(
        latest_payment
        and latest_payment.estado_verificacion
        in {
            PagoRealizado.EstadoVerificacion.PENDIENTE,
            PagoRealizado.EstadoVerificacion.RECHAZADO,
        }
    )

    return {
        "id": f"CUO-{cuota.pk:04d}",
        "rawId": cuota.pk,
        "operation": procedure_name(cuota.operacion),
        "quotaLabel": f"Cuota {cuota.nro_cuota}",
        "amount": currency(amount_value),
        "amountValue": f"{amount_value:.2f}",
        "dueDate": date_label(cuota.fecha_vencimiento),
        "status": status,
        "statusTone": status_tone,
        "latestPaymentStatus": latest_payment_status,
        "latestPaymentTone": _payment_tone(latest_payment) if latest_payment else "neutral",
        "canUploadReceipt": cuota.estado != CuotaPlanPago.Estado.PAGADO,
        "canReplaceReceipt": can_replace_receipt,
        "uploadActionLabel": (
            "Cambiar comprobante subido"
            if can_replace_receipt
            else "Pagar por QR y subir comprobante"
        ),
    }


def _payment_item(payment):
    return {
        "id": f"PAY-{payment.pk:04d}",
        "rawId": payment.pk,
        "operation": procedure_name(payment.cuota.operacion),
        "quotaLabel": f"Cuota {payment.cuota.nro_cuota}",
        "amount": currency(payment.monto_pagado),
        "submittedAt": datetime_label(payment.created_at),
        "status": payment.get_estado_verificacion_display(),
        "statusTone": _payment_tone(payment),
        "dueDate": date_label(payment.cuota.fecha_vencimiento),
        "receiptUrl": payment.comprobante_url.url if payment.comprobante_url else "",
        "verifier": full_name(payment.verificado_por) if payment.verificado_por else "Pendiente de revisión",
        "note": payment.observacion_verificacion or payment.detalles_pago or "Sin observaciones.",
    }


def _payment_qr_config_item(config):
    return {
        "hasQr": bool(config and config.imagen_qr),
        "qrImageUrl": config.imagen_qr.url if config and config.imagen_qr else "",
        "instructions": (
            config.instrucciones
            if config
            else "Escanea el QR de pago y luego adjunta tu comprobante para revisión administrativa."
        ),
    }


def _appointment_item(cita, appointment_index=None, total_appointments=None):
    can_manage = cita.estado == CitaMedica.Estado.PROGRAMADA

    verification_status_map = {
        CitaMedica.EstadoVerificacion.PENDIENTE: "pendiente",
        CitaMedica.EstadoVerificacion.VERIFICADA: "verificada",
        CitaMedica.EstadoVerificacion.NO_REQUERIDA: "no_requerida",
    }
    verification_status = verification_status_map.get(
        cita.estado_verificacion,
        "no_requerida",
    )

    verification_method = None
    if cita.metodo_confirmacion == CitaMedica.MetodoConfirmacion.BIOMETRICO:
        verification_method = "biometria"
    elif cita.metodo_confirmacion == CitaMedica.MetodoConfirmacion.TABLET:
        verification_method = "qr"
    elif cita.metodo_confirmacion == CitaMedica.MetodoConfirmacion.MANUAL:
        verification_method = "manual"
    zona = ", ".join(
        [value for value in [cita.operacion.zona_general, cita.operacion.zona_especifica] if value]
    ) or "Sin zona registrada"
    return {
        "id": f"CIT-{cita.pk:04d}",
        "rawId": cita.pk,
        "operationRawId": cita.operacion_id,
        "operation": procedure_name(cita.operacion),
        "specialist": "Sin asignar",
        "dateTime": datetime_label(cita.fecha_hora),
        "status": cita.get_estado_display(),
        "statusTone": _appointment_tone(cita),
        "verificationStatus": verification_status,
        "verificationMethod": verification_method,
        "details": cita.detalles_cita or "Sin notas adicionales.",
        "canManage": can_manage,
        "canMarkPendingBiometric": cita.estado == CitaMedica.Estado.PROGRAMADA,
        "canConfirmBiometric": (not settings.BIOMETRIC_SUSPENDED) and cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        "canCancelFromVerification": cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        "biometricMockTemplate": "" if settings.BIOMETRIC_SUSPENDED else getattr(cita.operacion.paciente, "huella_biometrica", None).template_biometrico
        if hasattr(cita.operacion.paciente, "huella_biometrica")
        and cita.operacion.paciente.huella_biometrica.activo
        and cita.operacion.paciente.huella_biometrica.proveedor == "MOCK"
        else "",
        "zona": zona,
        "appointmentIndex": appointment_index,
        "totalAppointments": total_appointments,
        # Planning fields (used by the RescheduleModal prefill).
        "duracionEstimadaMinutos": cita.duracion_estimada_minutos,
        "descripcionGeneral": cita.descripcion_general or "",
        "notasPrevias": cita.notas_previas or "",
        "procedimientoPlanificado": cita.procedimiento_planificado or "",
        "zonaCuerpoPlanificada": cita.zona_cuerpo_planificada or "",
        "especialistasPlanificados": list(
            cita.especialistas_items.filter(planificada=True)
            .select_related("especialista__usuario__especialista")
            .values(
                "especialista_id",
                "especialista__usuario__primer_nombre",
                "especialista__usuario__apellido_paterno",
                "especialista__usuario__username",
            )
        ),
        "maquinariaPlanificada": list(
            cita.maquinaria_items.filter(planificada=True)
            .select_related("maquinaria")
            .values(
                "maquinaria_id",
                "cantidad",
                "maquinaria__nombre",
                "maquinaria__marca",
            )
        ),
        # Real-time close data (populated via POST /cerrar/ once the client
        # confirms and the admin sets the close fields). The "Ver datos"
        # button in cms/clientes/<id> uses hasRealTimeData to decide
        # whether to render; when true the rest of the fields populate
        # the comparison modal alongside the planning block.
        "hasRealTimeData": bool(
            cita.hora_real_inicio
            or cita.hora_real_fin
            or cita.procedimiento_realizado
            or cita.zona_cuerpo_realizada
        ),
        "horaRealInicio": (
            timezone.localtime(cita.hora_real_inicio).strftime("%d/%m %H:%M")
            if cita.hora_real_inicio
            else None
        ),
        "horaRealFin": (
            timezone.localtime(cita.hora_real_fin).strftime("%d/%m %H:%M")
            if cita.hora_real_fin
            else None
        ),
        "procedimientoRealizado": cita.procedimiento_realizado or "",
        "zonaCuerpoRealizada": cita.zona_cuerpo_realizada or "",
        "notasPost": cita.notas_post or "",
        "especialistasAtendieron": list(
            cita.especialistas_items.filter(planificada=False)
            .select_related("especialista__usuario__especialista")
            .values(
                "especialista_id",
                "especialista__usuario__primer_nombre",
                "especialista__usuario__apellido_paterno",
                "especialista__usuario__username",
            )
        ),
        "maquinariaUtilizada": list(
            cita.maquinaria_items.filter(planificada=False)
            .select_related("maquinaria")
            .values(
                "maquinaria_id",
                "cantidad",
                "maquinaria__nombre",
                "maquinaria__marca",
            )
        ),
        # Photo URLs (absolute path). Empty string when no photo.
        "fotoAntesUrl": cita.foto_antes.url if cita.foto_antes else "",
        "fotoDespuesUrl": cita.foto_despues.url if cita.foto_despues else "",
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
                "description": "Uno o mas pagos necesitan un nuevo comprobante o revisión administrativa.",
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
                "description": "Tus tratamientos, pagos y próximas citas no muestran bloqueos importantes.",
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
    mark_expired_programmed_appointments_as_no_show()
    operations_qs = (
        Operacion.objects.filter(paciente=cliente)
        .select_related(
            "servicio_config__tipo_servicio",
            "servicio_config__proc_estetico",
        )
        .prefetch_related(
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.select_related().order_by("fecha_hora"),
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
    pending_quotas = list(
        quotas_qs.exclude(
            estado__in=[CuotaPlanPago.Estado.PAGADO, CuotaPlanPago.Estado.NO_PAGADA]
        )
    )
    upcoming_appointments = list(appointments_qs.filter(fecha_hora__gte=timezone.now()))
    latest_analysis = cliente.analisis_esteticos.order_by("-fecha_analisis").first()

    data = {
        "welcome": {
            "name": full_name(cliente.usuario),
            "status": cliente.get_estado_cliente_display(),
            "phone": cliente.telefono or "Sin teléfono",
            "ci": cliente.ci or "Sin CI registrado",
            "lastAnalysis": date_label(latest_analysis.fecha_analisis) if latest_analysis else "Sin analisis",
            "activeOperations": len(active_operations),
            "totalOperations": operations_qs.count(),
        },
        "metrics": [
            metric(
                "client-active-operations",
                "Tratamientos activos",
                len(active_operations),
                f"{operations_qs.filter(estado=Operacion.Estado.FINALIZADA).count()} finalizados",
                "primary",
            ),
            metric(
                "client-pending-quotas",
                "Cuotas activas",
                len(pending_quotas),
                f"{len([cuota for cuota in pending_quotas if cuota.estado == CuotaPlanPago.Estado.VENCIDA])} vencidas",
                "warning",
            ),
            metric(
                "client-pending-payments",
                "Pagos en revisión",
                payments_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE).count(),
                f"{payments_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO).count()} aprobados",
                "success",
            ),
            metric(
                "client-upcoming-appointments",
                "Próximas citas",
                len(upcoming_appointments),
                f"{appointments_qs.filter(estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION).count()} pendientes de biometria",
                "danger" if appointments_qs.filter(estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION).exists() else "primary",
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
    return json_response(data)


@require_GET
@_client_required
def client_treatments(request):
    operations_qs, _, appointments_qs, _ = _base_client_queryset(request.cliente)

    data = {
        "metrics": [
            metric(
                "client-treatments-total",
                "Tratamientos totales",
                operations_qs.count(),
                "Incluye historial y tratamientos vigentes",
                "primary",
            ),
            metric(
                "client-treatments-active",
                "En proceso",
                operations_qs.filter(estado=Operacion.Estado.EN_PROCESO).count(),
                "Con reservas o sesiones disponibles",
                "success",
            ),
            metric(
                "client-treatments-finished",
                "Finalizados",
                operations_qs.filter(estado=Operacion.Estado.FINALIZADA).count(),
                "Historial clinico consolidado",
                "warning",
            ),
            metric(
                "client-treatments-sessions",
                "Sesiones confirmadas",
                appointments_qs.filter(estado=CitaMedica.Estado.CONFIRMADA, verif_biometria=True).count(),
                "Citas ya cerradas con biometria",
                "danger",
            ),
        ],
        "operations": [_operation_item(operacion) for operacion in operations_qs],
    }
    return json_response(data)


@require_GET
@_client_required
def client_payments(request):
    _, payments_qs, _, quotas_qs = _base_client_queryset(request.cliente)

    client_branch = getattr(request.cliente.usuario, "sucursal", None)
    if not client_branch:
        return json_response({"detail": "No branch assigned to user"}, status=404)

    qr_config = ConfiguracionPagoQR.objects.filter(sucursal=client_branch).first()

    data = {
        "metrics": [
            metric(
                "client-payments-pending",
                "Pagos en revisión",
                payments_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE).count(),
                "Comprobantes enviados a administracion",
                "warning",
            ),
            metric(
                "client-payments-approved",
                "Pagos aprobados",
                payments_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO).count(),
                "Ya impactaron tus cuotas",
                "success",
            ),
            metric(
                "client-payments-observed",
                "Pagos observados",
                payments_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.RECHAZADO).count(),
                "Necesitan correccion o nuevo comprobante",
                "danger",
            ),
            metric(
                "client-payments-quotas",
                "Cuotas vigentes",
                quotas_qs.exclude(estado__in=[CuotaPlanPago.Estado.PAGADO, CuotaPlanPago.Estado.NO_PAGADA]).count(),
                f"{quotas_qs.filter(estado=CuotaPlanPago.Estado.VENCIDA).count()} vencidas",
                "primary",
            ),
        ],
        "paymentQrConfig": _payment_qr_config_item(qr_config),
        "activeQuotas": [
            _quota_item(cuota)
            for cuota in quotas_qs.exclude(
                estado__in=[CuotaPlanPago.Estado.PAGADO, CuotaPlanPago.Estado.NO_PAGADA]
            )
        ],
        "payments": [_payment_item(payment) for payment in payments_qs],
    }
    return json_response(data)


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
        return json_response({"detail": "No encontramos la cuota solicitada."}, status=404)
    if cuota.estado == CuotaPlanPago.Estado.PAGADO:
        return json_response({"detail": "Esta cuota ya fue pagada y no admite nuevos comprobantes."}, status=400)

    receipt_file = request.FILES.get("receiptFile")
    if not receipt_file:
        return json_response({"detail": "Debes adjuntar el comprobante del pago."}, status=400)

    amount = (request.POST.get("amount") or "").strip()
    details = (request.POST.get("details") or "").strip()
    try:
        amount_value = Decimal(amount)
    except Exception:
        return json_response({"detail": "Debes indicar un monto valido para registrar el pago."}, status=400)

    editable_payment = cuota.pagos_realizados.filter(
        estado_verificacion__in=[
            PagoRealizado.EstadoVerificacion.PENDIENTE,
            PagoRealizado.EstadoVerificacion.RECHAZADO,
        ]
    ).order_by("-created_at").first()

    if editable_payment:
        editable_payment.monto_pagado = amount_value
        editable_payment.comprobante_url = receipt_file
        editable_payment.detalles_pago = details or "Comprobante actualizado por el cliente desde el portal."
        editable_payment.estado_verificacion = PagoRealizado.EstadoVerificacion.PENDIENTE
        editable_payment.verificado = False
        editable_payment.verificado_por = None
        editable_payment.fecha_verificacion = None
        editable_payment.observacion_verificacion = ""
        editable_payment.save()
        payment = editable_payment
        detail = "El comprobante fue actualizado correctamente y quedo pendiente de revisión."
    else:
        payment = PagoRealizado.objects.create(
            cuota=cuota,
            monto_pagado=amount_value,
            comprobante_url=receipt_file,
            detalles_pago=details or "Comprobante enviado por el cliente desde el portal.",
        )
        paciente_user = payment.cuota.operacion.paciente.usuario
        paciente_cliente = payment.cuota.operacion.paciente
        identificador_cliente = paciente_cliente.ci or paciente_user.username
        procedimiento = payment.cuota.operacion.servicio_config.proc_estetico.proceso
        sucursal = payment.cuota.operacion.paciente.usuario.sucursal
        operacion_id = payment.cuota.operacion.pk
        nro_cuota = payment.cuota.nro_cuota
        monto_cuota = payment.monto_pagado
        for admin in admins_for_specialist_branch(sucursal):
            create_notification(
                recipient=admin,
                branch=sucursal,
                type=Notification.Type.ADMIN_PAYMENT_PENDING_CONFIRMATION,
                title="Nuevo pago pendiente de revisión",
                message=(
                    f"El cliente {paciente_user.primer_nombre} {paciente_user.apellido_paterno} "
                    f"({identificador_cliente}), envio el comprobante del pago de la cuota Nro {nro_cuota} "
                    f"del procedimiento {procedimiento} con ID {operacion_id}. "
                    f"El monto de la cuota de pago es: Bs {monto_cuota}."
                ),
                action_url="/cms/pagos",
                source_event="payment.pending_submission",
                source_entity_type="payment",
                source_entity_id=payment.id,
                created_by_type="client",
                created_by_id=request.user.id,
            )
        detail = "El comprobante fue enviado correctamente y quedo pendiente de revisión."

    cuota.refresh_from_db(fields=["estado"])

    return json_response(
        {
            "detail": detail,
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
            metric(
                "client-reservations-upcoming",
                "Citas futuras",
                upcoming_appointments.count(),
                "Reservas ya registradas para tus tratamientos",
                "primary",
            ),
            metric(
                "client-reservations-reservable",
                "Tratamientos con cupo",
                sum(1 for operacion in reservable_operations if operacion.puede_reservar),
                "Puedes solicitar una nueva reserva en estos casos",
                "success",
            ),
            metric(
                "client-reservations-blocked",
                "Tratamientos sin cupo",
                sum(1 for operacion in reservable_operations if not operacion.puede_reservar),
                "No permiten nuevas reservas por ahora",
                "warning",
            ),
            metric(
                "client-reservations-biometric",
                "Pendientes de biometria",
                appointments_qs.filter(estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION).count(),
                "Citas realizadas que esperan cierre final",
                "danger",
            ),
        ],
        "appointments": [_appointment_item(cita) for cita in appointments_qs],
        "operations": [_operation_item(operacion) for operacion in reservable_operations],
    }
    return json_response(data)


@require_GET
@_tablet_kiosk_required
@_tablet_client_required
def client_tablet_current_appointment(request):
    mark_expired_programmed_appointments_as_no_show()
    now = timezone.now()
    today = timezone.localdate()
    mode = (request.GET.get("mode") or "ONLINE").upper()
    is_offline = mode == "OFFLINE"

    appointments_qs = (
        CitaMedica.objects.filter(
            operacion__paciente=request.cliente,
            sucursal=request.tablet_kiosk.sucursal,
        )
        .select_related("operacion__servicio_config__tipo_servicio", "operacion__servicio_config__proc_estetico")
        .order_by("fecha_hora")
    )

    # Online: solo pendientes de verificacion. Offline: programadas + pendientes de verificacion.
    if is_offline:
        today_appointments = appointments_qs.filter(
            estado__in=[
                CitaMedica.Estado.PROGRAMADA,
                CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
            ],
            fecha_hora__date=today,
        )
    else:
        today_appointments = appointments_qs.filter(
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
            fecha_hora__date=today,
        )

    current = today_appointments.first()

    if is_offline:
        pending_count = appointments_qs.filter(
            estado__in=[CitaMedica.Estado.PROGRAMADA, CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION],
            fecha_hora__gte=now,
        ).count()
    else:
        pending_count = appointments_qs.filter(
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
            fecha_hora__gte=now,
        ).count()
    procedure_options = []
    operation_map = {}
    # Precompute total appointments and index per operation (exclude cancelled/no-show)
    operation_indices = {}
    valid_states = [
        CitaMedica.Estado.PROGRAMADA,
        CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        CitaMedica.Estado.CONFIRMADA,
    ]
    for cita in today_appointments:
        op = cita.operacion
        if not op or op.estado != Operacion.Estado.EN_PROCESO:
            continue
        if op.id not in operation_indices:
            valid_citas = op.citas_medicas.filter(
                estado__in=valid_states
            ).order_by("fecha_hora")
            total = valid_citas.count()
            indices = {c.pk: i + 1 for i, c in enumerate(valid_citas)}
            operation_indices[op.id] = (total, indices)

    for cita in today_appointments:
        operation = cita.operacion
        if not operation or operation.estado != Operacion.Estado.EN_PROCESO:
            continue
        if operation.id not in operation_map:
            operation_map[operation.id] = {
                "operation": _operation_item(operation),
                "appointments": [],
            }
        total, indices = operation_indices[operation.id]
        appointment_index = indices.get(cita.pk, 1)
        operation_map[operation.id]["appointments"].append(
            _appointment_item(cita, appointment_index, total)
        )
    procedure_options = list(operation_map.values())

    return json_response(
        {
            "currentAppointment": _appointment_item(current) if current else None,
            "pendingAppointmentsCount": pending_count,
            "procedureOptions": procedure_options,
        }
    )


@require_POST
def tablet_kiosk_login(request):
    payload = _load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)
    codigo = (payload.get("codigo") or "").strip()
    clave = (payload.get("clave") or "").strip()
    if not codigo or not clave:
        return json_response({"detail": "Debes enviar codigo y clave del kiosko."}, status=400)

    kiosko = TabletKiosko.objects.filter(codigo=codigo, activo=True).select_related("sucursal").first()
    if not kiosko or not kiosko.check_clave(clave):
        return json_response({"detail": "Credenciales de kiosko invalidas."}, status=401)

    request.session["tablet_kiosk_id"] = kiosko.id
    request.session.pop("tablet_client_id", None)
    kiosko.ultimo_acceso = timezone.now()
    kiosko.save(update_fields=["ultimo_acceso", "updated_at"])
    return json_response(
        {
            "detail": "Kiosko autenticado correctamente.",
            "kiosk": {"id": kiosko.id, "codigo": kiosko.codigo, "nombre": kiosko.nombre, "branchId": kiosko.sucursal_id},
        }
    )


@require_POST
@_tablet_kiosk_required
def tablet_client_login(request):
    payload = _load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()
    if not username or not password:
        return json_response({"detail": "Debes ingresar usuario y contraseña del cliente."}, status=400)
    user = authenticate(request, username=username, password=password)
    if not user or not user.es_cliente:
        return json_response({"detail": "Credenciales de cliente invalidas."}, status=401)
    cliente = Cliente.objects.filter(usuario=user).select_related("usuario").first()
    if not cliente:
        return json_response({"detail": "No existe un perfil de cliente para esta cuenta."}, status=404)
    # Validate the client belongs to this tablet's branch (data isolation)
    kiosk_sucursal = request.tablet_kiosk.sucursal
    cliente_sucursal = getattr(cliente.usuario, "sucursal", None)
    cliente_sucursal_id = cliente_sucursal.id if cliente_sucursal else None
    if cliente_sucursal_id is None or cliente_sucursal_id != kiosk_sucursal.id:
        return json_response({"detail": "Nombre de usuario y/o contraseña incorrecta."}, status=403)
    request.session["tablet_client_id"] = cliente.id
    return json_response({"detail": "Cliente autenticado en tablet.", "clientId": cliente.id, "fullName": user.nombre_completo or user.username})


@require_POST
@_tablet_kiosk_required
def tablet_client_reset(request):
    request.session.pop("tablet_client_id", None)
    return json_response({"detail": "Sesion del cliente reiniciada en la tablet."})


@require_POST
@_tablet_kiosk_required
@_tablet_client_required
@transaction.atomic
def client_tablet_confirm_current_appointment(request):
    mark_expired_programmed_appointments_as_no_show()
    today = timezone.localdate()
    cita = (
        CitaMedica.objects.select_for_update(of=("self",))
        .select_related("operacion__paciente", "sucursal")
        .filter(
            operacion__paciente=request.cliente,
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
            fecha_hora__date=today,
        )
        .order_by("fecha_hora")
        .first()
    )
    if not cita:
        return json_response(
            {"detail": "No tienes una cita pendiente de confirmación para confirmar hoy."},
            status=404,
        )

    cita.estado = CitaMedica.Estado.CONFIRMADA
    cita.metodo_confirmacion = CitaMedica.MetodoConfirmacion.TABLET
    cita.verif_biometria = False
    cita.save(update_fields=["estado", "metodo_confirmacion", "verif_biometria", "updated_at"])

    EventoConfirmacionCita.objects.create(
        cita=cita,
        paciente=request.cliente,
        sucursal=cita.sucursal,
        metodo=EventoConfirmacionCita.Metodo.TABLET,
        confirmado_en=timezone.now(),
        ip_origen=_client_ip(request),
    )

    return json_response(
        {
            "detail": "Cita realizada",
            "appointment": _appointment_item(cita),
        }
    )


@require_POST
@_tablet_kiosk_required
@_tablet_client_required
@transaction.atomic
def client_tablet_confirm_appointment_for_operation(request):
    mark_expired_programmed_appointments_as_no_show()
    payload = _load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    operation_id = payload.get("operationId")
    if not operation_id:
        return json_response({"detail": "Debes seleccionar un procedimiento para confirmar la cita."}, status=400)

    today = timezone.localdate()
    cita = (
        CitaMedica.objects.select_for_update(of=("self",))
        .select_related("operacion__paciente", "sucursal")
        .filter(
            operacion__paciente=request.cliente,
            operacion_id=operation_id,
            sucursal=request.tablet_kiosk.sucursal,
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
            fecha_hora__date=today,
        )
        .order_by("fecha_hora")
        .first()
    )
    if not cita:
        return json_response(
            {"detail": "No tienes una cita pendiente de confirmación para confirmar hoy."},
            status=404,
        )

    cita.estado = CitaMedica.Estado.CONFIRMADA
    cita.metodo_confirmacion = CitaMedica.MetodoConfirmacion.TABLET
    cita.verif_biometria = False
    cita.save(update_fields=["estado", "metodo_confirmacion", "verif_biometria", "updated_at"])

    EventoConfirmacionCita.objects.create(
        cita=cita,
        paciente=request.cliente,
        sucursal=cita.sucursal,
        metodo=EventoConfirmacionCita.Metodo.TABLET,
        confirmado_en=timezone.now(),
        ip_origen=_client_ip(request),
    )

    return json_response(
        {
            "detail": "Cita realizada",
            "appointment": _appointment_item(cita),
        }
    )




@require_POST
@_tablet_kiosk_required
@_tablet_client_required
@transaction.atomic
def client_tablet_sync_offline_events(request):
    payload = _load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    events = payload.get("events")
    if not isinstance(events, list):
        return json_response({"detail": "Debes enviar una lista de eventos."}, status=400)

    device_id = str(payload.get("deviceId") or "").strip()
    results = []
    processed_ids = set()
    today = timezone.localdate()

    for item in events:
        item = item or {}
        event_id = str(item.get("eventId") or "").strip()
        operation_id = item.get("operationId")
        recorded_raw = item.get("createdAt")
        recorded_at = parse_datetime(recorded_raw) if recorded_raw else None

        if not event_id or not operation_id:
            results.append({"eventId": event_id or None, "status": "rejected", "reason": "invalid_payload"})
            continue
        if event_id in processed_ids:
            results.append({"eventId": event_id, "status": "duplicate", "reason": "duplicated_in_batch"})
            continue
        processed_ids.add(event_id)

        existing_event = EventoConfirmacionCita.objects.filter(event_id=event_id).first()
        if existing_event:
            results.append({"eventId": event_id, "status": "duplicate", "reason": "already_processed", "appointmentId": existing_event.cita_id})
            continue

        cita = (
            CitaMedica.objects.select_for_update(of=("self",))
            .select_related("operacion__paciente", "sucursal")
            .filter(
                operacion__paciente=request.cliente,
                operacion_id=operation_id,
                sucursal=request.tablet_kiosk.sucursal,
                estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
                fecha_hora__date=today,
            )
            .order_by("fecha_hora")
            .first()
        )

        if not cita:
            fallback_cita = (
                CitaMedica.objects.select_related("operacion__paciente", "sucursal")
                .filter(operacion__paciente=request.cliente, operacion_id=operation_id, sucursal=request.tablet_kiosk.sucursal, fecha_hora__date=today)
                .order_by("fecha_hora")
                .first()
            )
            if fallback_cita:
                EventoConfirmacionCita.objects.create(
                    cita=fallback_cita,
                    paciente=request.cliente,
                    sucursal=fallback_cita.sucursal,
                    metodo=EventoConfirmacionCita.Metodo.TABLET,
                    confirmado_en=timezone.now(),
                    ip_origen=_client_ip(request),
                    event_id=event_id,
                    origin_mode=EventoConfirmacionCita.ModoOrigen.OFFLINE,
                    device_id=device_id,
                    recorded_at_device=recorded_at,
                    confirmed_at_server=timezone.now(),
                    sync_status=EventoConfirmacionCita.EstadoSync.CONFLICT,
                    conflict_reason="appointment_not_pending",
                )
            results.append({"eventId": event_id, "status": "conflict", "reason": "appointment_not_pending"})
            continue

        cita.estado = CitaMedica.Estado.CONFIRMADA
        cita.metodo_confirmacion = CitaMedica.MetodoConfirmacion.TABLET
        cita.verif_biometria = False
        cita.save(update_fields=["estado", "metodo_confirmacion", "verif_biometria", "updated_at"])

        event = EventoConfirmacionCita.objects.create(
            cita=cita,
            paciente=request.cliente,
            sucursal=cita.sucursal,
            metodo=EventoConfirmacionCita.Metodo.TABLET,
            confirmado_en=timezone.now(),
            ip_origen=_client_ip(request),
            event_id=event_id,
            origin_mode=EventoConfirmacionCita.ModoOrigen.OFFLINE,
            device_id=device_id,
            recorded_at_device=recorded_at,
            confirmed_at_server=timezone.now(),
            sync_status=EventoConfirmacionCita.EstadoSync.ACCEPTED,
            conflict_reason="",
        )
        results.append({"eventId": event_id, "status": "accepted", "appointmentId": event.cita_id})

    return json_response({"detail": "Sincronizacion procesada.", "results": results})


@require_GET
@_client_required
def client_reservation_availability(request, operation_id):
    operacion = _get_client_operation(request.cliente, operation_id)
    if not operacion:
        return json_response({"detail": "No encontramos la operacion solicitada."}, status=404)
    if operacion.estado != Operacion.Estado.EN_PROCESO:
        return json_response({"detail": "Solo puedes reservar citas para tratamientos en proceso."}, status=400)

    data = {
        "operation": _operation_item(operacion),
        "calendar": _build_operation_slot_map(operacion),
    }
    return json_response(data)


@require_GET
@_client_required
def client_edit_reservation_availability(request, appointment_id):
    cita = _get_client_appointment(request.cliente, appointment_id)
    if not cita:
        return json_response({"detail": "No encontramos la cita solicitada."}, status=404)
    if cita.estado != CitaMedica.Estado.PROGRAMADA or cita.fecha_hora <= timezone.now():
        return json_response(
            {"detail": "Solo puedes editar reservas futuras que sigan programadas."},
            status=400,
        )

    data = {
        "operation": _operation_item(cita.operacion),
        "calendar": _build_operation_slot_map(cita.operacion, editing_appointment=cita),
        "appointment": _appointment_item(cita),
        "currentSlotId": cita.disponibilidad_id,
    }
    return json_response(data)


@require_POST
@_client_required
@transaction.atomic
def client_create_reservation(request, operation_id):
    operacion = _get_client_operation(request.cliente, operation_id)
    if not operacion:
        return json_response({"detail": "No encontramos la operacion solicitada."}, status=404)
    if not operacion.puede_reservar:
        return json_response(
            {
                "detail": operacion.motivo_bloqueo_reserva
                or "Esta operacion ya no permite nuevas reservas por ahora."
            },
            status=400,
        )

    payload = _load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    slot_id = payload.get("slotId")
    if not slot_id:
        return json_response({"detail": "Debes seleccionar un horario disponible antes de confirmar la reserva."}, status=400)

    slot = (
        DisponibilidadCita.objects.select_for_update()
        .select_related("especialista__usuario")
        .prefetch_related("citas_prospectos_origen", "citas_clientes_libres_origen")
        .filter(pk=slot_id, activo=True, fecha_hora__gt=timezone.now())
        .first()
    )
    if not slot or not slot.coincide_con_operacion(operacion):
        return json_response(
            {"detail": "El horario seleccionado ya no esta disponible para este tratamiento."},
            status=409,
        )

    if slot.citas_origen.filter(estado__in=BLOCKING_RESERVATION_STATES).exists():
        return json_response(
            {"detail": "El horario seleccionado acaba de ocuparse. Actualiza el calendario e intenta de nuevo."},
            status=409,
        )
    if slot.citas_prospectos_origen.filter(estado=CitaProspecto.Estado.PROGRAMADA).exists():
        return json_response(
            {"detail": "El horario seleccionado acaba de ocuparse. Actualiza el calendario e intenta de nuevo."},
            status=409,
        )
    if slot.citas_clientes_libres_origen.filter(estado=CitaClienteLibre.Estado.PROGRAMADA).exists():
        return json_response(
            {"detail": "El horario seleccionado acaba de ocuparse. Actualiza el calendario e intenta de nuevo."},
            status=409,
        )

    cita = CitaMedica.objects.create(
        operacion=operacion,
        disponibilidad=slot,
        fecha_hora=slot.fecha_hora,
        estado=CitaMedica.Estado.PROGRAMADA,
        detalles_cita="Reserva web creada por el cliente desde el portal.",
    )

    return json_response(
        {
            "detail": "La cita fue reservada correctamente.",
            "appointment": _appointment_item(cita),
            "operation": _operation_item(operacion),
        },
        status=201,
    )


@require_POST
@_client_required
@transaction.atomic
def client_update_reservation(request, appointment_id):
    cita = (
        CitaMedica.objects.select_for_update(of=("self",))
        .select_related(
            "operacion__servicio_config__tipo_servicio",
            "operacion__servicio_config__proc_estetico",
            
            "disponibilidad",
        )
        .prefetch_related("disponibilidad__citas_origen", "disponibilidad__citas_prospectos_origen", "disponibilidad__citas_clientes_libres_origen")
        .filter(operacion__paciente=request.cliente, pk=appointment_id)
        .first()
    )
    if not cita:
        return json_response({"detail": "No encontramos la cita solicitada."}, status=404)
    if cita.estado != CitaMedica.Estado.PROGRAMADA or cita.fecha_hora <= timezone.now():
        return json_response(
            {"detail": "Solo puedes editar reservas futuras que sigan programadas."},
            status=400,
        )

    payload = _load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    slot_id = payload.get("slotId")
    if not slot_id:
        return json_response({"detail": "Debes seleccionar un horario disponible antes de guardar."}, status=400)

    slot = (
        DisponibilidadCita.objects.select_for_update()
        .select_related("especialista__usuario")
        .prefetch_related("citas_origen", "citas_prospectos_origen", "citas_clientes_libres_origen")
        .filter(pk=slot_id, activo=True, fecha_hora__gt=timezone.now())
        .first()
    )
    if not slot or not slot.coincide_con_operacion(cita.operacion):
        return json_response(
            {"detail": "El horario seleccionado ya no esta disponible para este tratamiento."},
            status=409,
        )

    if slot.citas_origen.exclude(pk=cita.pk).filter(estado__in=BLOCKING_RESERVATION_STATES).exists():
        return json_response(
            {"detail": "El horario seleccionado acaba de ocuparse. Actualiza el calendario e intenta de nuevo."},
            status=409,
        )
    if slot.citas_prospectos_origen.filter(estado=CitaProspecto.Estado.PROGRAMADA).exists():
        return json_response(
            {"detail": "El horario seleccionado acaba de ocuparse. Actualiza el calendario e intenta de nuevo."},
            status=409,
        )
    if slot.citas_clientes_libres_origen.filter(estado=CitaClienteLibre.Estado.PROGRAMADA).exists():
        return json_response(
            {"detail": "El horario seleccionado acaba de ocuparse. Actualiza el calendario e intenta de nuevo."},
            status=409,
        )
    cita.disponibilidad = slot
    cita.fecha_hora = slot.fecha_hora
    cita.detalles_cita = "Reserva web actualizada por el cliente desde el portal."
    cita.save(update_fields=["disponibilidad", "fecha_hora", "detalles_cita", "updated_at"])

    return json_response(
        {
            "detail": "La reserva fue actualizada correctamente.",
            "appointment": _appointment_item(cita),
            "operation": _operation_item(cita.operacion),
        },
        status=200,
    )


@require_POST
@_client_required
@transaction.atomic
def client_cancel_reservation(request, appointment_id):
    cita = (
        CitaMedica.objects.select_for_update(of=("self",))
        .select_related(
            "operacion__servicio_config__tipo_servicio",
            "operacion__servicio_config__proc_estetico",
        )
        .filter(operacion__paciente=request.cliente, pk=appointment_id)
        .first()
    )
    if not cita:
        return json_response({"detail": "No encontramos la cita solicitada."}, status=404)
    if cita.estado != CitaMedica.Estado.PROGRAMADA or cita.fecha_hora <= timezone.now():
        return json_response(
            {"detail": "Solo puedes cancelar reservas futuras que sigan programadas."},
            status=400,
        )

    cita.estado = CitaMedica.Estado.CANCELADA
    cita.detalles_cita = "Reserva cancelada por el cliente desde el portal."
    cita.save(update_fields=["estado", "detalles_cita", "updated_at"])

    return json_response(
        {
            "detail": "La reserva fue cancelada correctamente.",
            "appointment": _appointment_item(cita),
            "operation": _operation_item(cita.operacion),
        },
        status=200,
    )


@require_POST
@_client_required
@transaction.atomic
def client_confirm_pending_appointment_tablet(request, appointment_id):
    cita = (
        CitaMedica.objects.select_for_update(of=("self",))
        .select_related("operacion__paciente", "sucursal")
        .filter(operacion__paciente=request.cliente, pk=appointment_id)
        .first()
    )
    if not cita:
        return json_response({"detail": "No encontramos la cita solicitada."}, status=404)
    if cita.estado != CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
        return json_response(
            {"detail": "Solo se pueden confirmar por tablet citas pendientes de biometria."},
            status=400,
        )
    if timezone.localdate(cita.fecha_hora) != timezone.localdate():
        return json_response({"detail": "Solo puedes confirmar la cita el mismo dia de la atencion."}, status=400)

    cita.estado = CitaMedica.Estado.CONFIRMADA
    cita.metodo_confirmacion = CitaMedica.MetodoConfirmacion.TABLET
    cita.verif_biometria = False
    cita.save(update_fields=["estado", "metodo_confirmacion", "verif_biometria", "updated_at"])

    EventoConfirmacionCita.objects.create(
        cita=cita,
        paciente=request.cliente,
        sucursal=cita.sucursal,
        metodo=EventoConfirmacionCita.Metodo.TABLET,
        confirmado_en=timezone.now(),
        ip_origen=_client_ip(request),
    )

    return json_response(
        {
            "detail": "Cita realizada",
            "appointment": _appointment_item(cita),
        },
        status=200,
    )
