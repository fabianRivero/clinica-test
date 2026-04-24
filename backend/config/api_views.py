import json
from pathlib import PurePosixPath
from datetime import timedelta
from functools import wraps

from django.db.models import Prefetch
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from billing.models import CuotaPlanPago, PagoRealizado
from catalogs.models import (
    GrupoOpciones,
    OpcionCatalogo,
    PatologiaCutanea,
    ProcEstetico,
    ServicioConfig,
    TipoServicio,
)
from customers.models import Cliente, Prospecto
from operations.models import CitaMedica, FichaCampo, Operacion
from staff.models import Especialidad, Especialista


def _json(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _admin_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return _json({"detail": "Autenticacion requerida."}, status=401)
        if not (user.is_superuser or user.es_administrador):
            return _json({"detail": "No tienes permisos para acceder a esta vista."}, status=403)
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
    return timezone.localtime(value).strftime("%d/%m %H:%M")


def _full_name(user):
    if not user:
        return "Sin asignar"
    return user.nombre_completo or user.username


def _procedure_name(operacion):
    procedimiento = operacion.servicio_config.proc_estetico
    if procedimiento:
        return procedimiento.proceso
    return operacion.servicio_config.tipo_servicio.tipo


def _payment_status(payment):
    if payment.estado_verificacion == PagoRealizado.EstadoVerificacion.APROBADO:
        return "aprobado"
    if payment.estado_verificacion == PagoRealizado.EstadoVerificacion.RECHAZADO:
        return "observado"
    return "pendiente"


def _agenda_status(cita):
    if cita.estado == CitaMedica.Estado.CONFIRMADA:
        return "confirmada"
    if cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA:
        return "biometria"
    return "programada"


def _prospect_stage(prospecto):
    if prospecto.estado == Prospecto.Estado.CONVERTIDO:
        return "convertido"
    if prospecto.created_at >= timezone.now() - timedelta(days=2):
        return "nuevo"
    return "seguimiento"


def _prospect_interest(prospecto):
    if prospecto.estado == Prospecto.Estado.CONVERTIDO:
        return "Cliente convertido"
    if prospecto.observaciones:
        return prospecto.observaciones
    return "Consulta general"


def _quota_status(operacion):
    cuotas = list(operacion.cuotas_plan_pagos.all())
    if not cuotas:
        return "Sin plan de pagos"

    has_observed = any(
        pago.estado_verificacion == PagoRealizado.EstadoVerificacion.RECHAZADO
        for cuota in cuotas
        for pago in cuota.pagos_realizados.all()
    )
    if has_observed:
        return "Pago observado"

    pending_payments = sum(
        1
        for cuota in cuotas
        for pago in cuota.pagos_realizados.all()
        if pago.estado_verificacion == PagoRealizado.EstadoVerificacion.PENDIENTE
    )
    if pending_payments:
        return f"{pending_payments} pago(s) pendientes"

    pending_quotas = sum(1 for cuota in cuotas if cuota.estado != CuotaPlanPago.Estado.PAGADO)
    if pending_quotas:
        return f"{pending_quotas} cuota(s) pendientes"

    return "Cuotas al dia"


def _operation_specialist(operacion):
    citas = list(operacion.citas_medicas.all())
    if not citas:
        return "Sin asignar"

    now = timezone.now()
    upcoming = [cita for cita in citas if cita.fecha_hora >= now]
    if upcoming:
        return _full_name(upcoming[0].medico.usuario)
    return _full_name(citas[-1].medico.usuario)


def _operation_next_appointment(operacion):
    citas = list(operacion.citas_medicas.all())
    if not citas:
        return "Sin cita programada"

    now = timezone.now()
    upcoming = [cita for cita in citas if cita.fecha_hora >= now]
    cita = upcoming[0] if upcoming else citas[-1]
    return _datetime_label(cita.fecha_hora)


def _operation_card(operacion):
    return {
        "id": f"OP-{operacion.pk:04d}",
        "rawId": operacion.pk,
        "patient": _full_name(operacion.paciente.usuario),
        "procedure": _procedure_name(operacion),
        "specialist": _operation_specialist(operacion),
        "sessions": (
            f"{operacion.sesiones_totales} total | "
            f"{operacion.sesiones_confirmadas} confirmadas | "
            f"{operacion.reservas_activas} reservadas | "
            f"{operacion.sesiones_disponibles} libres"
        ),
        "nextAppointment": _operation_next_appointment(operacion),
        "quotaStatus": _quota_status(operacion),
        "status": operacion.get_estado_display(),
        "price": _currency(operacion.precio_total),
    }


def _operation_detail(operacion):
    ficha = getattr(operacion, "ficha_clinica", None)
    procedure = operacion.servicio_config.proc_estetico
    document_field = ficha.documento_escaneado_pdf if ficha else None
    document_url = document_field.url if document_field else ""
    document_name = PurePosixPath(document_field.name).name if document_field else ""

    return {
        "id": f"OP-{operacion.pk:04d}",
        "rawId": operacion.pk,
        "patient": _full_name(operacion.paciente.usuario),
        "procedure": _procedure_name(operacion),
        "serviceType": operacion.servicio_config.tipo_servicio.tipo,
        "procedureType": procedure.tipo_p_estetico.tipo if procedure else "Sin tipo",
        "specialist": _operation_specialist(operacion),
        "sessions": (
            f"{operacion.sesiones_totales} total | "
            f"{operacion.sesiones_confirmadas} confirmadas | "
            f"{operacion.reservas_activas} reservadas | "
            f"{operacion.sesiones_disponibles} libres"
        ),
        "nextAppointment": _operation_next_appointment(operacion),
        "quotaStatus": _quota_status(operacion),
        "status": operacion.get_estado_display(),
        "price": _currency(operacion.precio_total),
        "startDate": _date_label(operacion.fecha_inicio),
        "endDate": _date_label(operacion.fecha_final),
        "zonaGeneral": operacion.zona_general or "Sin especificar",
        "zonaEspecifica": operacion.zona_especifica or "Sin especificar",
        "detallesOperacion": operacion.detalles_op or "Sin detalles registrados.",
        "recomendaciones": operacion.recomendaciones or "Sin recomendaciones registradas.",
        "medicalRecordDate": _date_label(ficha.fecha_ficha) if ficha else "Sin ficha registrada",
        "medicalRecordReason": ficha.motivo_consulta if ficha and ficha.motivo_consulta else "Sin motivo registrado.",
        "medicalRecordNotes": ficha.observaciones if ficha and ficha.observaciones else "Sin observaciones registradas.",
        "consentAccepted": bool(ficha and ficha.consentimiento_aceptado),
        "documentPdfUrl": document_url,
        "documentPdfName": document_name,
        "appointments": [
            {
                "id": f"CIT-{cita.pk:04d}",
                "dateTime": _datetime_label(cita.fecha_hora),
                "specialist": _full_name(cita.medico.usuario),
                "status": cita.get_estado_display(),
                "biometricStatus": "Validada" if cita.verif_biometria else "Pendiente",
            }
            for cita in operacion.citas_medicas.all()
        ],
        "quotas": [
            {
                "id": f"CUO-{cuota.pk:04d}",
                "number": cuota.nro_cuota,
                "dueDate": _date_label(cuota.fecha_vencimiento),
                "status": cuota.get_estado_display(),
                "paymentsCount": cuota.pagos_realizados.count(),
            }
            for cuota in operacion.cuotas_plan_pagos.all()
        ],
    }


def _prospect_item(prospecto):
    return {
        "id": f"PRO-{prospecto.pk:04d}",
        "rawId": prospecto.pk,
        "name": str(prospecto),
        "phone": prospecto.telefono or "Sin telefono",
        "interest": _prospect_interest(prospecto),
        "registeredBy": _full_name(prospecto.registrado_por),
        "stage": _prospect_stage(prospecto),
        "state": prospecto.get_estado_display(),
        "createdAt": _datetime_label(prospecto.created_at),
        "convertedAt": _datetime_label(prospecto.fecha_conversion) if prospecto.fecha_conversion else "-",
    }


def _client_item(cliente):
    analisis = next(iter(cliente.analisis_esteticos.all()), None)
    return {
        "id": f"CLI-{cliente.pk:04d}",
        "name": _full_name(cliente.usuario),
        "phone": cliente.telefono or "Sin telefono",
        "status": cliente.get_estado_cliente_display(),
        "activeOperations": cliente.operaciones.filter(estado=Operacion.Estado.EN_PROCESO).count(),
        "totalOperations": cliente.operaciones.count(),
        "lastAnalysis": _date_label(analisis.fecha_analisis) if analisis else "Sin analisis",
    }


def _payment_item(payment):
    operacion = payment.cuota.operacion
    return {
        "id": f"PAY-{payment.pk:04d}",
        "patient": _full_name(operacion.paciente.usuario),
        "operation": _procedure_name(operacion),
        "amount": _currency(payment.monto_pagado),
        "submittedAt": _datetime_label(payment.created_at),
        "bank": "Transferencia",
        "status": _payment_status(payment),
        "quota": f"Cuota {payment.cuota.nro_cuota}",
        "dueDate": _date_label(payment.cuota.fecha_vencimiento),
        "verifier": _full_name(payment.verificado_por) if payment.verificado_por else "Sin revisar",
        "receiptUrl": payment.comprobante_url or "",
        "note": payment.observacion_verificacion or payment.detalles_pago or "",
    }


def _catalog_item(identifier, name, count, note):
    return {
        "id": identifier,
        "name": name,
        "count": count,
        "note": note,
    }


def _staff_item(especialista):
    citas = list(especialista.citas_medicas.all())
    now = timezone.now()
    upcoming = [cita for cita in citas if cita.fecha_hora >= now]
    pending_biometric = sum(
        1
        for cita in citas
        if cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA
    )
    active_operations = {
        cita.operacion_id
        for cita in citas
        if cita.operacion.estado == Operacion.Estado.EN_PROCESO
    }
    load = min(100, len(active_operations) * 25 + len(upcoming[:7]) * 15)
    specialties = [rel.especialidad.nombre for rel in especialista.especialidades_rel.all()]

    return {
        "id": f"STF-{especialista.pk:04d}",
        "specialist": _full_name(especialista.usuario),
        "specialty": ", ".join(specialties) if specialties else "Sin especialidad",
        "load": load,
        "pendingValidations": pending_biometric,
        "phone": especialista.telefono or "Sin telefono",
        "activeOperations": len(active_operations),
        "upcomingAppointments": len(upcoming),
    }


def _metric(identifier, label, value, delta, tone):
    return {
        "id": identifier,
        "label": label,
        "value": str(value),
        "delta": delta,
        "tone": tone,
    }


def _dashboard_alerts():
    now = timezone.now()
    overdue_pending = PagoRealizado.objects.filter(
        estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
        created_at__lt=now - timedelta(hours=24),
    ).count()
    operations_without_capacity = sum(
        1
        for operacion in Operacion.objects.filter(estado=Operacion.Estado.EN_PROCESO)
        if operacion.sesiones_disponibles == 0
    )
    procedures_without_sections = ProcEstetico.objects.filter(activo=True, secciones_ficha__isnull=True).count()

    alerts = []
    if overdue_pending:
        alerts.append(
            {
                "id": "alert-payments",
                "title": "Pagos pendientes por mas de 24 horas",
                "description": f"Hay {overdue_pending} comprobante(s) que aun no fueron revisados.",
                "severity": "high",
                "action": "Revisar cola de pagos",
            }
        )
    else:
        alerts.append(
            {
                "id": "alert-payments-ok",
                "title": "Cola de pagos controlada",
                "description": "No hay comprobantes vencidos esperando revision administrativa.",
                "severity": "low",
                "action": "Ver pagos recientes",
            }
        )

    if operations_without_capacity:
        alerts.append(
            {
                "id": "alert-capacity",
                "title": "Operaciones sin sesiones disponibles",
                "description": (
                    f"{operations_without_capacity} operacion(es) activas ya no admiten nuevas reservas."
                ),
                "severity": "medium",
                "action": "Revisar operaciones",
            }
        )
    else:
        alerts.append(
            {
                "id": "alert-capacity-ok",
                "title": "Reservas con capacidad disponible",
                "description": "Las operaciones activas aun tienen sesiones para agendar sin bloqueo.",
                "severity": "low",
                "action": "Monitorear agenda",
            }
        )

    if procedures_without_sections:
        alerts.append(
            {
                "id": "alert-catalogs",
                "title": "Procedimientos sin ficha configurada",
                "description": (
                    f"Hay {procedures_without_sections} procedimiento(s) activos sin secciones de ficha clinica."
                ),
                "severity": "medium",
                "action": "Completar catalogos",
            }
        )

    return alerts


@require_GET
@_admin_required
def admin_dashboard(request):
    today = timezone.localdate()
    pending_payments_qs = (
        PagoRealizado.objects.select_related(
            "cuota__operacion__paciente__usuario",
            "cuota__operacion__servicio_config__proc_estetico",
        )
        .order_by("-created_at")
    )
    agenda_qs = (
        CitaMedica.objects.select_related(
            "operacion__paciente__usuario",
            "operacion__servicio_config__proc_estetico",
            "medico__usuario",
        )
        .filter(fecha_hora__date__gte=today)
        .order_by("fecha_hora")
    )
    if not agenda_qs.exists():
        agenda_qs = (
            CitaMedica.objects.select_related(
                "operacion__paciente__usuario",
                "operacion__servicio_config__proc_estetico",
                "medico__usuario",
            )
            .order_by("-fecha_hora")
        )

    operations_qs = (
        Operacion.objects.select_related(
            "paciente__usuario",
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
                queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
            ),
        )
        .filter(estado=Operacion.Estado.EN_PROCESO)
        .order_by("-created_at")
    )
    prospectos_qs = Prospecto.objects.select_related("registrado_por").order_by("-created_at")
    staff_qs = (
        Especialista.objects.select_related("usuario")
        .prefetch_related(
            "especialidades_rel__especialidad",
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.select_related("operacion").order_by("fecha_hora"),
            ),
        )
        .order_by("usuario__primer_nombre", "usuario__apellido_paterno")
    )

    pending_payments = pending_payments_qs.filter(
        estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE
    )
    payments_today = pending_payments.filter(created_at__date=today).count()
    operations_started_this_month = Operacion.objects.filter(
        created_at__year=today.year,
        created_at__month=today.month,
    ).count()
    converted_prospects = Prospecto.objects.filter(estado=Prospecto.Estado.CONVERTIDO).count()
    total_prospects = Prospecto.objects.count()
    prospect_delta = (
        f"{round((converted_prospects / total_prospects) * 100)}% convertidos"
        if total_prospects
        else "Sin conversiones aun"
    )
    appointments_today = CitaMedica.objects.filter(fecha_hora__date=today).count()
    pending_biometric = CitaMedica.objects.filter(
        estado=CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA
    ).count()

    data = {
        "metrics": [
            _metric(
                "payments",
                "Pagos por verificar",
                pending_payments.count(),
                f"{payments_today} subidos hoy",
                "warning",
            ),
            _metric(
                "operations",
                "Tratamientos activos",
                operations_qs.count(),
                f"{operations_started_this_month} iniciadas este mes",
                "primary",
            ),
            _metric(
                "prospects",
                "Prospectos en seguimiento",
                prospectos_qs.filter(estado=Prospecto.Estado.PASAJERO).count(),
                prospect_delta,
                "success",
            ),
            _metric(
                "appointments",
                "Citas del dia",
                appointments_today,
                f"{pending_biometric} pendientes de biometria",
                "danger" if pending_biometric else "success",
            ),
        ],
        "payments": [_payment_item(payment) for payment in pending_payments_qs[:5]],
        "agenda": [
            {
                "id": f"CIT-{cita.pk:04d}",
                "time": timezone.localtime(cita.fecha_hora).strftime("%H:%M"),
                "patient": _full_name(cita.operacion.paciente.usuario),
                "procedure": _procedure_name(cita.operacion),
                "specialist": _full_name(cita.medico.usuario),
                "status": _agenda_status(cita),
            }
            for cita in agenda_qs[:4]
        ],
        "prospects": [_prospect_item(prospecto) for prospecto in prospectos_qs[:4]],
        "alerts": _dashboard_alerts(),
        "operations": [_operation_card(operacion) for operacion in operations_qs[:4]],
        "catalogHealth": [
            _catalog_item(
                "procedures",
                "Procedimientos esteticos",
                ProcEstetico.objects.filter(activo=True).count(),
                f"{ServicioConfig.objects.filter(activo=True).count()} servicio(s) activos configurados",
            ),
            _catalog_item(
                "fields",
                "Campos clinicos",
                FichaCampo.objects.filter(activo=True).count(),
                f"{GrupoOpciones.objects.filter(activo=True).count()} grupo(s) de opciones disponibles",
            ),
            _catalog_item(
                "specialties",
                "Especialidades",
                Especialidad.objects.filter(activo=True).count(),
                f"{staff_qs.count()} especialista(s) con carga operativa",
            ),
            _catalog_item(
                "skin",
                "Patologias cutaneas",
                PatologiaCutanea.objects.filter(activo=True).count(),
                f"{OpcionCatalogo.objects.filter(activo=True).count()} opciones catalogadas en total",
            ),
        ],
        "staffCapacity": [_staff_item(especialista) for especialista in staff_qs[:4]],
    }
    return _json(data)


@require_GET
@_admin_required
def admin_prospectos(request):
    prospectos_qs = Prospecto.objects.select_related("registrado_por").order_by("-created_at")
    clientes_qs = (
        Cliente.objects.select_related("usuario")
        .prefetch_related("operaciones", "analisis_esteticos")
        .order_by("usuario__primer_nombre", "usuario__apellido_paterno")
    )

    data = {
        "metrics": [
            _metric(
                "prospects-open",
                "Prospectos abiertos",
                prospectos_qs.filter(estado=Prospecto.Estado.PASAJERO).count(),
                "Registrados internamente por el equipo",
                "primary",
            ),
            _metric(
                "prospects-converted",
                "Prospectos convertidos",
                prospectos_qs.filter(estado=Prospecto.Estado.CONVERTIDO).count(),
                "Ya cuentan con tratamiento activo o historico",
                "success",
            ),
            _metric(
                "clients-active",
                "Clientes activos",
                clientes_qs.filter(estado_cliente=Cliente.Estado.ACTIVO).count(),
                "Con al menos una operacion vigente",
                "warning",
            ),
            _metric(
                "clients-inactive",
                "Clientes inactivos",
                clientes_qs.filter(estado_cliente=Cliente.Estado.INACTIVO).count(),
                "Con historial disponible en portal",
                "danger",
            ),
        ],
        "prospects": [_prospect_item(prospecto) for prospecto in prospectos_qs],
        "clients": [_client_item(cliente) for cliente in clientes_qs],
    }
    return _json(data)


@require_POST
@_admin_required
def admin_crear_prospecto(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    nombres = (payload.get("nombres") or "").strip()
    apellidos = (payload.get("apellidos") or "").strip()
    telefono = (payload.get("telefono") or "").strip()
    observaciones = (payload.get("observaciones") or "").strip()
    estado = (payload.get("estado") or Prospecto.Estado.PASAJERO).strip()

    errors = {}
    if not nombres:
        errors["nombres"] = "Los nombres son obligatorios."
    if not apellidos:
        errors["apellidos"] = "Los apellidos son obligatorios."
    if estado not in {Prospecto.Estado.PASAJERO, Prospecto.Estado.DESCARTADO}:
        errors["estado"] = "Solo puedes crear prospectos en estado pasajero o descartado."

    if errors:
        return _json({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)

    prospecto = Prospecto.objects.create(
        nombres=nombres,
        apellidos=apellidos,
        telefono=telefono,
        estado=estado,
        observaciones=observaciones,
        registrado_por=request.user,
    )

    return _json(
        {
            "detail": "Prospecto registrado correctamente.",
            "prospect": _prospect_item(prospecto),
        },
        status=201,
    )


@require_GET
@_admin_required
def admin_operaciones(request):
    operaciones_qs = (
        Operacion.objects.select_related(
            "paciente__usuario",
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
                queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
            ),
        )
        .order_by("-created_at")
    )
    blocked_reservations = sum(
        1
        for operacion in operaciones_qs
        if operacion.estado == Operacion.Estado.EN_PROCESO and not operacion.puede_reservar
    )

    data = {
        "metrics": [
            _metric(
                "operations-active",
                "Operaciones en proceso",
                operaciones_qs.filter(estado=Operacion.Estado.EN_PROCESO).count(),
                "Tratamientos actualmente vigentes",
                "primary",
            ),
            _metric(
                "operations-draft",
                "Operaciones en borrador",
                operaciones_qs.filter(estado=Operacion.Estado.BORRADOR).count(),
                "Pendientes de activacion o venta",
                "warning",
            ),
            _metric(
                "operations-finished",
                "Operaciones finalizadas",
                operaciones_qs.filter(estado=Operacion.Estado.FINALIZADA).count(),
                "Historial clinico consolidado",
                "success",
            ),
            _metric(
                "operations-blocked",
                "Reservas bloqueadas",
                blocked_reservations,
                "Sin sesiones libres para reservar",
                "danger",
            ),
        ],
        "operations": [_operation_card(operacion) for operacion in operaciones_qs],
    }
    return _json(data)


@require_GET
@_admin_required
def admin_operacion_detalle(request, operacion_id):
    operacion = (
        Operacion.objects.select_related(
            "paciente__usuario",
            "servicio_config__tipo_servicio",
            "servicio_config__proc_estetico__tipo_p_estetico",
            "ficha_clinica",
        )
        .prefetch_related(
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.select_related("medico__usuario").order_by("fecha_hora"),
            ),
            Prefetch(
                "cuotas_plan_pagos",
                queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
            ),
        )
        .filter(pk=operacion_id)
        .first()
    )

    if not operacion:
        return _json({"detail": "No encontramos la operacion solicitada."}, status=404)

    return _json({"operation": _operation_detail(operacion)})


@require_GET
@_admin_required
def admin_pagos(request):
    pagos_qs = (
        PagoRealizado.objects.select_related(
            "cuota__operacion__paciente__usuario",
            "cuota__operacion__servicio_config__proc_estetico",
            "verificado_por",
        )
        .order_by("-created_at")
    )
    pending_amount = sum(
        payment.monto_pagado
        for payment in pagos_qs
        if payment.estado_verificacion == PagoRealizado.EstadoVerificacion.PENDIENTE
    )

    data = {
        "metrics": [
            _metric(
                "payments-pending",
                "Pendientes de revision",
                pagos_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE).count(),
                _currency(pending_amount),
                "warning",
            ),
            _metric(
                "payments-approved",
                "Pagos aprobados",
                pagos_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO).count(),
                "Impactan el estado de cuotas",
                "success",
            ),
            _metric(
                "payments-observed",
                "Pagos observados",
                pagos_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.RECHAZADO).count(),
                "Requieren seguimiento administrativo",
                "danger",
            ),
            _metric(
                "payments-total",
                "Pagos registrados",
                pagos_qs.count(),
                "Incluye historico completo del sistema",
                "primary",
            ),
        ],
        "payments": [_payment_item(payment) for payment in pagos_qs],
    }
    return _json(data)


@require_GET
@_admin_required
def admin_catalogos(request):
    active_services = ServicioConfig.objects.filter(activo=True).count()
    active_service_types = TipoServicio.objects.filter(activo=True).count()
    active_groups = GrupoOpciones.objects.filter(activo=True).count()
    active_options = OpcionCatalogo.objects.filter(activo=True).count()

    data = {
        "metrics": [
            _metric(
                "catalog-procedures",
                "Procedimientos activos",
                ProcEstetico.objects.filter(activo=True).count(),
                f"{active_services} servicio(s) configurados",
                "primary",
            ),
            _metric(
                "catalog-types",
                "Tipos de servicio",
                active_service_types,
                "Base comercial editable",
                "success",
            ),
            _metric(
                "catalog-fields",
                "Campos de ficha",
                FichaCampo.objects.filter(activo=True).count(),
                f"{active_groups} grupo(s) de opciones",
                "warning",
            ),
            _metric(
                "catalog-options",
                "Opciones catalogadas",
                active_options,
                "Respuestas reutilizables para fichas y analisis",
                "danger",
            ),
        ],
        "catalogs": [
            _catalog_item(
                "procedures",
                "Procedimientos esteticos",
                ProcEstetico.objects.filter(activo=True).count(),
                f"{ServicioConfig.objects.filter(activo=True).count()} configuraciones activas de servicio",
            ),
            _catalog_item(
                "service-types",
                "Tipos de servicio",
                active_service_types,
                "Categorias comerciales visibles en operaciones y ventas",
            ),
            _catalog_item(
                "form-fields",
                "Campos de ficha",
                FichaCampo.objects.filter(activo=True).count(),
                f"{FichaCampo.objects.filter(activo=False).count()} campo(s) inactivos preservados",
            ),
            _catalog_item(
                "option-groups",
                "Grupos de opciones",
                active_groups,
                f"{active_options} opcion(es) activas asociadas",
            ),
            _catalog_item(
                "skin-pathologies",
                "Patologias cutaneas",
                PatologiaCutanea.objects.filter(activo=True).count(),
                "Disponibles para analisis estetico y reportes",
            ),
            _catalog_item(
                "specialties",
                "Especialidades",
                Especialidad.objects.filter(activo=True).count(),
                "Catalogo usado para especialistas y asignaciones del equipo",
            ),
        ],
    }
    return _json(data)


@require_GET
@_admin_required
def admin_equipo(request):
    staff_qs = (
        Especialista.objects.select_related("usuario")
        .prefetch_related(
            "especialidades_rel__especialidad",
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.select_related("operacion").order_by("fecha_hora"),
            ),
        )
        .order_by("usuario__primer_nombre", "usuario__apellido_paterno")
    )
    upcoming_appointments = CitaMedica.objects.filter(fecha_hora__gte=timezone.now()).count()
    pending_biometric = CitaMedica.objects.filter(
        estado=CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA
    ).count()

    data = {
        "metrics": [
            _metric(
                "team-specialists",
                "Especialistas activos",
                staff_qs.count(),
                "Usuarios con perfil operativo asignado",
                "primary",
            ),
            _metric(
                "team-specialties",
                "Especialidades",
                Especialidad.objects.filter(activo=True).count(),
                "Catalogo editable desde administracion",
                "success",
            ),
            _metric(
                "team-agenda",
                "Citas futuras",
                upcoming_appointments,
                "Carga agendada a partir de hoy",
                "warning",
            ),
            _metric(
                "team-biometric",
                "Pendientes de biometria",
                pending_biometric,
                "Citas realizadas sin cierre final",
                "danger",
            ),
        ],
        "staff": [_staff_item(especialista) for especialista in staff_qs],
    }
    return _json(data)
