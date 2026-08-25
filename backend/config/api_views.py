import json
import logging
from pathlib import PurePosixPath
from datetime import date, timedelta, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db import models
from django.db.models import Max, Prefetch, Q
from django.contrib.sessions.models import Session
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.cache import cache
from django.views.decorators.http import require_GET, require_POST
from django.conf import settings
from biometric.serializers import verification_suspended_payload


def _request_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


from accounts.models import Rol, Usuario
from billing.models import CategoriaGasto, ConfiguracionPagoQR, CuotaPlanPago, GastoSucursal, PagoRealizado
from catalogs.models import (
    GrupoOpciones,
    OpcionCatalogo,
    PatologiaCutanea,
    ProcEstetico,
    ProcEsteticosTipo,
    Sector,
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from customers.models import Cliente, HuellaBiometricaCliente, Prospecto
from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualEspecialista,
    CitaClienteLibre,
    CitaMedica,
    CitaProspecto,
    EventoConfirmacionCita,
    Operacion,
    BranchAdminAuditLog,
    TabletKiosko,
)
from clinical.models import FichaCampo, FichaSeccion
from operations.scheduling import mark_expired_programmed_appointments_as_no_show
from config.api_helpers import (
    admin_required,
    capitalize_first_letter,
    currency,
    date_label,
    datetime_label,
    full_name,
    get_user_branch,
    json_response,
    load_payload,
    metric,
    procedure_name,
    split_amount,
)
from config.api.helpers_operations import (
    agenda_status,
    agenda_appointment_status,
    agenda_verification_status,
    agenda_verification_method,
    operation_branch,
    operation_branch_id,
    operation_card,
    operation_next_appointment,
    operation_reference_appointment,
    prospect_appointment_operation_card,
    quota_display_status,
    quota_programmed_amount,
    quota_status,
    appointment_biometric_status,
)
from config.client_api_views import (
    _appointment_item as _client_appointment_item,
    _build_operation_slot_map as _client_operation_slot_map,
    _operation_item as _client_operation_item,
    _payment_item as _client_payment_item,
    _quota_item as _client_quota_item,
    BLOCKING_RESERVATION_STATES,
)
from staff.models import Especialidad, Especialista, EspecialistaEspecialidad
from notifications.models import Notification
from notifications.services import create_notification

logger = logging.getLogger(__name__)
IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24
BRANCH_CREATE_WIZARD_SESSION_KEY = "admin_branch_create_wizard_draft"


# ---------------------------------------------------------------------------
# Backward-compatible aliases for helpers moved to config/api/helpers_operations.py
# ---------------------------------------------------------------------------
_agenda_status = agenda_status
_agenda_appointment_status = agenda_appointment_status
_agenda_verification_status = agenda_verification_status
_agenda_verification_method = agenda_verification_method
_quota_status = quota_status
_quota_programmed_amount = quota_programmed_amount
_quota_display_status = quota_display_status
_operation_reference_appointment = operation_reference_appointment
_operation_branch = operation_branch
_operation_branch_id = operation_branch_id
_operation_next_appointment = operation_next_appointment
_operation_card = operation_card
_appointment_biometric_status = appointment_biometric_status
_prospect_appointment_operation_card = prospect_appointment_operation_card

_capitalize_first_letter = capitalize_first_letter



def _client_has_pending_reservations(cliente):
    now = timezone.now()
    return (
        CitaMedica.objects.filter(
            operacion__paciente=cliente,
            estado=CitaMedica.Estado.PROGRAMADA,
            fecha_hora__gte=now,
        ).exists()
        or CitaClienteLibre.objects.filter(
            cliente=cliente,
            estado=CitaClienteLibre.Estado.PROGRAMADA,
            fecha_hora__gte=now,
        ).exists()
    )


def _admin_principal_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return json_response({"detail": "Autenticacion requerida."}, status=401)
        if not (user.is_superuser or user.es_admin_principal):
            return json_response({"detail": "Esta accion requiere permisos de administrador principal."}, status=403)
        return view_func(request, *args, **kwargs)

    return wrapped


def _capitalize_first_letter(value):
    value = (value or "").strip()
    return value[:1].upper() + value[1:] if value else ""


def _branch_payload(payload, *, partial=False):
    fields = ("nombre", "ciudad", "direccion")
    errors = {}
    data = {}
    for field in fields:
        value = payload.get(field)
        if value is None:
            if not partial:
                errors[field] = "Este campo es obligatorio."
            continue
        cleaned = str(value).strip()
        if not cleaned and field == "nombre":
            errors[field] = "Este campo es obligatorio."
            continue
        data[field] = cleaned
    return data, errors


def _idempotency_cache_key(request, scope):
    idem_key = request.headers.get("Idempotency-Key")
    if not idem_key:
        return None, None
    user_id = request.user.id if request.user.is_authenticated else "anon"
    return f"idempotency:{scope}:{user_id}:{idem_key}", None


def _idempotency_replay_or_store(cache_key, fn):
    if cache_key is None:
        return fn()
    cached = cache.get(cache_key)
    if cached:
        return json_response(cached["data"], status=cached["status"])
    response = fn()
    if 200 <= response.status_code < 300:
        payload = json.loads(response.content.decode("utf-8"))
        cache.set(cache_key, {"status": response.status_code, "data": payload}, IDEMPOTENCY_TTL_SECONDS)
    elif response.status_code == 409:
        pass
    return response


def _branch_deactivation_impact(branch):
    now = timezone.now()
    appointments_pending = (
        CitaMedica.objects.filter(sucursal=branch, fecha_hora__gte=now, estado=CitaMedica.Estado.PROGRAMADA).count()
        + CitaProspecto.objects.filter(sucursal=branch, fecha_hora__gte=now, estado=CitaProspecto.Estado.PROGRAMADA).count()
        + CitaClienteLibre.objects.filter(sucursal=branch, fecha_hora__gte=now, estado=CitaClienteLibre.Estado.PROGRAMADA).count()
    )
    payments_pending = PagoRealizado.objects.filter(
        cuota__operacion__paciente__usuario__sucursal_id=branch,
        estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
    ).count()
    processes_pending = Operacion.objects.filter(
        paciente__usuario__sucursal_id=branch
    ).exclude(estado=Operacion.Estado.CANCELADA).count()
    return {
        "appointments_pending": appointments_pending,
        "payments_pending": payments_pending,
        "processes_pending": processes_pending,
    }


def _get_branch_admin_role():
    role, _ = Rol.objects.get_or_create(rol="ADMIN_SUCURSAL")
    return role


def _branch_admin_item(user):
    return {
        "id": user.id,
        "username": user.username,
        "fullName": user.nombre_completo or user.username,
        "email": user.email or "",
        "telefono": user.telefono or "",
        "fechaNacimiento": user.fecha_nacimiento.isoformat() if isinstance(user.fecha_nacimiento, date) else (user.fecha_nacimiento or ""),
        "isActive": bool(user.is_active),
        "branchId": user.sucursal_id,
        "branchName": user.sucursal.nombre if user.sucursal else "Inactivo",
    }


def _log_branch_admin_audit(*, request, branch, action, detail="", metadata=None):
    BranchAdminAuditLog.objects.create(
        branch=branch,
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        detail=detail,
        metadata=metadata or {},
    )


def _invalidate_user_sessions(user_ids):
    user_ids = {int(user_id) for user_id in user_ids if user_id}
    if not user_ids:
        return

    stale_session_keys = []
    for session in Session.objects.filter(expire_date__gte=timezone.now()).only("session_key", "session_data"):
        try:
            session_data = session.get_decoded()
            auth_user_id = int(session_data.get("_auth_user_id") or 0)
        except Exception:
            continue
        if auth_user_id in user_ids:
            stale_session_keys.append(session.session_key)

    if stale_session_keys:
        Session.objects.filter(session_key__in=stale_session_keys).delete()


def _active_branch_has_any_admin(branch):
    has_main_admin = Usuario.objects.filter(rol__rol="ADMIN_PRINCIPAL", is_active=True, sucursal=branch).exists()
    has_branch_admin = Usuario.objects.filter(rol__rol="ADMIN_SUCURSAL", is_active=True, sucursal=branch).exists()
    return has_main_admin or has_branch_admin


@require_POST
@admin_required
def admin_set_session_branch(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
        branch_id = payload.get("branchId")
        if not branch_id:
            return json_response({"detail": "branchId es obligatorio."}, status=400)
        
        from catalogs.models import Sucursal
        branch = Sucursal.objects.filter(pk=int(branch_id), activa=True).first()
        if not branch:
            return json_response({"detail": "Sucursal no encontrada o inactiva."}, status=404)
        
        request.session["selected_branch_id"] = branch.pk
        return json_response({"detail": f"Sucursal activa cambiada a {branch.nombre}.", "branchId": branch.pk})
    except (ValueError, TypeError, json.JSONDecodeError):
        return json_response({"detail": "Datos invalidos."}, status=400)


def _parse_payload_decimal(payload, field_name, errors, *, min_value=Decimal("0")):
    raw = payload.get(field_name)
    if raw in (None, ""):
        errors[field_name] = "Este campo es obligatorio."
        return None
    try:
        value = Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        errors[field_name] = "Debes enviar un monto valido."
        return None
    if value < min_value:
        errors[field_name] = f"El valor minimo permitido es {min_value}."
        return None
    return value


def _parse_payload_int(payload, field_name, errors, *, min_value=0):
    raw = payload.get(field_name)
    if raw in (None, ""):
        errors[field_name] = "Este campo es obligatorio."
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        errors[field_name] = "Debes enviar un numero entero valido."
        return None
    if value < min_value:
        errors[field_name] = f"El valor minimo permitido es {min_value}."
        return None
    return value


# Backward-compatible alias for internal usages within this module
_datetime_label = datetime_label


def _notify_client_appointment_scheduled(*, cliente, fecha_hora, sucursal_id, appointment_id, appointment_type):
    recipient = getattr(cliente, "usuario", None)
    if not recipient:
        return

    branch = Sucursal.objects.filter(pk=sucursal_id).first()
    fecha_legible = _datetime_label(fecha_hora)
    nombre_sucursal = branch.nombre if branch else "Sucursal no especificada"

    create_notification(
        recipient=recipient,
        branch=branch,
        type="appointment_scheduled",
        title="Nueva cita programada",
        message=f"Tu cita fue programada para el {fecha_legible} en {nombre_sucursal}.",
        action_url="/cliente/reservas",
        payload={
            "appointmentType": appointment_type,
            "appointmentId": appointment_id,
            "scheduledAt": fecha_hora.isoformat(),
            "branchId": sucursal_id,
        },
        source_event="appointment_scheduled",
        source_entity_type=appointment_type,
        source_entity_id=appointment_id,
    )





def _payment_status(payment):
    if payment.estado_verificacion == PagoRealizado.EstadoVerificacion.APROBADO:
        return "aprobado"
    if payment.estado_verificacion == PagoRealizado.EstadoVerificacion.RECHAZADO:
        return "observado"
    if payment.estado_verificacion == PagoRealizado.EstadoVerificacion.CANCELADO:
        return "cancelado"
    return "pendiente"


# Aliased above at lines 98-107. These stubs are removed to avoid confusion.
# _agenda_status, _agenda_appointment_status, _agenda_verification_status,
# _agenda_verification_method are defined in helpers_operations.py


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


# Remaining functions are aliased above — stubs removed to avoid confusion.
# _quota_status, _quota_programmed_amount, _quota_display_status,
# _operation_reference_appointment, _operation_branch, _operation_branch_id,
# _operation_next_appointment, _operation_card, _prospect_appointment_operation_card,
# _appointment_biometric_status are defined in helpers_operations and aliased at lines 98-107.


def _operation_detail(operacion):
    ficha = getattr(operacion, "ficha_clinica", None)
    huella = getattr(operacion.paciente, "huella_biometrica", None)
    procedure = operacion.servicio_config.proc_estetico
    document_field = ficha.documento_escaneado_pdf if ficha else None
    document_url = document_field.url if document_field else ""
    document_name = PurePosixPath(document_field.name).name if document_field else ""

    quotas_payload = [
        {
            "id": f"CUO-{cuota.pk:04d}",
            "number": cuota.nro_cuota,
            "rawId": cuota.pk,
            "amount": currency(_quota_programmed_amount(cuota)),
            "amountValue": f"{_quota_programmed_amount(cuota):.2f}",
            "dueDate": date_label(cuota.fecha_vencimiento),
            "status": _quota_display_status(cuota),
            "paymentsCount": cuota.pagos_realizados.count(),
        }
        for cuota in operacion.cuotas_plan_pagos.all()
    ]
    logger.warning(
        "operation_detail operation=%s estado=%s quotas=%s",
        operacion.pk,
        operacion.estado,
        [
            {
                "cuota_id": item["rawId"],
                "status": item["status"],
                "paymentsCount": item["paymentsCount"],
            }
            for item in quotas_payload
        ],
    )

    return {
        "id": f"OP-{operacion.pk:04d}",
        "rawId": operacion.pk,
        "patientId": operacion.paciente_id,
        "patient": full_name(operacion.paciente.usuario),
        "procedure": procedure_name(operacion),
        "serviceType": operacion.servicio_config.tipo_servicio.tipo,
        "procedureType": procedure.tipo_p_estetico.tipo if procedure else "Sin tipo",
        "branch": _operation_branch(operacion),
        "branchId": _operation_branch_id(operacion),
        "sessions": (
            f"{operacion.sesiones_totales} total | "
            f"{operacion.sesiones_confirmadas} confirmadas | "
            f"{operacion.reservas_activas} reservadas | "
            f"{operacion.sesiones_disponibles} libres"
        ),
        # Cupos que quedan para una nueva reserva. El frontend usa este
        # numero directo para bloquear el formulario "Reservar nueva
        # cita" sin parsear el string localizado de ``sessions``.
        "availableAppointments": operacion.sesiones_disponibles,
        "nextAppointment": _operation_next_appointment(operacion),
        "quotaStatus": _quota_status(operacion),
        "status": operacion.get_estado_display(),
        "price": currency(operacion.precio_total),
        "startDate": date_label(operacion.fecha_inicio),
        "endDate": date_label(operacion.fecha_final),
        "zonaGeneral": operacion.zona_general or "Sin especificar",
        "zonaEspecifica": operacion.zona_especifica or "Sin especificar",
        "detallesOperacion": operacion.detalles_op or "Sin detalles registrados.",
        "recomendaciones": operacion.recomendaciones or "Sin recomendaciones registradas.",
        "medicalRecordDate": date_label(ficha.fecha_ficha) if ficha else "Sin ficha registrada",
        "medicalRecordReason": ficha.motivo_consulta if ficha and ficha.motivo_consulta else "Sin motivo registrado.",
        "medicalRecordNotes": ficha.observaciones if ficha and ficha.observaciones else "Sin observaciones registradas.",
        "documentPdfUrl": document_url,
        "documentPdfName": document_name,
        "hasBiometricEnrollment": bool(huella and huella.activo),
        "biometricMockTemplate": "" if settings.BIOMETRIC_SUSPENDED else (huella.template_biometrico if huella and huella.proveedor == HuellaBiometricaCliente.Proveedor.MOCK_LEGACY else ""),
        "appointments": [
            {
                "id": f"CIT-{cita.pk:04d}",
                "rawId": cita.pk,
                "dateTime": _datetime_label(cita.fecha_hora),
                "specialist": "Sin asignar",
                "status": cita.get_estado_display(),
                "biometricStatus": _appointment_biometric_status(cita),
                "canConfirmBiometric": (not settings.BIOMETRIC_SUSPENDED) and cita.estado in {
                    CitaMedica.Estado.PROGRAMADA,
                    CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
                },
                "canManage": cita.estado == CitaMedica.Estado.PROGRAMADA,

            }
            for cita in operacion.citas_medicas.all()
        ],
        "quotas": quotas_payload,
    }


def _prospect_item(prospecto):
    active_appointment = next(
        (
            cita
            for cita in prospecto.citas_medicas.all()
            if cita.estado == CitaProspecto.Estado.PROGRAMADA
        ),
        None,
    )
    citas = prospecto.citas_medicas.order_by("-fecha_hora").all()
    return {
        "id": f"PRO-{prospecto.pk:04d}",
        "rawId": prospecto.pk,
        "name": str(prospecto),
        "firstName": prospecto.primer_nombre,
        "lastName": prospecto.apellido_paterno,
        "primerNombre": prospecto.primer_nombre,
        "segundoNombre": prospecto.segundo_nombre,
        "apellidoPaterno": prospecto.apellido_paterno,
        "apellidoMaterno": prospecto.apellido_materno,
        "phone": prospecto.telefono or "Sin teléfono",
        "interest": _prospect_interest(prospecto),
        "registeredBy": full_name(prospecto.registrado_por),
        "stage": _prospect_stage(prospecto),
        "state": prospecto.get_estado_display(),
        "stateValue": prospecto.estado,
        "observations": prospecto.observaciones,
        "createdAt": _datetime_label(prospecto.created_at),
        "convertedAt": _datetime_label(prospecto.fecha_conversion) if prospecto.fecha_conversion else "-",
        "medicalAppointments": [_prospect_appointment_item(c) for c in citas],
    }


def _prospect_appointment_item(appointment):
    if not appointment:
        return None
    return {
        "id": f"CPR-{appointment.pk:04d}",
        "rawId": appointment.pk,
        "prospectRawId": appointment.prospecto_id,
        "dateTime": _datetime_label(appointment.fecha_hora),
        "specialist": "Sin asignar",
        "service": appointment.servicio_config.tipo_servicio.tipo,
        "status": appointment.get_estado_display(),
        "statusValue": appointment.estado,
        "statusTone": (
            "approved" if appointment.estado == CitaProspecto.Estado.PROGRAMADA
            else "danger" if appointment.estado == CitaProspecto.Estado.CANCELADA
            else "observed"
        ),
        "canCancel": appointment.estado == CitaProspecto.Estado.PROGRAMADA and appointment.fecha_hora > timezone.now(),
    }


def _free_client_appointment_item(appointment):
    if not appointment:
        return None
    return {
        "id": f"CLI-CIT-{appointment.pk:04d}",
        "rawId": appointment.pk,
        "operationRawId": None,
        "operation": "Cita medica libre",
        "specialist": "Sin asignar",
        "dateTime": _datetime_label(appointment.fecha_hora),
        "status": appointment.get_estado_display(),
        "statusTone": (
            "danger"
            if appointment.estado == CitaClienteLibre.Estado.CANCELADA
            else "observed"
            if appointment.estado == CitaClienteLibre.Estado.NO_ASISTIO
            else "pending"
        ),
        "biometric": "No aplica",
        "details": appointment.detalles_cita or "Cita medica libre sin tratamiento asociado.",
        "canManage": False,
        "canMarkPendingBiometric": False,
        "canConfirmBiometric": False,
        "biometricMockTemplate": "",
        "isFreeMedicalAppointment": True,
    }


def _medical_appointment_service_config():
    queryset = ServicioConfig.objects.select_related("tipo_servicio").filter(
        activo=True,
        proc_estetico__isnull=True,
    )
    preferred = queryset.filter(
        Q(tipo_servicio__tipo__icontains="cita")
        | Q(tipo_servicio__tipo__icontains="consulta")
        | Q(tipo_servicio__tipo__icontains="medica")
        | Q(tipo_servicio__tipo__icontains="médica")
    ).order_by("tipo_servicio__orden", "tipo_servicio__tipo", "pk").first()
    return preferred or queryset.order_by("tipo_servicio__orden", "tipo_servicio__tipo", "pk").first()


def _build_prospect_medical_slot_map(service_config, branch_id=1):
    from operations.scheduling import get_available_dates
    
    today = timezone.localdate()
    window_start = today
    window_end = today + timedelta(days=34)
    
    available_dates_set = get_available_dates(branch_id, window_start, window_end)
    available_dates = []
    
    # Format the response
    for i in range(35):
        current_date = window_start + timedelta(days=i)
        if current_date in available_dates_set:
            available_dates.append(
                {
                    "date": current_date.isoformat(),
                    "label": current_date.strftime("%d/%m"),
                    "slotCount": 1, # Indication that it is available
                    "weekday": current_date.strftime("%A").capitalize(),
                }
            )

    return {
        "windowStart": window_start.isoformat(),
        "windowEnd": window_end.isoformat(),
        "monthLabel": window_start.strftime("%B %Y").capitalize(),
        "availableDates": available_dates,
        "slotsByDate": {},
        "slotCount": len(available_dates),
    }


def _client_item(cliente):
    cliente.actualizar_estado_automaticamente()
    analisis = next(iter(cliente.analisis_esteticos.all()), None)
    huella = getattr(cliente, "huella_biometrica", None)
    scheduled_appointments = []
    for operacion in cliente.operaciones.all():
        for cita in operacion.citas_medicas.all():
            if cita.estado != CitaMedica.Estado.PROGRAMADA:
                continue
            scheduled_appointments.append(
                {
                    "id": f"CIT-{cita.pk:04d}",
                    "rawId": cita.pk,
                    "_sortDate": cita.fecha_hora,
                    "dateTime": _datetime_label(cita.fecha_hora),
                    "operation": procedure_name(operacion),
                    "specialist": "Sin asignar",
                    "status": cita.get_estado_display(),
                }
            )

    scheduled_appointments.sort(key=lambda item: item["_sortDate"])
    for appointment in scheduled_appointments:
        appointment.pop("_sortDate", None)
    return {
        "id": f"CLI-{cliente.pk:04d}",
        "rawId": cliente.pk,
        "name": full_name(cliente.usuario),
        "phone": cliente.telefono or "Sin teléfono",
        "ci": cliente.ci or "Sin CI",
        "email": cliente.usuario.email or "",
        "clienteCodigo": cliente.cliente_codigo,
        "status": cliente.get_estado_cliente_display(),
        "activeOperations": cliente.operaciones.filter(estado=Operacion.Estado.EN_PROCESO).count(),
        "totalOperations": cliente.operaciones.count(),
        "lastAnalysis": date_label(analisis.fecha_analisis) if analisis else "Sin analisis",
        "scheduledAppointments": scheduled_appointments[:1],
        "hasBiometricEnrollment": bool(huella and huella.activo),
    }


def _admin_client_queryset():
    mark_expired_programmed_appointments_as_no_show()
    return (
        Cliente.objects.select_related("usuario")
        .prefetch_related(
            Prefetch(
                "operaciones",
                queryset=Operacion.objects.select_related(
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
                            Prefetch(
                                "pagos_realizados",
                                queryset=PagoRealizado.objects.select_related("verificado_por").order_by("-created_at"),
                            )
                        ).order_by("nro_cuota"),
                    ),
                ).order_by("-created_at"),
            ),
            "analisis_esteticos",
            Prefetch(
                "citas_medicas_libres",
                queryset=CitaClienteLibre.objects.select_related().order_by("fecha_hora"),
            ),
        )
    )


def _admin_client_detail(cliente):
    operations = list(cliente.operaciones.all())
    appointments = [
        cita
        for operacion in operations
        for cita in operacion.citas_medicas.all()
    ]
    free_appointments = list(cliente.citas_medicas_libres.all())
    quotas = [
        cuota
        for operacion in operations
        for cuota in operacion.cuotas_plan_pagos.all()
    ]
    payments = [
        pago
        for cuota in quotas
        for pago in cuota.pagos_realizados.all()
    ]
    pending_quotas = [
        cuota
        for cuota in quotas
        if cuota.estado != CuotaPlanPago.Estado.PAGADO
        and cuota.operacion.estado == Operacion.Estado.EN_PROCESO
    ]
    completed_sessions = [
        cita
        for cita in appointments
        if cita.estado == CitaMedica.Estado.CONFIRMADA and cita.verif_biometria
    ]
    upcoming_appointments = [
        cita
        for cita in appointments
        if cita.estado == CitaMedica.Estado.PROGRAMADA and cita.fecha_hora >= timezone.now()
    ]

    return {
        "client": _client_item(cliente),
        "metrics": [
            metric(
                "admin-client-appointments",
                "Citas reservadas",
                len(appointments),
                f"{len(upcoming_appointments)} próxima(s)",
                "primary",
            ),
            metric(
                "admin-client-sessions",
                "Sesiones realizadas",
                len(appointments),
                "Todas las sesiones",
                "success",
            ),
            metric(
                "admin-client-payments",
                "Pagos realizados",
                len(payments),
                f"{len([p for p in payments if p.estado_verificacion == PagoRealizado.EstadoVerificacion.PENDIENTE])} en revisión",
                "warning",
            ),
            metric(
                "admin-client-pending-quotas",
                "Pagos pendientes",
                len(pending_quotas),
                "Cuotas aun no pagadas",
                "danger",
            ),
        ],
        "operations": [_client_operation_item(operacion) for operacion in operations],
        "appointments": [
            *[_client_appointment_item(cita) for cita in sorted(appointments, key=lambda item: item.fecha_hora)],
            *[_free_client_appointment_item(cita) for cita in sorted(free_appointments, key=lambda item: item.fecha_hora)],
        ],
        "sessions": [
            *[_client_appointment_item(cita) for cita in sorted(appointments, key=lambda item: item.fecha_hora)],
            *[_free_client_appointment_item(cita) for cita in sorted(free_appointments, key=lambda item: item.fecha_hora)],
        ],
        "payments": [_client_payment_item(payment) for payment in sorted(payments, key=lambda item: item.created_at, reverse=True)],
        "pendingQuotas": [_client_quota_item(cuota) for cuota in sorted(pending_quotas, key=lambda item: (item.fecha_vencimiento, item.nro_cuota))],
    }


def _payment_item(payment):
    operacion = payment.cuota.operacion
    return {
        "id": f"PAY-{payment.pk:04d}",
        "rawId": payment.pk,
        "patient": full_name(operacion.paciente.usuario),
        "operation": procedure_name(operacion),
        "amount": currency(payment.monto_pagado),
        "submittedAt": _datetime_label(payment.created_at),
        "bank": "Transferencia",
        "status": _payment_status(payment),
        "quota": f"Cuota {payment.cuota.nro_cuota}",
        "dueDate": date_label(payment.cuota.fecha_vencimiento),
        "verifier": full_name(payment.verificado_por) if payment.verificado_por else "Sin revisar",
        "receiptUrl": payment.comprobante_url.url if payment.comprobante_url else "",
        "note": payment.observacion_verificacion or payment.detalles_pago or "",
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


def _admin_quota_item(cuota):
    operacion = cuota.operacion
    return {
        "id": f"CUO-{cuota.pk:04d}",
        "rawId": cuota.pk,
        "patient": full_name(operacion.paciente.usuario),
        "operation": procedure_name(operacion),
        "quotaNumber": cuota.nro_cuota,
        "amount": currency(_quota_programmed_amount(cuota)),
        "dueDate": date_label(cuota.fecha_vencimiento),
        "status": _quota_display_status(cuota),
        "paymentsCount": cuota.pagos_realizados.count(),
    }


def _expense_category_item(category):
    return {
        "id": category.pk,
        "name": category.nombre,
        "description": category.descripcion,
    }


def _expense_categories_queryset(*, active_only=False):
    queryset = CategoriaGasto.objects.all()
    if active_only:
        queryset = queryset.filter(activo=True)
    return queryset.order_by(
        models.Case(
            models.When(nombre__iexact="Otros", then=0),
            default=1,
            output_field=models.IntegerField(),
        ),
        "nombre",
    )


def _expense_item(expense):
    return {
        "id": f"GAS-{expense.pk:04d}",
        "rawId": expense.pk,
        "date": expense.fecha.isoformat(),
        "dateLabel": date_label(expense.fecha),
        "categoryId": expense.categoria_id,
        "category": expense.categoria.nombre,
        "concept": expense.concepto,
        "units": str(expense.unidades),
        "unitCost": str(expense.costo_unidad),
        "total": str(expense.gasto_total),
        "totalLabel": currency(expense.gasto_total),
        "provider": expense.proveedor,
        "invoiceUrl": expense.factura.url if expense.factura else "",
        "invoiceName": PurePosixPath(expense.factura.name).name if expense.factura else "",
        "details": expense.detalles,
        "branchId": expense.sucursal_id,
        "branchName": expense.sucursal.nombre,
        "registeredBy": full_name(expense.registrado_por) if expense.registrado_por else "Sin registrar",
    }


def _parse_expense_payload(request, *, instance=None):
    errors = {}

    def text_value(field_name):
        return (request.POST.get(field_name) or "").strip()

    def decimal_value(field_name, *, required=False, minimum=Decimal("0")):
        raw = request.POST.get(field_name)
        if raw in (None, ""):
            if required:
                errors[field_name] = "Este campo es obligatorio."
            return None
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError):
            errors[field_name] = "Debes enviar un numero valido."
            return None
        if value < minimum:
            errors[field_name] = f"El valor minimo permitido es {minimum}."
            return None
        return value

    raw_date = text_value("date")
    expense_date = None
    if not raw_date:
        errors["date"] = "La fecha es obligatoria."
    else:
        try:
            expense_date = date.fromisoformat(raw_date)
        except ValueError:
            errors["date"] = "Debes enviar una fecha valida."

    raw_category_id = text_value("categoryId")
    category = None
    if not raw_category_id:
        errors["categoryId"] = "La categoria es obligatoria."
    else:
        try:
            category_id = int(raw_category_id)
        except ValueError:
            errors["categoryId"] = "Selecciona una categoria valida."
        else:
            category = CategoriaGasto.objects.filter(pk=category_id, activo=True).first()
            if not category:
                errors["categoryId"] = "Selecciona una categoria activa."

    concept = text_value("concept")
    if not concept:
        errors["concept"] = "El concepto es obligatorio."

    units = decimal_value("units", required=True)
    unit_cost = decimal_value("unitCost", required=True)
    total = decimal_value("total", required=True)

    if errors:
        raise ValidationError(errors)

    expense = instance or GastoSucursal()
    expense.fecha = expense_date
    expense.categoria = category
    expense.concepto = concept
    expense.unidades = units
    expense.costo_unidad = unit_cost
    expense.gasto_total = total
    expense.proveedor = text_value("provider")
    expense.detalles = text_value("details")
    invoice_file = request.FILES.get("invoice")
    if invoice_file:
        expense.factura = invoice_file
    return expense


def _catalog_item(identifier, name, count, note):
    return {
        "id": identifier,
        "name": name,
        "count": count,
        "note": note,
    }


def _catalog_field(
    name,
    label,
    input_type,
    *,
    required=False,
    options=None,
    placeholder="",
    hint="",
    value_type="string",
    allow_empty=False,
    min_value=None,
):
    payload = {
        "name": name,
        "label": label,
        "inputType": input_type,
        "required": required,
        "placeholder": placeholder,
        "hint": hint,
        "valueType": value_type,
        "allowEmpty": allow_empty,
    }
    if options is not None:
        payload["options"] = options
    if min_value is not None:
        payload["minValue"] = min_value
    return payload


def _catalog_option(value, label, secondary_label=""):
    payload = {"value": value, "label": label}
    if secondary_label:
        payload["secondaryLabel"] = secondary_label
    return payload


def _catalog_entry(item_id, title, subtitle, active, metadata, values):
    return {
        "id": item_id,
        "title": title,
        "subtitle": subtitle,
        "active": active,
        "activeLabel": "Activo" if active else "Inactivo",
        "metadata": metadata,
        "values": values,
    }


def _catalog_metric_set(active_count, inactive_count, total_count, relation_label):
    return [
        metric("catalog-active", "Activos", active_count, "Visibles para nuevas operaciones", "success"),
        metric("catalog-inactive", "Inactivos", inactive_count, "Preservados para historico y reactivación", "warning"),
        metric("catalog-total", "Total", total_count, relation_label, "primary"),
    ]


def _catalog_key_to_slug(catalog_key):
    if catalog_key in {
        "todos-los-servicios",
        "procedimientos-esteticos",
        "tipos-servicio",
        "tipos-procedimiento",
        "campos-ficha",
        "patologias-cutaneas",
        "especialidades",
        "grupos-opciones",
        "categorias-gasto",
        "sectores",
        "secciones-ficha",
    }:
        return catalog_key
    raise KeyError(catalog_key)


def _catalog_summary_descriptor():
    return [
        {
            "key": "todos-los-servicios",
            "title": "Todos los servicios",
            "description": "Configuraciones completas de servicio con su precio base y procedimiento asociado.",
        },
        {
            "key": "procedimientos-esteticos",
            "title": "Procedimientos estéticos",
            "description": "Catálogo operativo de procedimientos disponibles para las ventas y fichas clínicas.",
        },
        {
            "key": "tipos-servicio",
            "title": "Tipos de servicio",
            "description": "Categorias comerciales utilizadas al crear configuraciones de servicio y operaciones.",
        },
        {
            "key": "tipos-procedimiento",
            "title": "Tipos de procedimiento",
            "description": "Tipos de procedimiento estético disponibles para asociar a los procedimientos.",
        },
        {
            "key": "campos-ficha",
            "title": "Campos de ficha",
            "description": "Preguntas configurables por procedimiento dentro de la ficha clínica.",
        },
        {
            "key": "patologias-cutaneas",
            "title": "Patologías cutaneas",
            "description": "Catálogo de patologías usado en el análisis estético del paciente.",
        },
        {
            "key": "especialidades",
            "title": "Especialidades",
            "description": "Especialidades disponibles para especialistas y asignación de agenda.",
        },
        {
            "key": "grupos-opciones",
            "title": "Grupos de opciones",
            "description": "Grupos reutilizables para respuestas de selección única o múltiple.",
        },
        {
            "key": "categorias-gasto",
            "title": "Categorías de gasto",
            "description": "Categorías administrativas usadas al registrar gastos de sucursal.",
        },
        {
            "key": "sectores",
            "title": "Sectores",
            "description": "Sectores especializados que agrupan secciones de ficha clínica por ámbito (depilación, manchas, tatuajes).",
        },
        {
            "key": "secciones-ficha",
            "title": "Secciones de ficha",
            "description": "Secciones de ficha clínica que agrupan campos configurables por sector o procedimiento estético.",
        },
    ]


def _catalog_page_data(catalog_key, q="", active="all", **filters):
    catalog_key = _catalog_key_to_slug(catalog_key)

    if catalog_key == "todos-los-servicios":
        unfiltered = ServicioConfig.objects.all()
        base_queryset = unfiltered.select_related(
            "tipo_servicio",
            "proc_estetico",
            "proc_estetico__tipo_p_estetico",
            "sector",
        )
        if q:
            base_queryset = base_queryset.filter(
                Q(tipo_servicio__tipo__icontains=q) | Q(proc_estetico__proceso__icontains=q)
            )
        if active == "true":
            base_queryset = base_queryset.filter(activo=True)
        elif active == "false":
            base_queryset = base_queryset.filter(activo=False)
        queryset = base_queryset.order_by("tipo_servicio__tipo", "proc_estetico__proceso", "pk")
        # Metrics always reflect the unfiltered catalog so the header shows real totals.
        active_count = unfiltered.filter(activo=True).count()
        total_count = unfiltered.count()
        items = [
            _catalog_entry(
                item.pk,
                str(item),
                f"Precio base: {currency(item.precio_base)}",
                item.activo,
                [
                    {"label": "Tipo de servicio", "value": item.tipo_servicio.tipo},
                    {
                        "label": "Procedimiento",
                        "value": item.proc_estetico.proceso if item.proc_estetico else "Sín procedimiento",
                    },
                    {
                        "label": "Tipo de procedimiento",
                        "value": item.proc_estetico.tipo_p_estetico.tipo if item.proc_estetico else "No aplica",
                    },
                    {
                        "label": "Sector",
                        "value": item.sector.nombre if item.sector else "Sin sector",
                    },
                    {
                        "label": "Operaciones vinculadas",
                        "value": str(item.operaciones.count()),
                    },
                ],
                {
                    "serviceTypeId": item.tipo_servicio_id,
                    "procedureId": item.proc_estetico_id,
                    "basePrice": str(item.precio_base),
                    "sectorId": item.sector_id,
                },
            )
            for item in queryset
        ]
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Todos los servicios",
                "description": "Administra cada servicio disponible con su precio base y el procedimiento estético asociado.",
                "createLabel": "Crear servicio",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{Operacion.objects.count()} operacion(es) usan este catálogo",
            ),
            "fields": [
                _catalog_field(
                    "serviceTypeId",
                    "Tipo de servicio",
                    "select",
                    required=True,
                    value_type="number",
                    options=[
                        _catalog_option(tipo.pk, tipo.tipo)
                        for tipo in TipoServicio.objects.filter(activo=True).order_by("orden", "tipo")
                    ],
                ),
                _catalog_field(
                    "procedureId",
                    "Procedimiento estético",
                    "select",
                    value_type="number",
                    allow_empty=True,
                    options=[
                        _catalog_option(
                            procedimiento.pk,
                            procedimiento.proceso,
                            secondary_label=procedimiento.tipo_p_estetico.tipo,
                        )
                        for procedimiento in ProcEstetico.objects.select_related("tipo_p_estetico")
                        .filter(activo=True)
                        .order_by("tipo_p_estetico__tipo", "orden", "proceso")
                    ],
                    hint="Deja este campo vacío para servicios generales como la cita de consulta.",
                ),
                _catalog_field(
                    "sectorId",
                    "Sector de ficha médica",
                    "select",
                    value_type="number",
                    allow_empty=True,
                    options=[
                        _catalog_option(
                            sector.pk,
                            sector.nombre,
                            secondary_label=sector.codigo,
                        )
                        for sector in Sector.objects.filter(activo=True).order_by("orden", "nombre")
                    ],
                    hint=(
                        "Sin sector: el servicio no mostrará ficha médica en la conversión."
                        " Si elegiste un procedimiento estético, asegúrate de asignar un sector."
                    ),
                ),
                _catalog_field(
                    "basePrice",
                    "Precio base",
                    "number",
                    required=True,
                    value_type="number",
                    min_value=0,
                ),
            ],
            "items": items,
        }

    if catalog_key == "procedimientos-esteticos":
        unfiltered = ProcEstetico.objects.all()
        base_queryset = unfiltered.select_related("tipo_p_estetico")
        if q:
            base_queryset = base_queryset.filter(proceso__icontains=q)
        if active == "true":
            base_queryset = base_queryset.filter(activo=True)
        elif active == "false":
            base_queryset = base_queryset.filter(activo=False)
        queryset = base_queryset.order_by("orden", "proceso")
        items = [
            _catalog_entry(
                item.pk,
                item.proceso,
                f"Tipo: {item.tipo_p_estetico.tipo}",
                item.activo,
                [
                    {"label": "Descripción", "value": item.descripcion or "Sin descripción"},
                    {
                        "label": "Servicios vinculados",
                        "value": str(item.servicios_config.count()),
                    },
                ],
                {
                    "procedureTypeId": item.tipo_p_estetico_id,
                    "name": item.proceso,
                    "description": item.descripcion,
                },
            )
            for item in queryset
        ]
        # Metrics reflect the unfiltered catalog so the header shows real totals.
        active_count = unfiltered.filter(activo=True).count()
        total_count = unfiltered.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Procedimientos estéticos",
                "description": "Crea, edita y desactiva procedimientos especificos que luego pueden vincularse a servicios.",
                "createLabel": "Crear procedimiento",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{ServicioConfig.objects.filter(proc_estetico__isnull=False).count()} configuracion(es) de servicio vinculadas",
            ),
            "fields": [
                _catalog_field(
                    "procedureTypeId",
                    "Tipo de procedimiento",
                    "select",
                    required=True,
                    value_type="number",
                    options=[
                        _catalog_option(tipo.pk, tipo.tipo)
                        for tipo in ProcEsteticosTipo.objects.filter(activo=True).order_by("orden", "tipo")
                    ],
                ),
                _catalog_field("name", "Procedimiento", "text", required=True, placeholder="Ej. Borrado de tatuajes"),
                _catalog_field("description", "Descripción", "textarea", placeholder="Notas internas del procedimiento"),
            ],
            "items": items,
        }

    if catalog_key == "tipos-servicio":
        unfiltered = TipoServicio.objects.all()
        base_queryset = unfiltered
        if q:
            base_queryset = base_queryset.filter(tipo__icontains=q)
        if active == "true":
            base_queryset = base_queryset.filter(activo=True)
        elif active == "false":
            base_queryset = base_queryset.filter(activo=False)
        queryset = base_queryset.order_by("orden", "tipo")
        items = [
            _catalog_entry(
                item.pk,
                item.tipo,
                "Base comercial del servicio",
                item.activo,
                [
                    {"label": "Descripción", "value": item.descripcion or "Sin descripción"},
                    {
                        "label": "Configuraciones activas",
                        "value": str(item.servicios_config.filter(activo=True).count()),
                    },
                ],
                {
                    "name": item.tipo,
                    "description": item.descripcion,
                },
            )
            for item in queryset
        ]
        # Metrics reflect the unfiltered catalog so the header shows real totals.
        active_count = unfiltered.filter(activo=True).count()
        total_count = unfiltered.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Tipos de servicio",
                "description": "Administra las categorías comerciales que se usan al vender tratamientos y consultas.",
                "createLabel": "Crear tipo de servicio",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{ServicioConfig.objects.filter(activo=True).count()} configuracion(es) de servicio activas",
            ),
            "fields": [
                _catalog_field("name", "Tipo de servicio", "text", required=True, placeholder="Ej. Cita de consulta"),
                _catalog_field("description", "Descripción", "textarea", placeholder="Notas internas del tipo de servicio"),
            ],
            "items": items,
        }

    if catalog_key == "tipos-procedimiento":
        unfiltered = ProcEsteticosTipo.objects.all()
        base_queryset = unfiltered
        if q:
            base_queryset = base_queryset.filter(tipo__icontains=q)
        if active == "true":
            base_queryset = base_queryset.filter(activo=True)
        elif active == "false":
            base_queryset = base_queryset.filter(activo=False)
        queryset = base_queryset.order_by("orden", "tipo")
        items = [
            _catalog_entry(
                item.pk,
                item.tipo,
                "Tipo de procedimiento estetico",
                item.activo,
                [
                    {"label": "Descripcion", "value": item.descripcion or "Sin descripcion"},
                    {
                        "label": "Procedimientos vinculados",
                        "value": str(item.procedimientos.count()),
                    },
                ],
                {
                    "name": item.tipo,
                    "description": item.descripcion,
                    "order": item.orden,
                },
            )
            for item in queryset
        ]
        # Metrics reflect the unfiltered catalog so the header shows real totals.
        active_count = unfiltered.filter(activo=True).count()
        total_count = unfiltered.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Tipos de procedimiento",
                "description": "Administra los tipos de procedimiento estetico disponibles para asociar a los procedimientos.",
                "createLabel": "Crear tipo de procedimiento",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{ProcEstetico.objects.filter(activo=True).count()} procedimiento(s) activo(s)",
            ),
            "fields": [
                _catalog_field("name", "Tipo de procedimiento", "text", required=True, placeholder="Ej. Laser"),
                _catalog_field("description", "Descripcion", "textarea", placeholder="Notas internas"),
            ],
            "items": items,
        }

    if catalog_key == "campos-ficha":
        unfiltered = FichaCampo.objects.all()
        base_queryset = unfiltered.select_related("seccion__proc_estetico", "grupo_opciones")
        if q:
            base_queryset = base_queryset.filter(
                Q(etiqueta__icontains=q) | Q(codigo__icontains=q)
            )
        if active == "true":
            base_queryset = base_queryset.filter(activo=True)
        elif active == "false":
            base_queryset = base_queryset.filter(activo=False)
        queryset = base_queryset.order_by(
            "seccion__proc_estetico__proceso", "seccion__orden", "orden", "etiqueta"
        )
        items = [
            _catalog_entry(
                item.pk,
                item.etiqueta,
                f"{item.seccion.proc_estetico.proceso} · {item.seccion.nombre}",
                item.activo,
                [
                    {"label": "Código", "value": item.codigo},
                    {"label": "Tipo", "value": item.get_tipo_campo_display()},
                    {
                        "label": "Grupo de opciones",
                        "value": item.grupo_opciones.nombre if item.grupo_opciones else "Sin grupo",
                    },
                    {"label": "Requerido", "value": "Si" if item.requerido else "No"},
                    {"label": "Detalle", "value": "Permitido" if item.permite_detalle else "No"},
                ],
                {
                    "sectionId": item.seccion_id,
                    "code": item.codigo,
                    "label": item.etiqueta,
                    "fieldType": item.tipo_campo,
                    "optionGroupId": item.grupo_opciones_id,
                    "isMultiple": item.es_multiple,
                    "allowsDetail": item.permite_detalle,
                    "required": item.requerido,
                },
            )
            for item in queryset
        ]
        # Metrics reflect the unfiltered catalog so the header shows real totals.
        active_count = unfiltered.filter(activo=True).count()
        total_count = unfiltered.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Campos de ficha",
                "description": "Gestiona las preguntas configurables que aparecen en las fichas clinicas por procedimiento.",
                "createLabel": "Crear campo de ficha",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{FichaSeccion.objects.filter(activo=True).count()} seccion(es) disponibles",
            ),
            "fields": [
                _catalog_field(
                    "sectionId",
                    "Seccion",
                    "select",
                    required=True,
                    value_type="number",
                    options=[
                        _catalog_option(
                            seccion.pk,
                            seccion.nombre,
                            secondary_label=seccion.proc_estetico.proceso,
                        )
                        for seccion in FichaSeccion.objects.select_related("proc_estetico").filter(activo=True).order_by(
                            "proc_estetico__proceso",
                            "orden",
                            "nombre",
                        )
                    ],
                ),
                _catalog_field("code", "Codigo interno", "text", required=True, placeholder="Ej. BRONCEADO"),
                _catalog_field("label", "Etiqueta visible", "text", required=True, placeholder="Ej. Bronceado reciente"),
                _catalog_field(
                    "fieldType",
                    "Tipo de campo",
                    "select",
                    required=True,
                    options=[
                        _catalog_option(choice_value, choice_label)
                        for choice_value, choice_label in FichaCampo.TipoCampo.choices
                    ],
                ),
                _catalog_field(
                    "optionGroupId",
                    "Grupo de opciones",
                    "select",
                    value_type="number",
                    allow_empty=True,
                    options=[
                        _catalog_option(grupo.pk, grupo.nombre, secondary_label=grupo.codigo)
                        for grupo in GrupoOpciones.objects.order_by("nombre")
                    ],
                    hint="Solo aplica a campos de seleccion.",
                ),
                _catalog_field("isMultiple", "Permite multiples respuestas", "checkbox", value_type="boolean"),
                _catalog_field("allowsDetail", "Permite detalle adicional", "checkbox", value_type="boolean"),
                _catalog_field("required", "Campo obligatorio", "checkbox", value_type="boolean"),
            ],
            "items": items,
        }

    if catalog_key == "patologias-cutaneas":
        unfiltered = PatologiaCutanea.objects.all()
        base_queryset = unfiltered
        if q:
            base_queryset = base_queryset.filter(nombre__icontains=q)
        if active == "true":
            base_queryset = base_queryset.filter(activo=True)
        elif active == "false":
            base_queryset = base_queryset.filter(activo=False)
        queryset = base_queryset.order_by("orden", "nombre")
        items = [
            _catalog_entry(
                item.pk,
                item.nombre,
                "Catálogo clínico",
                item.activo,
                [
                    {"label": "Descripción", "value": item.descripcion or "Sin descripción"},
                ],
                {
                    "name": item.nombre,
                    "description": item.descripcion,
                },
            )
            for item in queryset
        ]
        # Metrics reflect the unfiltered catalog so the header shows real totals.
        active_count = unfiltered.filter(activo=True).count()
        total_count = unfiltered.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Patologias cutaneas",
                "description": "Administra las patologias disponibles para el análisis estético y sus reportes.",
                "createLabel": "Crear patología cutanea",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                "Utilizadas en análisis estéticos históricos",
            ),
            "fields": [
                _catalog_field("name", "Patología cutanea", "text", required=True, placeholder="Ej. Rosacea"),
                _catalog_field("description", "Descripción", "textarea", placeholder="Notas internas o alcance"),
            ],
            "items": items,
        }

    if catalog_key == "especialidades":
        unfiltered = Especialidad.objects.all()
        base_queryset = unfiltered
        if q:
            base_queryset = base_queryset.filter(nombre__icontains=q)
        if active == "true":
            base_queryset = base_queryset.filter(activo=True)
        elif active == "false":
            base_queryset = base_queryset.filter(activo=False)
        queryset = base_queryset.order_by("orden", "nombre")
        items = [
            _catalog_entry(
                item.pk,
                item.nombre,
                "Especialidad del equipo",
                item.activo,
                [
                    {"label": "Descripción", "value": item.descripcion or "Sin descripción"},
                    {
                        "label": "Especialistas vinculados",
                        "value": str(item.especialistas_rel.count()),
                    },
                ],
                {
                    "name": item.nombre,
                    "description": item.descripcion,
                },
            )
            for item in queryset
        ]
        # Metrics reflect the unfiltered catalog so the header shows real totals.
        active_count = unfiltered.filter(activo=True).count()
        total_count = unfiltered.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Especialidades",
                "description": "Administra las especialidades disponibles para asignar al equipo médico y técnico.",
                "createLabel": "Crear especialidad",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{Especialista.objects.count()} especialista(s) registrados",
            ),
            "fields": [
                _catalog_field("name", "Especialidad", "text", required=True, placeholder="Ej. Laser terapéutico"),
                _catalog_field("description", "Descripción", "textarea", placeholder="Notas internas sobre la especialidad"),
            ],
            "items": items,
        }

    if catalog_key == "grupos-opciones":
        unfiltered = GrupoOpciones.objects.all()
        base_queryset = unfiltered.prefetch_related("opciones")
        if q:
            base_queryset = base_queryset.filter(
                Q(nombre__icontains=q) | Q(codigo__icontains=q)
            )
        if active == "true":
            base_queryset = base_queryset.filter(activo=True)
        elif active == "false":
            base_queryset = base_queryset.filter(activo=False)
        queryset = base_queryset.order_by("nombre")
        items = [
            _catalog_entry(
                item.pk,
                item.nombre,
                item.codigo,
                item.activo,
                [
                    {"label": "Descripción", "value": item.descripcion or "Sin descripción"},
                    {"label": "Opciones activas", "value": str(item.opciones.filter(activo=True).count())},
                    {"label": "Opciones totales", "value": str(item.opciones.count())},
                ],
                {
                    "code": item.codigo,
                    "name": item.nombre,
                    "description": item.descripcion,
                },
            )
            for item in queryset
        ]
        # Metrics reflect the unfiltered catalog so the header shows real totals.
        active_count = unfiltered.filter(activo=True).count()
        total_count = unfiltered.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Grupos de opciones",
                "description": "Agrupa respuestas reutilizables para campos de ficha y otros formularios dinámicos.",
                "createLabel": "Crear grupo de opciones",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{OpcionCatalogo.objects.filter(activo=True).count()} opcion(es) activas asociadas",
            ),
            "fields": [
                _catalog_field("code", "Código", "text", required=True, placeholder="Ej. SI_NO"),
                _catalog_field("name", "Nombre", "text", required=True, placeholder="Ej. Si / No"),
                _catalog_field("description", "Descripción", "textarea", placeholder="Describe el uso del grupo"),
            ],
            "items": items,
        }

    if catalog_key == "categorias-gasto":
        unfiltered = CategoriaGasto.objects.all()
        base_queryset = unfiltered
        if q:
            base_queryset = base_queryset.filter(nombre__icontains=q)
        if active == "true":
            base_queryset = base_queryset.filter(activo=True)
        elif active == "false":
            base_queryset = base_queryset.filter(activo=False)
        queryset = base_queryset.order_by(
            models.Case(
                models.When(nombre__iexact="Otros", then=0),
                default=1,
                output_field=models.IntegerField(),
            ),
            "nombre",
        )
        items = [
            _catalog_entry(
                item.pk,
                item.nombre,
                "Categoría administrativa de gasto",
                item.activo,
                [
                    {"label": "Descripción", "value": item.descripcion or "Sin descripción"},
                    {"label": "Gastos vinculados", "value": str(item.gastos.count())},
                ],
                {
                    "name": item.nombre,
                    "description": item.descripcion,
                },
            )
            for item in queryset
        ]
        # Metrics reflect the unfiltered catalog so the header shows real totals.
        active_count = unfiltered.filter(activo=True).count()
        total_count = unfiltered.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Categorias de gasto",
                "description": "Administra las categorias disponibles para clasificar gastos de sucursal.",
                "createLabel": "Crear categoria",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{GastoSucursal.objects.count()} gasto(s) registrados",
            ),
            "fields": [
                _catalog_field("name", "Categoría", "text", required=True, placeholder="Ej. Insumos"),
                _catalog_field("description", "Descripción", "textarea", placeholder="Notas internas o alcance"),
            ],
            "items": items,
        }

    if catalog_key == "sectores":
        unfiltered = Sector.objects.all()
        base_queryset = unfiltered
        if q:
            base_queryset = base_queryset.filter(
                Q(nombre__icontains=q) | Q(codigo__icontains=q)
            )
        if active == "true":
            base_queryset = base_queryset.filter(activo=True)
        elif active == "false":
            base_queryset = base_queryset.filter(activo=False)
        queryset = base_queryset.order_by("orden", "nombre")
        items = [
            _catalog_entry(
                item.pk,
                item.nombre,
                item.codigo,
                item.activo,
                [
                    {"label": "Código", "value": item.codigo},
                    {"label": "Descripción", "value": item.descripcion or "Sin descripción"},
                    {
                        "label": "Servicios vinculados",
                        "value": str(item.servicios_config.count()),
                    },
                ],
                {
                    "code": item.codigo,
                    "name": item.nombre,
                    "description": item.descripcion,
                },
            )
            for item in queryset
        ]
        # Metrics reflect the unfiltered catalog so the header shows real totals.
        active_count = unfiltered.filter(activo=True).count()
        total_count = unfiltered.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Sectores",
                "description": "Administra los sectores especializados que agrupan secciones de ficha clínica por ámbito.",
                "createLabel": "Crear sector",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{ServicioConfig.objects.exclude(sector__isnull=True).count()} configuracion(es) de servicio vinculadas",
            ),
            "fields": [
                _catalog_field("code", "Código", "text", required=True, placeholder="Ej. DEP"),
                _catalog_field("name", "Nombre", "text", required=True, placeholder="Ej. Depilación"),
                _catalog_field("description", "Descripción", "textarea", placeholder="Notas internas del sector"),
            ],
            "items": items,
        }

    if catalog_key == "secciones-ficha":
        unfiltered = FichaSeccion.objects.all()
        base_queryset = unfiltered.select_related("sector", "proc_estetico")

        if q:
            base_queryset = base_queryset.filter(
                Q(codigo__icontains=q) | Q(nombre__icontains=q)
            )
        if active == "true":
            base_queryset = base_queryset.filter(activo=True)
        elif active == "false":
            base_queryset = base_queryset.filter(activo=False)

        sector_filter = filters.get("sector_id")
        if sector_filter:
            try:
                base_queryset = base_queryset.filter(sector_id=int(sector_filter))
            except (TypeError, ValueError):
                pass
        proc_filter = filters.get("proc_estetico_id")
        if proc_filter:
            try:
                base_queryset = base_queryset.filter(proc_estetico_id=int(proc_filter))
            except (TypeError, ValueError):
                pass

        queryset = base_queryset.order_by("orden", "nombre")

        items = [
            _catalog_entry(
                item.pk,
                item.nombre,
                item.codigo,
                item.activo,
                [
                    {"label": "Código", "value": item.codigo},
                    {
                        "label": "Sector",
                        "value": item.sector.nombre if item.sector else "Sin sector",
                    },
                    {
                        "label": "Procedimiento estético",
                        "value": item.proc_estetico.proceso if item.proc_estetico else "Sin procedimiento",
                    },
                ],
                {
                    "name": item.nombre,
                    "code": item.codigo,
                    "sectorId": item.sector_id,
                    "procEsteticoId": item.proc_estetico_id,
                },
            )
            for item in queryset
        ]
        active_count = unfiltered.filter(activo=True).count()
        total_count = unfiltered.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Secciones de ficha",
                "description": "Administra las secciones que agrupan campos de ficha clínica por sector o procedimiento estético.",
                "createLabel": "Crear sección de ficha",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{FichaSeccion.objects.exclude(sector__isnull=True).count()} seccion(es) vinculada(s) a un sector",
            ),
            "fields": [
                _catalog_field("name", "Nombre", "text", required=True, placeholder="Ej. Plástica"),
                _catalog_field("code", "Código", "text", required=True, placeholder="Ej. PLASTICA"),
                _catalog_field(
                    "sectorId",
                    "Sector",
                    "select",
                    value_type="number",
                    allow_empty=True,
                    options=[
                        _catalog_option(sector.pk, sector.nombre, secondary_label=sector.codigo)
                        for sector in Sector.objects.filter(activo=True).order_by("orden", "nombre")
                    ],
                    hint="Opcional si se asigna un procedimiento estético.",
                ),
                _catalog_field(
                    "procEsteticoId",
                    "Procedimiento estético",
                    "select",
                    value_type="number",
                    allow_empty=True,
                    options=[
                        _catalog_option(proc.pk, proc.proceso)
                        for proc in ProcEstetico.objects.filter(activo=True).order_by("proceso")
                    ],
                    hint="Opcional si se asigna un sector.",
                ),
            ],
            "items": items,
        }

    raise KeyError(catalog_key)


def _catalog_parse_payload(catalog_key, payload, instance=None):
    catalog_key = _catalog_key_to_slug(catalog_key)
    errors = {}

    def text_value(field_name):
        return (payload.get(field_name) or "").strip()

    def int_value(field_name, *, required=False, minimum=0, allow_empty=False):
        raw = payload.get(field_name)
        if raw in (None, ""):
            if required and not allow_empty:
                errors[field_name] = "Este campo es obligatorio."
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            errors[field_name] = "Debes enviar un numero válido."
            return None
        if value < minimum:
            errors[field_name] = f"El valor mínimo permitido es {minimum}."
            return None
        return value

    def decimal_value(field_name, *, required=False, minimum=Decimal("0")):
        raw = payload.get(field_name)
        if raw in (None, ""):
            if required:
                errors[field_name] = "Este campo es obligatorio."
            return None
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError):
            errors[field_name] = "Debes enviar un monto válido."
            return None
        if value < minimum:
            errors[field_name] = f"El valor mínimo permitido es {minimum}."
            return None
        return value

    def bool_value(field_name):
        return bool(payload.get(field_name))

    if catalog_key == "todos-los-servicios":
        service_type_id = int_value("serviceTypeId", required=True, minimum=1)
        procedure_id = int_value("procedureId", minimum=1, allow_empty=True)
        sector_id = int_value("sectorId", minimum=1, allow_empty=True)
        base_price = decimal_value("basePrice", required=True)
        if errors:
            raise ValidationError(errors)

        service_type = TipoServicio.objects.filter(pk=service_type_id).first()
        if not service_type:
            raise ValidationError({"serviceTypeId": "Selecciona un tipo de servicio válido."})

        procedure = None
        if procedure_id:
            procedure = ProcEstetico.objects.filter(pk=procedure_id).first()
            if not procedure:
                raise ValidationError({"procedureId": "Selecciona un procedimiento válido."})

        sector = None
        if sector_id:
            sector = Sector.objects.filter(pk=sector_id).first()
            if not sector:
                raise ValidationError({"sectorId": "Selecciona un sector válido."})

        obj = instance or ServicioConfig()
        obj.tipo_servicio = service_type
        obj.proc_estetico = procedure
        obj.sector = sector
        obj.precio_base = base_price
        return obj

    if catalog_key == "procedimientos-esteticos":
        procedure_type_id = int_value("procedureTypeId", required=True, minimum=1)
        name = text_value("name")
        if not name:
            errors["name"] = "El nombre del procedimiento es obligatorio."
        if errors:
            raise ValidationError(errors)
        procedure_type = ProcEsteticosTipo.objects.filter(pk=procedure_type_id).first()
        if not procedure_type:
            raise ValidationError({"procedureTypeId": "Selecciona un tipo de procedimiento válido."})
        obj = instance or ProcEstetico()
        obj.tipo_p_estetico = procedure_type
        obj.proceso = name
        obj.descripcion = text_value("description")
        return obj

    if catalog_key == "tipos-servicio":
        name = text_value("name")
        if not name:
            errors["name"] = "El nombre del tipo de servicio es obligatorio."
        if errors:
            raise ValidationError(errors)
        obj = instance or TipoServicio()
        obj.tipo = name
        obj.descripcion = text_value("description")
        return obj

    if catalog_key == "tipos-procedimiento":
        if instance is None:
            max_orden = ProcEsteticosTipo.objects.aggregate(Max('orden'))['orden__max'] or 0
            return ProcEsteticosTipo(
                tipo=text_value("name"),
                descripcion=text_value("description"),
                orden=max_orden + 1,
            )
        instance.tipo = text_value("name")
        instance.descripcion = text_value("description")
        return instance

    if catalog_key == "campos-ficha":
        section_id = int_value("sectionId", required=True, minimum=1)
        code = text_value("code")
        label = text_value("label")
        field_type = text_value("fieldType")
        option_group_id = int_value("optionGroupId", minimum=1, allow_empty=True)
        # `order` is intentionally read (for forward-compat parsing) but never
        # assigned — the server auto-assigns orden on create and preserves the
        # existing value on update.
        _ = int_value("order", minimum=0, allow_empty=True)

        if not code:
            errors["code"] = "El código interno es obligatorio."
        if not label:
            errors["label"] = "La etiqueta visible es obligatoria."
        if field_type not in {choice for choice, _ in FichaCampo.TipoCampo.choices}:
            errors["fieldType"] = "Selecciona un tipo de campo válido."
        if (
            field_type in {FichaCampo.TipoCampo.SELECCION, FichaCampo.TipoCampo.MULTISELECCION}
            and not option_group_id
        ):
            errors["optionGroupId"] = (
                "El grupo de opciones es obligatorio para campos de selección."
            )
        if errors:
            raise ValidationError(errors)

        section = FichaSeccion.objects.filter(pk=section_id).first()
        if not section:
            raise ValidationError({"sectionId": "Selecciona una sección válida."})

        option_group = None
        if option_group_id:
            option_group = GrupoOpciones.objects.filter(pk=option_group_id).first()
            if not option_group:
                raise ValidationError({"optionGroupId": "Selecciona un grupo de opciones válido."})

        obj = instance or FichaCampo()
        obj.seccion = section
        obj.codigo = code
        obj.etiqueta = label
        obj.tipo_campo = field_type
        obj.grupo_opciones = option_group
        obj.es_multiple = bool_value("isMultiple")
        obj.permite_detalle = bool_value("allowsDetail")
        obj.requerido = bool_value("required")
        if instance is None:
            max_orden = FichaCampo.objects.aggregate(Max("orden"))["orden__max"] or 0
            obj.orden = max_orden + 1
        return obj

    if catalog_key == "patologias-cutaneas":
        name = text_value("name")
        if not name:
            errors["name"] = "El nombre de la patología es obligatorio."
        if errors:
            raise ValidationError(errors)
        obj = instance or PatologiaCutanea()
        obj.nombre = name
        obj.descripcion = text_value("description")
        return obj

    if catalog_key == "especialidades":
        name = text_value("name")
        if not name:
            errors["name"] = "El nombre de la especialidad es obligatorio."
        # `order` is intentionally read (for forward-compat parsing) but never
        # assigned — the server auto-assigns orden on create and preserves the
        # existing value on update.
        _ = int_value("order", minimum=0, allow_empty=True)
        if errors:
            raise ValidationError(errors)
        obj = instance or Especialidad()
        obj.nombre = name
        obj.descripcion = text_value("description")
        if instance is None:
            max_orden = Especialidad.objects.aggregate(Max("orden"))["orden__max"] or 0
            obj.orden = max_orden + 1
        return obj

    if catalog_key == "grupos-opciones":
        code = text_value("code")
        name = text_value("name")
        if not code:
            errors["code"] = "El código es obligatorio."
        if not name:
            errors["name"] = "El nombre es obligatorio."
        if errors:
            raise ValidationError(errors)
        obj = instance or GrupoOpciones()
        obj.codigo = code
        obj.nombre = name
        obj.descripcion = text_value("description")
        return obj

    if catalog_key == "categorias-gasto":
        name = text_value("name")
        if not name:
            errors["name"] = "El nombre de la categoría es obligatorio."
        if errors:
            raise ValidationError(errors)
        obj = instance or CategoriaGasto()
        obj.nombre = name
        obj.descripcion = text_value("description")
        return obj

    if catalog_key == "sectores":
        code = text_value("code")
        name = text_value("name")
        if not code:
            errors["code"] = "El código del sector es obligatorio."
        if not name:
            errors["name"] = "El nombre del sector es obligatorio."
        if errors:
            raise ValidationError(errors)
        obj = instance or Sector()
        obj.codigo = code
        obj.nombre = name
        obj.descripcion = text_value("description")
        if instance is None:
            # Auto-assign orden on create: append after the current max so new
            # entries land at the end without manual numbering. On update we
            # leave the existing orden untouched to preserve manual reorders.
            max_orden = Sector.objects.aggregate(Max("orden"))["orden__max"] or 0
            obj.orden = max_orden + 1
        return obj

    if catalog_key == "secciones-ficha":
        name = text_value("name")
        code = text_value("code")
        sector_id = int_value("sectorId", minimum=1, allow_empty=True)
        proc_estetico_id = int_value("procEsteticoId", minimum=1, allow_empty=True)
        # `order` is intentionally read (for forward-compat parsing) but never
        # assigned — the server auto-assigns orden on create and preserves the
        # existing value on update.
        _ = int_value("order", minimum=0, allow_empty=True)

        if not code:
            errors["code"] = "El código de la sección es obligatorio."
        if not name:
            errors["name"] = "El nombre de la sección es obligatorio."
        if not sector_id and not proc_estetico_id:
            errors["_general"] = (
                "Debes asignar al menos un sector o un procedimiento estético a la sección."
            )
        if errors:
            raise ValidationError(errors)

        sector = Sector.objects.filter(pk=sector_id).first() if sector_id else None
        proc = ProcEstetico.objects.filter(pk=proc_estetico_id).first() if proc_estetico_id else None

        # Friendly pre-check for UniqueConstraint(proc_estetico, codigo).
        # The DB constraint is enforced as a fallback via IntegrityError
        # handling in admin_catalogo_crear/admin_catalogo_actualizar, but
        # raising ValidationError here gives a clearer 400 message.
        uniqueness_qs = FichaSeccion.objects.filter(proc_estetico=proc, codigo=code)
        if instance is not None:
            uniqueness_qs = uniqueness_qs.exclude(pk=instance.pk)
        if uniqueness_qs.exists():
            raise ValidationError(
                {"code": "Ya existe una sección con ese código para este procedimiento estético."}
            )

        obj = instance or FichaSeccion()
        obj.nombre = name
        obj.codigo = code
        obj.sector = sector
        obj.proc_estetico = proc
        if instance is None:
            max_orden = FichaSeccion.objects.aggregate(Max("orden"))["orden__max"] or 0
            obj.orden = max_orden + 1
        return obj

    raise KeyError(catalog_key)


def _catalog_get_instance(catalog_key, item_id):
    catalog_key = _catalog_key_to_slug(catalog_key)
    model_map = {
        "todos-los-servicios": ServicioConfig,
        "procedimientos-esteticos": ProcEstetico,
        "tipos-servicio": TipoServicio,
        "tipos-procedimiento": ProcEsteticosTipo,
        "campos-ficha": FichaCampo,
        "patologias-cutaneas": PatologiaCutanea,
        "especialidades": Especialidad,
        "grupos-opciones": GrupoOpciones,
        "categorias-gasto": CategoriaGasto,
        "sectores": Sector,
        "secciones-ficha": FichaSeccion,
    }
    return model_map[catalog_key].objects.filter(pk=item_id).first()


def _staff_item(especialista):
    # Citas ya no se vinculan directamente a especialistas
    citas = []
    now = timezone.now()
    upcoming = [cita for cita in citas if cita.fecha_hora >= now]
    pending_biometric = sum(
        1
        for cita in citas
        if cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION
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
        "rawId": especialista.pk,
        "specialist": full_name(especialista.usuario),
        "specialty": ", ".join(specialties) if specialties else "Sin especialidad",
        "specialtyIds": [rel.especialidad_id for rel in especialista.especialidades_rel.all()],
        "load": load,
        "pendingValidations": pending_biometric,
        "username": especialista.usuario.username,
        "email": especialista.usuario.email or "",
        "primerNombre": especialista.usuario.primer_nombre,
        "segundoNombre": especialista.usuario.segundo_nombre,
        "apellidoPaterno": especialista.usuario.apellido_paterno,
        "apellidoMaterno": especialista.usuario.apellido_materno,
        "ci": especialista.ci or "",
        "phone": especialista.telefono or "",
        "status": "Activo" if especialista.usuario.is_active else "Inactivo",
        "isActive": bool(especialista.usuario.is_active),
        "activeOperations": len(active_operations),
        "upcomingAppointments": len(upcoming),
        "observations": especialista.observaciones or "",
        "fechaNacimiento": (
            especialista.usuario.fecha_nacimiento.isoformat()
            if especialista.usuario.fecha_nacimiento
            else None
        ),
    }


def _staff_specialty_option(item):
    return {
        "id": item.pk,
        "label": item.nombre,
    }


def _get_worker_role():
    role, _ = Rol.objects.get_or_create(rol="TRABAJADOR")
    return role


def _clear_specialist_availability(especialista):
    DisponibilidadCita.objects.filter(especialista=especialista).delete()
    AgendaHabitualEspecialista.objects.filter(especialista=especialista).delete()
    AgendaExcepcionEspecialista.objects.filter(especialista=especialista).delete()


def _parse_staff_payload(request, payload, errors, *, instance=None):
    username = (payload.get("username") or "").strip()
    email = (payload.get("email") or "").strip()
    primer_nombre = (payload.get("primerNombre") or "").strip()
    segundo_nombre = (payload.get("segundoNombre") or "").strip()
    apellido_paterno = (payload.get("apellidoPaterno") or "").strip()
    apellido_materno = (payload.get("apellidoMaterno") or "").strip()
    ci = (payload.get("ci") or "").strip()
    telefono = (payload.get("telefono") or "").strip()
    observaciones = (payload.get("observaciones") or "").strip()
    fecha_nacimiento_raw = (payload.get("fechaNacimiento") or "").strip()
    password = payload.get("password") or ""
    specialty_ids = payload.get("specialtyIds") or []
    branch_id = payload.get("branchId")

    if not username:
        errors["username"] = "El nombre de usuario es obligatorio."
    if not primer_nombre:
        errors["primerNombre"] = "El primer nombre es obligatorio."
    if not apellido_paterno:
        errors["apellidoPaterno"] = "El apellido paterno es obligatorio."
    if not ci:
        errors["ci"] = "El CI es obligatorio."
    if instance is None and not password:
        errors["password"] = "La contraseña inicial es obligatoria."

    if fecha_nacimiento_raw:
        try:
            date.fromisoformat(fecha_nacimiento_raw)
        except ValueError:
            errors["fechaNacimiento"] = "Fecha de nacimiento no válida."
    elif instance is None:
        errors["fechaNacimiento"] = "La fecha de nacimiento es obligatoria."

    specialties = list(Especialidad.objects.filter(pk__in=specialty_ids, activo=True))
    if len(specialties) != len(set(specialty_ids)):
        errors["specialtyIds"] = "Alguna de las especialidades ya no está disponible."

    # Resolver sucursal
    from catalogs.models import Sucursal
    user = request.user
    sucursal_base = None
    if not (user.is_superuser or user.es_admin_principal):
        sucursal_base = user.sucursal
    elif branch_id:
        sucursal_base = Sucursal.objects.filter(pk=branch_id, activa=True).first()
        if not sucursal_base:
            errors["branchId"] = "La sucursal seleccionada no es válida."
    else:
        # Admin principal/superuser sin branchId explicito: usar sucursal activa del contexto.
        sucursal_base = get_user_branch(request)

    if not sucursal_base:
        errors["branchId"] = "No encontramos una sucursal activa para este especialista."

    if errors:
        return None

    usuario = instance.usuario if instance else Usuario()
    if fecha_nacimiento_raw:
        usuario.fecha_nacimiento = date.fromisoformat(fecha_nacimiento_raw)
    usuario.username = username
    usuario.email = email
    usuario.primer_nombre = primer_nombre
    usuario.segundo_nombre = segundo_nombre
    usuario.apellido_paterno = apellido_paterno
    usuario.apellido_materno = apellido_materno
    usuario.rol = _get_worker_role()
    if instance is None:
        usuario.is_active = True
    if password:
        usuario.set_password(password)

    especialista = instance or Especialista(usuario=usuario)
    especialista.ci = ci
    especialista.telefono = telefono
    especialista.observaciones = observaciones
    if sucursal_base:
        especialista.sucursal_base = sucursal_base

    return {
        "usuario": usuario,
        "especialista": especialista,
        "specialties": specialties,
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
                "description": f"Hay {overdue_pending} comprobante(s) que aún no fueron revisados.",
                "severity": "high",
                "action": "Revisar cola de pagos",
            }
        )
    else:
        alerts.append(
            {
                "id": "alert-payments-ok",
                "title": "Cola de pagos controlada",
                "description": "No hay comprobantes vencidos esperando revisión administrativa.",
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
                    f"Hay {procedures_without_sections} procedimiento(s) activos sin secciones de ficha clínica."
                ),
                "severity": "medium",
                "action": "Completar catálogos",
            }
        )

    return alerts


@require_GET
@admin_required
def admin_offline_confirmation_conflicts(request):
    branch_id = request.GET.get("branchId")
    qs = EventoConfirmacionCita.objects.select_related("cita", "paciente", "sucursal").filter(
        origin_mode=EventoConfirmacionCita.ModoOrigen.OFFLINE,
        sync_status=EventoConfirmacionCita.EstadoSync.CONFLICT,
    )
    if branch_id:
        try:
            qs = qs.filter(sucursal_id=int(branch_id))
        except ValueError:
            return json_response({"detail": "branchId inválido."}, status=400)

    items = []
    for event in qs.order_by("-confirmado_en")[:200]:
        items.append({
            "eventId": event.event_id,
            "appointmentId": event.cita_id,
            "branchId": event.sucursal_id,
            "branch": event.sucursal.nombre if event.sucursal_id else "",
            "clientId": event.paciente_id,
            "clientName": event.paciente.nombre_completo,
            "deviceId": event.device_id,
            "recordedAtDevice": event.recorded_at_device.isoformat() if event.recorded_at_device else None,
            "confirmedAtServer": event.confirmed_at_server.isoformat() if event.confirmed_at_server else None,
            "conflictReason": event.conflict_reason,
            "syncStatus": event.sync_status,
        })
    return json_response({"items": items})


@require_POST
@admin_required
@transaction.atomic
def admin_resolve_offline_confirmation_conflict(request, event_id):
    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON válido."}, status=400)

    resolution = (payload.get("resolution") or "").strip().upper()
    reason = (payload.get("reason") or "").strip()
    if resolution not in {"ACCEPT", "REJECT"}:
        return json_response({"detail": "resolution debe ser ACCEPT o REJECT."}, status=400)
    if not reason:
        return json_response({"detail": "reason es obligatorio para resolver conflictos."}, status=400)

    event = EventoConfirmacionCita.objects.select_for_update(of=("self",)).select_related("cita").filter(event_id=event_id).first()
    if not event:
        return json_response({"detail": "No encontramos el evento solicitado."}, status=404)
    if event.sync_status != EventoConfirmacionCita.EstadoSync.CONFLICT:
        return json_response({"detail": "El evento no está en estado de conflicto."}, status=400)

    if resolution == "ACCEPT":
        event.sync_status = EventoConfirmacionCita.EstadoSync.ACCEPTED
        cita = event.cita
        if cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
            cita.estado = CitaMedica.Estado.CONFIRMADA
            cita.metodo_confirmacion = CitaMedica.MetodoConfirmacion.MANUAL
            cita.verif_biometria = False
            cita.save(update_fields=["estado", "metodo_confirmacion", "verif_biometria", "updated_at"])
    else:
        event.sync_status = EventoConfirmacionCita.EstadoSync.REJECTED

    event.conflict_reason = f"RESOLVED:{resolution}:{reason}"
    event.confirmed_at_server = timezone.now()
    event.save(update_fields=["sync_status", "conflict_reason", "confirmed_at_server", "updated_at"])

    return json_response({"detail": "Conflicto resuelto.", "eventId": event.event_id, "syncStatus": event.sync_status})




@require_GET
@admin_required
def admin_offline_confirmation_metrics(request):
    branch_id = request.GET.get("branchId")
    days = request.GET.get("days")
    try:
        days_int = int(days) if days else 7
    except ValueError:
        return json_response({"detail": "days inválido."}, status=400)
    days_int = max(1, min(days_int, 60))

    start_at = timezone.now() - timedelta(days=days_int)
    qs = EventoConfirmacionCita.objects.filter(origin_mode=EventoConfirmacionCita.ModoOrigen.OFFLINE, confirmado_en__gte=start_at)
    if branch_id:
        try:
            qs = qs.filter(sucursal_id=int(branch_id))
        except ValueError:
            return json_response({"detail": "branchId inválido."}, status=400)

    total = qs.count()
    accepted = qs.filter(sync_status=EventoConfirmacionCita.EstadoSync.ACCEPTED).count()
    conflicts = qs.filter(sync_status=EventoConfirmacionCita.EstadoSync.CONFLICT).count()
    rejected = qs.filter(sync_status=EventoConfirmacionCita.EstadoSync.REJECTED).count()
    duplicates = qs.filter(sync_status=EventoConfirmacionCita.EstadoSync.DUPLICATE).count()

    return json_response({
        "windowDays": days_int,
        "totals": {
            "total": total,
            "accepted": accepted,
            "conflicts": conflicts,
            "rejected": rejected,
            "duplicates": duplicates,
        },
        "rates": {
            "conflictRate": round((conflicts / total), 4) if total else 0,
            "rejectRate": round((rejected / total), 4) if total else 0,
        },
    })


@admin_required
def admin_dashboard(request):
    """Retorna solo las metricas basicas y alertas del dashboard"""
    mark_expired_programmed_appointments_as_no_show()
    today = timezone.localdate()
    branch = get_user_branch(request)

    operations_qs = Operacion.objects.filter(estado=Operacion.Estado.EN_PROCESO)
    prospectos_qs = Prospecto.objects.all()
    payments_qs = PagoRealizado.objects.all()
    operations_started_qs = Operacion.objects.filter(
        created_at__year=today.year,
        created_at__month=today.month,
    )

    if branch:
        operations_qs = operations_qs.filter(paciente__usuario__sucursal_id=branch).distinct()
        prospectos_qs = prospectos_qs.filter(sucursal_registro=branch)
        payments_qs = payments_qs.filter(cuota__operacion__paciente__usuario__sucursal_id=branch).distinct()
        operations_started_qs = operations_started_qs.filter(paciente__usuario__sucursal_id=branch).distinct()

    pending_payments_count = payments_qs.filter(
        estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE
    ).count()
    payments_today = payments_qs.filter(created_at__date=today).count()

    operations_started_this_month = operations_started_qs.count()

    converted_prospects = prospectos_qs.filter(estado=Prospecto.Estado.CONVERTIDO).count()
    total_prospects = prospectos_qs.count()
    prospect_delta = (
        f"{round((converted_prospects / total_prospects) * 100)}% convertidos"
        if total_prospects
        else "Sin conversiones aun"
    )

    appointments_today_qs = CitaMedica.objects.filter(fecha_hora__date=today)
    pending_biometric_qs = CitaMedica.objects.filter(
        estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION
    )
    if branch:
        appointments_today_qs = appointments_today_qs.filter(sucursal=branch)
        pending_biometric_qs = pending_biometric_qs.filter(sucursal=branch)

    appointments_today = appointments_today_qs.count()
    pending_biometric = pending_biometric_qs.count()

    data = {
        "metrics": [
            metric("payments", "Pagos por verificar", pending_payments_count, f"{payments_today} subidos hoy", "warning"),
            metric("operations", "Tratamientos activos", operations_qs.count(), f"{operations_started_this_month} iniciadas este mes", "primary"),
            metric("prospects", "Prospectos en seguimiento", prospectos_qs.filter(estado=Prospecto.Estado.PASAJERO).count(), prospect_delta, "success"),
            metric("appointments", "Citas del dia", appointments_today, f"{pending_biometric} pendientes de biometria", "danger" if pending_biometric else "success"),
        ],
        "alerts": _dashboard_alerts(),
    }
    return json_response(data)


@require_GET
@admin_required
def admin_dashboard_payments(request):
    """Retorna los pagos proximos filtrados por mes/año"""
    today = timezone.localdate()
    try:
        month = int(request.GET.get("month", today.month))
        year = int(request.GET.get("year", today.year))
    except (TypeError, ValueError):
        month, year = today.month, today.year

    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    range_start = start
    if month == today.month and year == today.year:
        range_start = today

    branch = get_user_branch(request)

    upcoming_quotas = CuotaPlanPago.objects.select_related(
        "operacion__paciente__usuario",
        "operacion__servicio_config__proc_estetico"
    ).filter(
        fecha_vencimiento__range=(range_start, end),
        estado__in=[CuotaPlanPago.Estado.PENDIENTE, CuotaPlanPago.Estado.VENCIDA]
    ).order_by("fecha_vencimiento")
    if branch:
        # Filter by the branch the client is registered in, NOT by where
        # the appointments happen to be scheduled. Filtering on
        # ``citas_medicas__sucursal`` hid cuotas whose operation had no
        # appointments yet (e.g. brand-new clients whose only pending item
        # is an unpaid due-today quota), which is the wrong semantics for a
        # "what's coming up to collect" dashboard.
        upcoming_quotas = upcoming_quotas.filter(
            operacion__paciente__usuario__sucursal_id=branch,
        ).distinct()

    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    upcoming_payments = []
    for q in upcoming_quotas:
        upcoming_payments.append({
            "id": q.pk,
            "dueDate": q.fecha_vencimiento.isoformat(),
            "dueDateLabel": date_label(q.fecha_vencimiento),
            "amount": currency(_quota_programmed_amount(q)),
            "client": full_name(q.operacion.paciente.usuario),
            "clientId": q.operacion.paciente_id,
            "operation": procedure_name(q.operacion),
            "operationId": q.operacion_id,
            "quotaNumber": q.nro_cuota,
            "isToday": q.fecha_vencimiento == today,
            "isThisWeek": start_of_week <= q.fecha_vencimiento <= end_of_week,
        })

    return json_response({
        "month": month,
        "year": year,
        "payments": upcoming_payments
    })


@require_GET
@admin_required
def admin_dashboard_agenda(request):
    """Retorna la agenda filtrada por mes/año"""
    today = timezone.localdate()
    try:
        month = int(request.GET.get("month", today.month))
        year = int(request.GET.get("year", today.year))
    except (TypeError, ValueError):
        month, year = today.month, today.year

    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    range_start = start
    if month == today.month and year == today.year:
        range_start = today

    branch = get_user_branch(request)

    agenda_qs = (
        CitaMedica.objects.select_related(
            "operacion__paciente__usuario",
            "operacion__servicio_config__proc_estetico"
        )
        .filter(
            fecha_hora__date__range=(range_start, end),
            estado=CitaMedica.Estado.PROGRAMADA
        )
        .order_by("fecha_hora")
    )
    if branch:
        agenda_qs = agenda_qs.filter(sucursal=branch)

    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    agenda_data = []
    for cita in agenda_qs:
        cita_local = timezone.localtime(cita.fecha_hora)
        agenda_data.append({
            "id": cita.pk,
            "time": cita_local.strftime("%H:%M"),
            "dateLabel": cita_local.strftime("%d/%m/%Y"),
            "patient": full_name(cita.operacion.paciente.usuario),
            "clientId": cita.operacion.paciente_id,
            "procedure": procedure_name(cita.operacion),
            "operationId": cita.operacion_id,
            "specialist": "Asignado",
            "status": _agenda_status(cita),
            "appointmentStatus": _agenda_appointment_status(cita),
            "verificationStatus": _agenda_verification_status(cita),
            "verificationMethod": _agenda_verification_method(cita),
            "isToday": cita.fecha_hora.date() == today,
            "isThisWeek": start_of_week <= cita.fecha_hora.date() <= end_of_week,
        })

    return json_response({
        "month": month,
        "year": year,
        "agenda": agenda_data
    })


@require_POST
@admin_required
def admin_prospect_check_duplicates(request):
    payload = load_payload(request)
    if not payload:
        return json_response({"detail": "Datos invalidos."}, status=400)

    primer_nombre = (payload.get("primerNombre") or payload.get("nombres") or "").strip()
    segundo_nombre = (payload.get("segundoNombre") or "").strip()
    apellido_paterno = (payload.get("apellidoPaterno") or payload.get("apellidos") or "").strip()
    apellido_materno = (payload.get("apellidoMaterno") or "").strip()
    telefono = (payload.get("telefono") or "").strip()

    if not primer_nombre or not apellido_paterno:
        return json_response({"detail": "Primer nombre y apellido paterno son requeridos."}, status=400)

    # Buscar coincidencias exactas o similares
    # Filtramos por nombre + apellido o por telefono
    duplicate_filter = Q(primer_nombre__iexact=primer_nombre, apellido_paterno__iexact=apellido_paterno)
    if segundo_nombre:
        duplicate_filter |= Q(
            primer_nombre__iexact=primer_nombre,
            segundo_nombre__iexact=segundo_nombre,
            apellido_paterno__iexact=apellido_paterno,
        )
    if apellido_materno:
        duplicate_filter |= Q(
            primer_nombre__iexact=primer_nombre,
            apellido_paterno__iexact=apellido_paterno,
            apellido_materno__iexact=apellido_materno,
        )
    if telefono:
        duplicate_filter |= Q(telefono=telefono)
    duplicates = Prospecto.objects.filter(duplicate_filter).exclude(estado=Prospecto.Estado.CONVERTIDO)

    if duplicates.exists():
        match = duplicates.first()
        branch = match.sucursal_registro
        branch_info = f"{branch.nombre} ({branch.ciudad})" if branch else "otra sucursal"
        
        return json_response({
            "exists": True,
            "message": f"Atencion: Ya existe un prospecto con datos similares ({match}) registrado en {branch_info}.",
            "match": {
                "id": match.pk,
                "name": str(match),
                "branch": branch_info
            }
        })

    return json_response({"exists": False})


@require_GET
@admin_required
def admin_clientes_global_search(request):
    """
    Cross-branch client search used by the import flow from a different
    branch's list. Match semantics mirror /api/admin/usuarios/buscar/:

    - A single token (no spaces) keeps the original OR semantics:
      match any field that contains the token. ``paciente`` matches a
      user whose username is "paciente.demo" or primer_nombre contains
      "Paciente".
    - Multiple tokens (whitespace-separated) switch to AND semantics
      over the user's full name only. Each token must appear, in any
      order, in the concatenation of primer_nombre, segundo_nombre,
      apellido_paterno, apellido_materno (case-insensitive).
      ``Maria Garcia`` matches "Maria Garcia Lopez"; ``Garcia Maria``
      matches the same row.

    We don't combine per-field OR with per-token AND: a query with
    spaces is treated as a name query. CI/username/email/phone are
    single-token fields; multi-token queries would not find "fabian
    r" by email reliably, and we don't lose much by being strict.
    """
    query = request.GET.get("q", "").strip()
    if len(query) < 3:
        return json_response({"clients": []})

    base = Cliente.objects.select_related("usuario", "sucursal_origen")

    tokens = query.split()
    if len(tokens) >= 2:
        # AND across tokens on the full name (case-insensitive). Each
        # token is OR'd across the four name fields so the operator
        # doesn't have to remember the order (Maria Garcia, Garcia
        # Maria, both work). Other fields (username, email, phone, CI)
        # are not searched for multi-token queries: a "fabian r"
        # looking for the email is rare enough that we don't lose much
        # by being strict.
        for token in tokens:
            base = base.filter(
                Q(usuario__primer_nombre__icontains=token)
                | Q(usuario__segundo_nombre__icontains=token)
                | Q(usuario__apellido_paterno__icontains=token)
                | Q(usuario__apellido_materno__icontains=token)
            )
    else:
        # Single-token OR across every searchable field. Includes
        # username so the operator can search by the account name
        # directly (e.g. "paciente.demo" matches the paciente.demo
        # Cliente profile).
        ci_q = Q(ci__icontains=query) | Q(usuario__cliente__ci__icontains=query) | Q(usuario__especialista__ci__icontains=query)
        text_match = (
            Q(usuario__username__icontains=query)
            | Q(usuario__primer_nombre__icontains=query)
            | Q(usuario__segundo_nombre__icontains=query)
            | Q(usuario__apellido_paterno__icontains=query)
            | Q(usuario__apellido_materno__icontains=query)
            | Q(usuario__email__icontains=query)
            | Q(usuario__telefono__icontains=query)
            | ci_q
        )
        base = base.filter(text_match)

    clients_qs = base.exclude(
        operaciones__citas_medicas__estado=CitaMedica.Estado.PROGRAMADA,
        operaciones__citas_medicas__fecha_hora__gte=timezone.now(),
    ).exclude(
        citas_medicas_libres__estado=CitaClienteLibre.Estado.PROGRAMADA,
        citas_medicas_libres__fecha_hora__gte=timezone.now(),
    ).distinct().order_by("usuario__username")[:10]

    return json_response({
        "clients": [
            {
                "id": c.pk,
                "name": c.usuario.nombre_completo,
                "ci": c.ci,
                "phone": c.telefono,
                "branchId": c.usuario.sucursal_id,
                "branchName": c.usuario.sucursal.nombre if c.usuario.sucursal else "Sin sucursal",
                "cityName": c.usuario.sucursal.ciudad if c.usuario.sucursal else "Sin ciudad"
            }
            for c in clients_qs
        ]
    })


@require_GET
@admin_required
def admin_prospectos(request):
    mark_expired_programmed_appointments_as_no_show()
    branch = get_user_branch(request)
    prospectos_qs = (
        Prospecto.objects.select_related("registrado_por")
        .prefetch_related(
            Prefetch(
                "citas_medicas",
                queryset=CitaProspecto.objects.select_related(
                    "servicio_config__tipo_servicio",
                ).order_by("fecha_hora"),
            )
        )
    )
    if branch:
        prospectos_qs = prospectos_qs.filter(sucursal_registro=branch)
    
    prospectos_qs = prospectos_qs.order_by("-created_at")
    clientes_qs = (
        Cliente.objects.select_related("usuario")
        .prefetch_related(
            Prefetch(
                "operaciones",
                queryset=Operacion.objects.prefetch_related(
                    Prefetch(
                        "citas_medicas",
                        queryset=CitaMedica.objects.select_related().order_by(
                            "fecha_hora"
                        ),
                    )
                ),
            ),
            "analisis_esteticos",
        ).order_by("usuario__primer_nombre", "usuario__apellido_paterno")
    )
    if branch:
        clientes_qs = clientes_qs.filter(usuario__sucursal_id=branch)

    data = {
        "metrics": [
            metric(
                "prospects-open",
                "Prospectos abiertos",
                prospectos_qs.filter(estado=Prospecto.Estado.PASAJERO).count(),
                "Registrados internamente por el equipo",
                "primary",
            ),
            metric(
                "prospects-converted",
                "Prospectos convertidos",
                prospectos_qs.filter(estado=Prospecto.Estado.CONVERTIDO).count(),
                "Ya cuentan con tratamiento activo o historico",
                "success",
            ),
            metric(
                "clients-active",
                "Clientes activos",
                clientes_qs.filter(estado_cliente=Cliente.Estado.ACTIVO).count(),
                "Con al menos una operacion vigente",
                "warning",
            ),
            metric(
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
    return json_response(data)


@require_GET
@admin_required
def admin_prospect_medical_availability(request, prospecto_id):
    prospecto = Prospecto.objects.filter(pk=prospecto_id).first()
    if not prospecto:
        return json_response({"detail": "No encontramos el prospecto solicitado."}, status=404)
    if prospecto.estado != Prospecto.Estado.PASAJERO:
        return json_response({"detail": "Solo se pueden agendar citas para prospectos no convertidos."}, status=400)

    service_config = _medical_appointment_service_config()
    if not service_config:
        return json_response(
            {"detail": "No existe un servicio activo de cita medica o consulta para agendar prospectos."},
            status=400,
        )

    branch_id = request.GET.get("branchId")
    if branch_id:
        try:
            branch_id = int(branch_id)
        except ValueError:
            branch_id = 1
    else:
        branch_id = 1

    return json_response(
        {
            "prospect": _prospect_item(prospecto),
            "service": {
                "rawId": service_config.pk,
                "name": service_config.tipo_servicio.tipo,
            },
            "calendar": _build_prospect_medical_slot_map(service_config, branch_id=branch_id),
        }
    )


@require_POST
@admin_required
@transaction.atomic
def admin_create_prospect_medical_appointment(request, prospecto_id):
    prospecto = (
        Prospecto.objects.select_for_update(of=("self",))
        .prefetch_related("citas_medicas")
        .filter(pk=prospecto_id)
        .first()
    )
    if not prospecto:
        return json_response({"detail": "No encontramos el prospecto solicitado."}, status=404)
    if prospecto.estado != Prospecto.Estado.PASAJERO:
        return json_response({"detail": "Solo se pueden agendar citas para prospectos no convertidos."}, status=400)
    if prospecto.citas_medicas.filter(estado=CitaProspecto.Estado.PROGRAMADA).exists():
        return json_response({"detail": "Este prospecto ya tiene una cita medica programada."}, status=400)

    service_config = _medical_appointment_service_config()
    if not service_config:
        return json_response(
            {"detail": "No existe un servicio activo de cita medica o consulta para agendar prospectos."},
            status=400,
        )

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    sucursal_id = payload.get("branchId")
    fecha_hora_str = payload.get("dateTime")
    if not sucursal_id or not fecha_hora_str:
        return json_response({"detail": "Faltan datos de sucursal o fecha/hora."}, status=400)
        
    try:
        from django.utils import dateparse
        fecha_hora = dateparse.parse_datetime(fecha_hora_str)
        if timezone.is_naive(fecha_hora):
            fecha_hora = timezone.make_aware(fecha_hora)
        if not fecha_hora:
            raise ValueError
    except Exception:
        return json_response({"detail": "Formato de fecha u hora invalido."}, status=400)

    appointment = CitaProspecto.objects.create(
        prospecto=prospecto,
        servicio_config=service_config,
        sucursal_id=sucursal_id,
        fecha_hora=fecha_hora,
        estado=CitaProspecto.Estado.PROGRAMADA,
        detalles_cita="Cita medica agendada libremente por administracion.",
    )
    return json_response(
        {
            "detail": "La cita medica fue agendada correctamente para el prospecto.",
            "appointment": _prospect_appointment_item(appointment),
        },
        status=201,
    )


@require_POST
@admin_required
@transaction.atomic
def admin_update_prospect(request, prospecto_id):
    prospecto = Prospecto.objects.select_for_update().filter(pk=prospecto_id).first()
    if not prospecto:
        return json_response({"detail": "No encontramos el prospecto solicitado."}, status=404)

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "Datos invalidos."}, status=400)

    def _capitalize_first_letter(value):
        text = (value or "").strip()
        if not text:
            return ""
        return text[:1].upper() + text[1:]

    if "firstName" in payload or "primerNombre" in payload:
        prospecto.primer_nombre = _capitalize_first_letter(payload.get("primerNombre") or payload.get("firstName"))
    if "segundoNombre" in payload:
        prospecto.segundo_nombre = _capitalize_first_letter(payload.get("segundoNombre"))
    if "lastName" in payload or "apellidoPaterno" in payload:
        prospecto.apellido_paterno = _capitalize_first_letter(payload.get("apellidoPaterno") or payload.get("lastName"))
    if "apellidoMaterno" in payload:
        prospecto.apellido_materno = _capitalize_first_letter(payload.get("apellidoMaterno"))
    if "phone" in payload:
        prospecto.telefono = payload["phone"]
    if "observations" in payload:
        prospecto.observaciones = payload["observations"]
    if "stateValue" in payload:
        requested_state = (payload.get("stateValue") or "").strip().upper()
        if requested_state in {Prospecto.Estado.PASAJERO, Prospecto.Estado.DESCARTADO}:
            prospecto.estado = requested_state
        elif requested_state:
            return json_response(
                {"detail": "El estado seleccionado no es valido para este prospecto."},
                status=400,
            )

    errors = {}
    if not prospecto.primer_nombre:
        errors["primerNombre"] = "El primer nombre es obligatorio."
    if not prospecto.apellido_paterno:
        errors["apellidoPaterno"] = "El apellido paterno es obligatorio."
    if errors:
        return json_response({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)

    prospecto.save()

    # Manejar actualizaciones de estados de citas si vienen en el payload
    appointment_statuses = payload.get("appointmentStatuses", {})
    if appointment_statuses:
        # appointment_statuses es un dict { "id": "NUEVO_ESTADO" }
        for app_id_str, new_status in appointment_statuses.items():
            try:
                app_id = int(app_id_str)
                appointment = CitaProspecto.objects.filter(pk=app_id, prospecto=prospecto).first()
                if appointment and new_status in CitaProspecto.Estado.values:
                    appointment.estado = new_status
                    appointment.save()
            except (ValueError, TypeError):
                continue

    return json_response(
        {
            "detail": "Datos del prospecto y estados de citas actualizados correctamente.",
            "prospect": _prospect_item(prospecto),
        }
    )


@require_POST
@admin_required
@transaction.atomic
def admin_cancel_prospect_medical_appointment(request, appointment_id):
    appointment = (
        CitaProspecto.objects.select_for_update(of=("self",))
        .select_related("prospecto",  "servicio_config__tipo_servicio")
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        return json_response({"detail": "No encontramos la cita solicitada."}, status=404)
    if appointment.estado != CitaProspecto.Estado.PROGRAMADA:
        return json_response({"detail": "Solo se pueden cancelar citas programadas."}, status=400)

    appointment.estado = CitaProspecto.Estado.CANCELADA
    appointment.detalles_cita = "Cita medica de prospecto cancelada desde administracion."
    appointment.save(update_fields=["estado", "detalles_cita", "updated_at"])

    return json_response(
        {
            "detail": "La cita medica del prospecto fue cancelada correctamente.",
            "appointment": _prospect_appointment_item(appointment),
        }
    )


@require_POST
@admin_required
@transaction.atomic
def admin_update_prospect_medical_appointment(request, appointment_id):
    appointment = (
        CitaProspecto.objects.select_for_update(of=("self",))
        .select_related("prospecto")
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        return json_response({"detail": "No encontramos la cita solicitada."}, status=404)

    payload = load_payload(request)
    if not payload or "status" not in payload:
        return json_response({"detail": "Datos insuficientes."}, status=400)

    new_status = payload["status"]
    if new_status not in CitaProspecto.Estado.values:
        return json_response({"detail": "Estado de cita invalido."}, status=400)

    appointment.estado = new_status
    appointment.save()

    return json_response(
        {
            "detail": "Cita medica actualizada correctamente.",
            "prospect": _prospect_item(appointment.prospecto),
        }
    )


@require_GET
@admin_required
def admin_cliente_detalle(request, client_id):
    mark_expired_programmed_appointments_as_no_show()
    cliente = _admin_client_queryset().filter(pk=client_id).first()
    if not cliente:
        return json_response({"detail": "No encontramos el cliente solicitado."}, status=404)

    return json_response(_admin_client_detail(cliente))


@require_GET
@admin_required
def admin_cliente_reservation_availability(request, client_id, operation_id):
    cliente = Cliente.objects.filter(pk=client_id).first()
    if not cliente:
        return json_response({"detail": "No encontramos el cliente solicitado."}, status=404)

    operacion = (
        Operacion.objects.filter(paciente=cliente, pk=operation_id)
        .select_related("servicio_config__tipo_servicio", "servicio_config__proc_estetico")
        .prefetch_related(
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.order_by("fecha_hora"),
            ),
            Prefetch("cuotas_plan_pagos", queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota")),
        )
        .first()
    )
    if not operacion:
        return json_response({"detail": "No encontramos la operacion solicitada para este cliente."}, status=404)
    if operacion.estado != Operacion.Estado.EN_PROCESO:
        return json_response({"detail": "Solo se pueden reservar citas para tratamientos en proceso."}, status=400)

    return json_response({"operation": _client_operation_item(operacion)})


@require_GET
@admin_required
def admin_cliente_free_medical_availability(request, client_id):
    cliente = Cliente.objects.filter(pk=client_id).first()
    if not cliente:
        return json_response({"detail": "No encontramos el cliente solicitado."}, status=404)

    service_config = _medical_appointment_service_config()
    if not service_config:
        return json_response(
            {"detail": "No existe un servicio activo de cita medica o consulta para agendar clientes."},
            status=400,
        )

    return json_response(
        {
            "client": _client_item(cliente),
            "service": {
                "rawId": service_config.pk,
                "name": service_config.tipo_servicio.tipo,
            },
        }
    )


@require_POST
@admin_required
@transaction.atomic
def admin_cliente_create_free_medical_appointment(request, client_id):
    cliente = Cliente.objects.select_for_update(of=("self",)).filter(pk=client_id).first()
    if not cliente:
        return json_response({"detail": "No encontramos el cliente solicitado."}, status=404)

    service_config = _medical_appointment_service_config()
    if not service_config:
        return json_response(
            {"detail": "No existe un servicio activo de cita medica o consulta para agendar clientes."},
            status=400,
        )

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)
        
    sucursal_id = payload.get("branchId")
    fecha_hora_str = payload.get("dateTime")
    if not sucursal_id or not fecha_hora_str:
        return json_response({"detail": "Faltan datos de sucursal o fecha/hora."}, status=400)
        
    try:
        from django.utils import dateparse
        fecha_hora = dateparse.parse_datetime(fecha_hora_str)
        if fecha_hora and timezone.is_naive(fecha_hora):
            fecha_hora = timezone.make_aware(fecha_hora)
        if not fecha_hora:
            raise ValueError
    except Exception:
        return json_response({"detail": "Formato de fecha u hora invalido."}, status=400)

    appointment = CitaClienteLibre.objects.create(
        cliente=cliente,
        servicio_config=service_config,
        sucursal_id=sucursal_id,
        fecha_hora=fecha_hora,
        estado=CitaClienteLibre.Estado.PROGRAMADA,
        detalles_cita="Cita medica libre agendada por administracion.",
    )
    _notify_client_appointment_scheduled(
        cliente=cliente,
        fecha_hora=appointment.fecha_hora,
        sucursal_id=appointment.sucursal_id,
        appointment_id=appointment.pk,
        appointment_type="cita_cliente_libre",
    )

    return json_response(
        {
            "detail": "La cita medica libre fue agendada correctamente para el cliente.",
            "appointment": _free_client_appointment_item(appointment),
        },
        status=201,
    )


@require_POST
@admin_required
@transaction.atomic
def admin_cliente_create_reservation(request, client_id, operation_id):
    cliente = Cliente.objects.filter(pk=client_id).first()
    if not cliente:
        return json_response({"detail": "No encontramos el cliente solicitado."}, status=404)

    operacion = (
        Operacion.objects.select_for_update(of=("self",))
        .filter(paciente=cliente, pk=operation_id)
        .select_related("servicio_config__tipo_servicio", "servicio_config__proc_estetico")
        .prefetch_related(
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.order_by("fecha_hora"),
            ),
            Prefetch("cuotas_plan_pagos", queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota")),
        )
        .first()
    )
    if not operacion:
        return json_response({"detail": "No encontramos la operacion solicitada para este cliente."}, status=404)
    if not operacion.puede_reservar:
        return json_response(
            {"detail": operacion.motivo_bloqueo_reserva or "Esta operacion no permite nuevas reservas."},
            status=400,
        )

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    sucursal_id = payload.get("branchId")
    fecha_hora_str = payload.get("dateTime")
    
    if not sucursal_id or not fecha_hora_str:
        return json_response({"detail": "Faltan datos de sucursal o fecha/hora."}, status=400)
        
    try:
        from django.utils import dateparse
        fecha_hora = dateparse.parse_datetime(fecha_hora_str)
        if fecha_hora and timezone.is_naive(fecha_hora):
            fecha_hora = timezone.make_aware(fecha_hora)
        if not fecha_hora:
            raise ValueError
    except Exception:
        return json_response({"detail": "Formato de fecha u hora invalido."}, status=400)

    cita = CitaMedica.objects.create(
        operacion=operacion,
        sucursal_id=sucursal_id,
        fecha_hora=fecha_hora,
        estado=CitaMedica.Estado.PROGRAMADA,
        detalles_cita="Reserva creada libremente por administracion.",
    )
    _notify_client_appointment_scheduled(
        cliente=cliente,
        fecha_hora=cita.fecha_hora,
        sucursal_id=cita.sucursal_id,
        appointment_id=cita.pk,
        appointment_type="cita_medica",
    )

    return json_response(
        {
            "detail": "La cita fue reservada correctamente para el cliente.",
            "appointment": _client_appointment_item(cita),
            "operation": _client_operation_item(operacion),
        },
        status=201,
    )


@require_POST
@admin_required
@transaction.atomic
def admin_cliente_inactivate(request, client_id):
    cliente = (
        Cliente.objects.select_for_update(of=("self",))
        .select_related("usuario")
        .prefetch_related(
            Prefetch(
                "operaciones",
                queryset=Operacion.objects.select_for_update(of=("self",)).prefetch_related(
                    "citas_medicas",
                    Prefetch(
                        "cuotas_plan_pagos",
                        queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados"),
                    ),
                ),
            )
        )
        .filter(pk=client_id)
        .first()
    )
    if not cliente:
        return json_response({"detail": "No encontramos el cliente solicitado."}, status=404)

    pending_review_payment = PagoRealizado.objects.filter(
        cuota__operacion__paciente=cliente,
        estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
    ).select_related("cuota__operacion").order_by("created_at").first()
    if pending_review_payment:
        return json_response(
            {
                "detail": (
                    "No se puede inactivar al cliente porque tiene un pago realizado pendiente de revisión. "
                    f"Primero revisa el pago #{pending_review_payment.pk} de la operación "
                    f"#{pending_review_payment.cuota.operacion_id}."
                )
            },
            status=400,
        )

    pendientes = cliente.pendientes_operativos()
    cancelled_operations = 0
    cancelled_appointments = 0
    converted_quotas = 0
    skipped_pending_review_quotas = 0
    for operacion in cliente.operaciones.all():
        if operacion.estado == Operacion.Estado.EN_PROCESO:
            operacion.estado = Operacion.Estado.CANCELADA
            operacion.save(update_fields=["estado", "updated_at"])
            cancelled_operations += 1
        for cuota in operacion.cuotas_plan_pagos.all():
            if cuota.estado not in {CuotaPlanPago.Estado.PENDIENTE, CuotaPlanPago.Estado.VENCIDA}:
                continue
            has_pending_review = cuota.pagos_realizados.filter(
                estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE
            ).exists()
            if has_pending_review:
                skipped_pending_review_quotas += 1
                continue
            cuota.estado = CuotaPlanPago.Estado.NO_PAGADA
            cuota.save(update_fields=["estado", "updated_at"])
            converted_quotas += 1
        for cita in operacion.citas_medicas.all():
            if cita.estado == CitaMedica.Estado.PROGRAMADA:
                cita.estado = CitaMedica.Estado.CANCELADA
                cita.detalles_cita = "Reserva cancelada al convertir el cliente a inactivo desde administracion."
                cita.save(update_fields=["estado", "detalles_cita", "updated_at"])
                cancelled_appointments += 1

    cliente.cambiar_estado(Cliente.Estado.INACTIVO, save=True, manual=True)

    return json_response(
        {
            "detail": (
                "El cliente fue convertido a inactivo. "
                f"Antes de la inactivación tenia {pendientes['sesiones_pendientes']} sesion(es) "
                f"y {pendientes['cuotas_pendientes']} cuota(s) pendiente(s). "
                f"Se convirtieron {converted_quotas} cuota(s) a no pagadas "
                f"y se omitieron {skipped_pending_review_quotas} por tener pagos pendientes de revisión. "
                f"Se cancelaron {cancelled_operations} procedimiento(s) en proceso y "
                f"{cancelled_appointments} cita(s) programada(s)."
            ),
            "client": _client_item(cliente),
        }
    )


@require_POST
@admin_required
@transaction.atomic
def admin_cancel_appointment(request, appointment_id):
    appointment = (
        CitaMedica.objects.select_related(
            
            "operacion__paciente__usuario",
            "operacion__servicio_config__tipo_servicio",
            "operacion__servicio_config__proc_estetico",
        )
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        return json_response({"detail": "No encontramos la cita solicitada."}, status=404)

    if appointment.estado != CitaMedica.Estado.PROGRAMADA:
        return json_response(
            {
                "detail": "Solo se pueden cancelar citas que todavia esten programadas."
            },
            status=400,
        )

    appointment.estado = CitaMedica.Estado.CANCELADA
    appointment.verif_biometria = False
    appointment.save()

    client_user = appointment.operacion.paciente.usuario
    procedimiento = procedure_name(appointment.operacion)
    fecha_cita = appointment.fecha_hora.strftime('%d/%m/%Y')
    hora_cita = appointment.fecha_hora.strftime('%H:%M')
    create_notification(
        recipient=client_user,
        branch=appointment.sucursal,
        type=Notification.Type.CLIENT_APPOINTMENT_CANCELLED,
        title="Cita cancelada",
        message=f"Tu cita de la fecha {fecha_cita}, a la hora {hora_cita}, para el procedimiento {procedimiento} fue cancelada. Puedes verlo en tu registro de citas.",
        action_url="/cliente/reservas",
        source_event="appointment.cancelled",
        source_entity_type="appointment",
        source_entity_id=appointment.id,
        created_by_type="admin",
        created_by_id=request.user.id,
    )

    return json_response(
        {
            "detail": "La cita programada fue cancelada correctamente.",
            "appointment": {
                "id": f"CIT-{appointment.pk:04d}",
                "rawId": appointment.pk,
                "dateTime": _datetime_label(appointment.fecha_hora),
                "operation": procedure_name(appointment.operacion),
                "specialist": "Sin asignar",
                "status": appointment.get_estado_display(),
            },
        }
    )


@require_POST
@admin_required
@transaction.atomic
def admin_mark_appointment_pending_biometric(request, appointment_id):
    appointment = (
        CitaMedica.objects.select_related(
            
            "operacion__paciente__usuario",
            "operacion__servicio_config__tipo_servicio",
            "operacion__servicio_config__proc_estetico",
        )
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        return json_response({"detail": "No encontramos la cita solicitada."}, status=404)

    if appointment.estado != CitaMedica.Estado.PROGRAMADA:
        return json_response({"detail": "Solo se pueden cerrar citas que aun estén programadas."}, status=400)

    appointment.estado = CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION
    appointment.verif_biometria = False
    appointment.detalles_cita = appointment.detalles_cita or "Cita marcada como realizada desde administracion."
    appointment.save()

    return json_response(
        {
            "detail": "La cita quedo realizada y pendiente de confirmaciòn.",
            "appointment": _client_appointment_item(appointment),
            "operation": _operation_detail(appointment.operacion),
        }
    )


@require_POST
@admin_required
@transaction.atomic
def admin_update_appointment_status(request, appointment_id):
    appointment = CitaMedica.objects.filter(pk=appointment_id).first()
    if not appointment:
        return json_response({"detail": "No encontramos la cita solicitada."}, status=404)

    payload = load_payload(request)
    nuevo_estado = payload.get("status")
    if nuevo_estado not in [choice[0] for choice in CitaMedica.Estado.choices]:
        return json_response({"detail": "El estado proporcionado no es válido."}, status=400)

    previous_status = appointment.estado
    appointment.estado = nuevo_estado
    # Si se marca como PROGRAMADA, nos aseguramos que verif_biometria sea False
    if appointment.estado == CitaMedica.Estado.PROGRAMADA:
        appointment.verif_biometria = False
        appointment.metodo_confirmacion = ""
    # Si se marca como CONFIRMADA manualmente, se registra como confirmacion manual
    elif appointment.estado == CitaMedica.Estado.CONFIRMADA:
        appointment.verif_biometria = False
        appointment.metodo_confirmacion = CitaMedica.MetodoConfirmacion.MANUAL

    appointment.save(update_fields=["estado", "verif_biometria", "metodo_confirmacion", "updated_at"])

    if (
        previous_status != CitaMedica.Estado.CONFIRMADA
        and appointment.estado == CitaMedica.Estado.CONFIRMADA
        and appointment.metodo_confirmacion == CitaMedica.MetodoConfirmacion.MANUAL
    ):
        EventoConfirmacionCita.objects.create(
            cita=appointment,
            paciente=appointment.operacion.paciente,
            sucursal=appointment.sucursal,
            metodo=EventoConfirmacionCita.Metodo.MANUAL,
            confirmado_en=timezone.now(),
            ip_origen=_request_ip(request),
        )

    return json_response(
        {
            "detail": f"El estado de la cita fue actualizado a {appointment.get_estado_display()}.",
            "appointment_id": appointment.id,
            "new_status": appointment.estado,
        }
    )


@require_POST
@admin_required
@transaction.atomic
def admin_reschedule_appointment(request, appointment_id):
    appointment = (
        CitaMedica.objects.select_related("operacion__paciente", "sucursal")
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        return json_response({"detail": "No encontramos la cita solicitada."}, status=404)

    if appointment.estado not in {CitaMedica.Estado.PROGRAMADA, CitaMedica.Estado.NO_ASISTIO}:
        return json_response({"detail": "Solo se pueden reprogramar citas programadas o no asistidas."}, status=400)

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "Datos invalidos."}, status=400)
    date_time_str = payload.get("dateTime")
    if not date_time_str:
        return json_response({"detail": "Debes enviar la nueva fecha y hora."}, status=400)
    try:
        from django.utils import dateparse
        new_date_time = dateparse.parse_datetime(date_time_str)
        if timezone.is_naive(new_date_time):
            new_date_time = timezone.make_aware(new_date_time)
        if not new_date_time:
            raise ValueError
    except Exception:
        return json_response({"detail": "Formato de fecha u hora inválido."}, status=400)
    if new_date_time <= timezone.now():
        return json_response({"detail": "La nueva fecha y hora debe ser futura."}, status=400)

    appointment.fecha_hora = new_date_time
    appointment.estado = CitaMedica.Estado.PROGRAMADA
    appointment.verif_biometria = False
    appointment.metodo_confirmacion = ""
    appointment.detalles_cita = "Reserva reprogramada desde administración."
    appointment.save(update_fields=["fecha_hora", "estado", "verif_biometria", "metodo_confirmacion", "detalles_cita", "updated_at"])
    client_user = appointment.operacion.paciente.usuario
    procedimiento = procedure_name(appointment.operacion)
    fecha_cita = appointment.fecha_hora.strftime('%d/%m/%Y')
    hora_cita = appointment.fecha_hora.strftime('%H:%M')
    create_notification(
        recipient=client_user,
        branch=appointment.sucursal,
        type=Notification.Type.CLIENT_APPOINTMENT_RESCHEDULED,
        title="Cita reprogramada",
        message=f"Tu cita de la fecha {fecha_cita}, a la hora {hora_cita}, para el procedimiento {procedimiento} fue reprogramada para la fecha {new_date_time.strftime('%d/%m/%Y')} a la hora {new_date_time.strftime('%H:%M')}. Puedes verlo en tu registro de citas.",
        action_url="/cliente/reservas",
        source_event="appointment.rescheduled",
        source_entity_type="appointment",
        source_entity_id=appointment.id,
        created_by_type="admin",
        created_by_id=request.user.id,
    )
    return json_response({"detail": "La reserva fue reprogramada correctamente.", "appointment": _client_appointment_item(appointment)})




@require_POST
@admin_required
@transaction.atomic
def admin_confirm_appointment_biometric(request, appointment_id):
    if settings.BIOMETRIC_SUSPENDED:
        logger.warning(
            "[SUSPENSION] legacy function biometric confirm gated family=verification cita_id=%s user=%s",
            appointment_id,
            getattr(request.user, "id", None),
        )
        return json_response(verification_suspended_payload(), status=503)

    appointment = (
        CitaMedica.objects.select_related(
            
            "operacion__paciente__usuario",
            "operacion__servicio_config__tipo_servicio",
            "operacion__servicio_config__proc_estetico",
        )
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        return json_response({"detail": "No encontramos la cita solicitada."}, status=404)

    if appointment.estado != CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
        return json_response({"detail": "Solo se pueden confirmar citas pendientes de confirmación."}, status=400)

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON válido."}, status=400)

    captured_template = (payload.get("template") or "").strip()
    try:
        quality = int(payload.get("quality") or 0)
    except (TypeError, ValueError):
        quality = 0
    enrollment = HuellaBiometricaCliente.objects.filter(
        cliente=appointment.operacion.paciente,
        activo=True,
    ).first()

    if not enrollment:
        return json_response({"detail": "El cliente no tiene una huella biometrica registrada."}, status=400)
    if not captured_template:
        return json_response({"detail": "Debes capturar la huella antes de confirmar la cita."}, status=400)
    if quality < 60:
        return json_response({"detail": "La calidad de captura simulada es insuficiente."}, status=400)
    if captured_template != enrollment.template_biometrico:
        return json_response({"detail": "La huella capturada no coincide con la huella registrada del cliente."}, status=400)

    appointment.estado = CitaMedica.Estado.CONFIRMADA
    appointment.verif_biometria = True
    appointment.metodo_confirmacion = CitaMedica.MetodoConfirmacion.BIOMETRICO
    appointment.save()
    EventoConfirmacionCita.objects.create(
        cita=appointment,
        paciente=appointment.operacion.paciente,
        sucursal=appointment.sucursal,
        metodo=EventoConfirmacionCita.Metodo.BIOMETRICO,
        confirmado_en=timezone.now(),
        ip_origen=_request_ip(request),
    )

    return json_response(
        {
            "detail": "La cita fue confirmada con huella biometrica simulada.",
            "appointment": {
                "id": f"CIT-{appointment.pk:04d}",
                "rawId": appointment.pk,
                "dateTime": _datetime_label(appointment.fecha_hora),
                "operation": procedure_name(appointment.operacion),
                "specialist": "Sin asignar",
                "status": appointment.get_estado_display(),
                "biometricStatus": "Validada",
                "confirmedAt": _datetime_label(appointment.fecha_confirmacion_biometrica),
            },
            "operation": _operation_detail(appointment.operacion),
        }
    )


@require_POST
@admin_required
@transaction.atomic
def admin_cancel_appointment_verification(request, appointment_id):
    appointment = (
        CitaMedica.objects.select_related(
            "operacion__paciente__usuario",
            "operacion__servicio_config__tipo_servicio",
            "operacion__servicio_config__proc_estetico",
        )
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        return json_response({"detail": "No encontramos la cita solicitada."}, status=404)
    if appointment.estado != CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
        return json_response({"detail": "Solo se puede cancelar la verificacion de citas pendientes."}, status=400)

    appointment.estado = CitaMedica.Estado.PROGRAMADA
    appointment.verif_biometria = False
    appointment.save(update_fields=["estado", "verif_biometria", "updated_at"])

    return json_response({
        "detail": "La verificacion fue cancelada. La cita volvio a estado Programada.",
        "appointment": {
            "id": f"CIT-{appointment.pk:04d}",
            "rawId": appointment.pk,
            "dateTime": _datetime_label(appointment.fecha_hora),
            "operation": procedure_name(appointment.operacion),
            "specialist": "Sin asignar",
            "status": appointment.get_estado_display(),
        },
    })


@require_POST
@admin_required
def admin_crear_prospecto(request):
    def _capitalize_first_letter(value):
        text = (value or "").strip()
        if not text:
            return ""
        return text[:1].upper() + text[1:]

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON válido."}, status=400)

    primer_nombre = _capitalize_first_letter(payload.get("primerNombre") or payload.get("nombres"))
    segundo_nombre = _capitalize_first_letter(payload.get("segundoNombre"))
    apellido_paterno = _capitalize_first_letter(payload.get("apellidoPaterno") or payload.get("apellidos"))
    apellido_materno = _capitalize_first_letter(payload.get("apellidoMaterno"))
    telefono = (payload.get("telefono") or "").strip()
    observaciones = (payload.get("observaciones") or "").strip()
    estado = (payload.get("estado") or Prospecto.Estado.PASAJERO).strip()

    errors = {}
    if not primer_nombre:
        errors["primerNombre"] = "El primer nombre es obligatorio."
    if not apellido_paterno:
        errors["apellidoPaterno"] = "El apellido paterno es obligatorio."
    if estado not in {Prospecto.Estado.PASAJERO, Prospecto.Estado.DESCARTADO}:
        errors["estado"] = "Solo puedes crear prospectos en estado pasajero o descartado."

    if errors:
        return json_response({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)

    branch = get_user_branch(request)
    if not branch:
        return json_response(
            {"detail": "No encontramos una sucursal activa para registrar el prospecto."},
            status=400,
        )

    prospecto = Prospecto.objects.create(
        primer_nombre=primer_nombre,
        segundo_nombre=segundo_nombre,
        apellido_paterno=apellido_paterno,
        apellido_materno=apellido_materno,
        telefono=telefono,
        estado=estado,
        observaciones=observaciones,
        registrado_por=request.user,
        sucursal_registro=branch,
    )

    return json_response(
        {
            "detail": "Prospecto registrado correctamente.",
            "prospect": _prospect_item(prospecto),
        },
        status=201,
    )


@require_GET
@admin_required
def admin_operaciones(request):
    mark_expired_programmed_appointments_as_no_show()
    branch = get_user_branch(request)
    operaciones_qs = (
        Operacion.objects.select_related(
            "paciente__usuario",
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
                queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
            ),
        ).order_by("-created_at")
    )
    if branch:
        operaciones_qs = operaciones_qs.filter(paciente__usuario__sucursal_id=branch)

    prospect_appointments_qs = CitaProspecto.objects.select_related("prospecto", "sucursal").order_by("-fecha_hora")
    if branch:
        prospect_appointments_qs = prospect_appointments_qs.filter(sucursal=branch)
    blocked_reservations = sum(
        1
        for operacion in operaciones_qs
        if operacion.estado == Operacion.Estado.EN_PROCESO and not operacion.puede_reservar
    )

    data = {
        "metrics": [
            metric(
                "operations-active",
                "Operaciones en proceso",
                operaciones_qs.filter(estado=Operacion.Estado.EN_PROCESO).count(),
                "Tratamientos actualmente vigentes",
                "primary",
            ),
            metric(
                "operations-finished",
                "Operaciones finalizadas",
                operaciones_qs.filter(estado=Operacion.Estado.FINALIZADA).count(),
                "Historial clinico",
                "success",
            ),
            metric(
                "operations-blocked",
                "Reservas bloqueadas",
                blocked_reservations,
                "Sin sesiones libres",
                "danger",
            ),
        ],
        "operations": [
            *[_operation_card(operacion) for operacion in operaciones_qs],
            *[_prospect_appointment_operation_card(cita) for cita in prospect_appointments_qs],
        ],
    }
    return json_response(data)


@require_GET
@admin_required
def admin_operacion_detalle(request, operacion_id):
    mark_expired_programmed_appointments_as_no_show()
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
                queryset=CitaMedica.objects.select_related().order_by("fecha_hora"),
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
        return json_response({"detail": "No encontramos la operacion solicitada."}, status=404)

    return json_response({"operation": _operation_detail(operacion)})


@require_POST
@admin_required
@transaction.atomic
def admin_update_operation_details(request, operacion_id):
    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    operacion = Operacion.objects.select_for_update(of=("self",)).filter(pk=operacion_id).first()
    if not operacion:
        return json_response({"detail": "No encontramos la operacion solicitada."}, status=404)

    errors = {}
    sesiones_totales = _parse_payload_int(payload, "sessionsTotal", errors, min_value=1)
    consumed_sessions = (
        operacion.sesiones_confirmadas
        + operacion.sesiones_pendientes_confirmacion
        + operacion.reservas_activas
    )
    if sesiones_totales is not None and sesiones_totales < consumed_sessions:
        errors["sessionsTotal"] = (
            f"No puedes bajar de {consumed_sessions} sesion(es), porque ya estan confirmadas, "
            "reservadas o pendientes de biometria."
        )
    if errors:
        return json_response({"detail": "Corrige los datos de la operacion.", "errors": errors}, status=400)

    operacion.detalles_op = (payload.get("details") or "").strip()
    operacion.recomendaciones = (payload.get("recommendations") or "").strip()
    operacion.sesiones_totales = sesiones_totales
    operacion.save(update_fields=["detalles_op", "recomendaciones", "sesiones_totales", "updated_at"])
    operacion.paciente.actualizar_estado_automaticamente()

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
                queryset=CitaMedica.objects.select_related().order_by("fecha_hora"),
            ),
            Prefetch(
                "cuotas_plan_pagos",
                queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
            ),
        )
        .get(pk=operacion.pk)
    )
    return json_response({"detail": "La operacion fue actualizada correctamente.", "operation": _operation_detail(operacion)})


@require_POST
@admin_required
@transaction.atomic
def admin_update_operation_price_plan(request, operacion_id):
    """Update the price and payment plan of an operation.

    Modes:

    * Sin ``quotas``: redistribucion automatica del saldo restante entre
      las cuotas pendientes (comportamiento historico).
    * Con ``quotas`` (``[{nroCuota, montoProgramado, fechaVencimiento}, ...]``):
      edicion por cuota individual. Solo se permite editar cuotas no
      pagadas y sin comprobantes; la suma del nuevo monto pendiente + lo
      ya pagado debe cerrar exactamente con ``priceTotal``.
    """
    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    with transaction.atomic():
        operacion = (
            Operacion.objects.select_for_update(of=("self",))
            .prefetch_related("cuotas_plan_pagos__pagos_realizados")
            .filter(pk=operacion_id)
            .first()
        )
        if not operacion:
            return json_response({"detail": "No encontramos la operacion solicitada."}, status=404)

        errors = {}
        new_price = _parse_payload_decimal(payload, "priceTotal", errors, min_value=Decimal("0.01"))
        new_quota_count = _parse_payload_int(payload, "quotaCount", errors, min_value=1)
        if errors:
            return json_response(
                {"detail": "Corrige los datos del plan de pagos.", "errors": errors}, status=400
            )

        incoming_quotas = payload.get("quotas") or []

        cuotas = list(operacion.cuotas_plan_pagos.all())
        paid_total = sum(
            (
                pago.monto_pagado
                for cuota in cuotas
                for pago in cuota.pagos_realizados.all()
                if pago.estado_verificacion == PagoRealizado.EstadoVerificacion.APROBADO
            ),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))
        paid_quotas = [cuota for cuota in cuotas if cuota.estado == CuotaPlanPago.Estado.PAGADO]
        unpaid_quotas = [cuota for cuota in cuotas if cuota.estado != CuotaPlanPago.Estado.PAGADO]
        # ``locked_unpaid`` son las cuotas que NO pueden editarse: estan
        # pendientes y tienen un comprobante en revision. Comprobantes
        # RECHAZADO o CANCELADO no cuentan (no hay revision abierta).
        locked_unpaid = [
            cuota
            for cuota in unpaid_quotas
            if cuota.pagos_realizados.filter(
                estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
            ).exists()
        ]

        if new_price < paid_total:
            errors["priceTotal"] = f"El nuevo precio no puede ser menor a lo ya pagado: Bs {paid_total:.2f}."
        if new_quota_count < len(paid_quotas):
            errors["quotaCount"] = (
                f"El numero de cuotas no puede ser menor a las {len(paid_quotas)} cuota(s) ya pagadas."
            )
        # ``locked_unpaid`` solo bloquea el modo automatico (sin
        # ``quotas[]``): si hay un comprobante en revision pendiente,
        # no redistribuimos el plan entero sin que el admin lo sepa.
        # En el modo edicion por cuota, el bloqueo se aplica por item
        # dentro del loop (mas granular: una cuota con comprobante
        # pendiente no impide editar las demas).
        if locked_unpaid and not incoming_quotas:
            errors["quotaCount"] = (
                "Hay cuotas no pagadas con comprobantes en revision. "
                "Resuelve o retira esos comprobantes antes de redistribuir el plan."
            )
        if errors:
            return json_response(
                {"detail": "No se pudo redistribuir el plan de pagos.", "errors": errors},
                status=400,
            )

        # Modo edicion por cuota
        if incoming_quotas:
            if not isinstance(incoming_quotas, list):
                return json_response(
                    {"detail": "El campo 'quotas' debe ser una lista."},
                    status=400,
                )
            # Validar el shape de cada item.
            item_errors: dict[str, str] = {}
            items: list[dict] = []
            for index, raw_item in enumerate(incoming_quotas):
                if not isinstance(raw_item, dict):
                    item_errors[f"quotas.{index}"] = "Cada cuota debe ser un objeto."
                    continue
                item = {}
                nro = _parse_payload_int(raw_item, "nroCuota", item_errors, min_value=1)
                if not nro:
                    continue
                # Si el campo estaba mal, ya se reporto arriba; evitamos
                # pisar la key con la del item.
                item_errors.pop(f"quotas.{index}.nroCuota", None)
                # Renombramos para mantener el traceback del campo
                # correcto en la respuesta final.
                if f"quotas.{index}.nroCuota" in item_errors:
                    item_errors[f"quotas.{index}.nroCuota"] = item_errors.pop("nroCuota")

                raw_monto = raw_item.get("montoProgramado")
                try:
                    monto = Decimal(str(raw_monto)) if raw_monto is not None else None
                except (InvalidOperation, TypeError, ValueError):
                    item_errors[f"quotas.{index}.montoProgramado"] = "Monto invalido."
                    monto = None
                if monto is not None and monto < Decimal("0"):
                    item_errors[f"quotas.{index}.montoProgramado"] = (
                        "El monto debe ser mayor o igual a 0."
                    )

                raw_fecha = raw_item.get("fechaVencimiento")
                try:
                    fecha = date.fromisoformat(str(raw_fecha)) if raw_fecha else None
                except (TypeError, ValueError):
                    item_errors[f"quotas.{index}.fechaVencimiento"] = "Fecha invalida (YYYY-MM-DD)."
                    fecha = None
                if not fecha and "fechaVencimiento" not in str(item_errors):
                    item_errors[f"quotas.{index}.fechaVencimiento"] = "Fecha obligatoria (YYYY-MM-DD)."

                if item_errors:
                    continue
                item = {"nroCuota": nro, "montoProgramado": monto, "fechaVencimiento": fecha}
                items.append(item)
            if item_errors:
                return json_response(
                    {"detail": "Corrige los datos de las cuotas.", "errors": item_errors},
                    status=400,
                )

            # Verificar cada item. Hay dos tipos:
            # - ``cuota existente editable``: nro_cuota esta en ``cuotas_by_number``
            #   y la cuota esta pendiente y sin comprobantes. Se edita in-place.
            # - ``cuota a crear``: el admin agrega UNA cuota nueva al final
            #   del plan. El nro_cuota tiene que ser exactamente
            #   ``max_existing_nro + 1`` (no permitimos huecos: facilita
            #   futuras ediciones y elimina ambiguedad con quotas ya
            #   borradas). Si el admin quiere agregar dos a la vez, lo
            #   hara en dos llamadas separadas.
            #
            # Caso especial: si TODOS los items son nuevos Y hay
            # exactamente UNO, es el flujo "agregar 1 sola cuota". En
            # ese modo NO exigimos que la suma cierre con el precio
            # total (el admin ira agregando mas cuotas despues); solo
            # validamos que el monto de la cuota no supere el precio
            # total y que la operacion tenga suficiente saldo pendiente
            # para cubrirlo.
            cuotas_by_number = {cuota.nro_cuota: cuota for cuota in cuotas}
            max_existing_nro = max((c.nro_cuota for c in cuotas), default=0)
            new_items_proposed = [it for it in items if it["nroCuota"] not in cuotas_by_number]
            existing_items_proposed = [it for it in items if it["nroCuota"] in cuotas_by_number]
            is_single_add_mode = (
                len(items) == 1
                and len(new_items_proposed) == 1
                and len(existing_items_proposed) == 0
            )

            field_errors: dict[str, str] = {}
            new_pending_sum = Decimal("0.00")
            seen_numbers = set()
            for index, item in enumerate(items):
                nro = item["nroCuota"]
                if nro in seen_numbers:
                    field_errors[f"quotas.{index}.nroCuota"] = (
                        f"La cuota #{nro} aparece mas de una vez."
                    )
                    continue
                seen_numbers.add(nro)
                cuota = cuotas_by_number.get(nro)
                if cuota is None:
                    # Cuota a crear: exactamente ``max + 1``.
                    expected_nro = max_existing_nro + 1
                    if nro != expected_nro:
                        field_errors[f"quotas.{index}.nroCuota"] = (
                            f"Para agregar una cuota nueva, su numero debe ser "
                            f"{expected_nro} (el siguiente libre del plan)."
                        )
                        continue
                else:
                    if cuota.estado == CuotaPlanPago.Estado.PAGADO:
                        field_errors[f"quotas.{index}.nroCuota"] = (
                            f"La cuota #{nro} ya fue pagada y no se puede editar."
                        )
                        continue
                    # Bloqueo solo si hay un comprobante en revision
                    # (``PENDIENTE``). Los comprobantes RECHAZADO o
                    # CANCELADO no bloquean la edicion: la cuota sigue
                    # pendiente y el admin puede reasignar monto/fecha.
                    has_pending_review = cuota.pagos_realizados.filter(
                        estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
                    ).exists()
                    if has_pending_review:
                        field_errors[f"quotas.{index}.nroCuota"] = (
                            f"La cuota #{nro} tiene un comprobante pendiente de revision y no se puede editar."
                        )
                        continue
                # Limite "no mayor al monto del tratamiento": cada item
                # nuevo debe ser <= precio total (proteccion basica para
                # que el admin no meta una sola cuota que ya supere el
                # total del tratamiento por confusion).
                if cuota is None and item["montoProgramado"] > new_price:
                    field_errors[f"quotas.{index}.montoProgramado"] = (
                        f"El monto (Bs {item['montoProgramado']:.2f}) no puede ser mayor "
                        f"al precio total del tratamiento (Bs {new_price:.2f})."
                    )
                    continue
                new_pending_sum += item["montoProgramado"].quantize(Decimal("0.01"))
            if field_errors:
                return json_response(
                    {"detail": "No se pudo actualizar el plan de pagos.", "errors": field_errors},
                    status=400,
                )

            # Modo batch: validamos por item individual arriba (PAGADA
            # bloquea, comprobante PENDIENTE bloquea, monto > precio_total
            # bloquea solo para cuotas NUEVAS). No exigimos que la suma
            # de los items pendientes cierre con el saldo del tratamiento
            # (``new_price - paid_total``): el admin puede editar una o
            # varias cuotas libremente y el saldo restante queda
            # "descubierto" hasta que agregue las cuotas que faltan via
            # el flujo "Agregar cuota" (single-add). Esto refleja el uso
            # real: el admin ajusta UNA cuota sin redistribuir todo el
            # plan.
            #
            # Unico tope del batch: la suma de TODAS las pendientes
            # (items del batch + cuotas pendientes existentes que el
            # admin no toco) no puede EXCEDER el precio total. Si la
            # suma lo supera, hay "sobrecuota" que no tiene sentido
            # cubrir. Por debajo si se permite (saldo pendiente queda
            # sin asignar).
            #
            # Esto cubre el caso de single-add: el item nuevo + las
            # pendientes existentes se suman para validar el tope. Si
            # el admin intenta meter una sola cuota de Bs 300 con un
            # tratamiento de Bs 850 que ya tiene una cuota de Bs 600,
            # la suma seria 900 > 850 y se rechaza.
            incoming_nros = {item["nroCuota"] for item in items}
            existing_untouched_sum = sum(
                (cuota.monto_programado or Decimal("0.00"))
                for cuota in unpaid_quotas
                if cuota.nro_cuota not in incoming_nros
            )
            total_after_save = new_pending_sum + existing_untouched_sum
            if total_after_save > new_price:
                return json_response(
                    {
                        "detail": "La suma de los montos de las cuotas supera al precio total del tratamiento.",
                        "errors": {
                            "quotas": (
                                f"La suma de las cuotas pendientes seria Bs {total_after_save:.2f} "
                                f"y no puede ser mayor al precio total del tratamiento "
                                f"(Bs {new_price:.2f})."
                            )
                        },
                    },
                    status=400,
                )
            # bloquea solo para cuotas NUEVAS). No exigimos que la suma
            # de los items pendientes cierre con el saldo del tratamiento
            # (``new_price - paid_total``): el admin puede editar una o
            # varias cuotas libremente y el saldo restante queda
            # "descubierto" hasta que agregue las cuotas que faltan via
            # el flujo "Agregar cuota" (single-add). Esto refleja el uso
            # real: el admin ajusta UNA cuota sin redistribuir todo el
            # plan.
            #
            # El modo single-add sigue validando monto <= new_price
            # arriba (el chequeo esta dentro del loop y se salta para
            # items que no son nuevos).

            # Aplicar los cambios. Para los items que apuntan a una cuota
            # existente, editamos in-place; los que tienen ``nroCuota``
            # nuevo los creamos como filas frescas. Los nuevos siempre
            # arrancan como "Pendiente" (los pagos se registran despues).
            edited_items_by_number = {item["nroCuota"]: item for item in items if item["nroCuota"] in cuotas_by_number}
            for nro, item in edited_items_by_number.items():
                cuota = cuotas_by_number[nro]
                cuota.monto_programado = item["montoProgramado"]
                cuota.fecha_vencimiento = item["fechaVencimiento"]
                cuota.save(update_fields=["monto_programado", "fecha_vencimiento", "updated_at"])

            new_items = [item for item in items if item["nroCuota"] not in cuotas_by_number]
            for item in sorted(new_items, key=lambda it: it["nroCuota"]):
                CuotaPlanPago.objects.create(
                    operacion=operacion,
                    nro_cuota=item["nroCuota"],
                    monto_programado=item["montoProgramado"],
                    fecha_vencimiento=item["fechaVencimiento"],
                )

            update_fields = []
            if not is_single_add_mode:
                operacion.precio_total = new_price
                update_fields.append("precio_total")
            # Las cuotas nuevas se numeran como max_existing + 1 (regla
            # validada arriba), asi que el total nuevo es el nro maximo.
            resulting_quota_count = max_existing_nro + len(new_items)
            if operacion.cuotas_totales != resulting_quota_count:
                operacion.cuotas_totales = resulting_quota_count
                update_fields.append("cuotas_totales")
            if update_fields:
                update_fields.append("updated_at")
                operacion.save(update_fields=update_fields)
            operacion.paciente.actualizar_estado_automaticamente()
        else:
            # Redistribucion automatica sobre el saldo restante.
            remaining_amount = (new_price - paid_total).quantize(Decimal("0.01"))
            remaining_quota_count = new_quota_count - len(paid_quotas)
            if remaining_quota_count == 0 and remaining_amount > 0:
                return json_response(
                    {
                        "detail": "No se pudo redistribuir el plan de pagos.",
                        "errors": {"quotaCount": "Necesitas al menos una cuota pendiente para el saldo restante."},
                    },
                    status=400,
                )

            existing_due_dates = [
                cuota.fecha_vencimiento
                for cuota in sorted(unpaid_quotas, key=lambda item: item.nro_cuota)
            ]
            latest_due_date = max(
                [cuota.fecha_vencimiento for cuota in cuotas],
                default=timezone.localdate(),
            )
            while len(existing_due_dates) < remaining_quota_count:
                latest_due_date = latest_due_date + timedelta(days=30)
                existing_due_dates.append(latest_due_date)

            for cuota in unpaid_quotas:
                cuota.delete()

            next_quota_number = max([cuota.nro_cuota for cuota in paid_quotas], default=0) + 1
            for index, amount in enumerate(split_amount(remaining_amount, remaining_quota_count)):
                CuotaPlanPago.objects.create(
                    operacion=operacion,
                    nro_cuota=next_quota_number + index,
                    fecha_vencimiento=existing_due_dates[index],
                    monto_programado=amount,
                )

            operacion.precio_total = new_price
            operacion.cuotas_totales = new_quota_count
            operacion.save(update_fields=["precio_total", "cuotas_totales", "updated_at"])
            operacion.paciente.actualizar_estado_automaticamente()

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
                queryset=CitaMedica.objects.select_related().order_by("fecha_hora"),
            ),
            Prefetch(
                "cuotas_plan_pagos",
                queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
            ),
        )
        .get(pk=operacion.pk)
    )
    return json_response({
        "detail": "El precio y las cuotas fueron actualizados correctamente.",
        "operation": _operation_detail(operacion),
    })


@require_POST
@admin_required
@transaction.atomic
def admin_delete_operation_quota(request, operacion_id):
    """Elimina UNA cuota del plan de pagos.

    Reglas (alineadas con la edicion batch de `actualizar-precio`):
    - Solo cuotas no PAGADAS (las pagadas son inmutables).
    - Solo cuotas sin comprobante en revision (PENDIENTE). Comprobantes
      RECHAZADO o CANCELADO NO bloquean.
    - Compacata la numeracion: si eliminas la cuota #2 de (1, 2, 3, 4, 5),
      las demas se renumeran (3 -> 2, 4 -> 3, 5 -> 4) para mantener la
      regla "cuotas nuevas = max + 1".
    """
    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    operacion = (
        Operacion.objects.select_for_update(of=("self",))
        .prefetch_related("cuotas_plan_pagos__pagos_realizados")
        .filter(pk=operacion_id)
        .first()
    )
    if not operacion:
        return json_response({"detail": "No encontramos la operacion solicitada."}, status=404)

    if operacion.estado != Operacion.Estado.EN_PROCESO:
        return json_response(
            {"detail": "Solo las operaciones en proceso pueden eliminar cuotas."},
            status=400,
        )

    nro_cuota = _parse_payload_int(payload, "nroCuota", {}, min_value=1)
    if nro_cuota is None:
        return json_response(
            {"detail": "Debes indicar el numero de cuota a eliminar.", "errors": {"nroCuota": "Numero de cuota obligatorio."}},
            status=400,
        )

    cuota_a_eliminar = next(
        (cuota for cuota in operacion.cuotas_plan_pagos.all() if cuota.nro_cuota == nro_cuota),
        None,
    )
    if cuota_a_eliminar is None:
        return json_response(
            {"detail": f"No existe la cuota #{nro_cuota} en esta operacion."},
            status=404,
        )

    if cuota_a_eliminar.estado == CuotaPlanPago.Estado.PAGADO:
        return json_response(
            {"detail": f"La cuota #{nro_cuota} ya fue pagada y no se puede eliminar."},
            status=400,
        )

    has_pending_review = cuota_a_eliminar.pagos_realizados.filter(
        estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
    ).exists()
    if has_pending_review:
        return json_response(
            {
                "detail": (
                    f"La cuota #{nro_cuota} tiene un comprobante pendiente de revision. "
                    "Resolvelo o retiralo antes de eliminar la cuota."
                )
            },
            status=400,
        )

    # Compactar numeracion: las cuotas con nro > nro_cuota se renumeran
    # para llenar el hueco. Hacemos el DELETE primero para liberar el
    # slot del nro_cuota; luego renumeramos de mayor a menor (cada save
    # toma un slot que la iteracion anterior ya dejo libre) para no
    # violar el UniqueConstraint("operacion", "nro_cuota") en SQLite.
    cuota_a_eliminar.delete()

    # Renumerar de menor a mayor: cada save toma el slot que la
    # iteracion anterior dejo libre (la pk=N se renumera a N-1, y la
    # pk=N+1 ocupa ese mismo N apenas N+1 ya no esta alli).
    # ``list(...)`` materializa el queryset del prefetch para que las
    # iteraciones siguientes no re-consulten la BD.
    cuotas_a_renumerar = sorted(
        list(
            cuota
            for cuota in operacion.cuotas_plan_pagos.all()
            if cuota.nro_cuota > nro_cuota
        ),
        key=lambda c: c.nro_cuota,
    )
    for cuota in cuotas_a_renumerar:
        cuota.nro_cuota = cuota.nro_cuota - 1
        cuota.save(update_fields=["nro_cuota", "updated_at"])

    # ``cuotas_totales`` se decrementa al nuevo maximo (post-compactacion).
    # Filtramos por ``pk is not None`` porque el queryset del prefetch
    # cacheado en la instancia puede seguir conteniendo la cuota
    # eliminada (con pk=None) tras el delete().
    restantes = [c for c in operacion.cuotas_plan_pagos.all() if c.pk is not None]
    nuevo_max = max(
        (c.nro_cuota for c in restantes),
        default=0,
    )
    if operacion.cuotas_totales != nuevo_max:
        operacion.cuotas_totales = nuevo_max
        operacion.save(update_fields=["cuotas_totales", "updated_at"])

    operacion.paciente.actualizar_estado_automaticamente()

    # Refetch para devolver el shape consistente del detail.
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
                queryset=CitaMedica.objects.select_related().order_by("fecha_hora"),
            ),
            Prefetch(
                "cuotas_plan_pagos",
                queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
            ),
        )
        .get(pk=operacion.pk)
    )
    return json_response({
        "detail": f"Cuota #{nro_cuota} eliminada correctamente.",
        "operation": _operation_detail(operacion),
    })


@require_GET
@admin_required
def admin_pagos(request):
    branch = get_user_branch(request)
    status_filter = (request.GET.get("status") or "").strip().upper()
    search = (request.GET.get("search") or "").strip()

    today = timezone.localdate()
    try:
        month = int(request.GET.get("month") or today.month)
        year = int(request.GET.get("year") or today.year)
        start = date(year, month, 1)
    except (TypeError, ValueError):
        return json_response({"detail": "Mes o anio invalido."}, status=400)

    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    pagos_qs = (
        PagoRealizado.objects.select_related(
            "cuota__operacion__paciente__usuario",
            "cuota__operacion__servicio_config__proc_estetico",
            "verificado_por",
        ).filter(cuota__fecha_vencimiento__range=(start, end)).order_by("-created_at")
    )
    if branch:
        # Filtrar por la sucursal activa del cliente/operacion sin depender de citas,
        # para incluir pagos pendientes aunque la operacion aun no tenga agenda.
        pagos_qs = pagos_qs.filter(cuota__operacion__paciente__usuario__sucursal_id=branch).distinct()
    valid_statuses = {choice[0] for choice in PagoRealizado.EstadoVerificacion.choices}
    if status_filter and status_filter in valid_statuses:
        pagos_qs = pagos_qs.filter(estado_verificacion=status_filter)
    if search:
        pagos_qs = pagos_qs.filter(
            Q(cuota__operacion__paciente__usuario__primer_nombre__icontains=search)
            | Q(cuota__operacion__paciente__usuario__segundo_nombre__icontains=search)
            | Q(cuota__operacion__paciente__usuario__apellido_paterno__icontains=search)
            | Q(cuota__operacion__paciente__usuario__apellido_materno__icontains=search)
            | Q(cuota__operacion__servicio_config__proc_estetico__proceso__icontains=search)
            | Q(cuota__operacion__servicio_config__tipo_servicio__tipo__icontains=search)
        )
    pending_amount = sum(
        payment.monto_pagado
        for payment in pagos_qs
        if payment.estado_verificacion == PagoRealizado.EstadoVerificacion.PENDIENTE
    )
    cuotas_qs = CuotaPlanPago.objects.select_related(
        "operacion__paciente__usuario",
        "operacion__servicio_config__proc_estetico",
    ).prefetch_related("pagos_realizados").filter(fecha_vencimiento__range=(start, end)).order_by("fecha_vencimiento", "nro_cuota")
    if branch:
        cuotas_qs = cuotas_qs.filter(operacion__paciente__usuario__sucursal_id=branch).distinct()

    data = {
        "month": month,
        "year": year,
        "metrics": [
            metric(
                "payments-pending",
                "Pendientes de revisión",
                pagos_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE).count(),
                currency(pending_amount),
                "warning",
            ),
            metric(
                "payments-approved",
                "Pagos aprobados",
                pagos_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO).count(),
                "Impactan el estado de cuotas",
                "success",
            ),
            metric(
                "payments-observed",
                "Pagos observados",
                pagos_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.RECHAZADO).count(),
                "Requieren seguimiento administrativo",
                "danger",
            ),
            metric(
                "payments-total",
                "Pagos registrados",
                pagos_qs.count(),
                "Incluye historico completo del sistema",
                "primary",
            ),
        ],
        "paymentQrConfig": _payment_qr_config_item(ConfiguracionPagoQR.objects.filter(sucursal=branch).first()),
        "payments": [_payment_item(payment) for payment in pagos_qs],
        "quotas": [_admin_quota_item(cuota) for cuota in cuotas_qs],
    }
    return json_response(data)


@require_POST
@admin_required
def admin_update_payment_qr_config(request):
    qr_file = request.FILES.get("qrImage")
    instructions = (request.POST.get("instructions") or "").strip()

    branch = get_user_branch(request)
    config = ConfiguracionPagoQR.objects.filter(sucursal=branch).first()
    if not config:
        config = ConfiguracionPagoQR(sucursal=branch)

    if qr_file:
        config.imagen_qr = qr_file
    elif not config.imagen_qr:
        return json_response({"detail": "Debes adjuntar una imagen QR para guardar la configuracion."}, status=400)

    if instructions:
        config.instrucciones = instructions

    config.full_clean()
    config.save()

    return json_response(
        {
            "detail": "El QR de pago fue actualizado correctamente.",
            "paymentQrConfig": _payment_qr_config_item(config),
        }
    )


@require_POST
@admin_required
def admin_update_payment_status(request, payment_id):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    payment = (
        PagoRealizado.objects.select_related(
            "cuota__operacion__paciente__usuario",
            "cuota__operacion__servicio_config__proc_estetico",
            "verificado_por",
        )
        .filter(pk=payment_id)
        .first()
    )
    if not payment:
        return json_response({"detail": "No encontramos el pago solicitado."}, status=404)

    status_value = (payload.get("status") or "").strip().upper()
    note = (payload.get("note") or "").strip()
    valid_statuses = {
        PagoRealizado.EstadoVerificacion.PENDIENTE,
        PagoRealizado.EstadoVerificacion.APROBADO,
        PagoRealizado.EstadoVerificacion.RECHAZADO,
        PagoRealizado.EstadoVerificacion.CANCELADO,
    }
    if status_value not in valid_statuses:
        return json_response({"detail": "El estado solicitado no es valido."}, status=400)

    payment.estado_verificacion = status_value
    if status_value == PagoRealizado.EstadoVerificacion.PENDIENTE:
        payment.observacion_verificacion = ""
    else:
        payment.verificado_por = request.user
        payment.fecha_verificacion = timezone.now()
        payment.observacion_verificacion = note

    payment.save()
    payment = (
        PagoRealizado.objects.select_related(
            "cuota__operacion__paciente__usuario",
            "cuota__operacion__servicio_config__proc_estetico",
            "verificado_por",
        )
        .get(pk=payment.pk)
    )

    paciente_user = payment.cuota.operacion.paciente.usuario
    nro_cuota = payment.cuota.nro_cuota
    monto_pago = payment.monto_pagado
    procedimiento = payment.cuota.operacion.servicio_config.proc_estetico.proceso

    if status_value == PagoRealizado.EstadoVerificacion.APROBADO:
        create_notification(
            recipient=paciente_user,
            branch=payment.cuota.operacion.paciente.usuario.sucursal,
            type=Notification.Type.CLIENT_PAYMENT_CONFIRMED,
            title="Pago confirmado",
            message=f"El pago de la cuota Nro {nro_cuota} de monto Bs {monto_pago} del procedimiento {procedimiento} fue aprobado.",
            action_url="/cliente/pagos",
            source_event="payment.approved",
            source_entity_type="payment",
            source_entity_id=payment.id,
            created_by_type="admin",
            created_by_id=request.user.id,
        )
    elif status_value == PagoRealizado.EstadoVerificacion.RECHAZADO:
        create_notification(
            recipient=paciente_user,
            branch=payment.cuota.operacion.paciente.usuario.sucursal,
            type=Notification.Type.CLIENT_PAYMENT_REJECTED,
            title="Pago rechazado",
            message=f"El pago de la cuota Nro {nro_cuota} de monto Bs {monto_pago} del procedimiento {procedimiento} fue rechazado.",
            action_url="/cliente/pagos",
            source_event="payment.rejected",
            source_entity_type="payment",
            source_entity_id=payment.id,
            created_by_type="admin",
            created_by_id=request.user.id,
        )

    detail_map = {
        PagoRealizado.EstadoVerificacion.PENDIENTE: "El pago volvio a estado pendiente.",
        PagoRealizado.EstadoVerificacion.APROBADO: "El pago fue aprobado correctamente.",
        PagoRealizado.EstadoVerificacion.RECHAZADO: "El pago fue observado correctamente.",
        PagoRealizado.EstadoVerificacion.CANCELADO: "El pago fue cancelado correctamente.",
    }

    return json_response(
        {
            "detail": detail_map[status_value],
            "payment": _payment_item(payment),
        }
    )


@require_GET
@admin_required
def admin_gastos(request):
    branch = get_user_branch(request)
    if not branch:
        return json_response({"detail": "Selecciona una sucursal para consultar gastos."}, status=400)

    today = timezone.localdate()
    try:
        month = int(request.GET.get("month") or today.month)
        year = int(request.GET.get("year") or today.year)
        start = date(year, month, 1)
    except (TypeError, ValueError):
        return json_response({"detail": "Mes o anio invalido."}, status=400)

    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    expenses_qs = (
        GastoSucursal.objects.select_related("categoria", "sucursal", "registrado_por")
        .filter(sucursal=branch, fecha__range=(start, end))
        .order_by("-fecha", "-created_at")
    )
    expenses = list(expenses_qs)
    total_amount = sum((expense.gasto_total for expense in expenses), Decimal("0"))
    average_amount = total_amount / len(expenses) if expenses else Decimal("0")
    categories_count = len({expense.categoria_id for expense in expenses})

    return json_response(
        {
            "month": month,
            "year": year,
            "branch": {"id": branch.pk, "name": branch.nombre},
            "metrics": [
                metric("expenses-total", "Gasto del mes", currency(total_amount), f"{len(expenses)} registro(s)", "danger"),
                metric("expenses-count", "Gastos registrados", len(expenses), f"{categories_count} categoria(s)", "primary"),
                metric("expenses-average", "Promedio por gasto", currency(average_amount), "Calculado sobre el mes", "warning"),
            ],
            "categories": [
                _expense_category_item(category)
                for category in _expense_categories_queryset(active_only=True)
            ],
            "expenses": [_expense_item(expense) for expense in expenses],
        }
    )


@require_GET
@admin_required
def admin_gastos_categorias(request):
    return json_response(
        {
            "categories": [
                _expense_category_item(category)
                for category in _expense_categories_queryset(active_only=True)
            ]
        }
    )


@require_POST
@admin_required
def admin_gasto_crear(request):
    branch = get_user_branch(request)
    if not branch:
        return json_response({"detail": "Selecciona una sucursal para registrar gastos."}, status=400)

    try:
        expense = _parse_expense_payload(request)
        expense.sucursal = branch
        expense.registrado_por = request.user
        expense.save()
    except ValidationError as exc:
        return json_response({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)

    expense = GastoSucursal.objects.select_related("categoria", "sucursal", "registrado_por").get(pk=expense.pk)
    return json_response(
        {
            "detail": "Gasto registrado correctamente.",
            "expense": _expense_item(expense),
        },
        status=201,
    )


@require_POST
@admin_required
def admin_gasto_actualizar(request, expense_id):
    branch = get_user_branch(request)
    if not branch:
        return json_response({"detail": "Selecciona una sucursal para actualizar gastos."}, status=400)

    expense = GastoSucursal.objects.filter(pk=expense_id, sucursal=branch).first()
    if not expense:
        return json_response({"detail": "No encontramos el gasto solicitado en esta sucursal."}, status=404)

    try:
        expense = _parse_expense_payload(request, instance=expense)
        expense.save()
    except ValidationError as exc:
        return json_response({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)

    expense = GastoSucursal.objects.select_related("categoria", "sucursal", "registrado_por").get(pk=expense.pk)
    return json_response(
        {
            "detail": "Gasto actualizado correctamente.",
            "expense": _expense_item(expense),
        }
    )


@require_POST
@admin_required
def admin_gasto_eliminar(request, expense_id):
    branch = get_user_branch(request)
    if not branch:
        return json_response({"detail": "Selecciona una sucursal para eliminar gastos."}, status=400)

    expense = GastoSucursal.objects.filter(pk=expense_id, sucursal=branch).first()
    if not expense:
        return json_response({"detail": "No encontramos el gasto solicitado en esta sucursal."}, status=404)

    expense.delete()
    return json_response({"detail": "Gasto eliminado correctamente."})


@require_GET
@admin_required
def admin_catalogos(request):
    active_services = ServicioConfig.objects.filter(activo=True).count()
    active_service_types = TipoServicio.objects.filter(activo=True).count()
    active_groups = GrupoOpciones.objects.filter(activo=True).count()
    active_options = OpcionCatalogo.objects.filter(activo=True).count()

    data = {
        "catalogs": [
            _catalog_item(
                "todos-los-servicios",
                "Todos los servicios",
                ServicioConfig.objects.filter(activo=True).count(),
                "Servicios completos con precio base y procedimiento asociado",
            ),
            _catalog_item(
                "procedimientos-esteticos",
                "Procedimientos esteticos",
                ProcEstetico.objects.filter(activo=True).count(),
                f"{ServicioConfig.objects.filter(activo=True).count()} configuraciones activas de servicio",
            ),
            _catalog_item(
                "tipos-servicio",
                "Tipos de servicio",
                active_service_types,
                "Categorias comerciales visibles en operaciones y ventas",
            ),
            _catalog_item(
                "campos-ficha",
                "Campos de ficha",
                FichaCampo.objects.filter(activo=True).count(),
                f"{FichaCampo.objects.filter(activo=False).count()} campo(s) inactivos preservados",
            ),
            _catalog_item(
                "grupos-opciones",
                "Grupos de opciones",
                active_groups,
                f"{active_options} opcion(es) activas asociadas",
            ),
            _catalog_item(
                "patologias-cutaneas",
                "Patologias cutaneas",
                PatologiaCutanea.objects.filter(activo=True).count(),
                "Disponibles para analisis estetico y reportes",
            ),
            _catalog_item(
                "especialidades",
                "Especialidades",
                Especialidad.objects.filter(activo=True).count(),
                "Catálogo usado para especialistas y asignaciones del equipo",
            ),
            _catalog_item(
                "categorias-gasto",
                "Categorias de gasto",
                CategoriaGasto.objects.filter(activo=True).count(),
                "Clasificación administrativa para gastos por sucursal",
            ),
            _catalog_item(
                "sectores",
                "Sectores",
                Sector.objects.filter(activo=True).count(),
                "Sectores especializados para agrupar secciones de ficha clínica",
            ),
            _catalog_item(
                "secciones-ficha",
                "Secciones",
                FichaSeccion.objects.filter(activo=True).count(),
                "Secciones de ficha clínica que se pueden asociar a sectores y procedimientos",
            ),
        ],
    }
    return json_response(data)


@require_GET
@admin_required
def admin_catalogo_detalle(request, catalog_key):
    q = request.GET.get("q", "")
    active = request.GET.get("active", "all")
    if active not in ("true", "false", "all"):
        return json_response(
            {"detail": "El parametro active solo acepta true, false o all."},
            status=400,
        )
    sector_id = request.GET.get("sector", "")
    proc_estetico_id = request.GET.get("proc_estetico", "")
    try:
        data = _catalog_page_data(
            catalog_key,
            q=q,
            active=active,
            sector_id=sector_id,
            proc_estetico_id=proc_estetico_id,
        )
    except KeyError:
        return json_response({"detail": "El catalogo solicitado no existe."}, status=404)
    return json_response(data)


@require_POST
@_admin_principal_required
def admin_catalogo_crear(request, catalog_key):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    try:
        obj = _catalog_parse_payload(catalog_key, payload)
        obj.full_clean()
        obj.save()
    except KeyError:
        return json_response({"detail": "El catalogo solicitado no existe."}, status=404)
    except ValidationError as exc:
        return json_response({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)
    except IntegrityError:
        return json_response({"detail": "Ya existe un registro con esos datos clave."}, status=400)

    return json_response(
        {
            "detail": "Registro creado correctamente.",
            "item": next(item for item in _catalog_page_data(catalog_key)["items"] if item["id"] == obj.pk),
        },
        status=201,
    )


@require_POST
@_admin_principal_required
def admin_catalogo_actualizar(request, catalog_key, item_id):
    instance = _catalog_get_instance(catalog_key, item_id)
    if not instance:
        return json_response({"detail": "No encontramos el registro solicitado."}, status=404)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    try:
        obj = _catalog_parse_payload(catalog_key, payload, instance=instance)
        obj.full_clean()
        obj.save()
    except KeyError:
        return json_response({"detail": "El catalogo solicitado no existe."}, status=404)
    except ValidationError as exc:
        return json_response({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)
    except IntegrityError:
        return json_response({"detail": "Ya existe un registro con esos datos clave."}, status=400)

    return json_response(
        {
            "detail": "Registro actualizado correctamente.",
            "item": next(item for item in _catalog_page_data(catalog_key)["items"] if item["id"] == obj.pk),
        }
    )


@require_POST
@_admin_principal_required
def admin_catalogo_estado(request, catalog_key, item_id):
    instance = _catalog_get_instance(catalog_key, item_id)
    if not instance:
        return json_response({"detail": "No encontramos el registro solicitado."}, status=404)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    active = payload.get("active")
    if not isinstance(active, bool):
        return json_response({"detail": "Debes indicar si el registro queda activo o inactivo."}, status=400)

    instance.activo = active
    instance.save(update_fields=["activo", "updated_at"])

    return json_response(
        {
            "detail": "Estado actualizado correctamente.",
            "item": next(item for item in _catalog_page_data(catalog_key)["items"] if item["id"] == instance.pk),
        }
    )


@require_GET
@admin_required
def admin_equipo(request):
    branch = get_user_branch(request)
    staff_qs = (
        Especialista.objects.select_related("usuario")
        .prefetch_related(
            "especialidades_rel__especialidad",
        )
        .order_by("-usuario__is_active", "usuario__primer_nombre", "usuario__apellido_paterno")
    )
    
    if branch:
        staff_qs = staff_qs.filter(sucursal_base=branch)

    upcoming_appointments_qs = CitaMedica.objects.filter(fecha_hora__gte=timezone.now())
    pending_biometric_qs = CitaMedica.objects.filter(
        estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION
    )
    
    if branch:
        upcoming_appointments_qs = upcoming_appointments_qs.filter(sucursal=branch)
        pending_biometric_qs = pending_biometric_qs.filter(sucursal=branch)

    active_staff = staff_qs.filter(usuario__is_active=True).count()
    inactive_staff = staff_qs.filter(usuario__is_active=False).count()

    data = {
        "metrics": [
            metric(
                "team-specialists",
                "Especialistas activos",
                active_staff,
                "Usuarios con perfil operativo asignado",
                "primary",
            ),
            metric(
                "team-specialties",
                "Especialidades",
                Especialidad.objects.filter(activo=True).count(),
                "Catálogo editable desde administración",
                "success",
            ),
            metric(
                "team-agenda",
                "Citas futuras",
                upcoming_appointments_qs.count(),
                "Carga agendada a partir de hoy",
                "warning",
            ),
            metric(
                "team-biometric",
                "Pendientes de biometria",
                pending_biometric_qs.count(),
                "Citas realizadas sin cierre final",
                "danger",
            ),
            metric(
                "team-inactive",
                "Especialistas inactivos",
                inactive_staff,
                "Sin disponibilidad publicada",
                "warning",
            ),
        ],
        "staff": [_staff_item(especialista) for especialista in staff_qs],
        "specialtyOptions": [
            _staff_specialty_option(item)
            for item in Especialidad.objects.filter(activo=True).order_by("orden", "nombre")
        ],
    }
    return json_response(data)


@require_GET
@_admin_principal_required
def admin_branch_admins_list(request):
    admins = Usuario.objects.select_related("sucursal").filter(rol__rol="ADMIN_SUCURSAL").order_by("-is_active", "username")
    return json_response({"admins": [_branch_admin_item(admin) for admin in admins]})


@require_POST
@_admin_principal_required
@transaction.atomic
def admin_branch_admins_create(request):
    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    username = (payload.get("username") or "").strip()
    primer_nombre = _capitalize_first_letter(payload.get("primerNombre"))
    apellido_paterno = _capitalize_first_letter(payload.get("apellidoPaterno"))
    password = payload.get("password") or ""
    fecha_nacimiento_raw = (payload.get("fechaNacimiento") or "").strip()
    if not username or not primer_nombre or not apellido_paterno or not password or not fecha_nacimiento_raw:
        return json_response({"detail": "username, primerNombre, apellidoPaterno, password y fechaNacimiento son obligatorios."}, status=400)
    try:
        fecha_nacimiento = date.fromisoformat(fecha_nacimiento_raw)
    except ValueError:
        return json_response({"detail": "fechaNacimiento debe tener formato YYYY-MM-DD."}, status=400)
    if Usuario.objects.filter(username=username).exists():
        return json_response({"detail": "Este nombre de usuario ya existe."}, status=409)

    user = Usuario(
        username=username,
        email=(payload.get("email") or "").strip(),
        primer_nombre=primer_nombre,
        segundo_nombre=_capitalize_first_letter(payload.get("segundoNombre")),
        apellido_paterno=apellido_paterno,
        apellido_materno=_capitalize_first_letter(payload.get("apellidoMaterno")),
        rol=_get_branch_admin_role(),
        telefono=(payload.get("telefono") or "").strip(),
        fecha_nacimiento=fecha_nacimiento,
        is_active=False,
        sucursal=None,
    )
    user.set_password(password)
    user.save()
    return json_response({"detail": "Administrador de sucursal creado como inactivo.", "admin": _branch_admin_item(user)}, status=201)


@require_GET
@_admin_principal_required
def admin_branch_admins_detail(request, user_id):
    user = get_object_or_404(Usuario.objects.select_related("sucursal"), pk=user_id, rol__rol="ADMIN_SUCURSAL")
    return json_response({"admin": _branch_admin_item(user)})


@require_POST
@_admin_principal_required
@transaction.atomic
def admin_branch_admins_update(request, user_id):
    user = get_object_or_404(Usuario.objects.select_related("sucursal"), pk=user_id, rol__rol="ADMIN_SUCURSAL")
    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    for field, key in (
        ("username", "username"),
        ("email", "email"),
        ("telefono", "telefono"),
    ):
        if key in payload:
            setattr(user, field, (payload.get(key) or "").strip())
    if "fechaNacimiento" in payload:
        fecha_nacimiento_raw = (payload.get("fechaNacimiento") or "").strip()
        if fecha_nacimiento_raw:
            try:
                user.fecha_nacimiento = date.fromisoformat(fecha_nacimiento_raw)
            except ValueError:
                return json_response({"detail": "fechaNacimiento debe tener formato YYYY-MM-DD."}, status=400)
        else:
            user.fecha_nacimiento = None
    new_password = (payload.get("password") or "").strip()
    if new_password:
        user.set_password(new_password)
    update_fields=["username", "email", "telefono", "fecha_nacimiento", "updated_at"]
    if new_password:
        update_fields.append("password")
    user.save(update_fields=update_fields)
    return json_response({"detail": "Administrador de sucursal actualizado.", "admin": _branch_admin_item(user)})


@require_POST
@_admin_principal_required
@transaction.atomic
def admin_branch_admins_toggle(request, user_id):
    user = get_object_or_404(Usuario.objects.select_related("sucursal"), pk=user_id, rol__rol="ADMIN_SUCURSAL")
    payload = load_payload(request) or {}
    active = payload.get("active")
    if not isinstance(active, bool):
        return json_response({"detail": "Debes indicar active true/false."}, status=400)
    old_branch = user.sucursal
    user.is_active = active
    if not active:
        if old_branch and old_branch.activa:
            has_other_admin = Usuario.objects.filter(
                rol__rol="ADMIN_SUCURSAL",
                is_active=True,
                sucursal=old_branch,
            ).exclude(pk=user.pk).exists() or Usuario.objects.filter(
                rol__rol="ADMIN_PRINCIPAL",
                is_active=True,
                sucursal=old_branch,
            ).exists()
            if not has_other_admin:
                return json_response({"detail": "No puedes inactivar este administrador porque la sucursal activa quedaría sin admin."}, status=409)
        user.sucursal = None
        user.save(update_fields=["is_active", "sucursal", "updated_at"])
    else:
        user.save(update_fields=["is_active", "updated_at"])
    if old_branch:
        _log_branch_admin_audit(
            request=request,
            branch=old_branch,
            action=BranchAdminAuditLog.Action.TOGGLE_BRANCH_ADMIN,
            detail=f"Estado de admin sucursal {user.username} actualizado a {'activo' if active else 'inactivo'}.",
            metadata={"adminUserId": user.id, "active": active},
        )
    return json_response({"detail": "Estado actualizado.", "admin": _branch_admin_item(user)})


@require_POST
@admin_required
@transaction.atomic
def admin_crear_especialista(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    errors = {}
    parsed = _parse_staff_payload(request, payload, errors)
    if errors:
        return json_response({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)

    usuario = parsed["usuario"]
    especialista = parsed["especialista"]
    specialties = parsed["specialties"]

    try:
        usuario.full_clean()
        usuario.save()
        especialista.usuario = usuario
        especialista.full_clean()
        especialista.save()
    except ValidationError as exc:
        return json_response({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)
    except IntegrityError:
        return json_response({"detail": "Ya existe un especialista o usuario con esos datos."}, status=400)

    EspecialistaEspecialidad.objects.bulk_create(
        [
            EspecialistaEspecialidad(especialista=especialista, especialidad=especialidad)
            for especialidad in specialties
        ]
    )

    especialista = (
        Especialista.objects.select_related("usuario")
        .prefetch_related("especialidades_rel__especialidad")
        .get(pk=especialista.pk)
    )

    return json_response(
        {
            "detail": "Especialista creado correctamente.",
            "staffMember": _staff_item(especialista),
        },
        status=201,
    )


@require_POST
@admin_required
@transaction.atomic
def admin_actualizar_especialista(request, specialist_id):
    especialista = (
        Especialista.objects.select_related("usuario")
        .prefetch_related("especialidades_rel")
        .filter(pk=specialist_id)
        .first()
    )
    if not especialista:
        return json_response({"detail": "No encontramos el especialista solicitado."}, status=404)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    errors = {}
    old_branch_id = especialista.sucursal_base_id
    parsed = _parse_staff_payload(request, payload, errors, instance=especialista)
    if errors:
        return json_response({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)

    usuario = parsed["usuario"]
    especialista = parsed["especialista"]
    specialties = parsed["specialties"]

    try:
        usuario.full_clean()
        usuario.save()
        especialista.full_clean()
        especialista.save()
        
        # Limpiar horarios si la sucursal cambio
        if old_branch_id and especialista.sucursal_base_id != old_branch_id:
            _clear_specialist_availability(especialista)
            
    except ValidationError as exc:
        return json_response({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)
    except IntegrityError:
        return json_response({"detail": "Ya existe un especialista o usuario con esos datos."}, status=400)

    especialista.especialidades_rel.all().delete()
    EspecialistaEspecialidad.objects.bulk_create(
        [
            EspecialistaEspecialidad(especialista=especialista, especialidad=especialidad)
            for especialidad in specialties
        ]
    )

    especialista = (
        Especialista.objects.select_related("usuario")
        .prefetch_related("especialidades_rel__especialidad")
        .get(pk=especialista.pk)
    )

    return json_response(
        {
            "detail": "Especialista actualizado correctamente.",
            "staffMember": _staff_item(especialista),
        }
    )


@require_POST
@admin_required
@transaction.atomic
def admin_estado_especialista(request, specialist_id):
    especialista = Especialista.objects.select_related("usuario").filter(pk=specialist_id).first()
    if not especialista:
        return json_response({"detail": "No encontramos el especialista solicitado."}, status=404)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    active = payload.get("active")
    if not isinstance(active, bool):
        return json_response({"detail": "Debes indicar si el especialista quedará activo o inactivo."}, status=400)

    especialista.usuario.is_active = active
    especialista.usuario.save(update_fields=["is_active"])
    if not active:
        _clear_specialist_availability(especialista)

    especialista = (
        Especialista.objects.select_related("usuario")
        .prefetch_related("especialidades_rel__especialidad")
        .get(pk=especialista.pk)
    )

    return json_response(
        {
            "detail": "Especialista activado correctamente."
            if active
            else "Especialista desactivado y disponibilidad eliminada correctamente.",
            "staffMember": _staff_item(especialista),
        }
    )

@require_POST
@_admin_principal_required
@transaction.atomic
def admin_prospecto_migrar(request, prospecto_id):
    from customers.models import Prospecto
    from catalogs.models import Sucursal
    prospecto = get_object_or_404(Prospecto, pk=prospecto_id)
    
    try:
        payload = json.loads(request.body.decode("utf-8"))
        branch_id = payload.get("branchId")
    except:
        return json_response({"detail": "Payload invalido."}, status=400)
        
    branch = get_object_or_404(Sucursal, pk=branch_id)
    prospecto.sucursal_registro = branch
    prospecto.save(update_fields=["sucursal_registro", "updated_at"])
    
    return json_response({
        "detail": f"Prospecto migrado exitosamente a {branch.nombre}.",
        "branch": {"id": branch.id, "name": branch.nombre}
    })

@require_POST
@_admin_principal_required
@transaction.atomic
def admin_cliente_migrar(request, client_id):
    from customers.models import Cliente
    from catalogs.models import Sucursal
    cliente = get_object_or_404(Cliente, pk=client_id)
    
    try:
        payload = json.loads(request.body.decode("utf-8"))
        branch_id = payload.get("branchId")
    except:
        return json_response({"detail": "Payload invalido."}, status=400)
        
    branch = get_object_or_404(Sucursal, pk=branch_id)
    if _client_has_pending_reservations(cliente):
        return json_response(
            {
                "detail": (
                    "No se puede importar este cliente porque tiene reservas pendientes. "
                    "Cancela o completa sus citas programadas antes de cambiarlo de sucursal."
                )
            },
            status=400,
        )

    cliente.sucursal_origen = branch
    cliente.save(update_fields=["sucursal_origen", "updated_at"])
    
    return json_response({
        "detail": f"Cliente migrado exitosamente a {branch.nombre}.",
        "branch": {"id": branch.id, "name": branch.nombre}
    })

@require_POST
@_admin_principal_required
@transaction.atomic
def admin_equipo_cambiar_sucursal(request, user_id):
    from catalogs.models import Sucursal
    especialista = Especialista.objects.select_related("usuario").filter(pk=user_id).first()
    if especialista:
        user_to_move = especialista.usuario
    else:
        user_to_move = get_object_or_404(Usuario, pk=user_id)
        if hasattr(user_to_move, "especialista"):
            especialista = user_to_move.especialista
    
    try:
        payload = json.loads(request.body.decode("utf-8"))
        branch_id = payload.get("branchId")
    except:
        return json_response({"detail": "Payload invalido."}, status=400)
        
    branch = get_object_or_404(Sucursal, pk=branch_id)
    
    # Si es un usuario (Admin de sucursal)
    user_to_move.sucursal = branch
    user_to_move.save(update_fields=["sucursal", "updated_at"])
    
    # Si tambien tiene perfil de especialista, actualizar su sucursal base
    if especialista:
        old_branch_id = especialista.sucursal_base_id
        especialista.sucursal_base = branch
        especialista.save(update_fields=["sucursal_base", "updated_at"])
        if old_branch_id and old_branch_id != branch.pk:
            AgendaHabitualEspecialista.objects.filter(
                especialista=especialista,
                sucursal_id=old_branch_id,
            ).delete()
            AgendaExcepcionEspecialista.objects.filter(
                especialista=especialista,
                sucursal_id=old_branch_id,
            ).delete()
        
    return json_response({
        "detail": f"Usuario movido exitosamente a {branch.nombre}.",
        "branch": {"id": branch.id, "name": branch.nombre}
    })


@require_GET
@_admin_principal_required
def admin_branch_management_list(request):
    status = (request.GET.get("status") or "all").lower()
    city = (request.GET.get("city") or "").strip()
    admin_name = (request.GET.get("admin_name") or "").strip()
    branch_id = request.GET.get("branch_id")

    branches = Sucursal.objects.all().order_by("nombre")
    if status == "active":
        branches = branches.filter(activa=True)
    elif status == "inactive":
        branches = branches.filter(activa=False)
    if city:
        branches = branches.filter(ciudad__icontains=city)
    if branch_id:
        branches = branches.filter(pk=branch_id)

    admins = Usuario.objects.filter(rol__rol="ADMIN_SUCURSAL", is_active=True).select_related("sucursal")
    if admin_name:
        admins = admins.filter(
            Q(primer_nombre__icontains=admin_name)
            | Q(apellido_paterno__icontains=admin_name)
            | Q(username__icontains=admin_name)
        )
        branches = branches.filter(pk__in=admins.values_list("sucursal_id", flat=True))
    admin_by_branch = {}
    for admin in admins:
        if admin.sucursal_id and admin.sucursal_id not in admin_by_branch:
            admin_by_branch[admin.sucursal_id] = admin

    items = []
    for branch in branches:
        admin = admin_by_branch.get(branch.id)
        items.append(
            {
                "id": branch.id,
                "nombre": branch.nombre,
                "ciudad": branch.ciudad,
                "direccion": branch.direccion,
                "activa": branch.activa,
                "esPrincipal": branch.es_principal,
                "admin": {
                    "id": admin.id,
                    "nombre": admin.nombre_completo,
                    "username": admin.username,
                }
                if admin
                else None,
            }
        )
    return json_response({"branches": items, "total": len(items)})


@require_POST
@_admin_principal_required
def admin_branch_wizard_initialize(request):
    request.session[BRANCH_CREATE_WIZARD_SESSION_KEY] = {}
    request.session.modified = True
    return json_response({"detail": "Wizard de sucursal inicializado.", "draft": {}})


@require_POST
@_admin_principal_required
def admin_branch_wizard_step1(request):
    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)
    data, errors = _branch_payload(payload, partial=False)
    if errors:
        return json_response({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)
    draft = request.session.get(BRANCH_CREATE_WIZARD_SESSION_KEY) or {}
    draft["branch"] = data
    request.session[BRANCH_CREATE_WIZARD_SESSION_KEY] = draft
    request.session.modified = True
    return json_response({"detail": "Paso 1 guardado.", "draft": draft})


@require_POST
@_admin_principal_required
def admin_branch_wizard_step2(request):
    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)
    draft = request.session.get(BRANCH_CREATE_WIZARD_SESSION_KEY) or {}
    if not draft.get("branch"):
        return json_response({"detail": "Debes completar el paso 1 primero."}, status=409)

    mode = (payload.get("mode") or "").strip()
    if mode not in {"existing_inactive", "create_new"}:
        return json_response({"detail": "mode debe ser existing_inactive o create_new."}, status=400)

    if mode == "existing_inactive":
        admin_id = payload.get("adminUserId")
        if not admin_id:
            return json_response({"detail": "adminUserId es obligatorio para existing_inactive."}, status=400)
        admin_user = get_object_or_404(Usuario, pk=admin_id)
        if not (admin_user.rol and admin_user.rol.rol == "ADMIN_SUCURSAL"):
            return json_response({"detail": "El usuario seleccionado no es admin de sucursal."}, status=400)
        if admin_user.is_active or admin_user.sucursal_id is not None:
            return json_response({"detail": "El admin seleccionado debe estar inactivo y sin sucursal."}, status=409)
        draft["admin"] = {"mode": "existing_inactive", "adminUserId": admin_user.id}
    else:
        username = (payload.get("username") or "").strip()
        primer_nombre = (payload.get("primerNombre") or "").strip()
        apellido_paterno = (payload.get("apellidoPaterno") or "").strip()
        password = payload.get("password") or ""
        ci = (payload.get("ci") or "").strip()
        errors = {}
        if not username:
            errors["username"] = "El nombre de usuario es obligatorio."
        if Usuario.objects.filter(username=username).exists():
            errors["username"] = "Este nombre de usuario ya existe."
        if not primer_nombre:
            errors["primerNombre"] = "El primer nombre es obligatorio."
        if not apellido_paterno:
            errors["apellidoPaterno"] = "El apellido paterno es obligatorio."
        if not ci:
            errors["ci"] = "El CI es obligatorio."
        if not password:
            errors["password"] = "La contraseña inicial es obligatoria."
        if errors:
            return json_response({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)
        draft["admin"] = {
            "mode": "create_new",
            "username": username,
            "email": (payload.get("email") or "").strip(),
            "primerNombre": primer_nombre,
            "segundoNombre": (payload.get("segundoNombre") or "").strip(),
            "apellidoPaterno": apellido_paterno,
            "apellidoMaterno": (payload.get("apellidoMaterno") or "").strip(),
            "ci": ci,
            "telefono": (payload.get("telefono") or "").strip(),
            "password": password,
        }

    request.session[BRANCH_CREATE_WIZARD_SESSION_KEY] = draft
    request.session.modified = True
    return json_response({"detail": "Paso 2 guardado.", "draft": draft})


@require_POST
@_admin_principal_required
@transaction.atomic
def admin_branch_wizard_finalize(request):
    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)
    draft = request.session.get(BRANCH_CREATE_WIZARD_SESSION_KEY) or {}
    branch_data = draft.get("branch")
    admin_data = draft.get("admin")
    if not branch_data or not admin_data:
        return json_response({"detail": "Debes completar los pasos 1 y 2 antes de finalizar."}, status=409)

    nombre = (payload.get("nombre") or "").strip()
    clave = (payload.get("clave") or "").strip()
    if not nombre or not clave:
        return json_response({"detail": "nombre y clave de tablet son obligatorios."}, status=400)

    branch = Sucursal.objects.create(**branch_data, activa=True)

    codigo = f"KIOSKO-{branch.id}"
    if TabletKiosko.objects.filter(codigo=codigo).exists():
        return json_response({"detail": "No se pudo autogenerar un código único de tablet."}, status=409)
    if admin_data["mode"] == "existing_inactive":
        admin_user = get_object_or_404(Usuario, pk=admin_data["adminUserId"])
        admin_user.is_active = True
        admin_user.sucursal = branch
        admin_user.save(update_fields=["is_active", "sucursal", "updated_at"])
    else:
        admin_user = Usuario(
            username=admin_data["username"],
            email=admin_data.get("email", ""),
            primer_nombre=admin_data["primerNombre"],
            segundo_nombre=admin_data.get("segundoNombre", ""),
            apellido_paterno=admin_data["apellidoPaterno"],
            apellido_materno=admin_data.get("apellidoMaterno", ""),
            rol=_get_branch_admin_role(),
            sucursal=branch,
            is_active=True,
        )
        admin_user.set_password(admin_data["password"])
        admin_user.save()

    kiosko = TabletKiosko(
        codigo=codigo,
        nombre=nombre,
        sucursal=branch,
        activo=True,
    )
    kiosko.set_clave(clave)
    kiosko.save()
    _log_branch_admin_audit(
        request=request,
        branch=branch,
        action=BranchAdminAuditLog.Action.CREATE_BRANCH_WIZARD,
        detail="Sucursal creada via wizard con admin y tablet.",
        metadata={"adminUserId": admin_user.id, "tabletKioskId": kiosko.id},
    )

    request.session.pop(BRANCH_CREATE_WIZARD_SESSION_KEY, None)
    request.session.modified = True
    return json_response(
        {
            "detail": "Sucursal creada correctamente con administrador y tablet.",
            "branchId": branch.id,
            "adminUserId": admin_user.id,
            "tabletKioskId": kiosko.id,
            "tabletKioskCode": kiosko.codigo,
        },
        status=201,
    )


@require_POST
@_admin_principal_required
@transaction.atomic
def admin_branch_management_create(request):
    cache_key, error_response = _idempotency_cache_key(request, "branch-create")
    if error_response:
        return error_response

    def _create():
        payload = load_payload(request)
        if payload is None:
            return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)
        data, errors = _branch_payload(payload, partial=False)
        if errors:
            return json_response({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)
        branch = Sucursal.objects.create(**data, activa=True)
        return json_response({"detail": "Sucursal creada correctamente.", "branchId": branch.id}, status=201)
    return _idempotency_replay_or_store(cache_key, _create)


@require_POST
@_admin_principal_required
@transaction.atomic
def admin_branch_management_update(request, branch_id):
    branch = get_object_or_404(Sucursal, pk=branch_id)
    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)
    data, errors = _branch_payload(payload, partial=True)
    if errors:
        return json_response({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)
    if not data:
        return json_response({"detail": "No hay campos para actualizar."}, status=400)
    for field, value in data.items():
        setattr(branch, field, value)
    branch.save(update_fields=[*data.keys(), "updated_at"])
    return json_response({"detail": "Sucursal actualizada correctamente."})


@require_POST
@_admin_principal_required
@transaction.atomic
def admin_branch_management_toggle(request, branch_id):
    cache_key, error_response = _idempotency_cache_key(request, f"branch-toggle:{branch_id}")
    if error_response:
        return error_response

    def _toggle():
        branch = get_object_or_404(Sucursal, pk=branch_id)
        payload = load_payload(request) or {}
        active = payload.get("active")
        force = bool(payload.get("force"))
        if not isinstance(active, bool):
            return json_response({"detail": "Debes indicar si la sucursal quedará activa o inactiva."}, status=400)
        impact = _branch_deactivation_impact(branch)
        has_pending = any(impact.values())
        if active is False and has_pending:
            return json_response(
                {"detail": "La sucursal tiene pendientes operativos.", "impact": impact},
                status=409,
            )
        if active is True and not _active_branch_has_any_admin(branch):
            return json_response({"detail": "No puedes activar una sucursal sin un administrador asignado."}, status=409)
        if active is False:
            branch_admin = Usuario.objects.filter(
                rol__rol="ADMIN_SUCURSAL",
                sucursal=branch,
                is_active=True,
            ).first()
            if branch_admin:
                branch_admin.is_active = False
                branch_admin.sucursal = None
                branch_admin.save(update_fields=["is_active", "sucursal", "updated_at"])
        branch.activa = active
        branch.save(update_fields=["activa", "updated_at"])
        _log_branch_admin_audit(
            request=request,
            branch=branch,
            action=BranchAdminAuditLog.Action.TOGGLE_BRANCH,
            detail=f"Sucursal {'activada' if active else 'desactivada'}.",
            metadata={"active": active, "force": force, "impact": impact, "adminDeactivated": branch_admin.id if active is False and branch_admin else None},
        )
        return json_response(
            {
                "detail": "Sucursal activada correctamente." if active else "Sucursal desactivada correctamente.",
                "impact": impact,
            }
        )
    return _idempotency_replay_or_store(cache_key, _toggle)


@require_POST
@_admin_principal_required
@transaction.atomic
def admin_branch_management_change_admin(request, branch_id):
    cache_key, error_response = _idempotency_cache_key(request, f"branch-change-admin:{branch_id}")
    if error_response:
        return error_response

    def _change_admin():
        branch = get_object_or_404(Sucursal, pk=branch_id)
        payload = load_payload(request)
        if payload is None:
            return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)
        new_admin_id = payload.get("newAdminUserId")
        if not new_admin_id:
            return json_response({"detail": "newAdminUserId es obligatorio."}, status=400)
        new_admin = get_object_or_404(Usuario, pk=new_admin_id)
        if not (new_admin.rol and new_admin.rol.rol == "ADMIN_SUCURSAL"):
            return json_response({"detail": "El usuario seleccionado no es admin de sucursal."}, status=400)
        current_main_admin = Usuario.objects.filter(
            rol__rol="ADMIN_PRINCIPAL",
            sucursal=branch,
            is_active=True,
        ).first()
        current_admin = (
            Usuario.objects.filter(rol__rol="ADMIN_SUCURSAL", sucursal=branch, is_active=True)
            .exclude(pk=new_admin.pk)
            .first()
        )
        previous_branch = new_admin.sucursal
        selected_is_inactive = (not new_admin.is_active) or (new_admin.sucursal_id is None)

        if current_main_admin:
            if selected_is_inactive:
                return json_response(
                    {"detail": "El administrador principal solo puede intercambiar con un admin de sucursal activo y con sucursal."},
                    status=409,
                )
            if not previous_branch:
                return json_response(
                    {"detail": "El admin de sucursal seleccionado debe tener una sucursal activa para intercambiar con el admin principal."},
                    status=409,
                )
            new_admin.sucursal = branch
            new_admin.save(update_fields=["sucursal", "updated_at"])
            current_main_admin.sucursal = previous_branch
            current_main_admin.is_active = True
            current_main_admin.save(update_fields=["sucursal", "is_active", "updated_at"])
            _log_branch_admin_audit(
                request=request,
                branch=branch,
                action=BranchAdminAuditLog.Action.CHANGE_ADMIN,
                detail="Intercambio entre admin principal y admin de sucursal.",
                metadata={
                    "mainAdminUserId": current_main_admin.id,
                    "newAdminUserId": new_admin.id,
                    "fromBranchId": previous_branch.id,
                    "mode": "swap_with_main_admin",
                },
            )
            transaction.on_commit(lambda user_ids=[current_main_admin.id, new_admin.id]: _invalidate_user_sessions(user_ids))
            return json_response({"detail": "Intercambio con administrador principal realizado correctamente.", "mode": "swap_with_main_admin"})

        if selected_is_inactive:
            new_admin.is_active = True
            new_admin.sucursal = branch
            new_admin.save(update_fields=["is_active", "sucursal", "updated_at"])
            if current_admin:
                current_admin.is_active = False
                current_admin.sucursal = None
                current_admin.save(update_fields=["is_active", "sucursal", "updated_at"])
            _log_branch_admin_audit(
                request=request,
                branch=branch,
                action=BranchAdminAuditLog.Action.CHANGE_ADMIN,
                detail="Reemplazo por admin inactivo.",
                metadata={"newAdminUserId": new_admin.id, "previousAdminUserId": current_admin.id if current_admin else None, "mode": "replace_with_inactive"},
            )
            affected_user_ids = [new_admin.id]
            if current_admin:
                affected_user_ids.append(current_admin.id)
            transaction.on_commit(lambda user_ids=affected_user_ids: _invalidate_user_sessions(user_ids))
            return json_response({"detail": "Administrador inactivo activado y asignado correctamente.", "mode": "replace_with_inactive"})

        if new_admin.sucursal_id == branch.id:
            return json_response({"detail": "El administrador ya está asignado a esta sucursal.", "mode": "assign"})

        new_admin.sucursal = branch
        new_admin.save(update_fields=["sucursal", "updated_at"])
        if current_admin and previous_branch and previous_branch.id != branch.id:
            current_admin.sucursal = previous_branch
            current_admin.save(update_fields=["sucursal", "updated_at"])
            _log_branch_admin_audit(
                request=request,
                branch=branch,
                action=BranchAdminAuditLog.Action.CHANGE_ADMIN,
                detail="Intercambio de administradores entre sucursales.",
                metadata={"newAdminUserId": new_admin.id, "previousAdminUserId": current_admin.id, "fromBranchId": previous_branch.id, "mode": "swap"},
            )
            transaction.on_commit(lambda user_ids=[new_admin.id, current_admin.id]: _invalidate_user_sessions(user_ids))
            return json_response({"detail": "Administradores intercambiados correctamente.", "mode": "swap"})
        _log_branch_admin_audit(
            request=request,
            branch=branch,
            action=BranchAdminAuditLog.Action.CHANGE_ADMIN,
            detail="Asignación directa de administrador.",
            metadata={"newAdminUserId": new_admin.id, "mode": "assign"},
        )
        transaction.on_commit(lambda user_ids=[new_admin.id]: _invalidate_user_sessions(user_ids))
        return json_response({"detail": "Administrador de sucursal actualizado correctamente.", "mode": "assign"})
    return _idempotency_replay_or_store(cache_key, _change_admin)


@require_GET
@_admin_principal_required
def admin_branch_management_deactivation_impact(request, branch_id):
    branch = get_object_or_404(Sucursal, pk=branch_id)
    return json_response({"branchId": branch.id, "impact": _branch_deactivation_impact(branch)})


@require_GET
@_admin_principal_required
def admin_branch_admin_audit_logs(request):
    branch_id = request.GET.get("branchId")
    logs = BranchAdminAuditLog.objects.select_related("branch", "actor")
    if branch_id:
        logs = logs.filter(branch_id=branch_id)
    items = [
        {
            "id": log.id,
            "createdAt": log.created_at.isoformat(),
            "action": log.action,
            "detail": log.detail,
            "branchId": log.branch_id,
            "branchName": log.branch.nombre,
            "actor": log.actor.nombre_completo if log.actor else "Sistema",
            "metadata": log.metadata or {},
        }
        for log in logs[:200]
    ]
    return json_response({"items": items, "total": len(items)})


# ---------------------------------------------------------------------------
# Nested OpcionCatalogo endpoints under grupos-opciones
# ---------------------------------------------------------------------------
# These endpoints power the option-management modal in the admin catalog
# page. An `OpcionCatalogo` cannot exist without a parent `GrupoOpciones`
# (CASCADE FK), so the parent id is encoded in the URL. Bulk create uses
# `transaction.atomic()` for all-or-nothing semantics (see ADR-2 in
# `openspec/changes/grupo-opciones-editor/design.md`).


def _serialize_opcion(opcion):
    """Return the JSON shape consumed by the option modal in the admin UI."""
    return {
        "id": opcion.id,
        "codigo": opcion.codigo,
        "nombre": opcion.nombre,
        "valor": opcion.valor,
        "orden": opcion.orden,
        "activo": opcion.activo,
        "grupoId": opcion.grupo_id,
    }


@require_GET
@admin_required
def admin_grupo_opciones_opciones_list(request, grupo_id):
    """List `OpcionCatalogo` entries for a group, with active + search filters."""
    grupo = GrupoOpciones.objects.filter(pk=grupo_id).first()
    if not grupo:
        return json_response(
            {"detail": "No encontramos el grupo de opciones solicitado."}, status=404
        )

    active = request.GET.get("active", "all")
    if active not in ("true", "false", "all"):
        return json_response(
            {"detail": "El parametro active solo acepta true, false o all."},
            status=400,
        )

    queryset = OpcionCatalogo.objects.filter(grupo_id=grupo_id)
    if active == "true":
        queryset = queryset.filter(activo=True)
    elif active == "false":
        queryset = queryset.filter(activo=False)

    q = (request.GET.get("q") or "").strip()
    if q:
        queryset = queryset.filter(
            Q(codigo__icontains=q) | Q(nombre__icontains=q) | Q(valor__icontains=q)
        )

    queryset = queryset.order_by("orden", "nombre")
    items = [_serialize_opcion(opcion) for opcion in queryset]
    return json_response({"items": items})


def _validate_opcion_payload(payload, *, grupo_id, instance=None, allow_codigo=True):
    """Validate the payload for create/update of an `OpcionCatalogo`.

    Returns a tuple `(data, errors)`. `data` is the cleaned dict ready to be
    applied to an instance; `errors` maps field names to human-readable
    messages and is empty when validation succeeds.
    """
    errors = {}

    def _text(field):
        value = payload.get(field)
        if value is None:
            return ""
        return str(value).strip()

    codigo = _text("codigo") if allow_codigo else (instance.codigo if instance else "")
    nombre = _text("nombre")
    valor = _text("valor")

    if allow_codigo and not codigo:
        errors["codigo"] = "El codigo es obligatorio."
    if not nombre:
        errors["nombre"] = "El nombre es obligatorio."
    if not valor:
        errors["valor"] = "El valor es obligatorio."

    orden_value = payload.get("orden")
    orden = None
    if orden_value is not None and orden_value != "":
        try:
            orden = int(orden_value)
            if orden < 0:
                errors["orden"] = "El orden no puede ser negativo."
        except (TypeError, ValueError):
            errors["orden"] = "El orden debe ser un numero entero."

    activo = payload.get("activo")
    if activo is not None and not isinstance(activo, bool):
        errors["activo"] = "El campo activo debe ser verdadero o falso."

    data = {
        "codigo": codigo,
        "nombre": nombre,
        "valor": valor,
        "orden": orden,
        "activo": activo if isinstance(activo, bool) else (instance.activo if instance else True),
    }
    return data, errors


@require_POST
@_admin_principal_required
def admin_grupo_opciones_opciones_crear(request, grupo_id):
    """Create a single `OpcionCatalogo` under a group."""
    grupo = GrupoOpciones.objects.filter(pk=grupo_id).first()
    if not grupo:
        return json_response(
            {"detail": "No encontramos el grupo de opciones solicitado."}, status=404
        )

    payload = load_payload(request)
    if payload is None:
        return json_response(
            {"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400
        )

    data, errors = _validate_opcion_payload(payload, grupo_id=grupo_id)
    if errors:
        return json_response(
            {"detail": "Hay errores en el formulario.", "errors": errors}, status=400
        )

    # Uniqueness pre-check on (grupo, codigo). The DB-level constraint is the
    # source of truth; this surfaces a clean 400 message before the INSERT.
    duplicate_qs = OpcionCatalogo.objects.filter(grupo_id=grupo_id, codigo=data["codigo"])
    if duplicate_qs.exists():
        return json_response(
            {
                "detail": "Ya existe una opcion con ese codigo en el grupo.",
                "errors": {"codigo": "Ya existe una opcion con ese codigo en el grupo."},
            },
            status=400,
        )

    # Auto-assign `orden` to the next slot when the caller does not supply one.
    if data["orden"] is None:
        max_orden = (
            OpcionCatalogo.objects.filter(grupo_id=grupo_id).aggregate(Max("orden"))["orden__max"]
            or 0
        )
        orden = max_orden + 1
    else:
        orden = data["orden"]

    try:
        opcion = OpcionCatalogo.objects.create(
            grupo_id=grupo_id,
            codigo=data["codigo"],
            nombre=data["nombre"],
            valor=data["valor"],
            orden=orden,
            activo=data["activo"],
        )
    except IntegrityError:
        return json_response(
            {"detail": "Ya existe una opcion con ese codigo en el grupo."},
            status=400,
        )

    return json_response(
        {
            "detail": "Opcion creada correctamente.",
            "item": _serialize_opcion(opcion),
        },
        status=201,
    )


@require_POST
@_admin_principal_required
def admin_grupo_opciones_opciones_crear_multiples(request, grupo_id):
    """Bulk-create `OpcionCatalogo` entries under a group.

    Wrapped in `transaction.atomic()` — any failure rolls back the entire
    batch so the modal list always reflects what the backend has.
    """
    grupo = GrupoOpciones.objects.filter(pk=grupo_id).first()
    if not grupo:
        return json_response(
            {"detail": "No encontramos el grupo de opciones solicitado."}, status=404
        )

    payload = load_payload(request)
    if payload is None:
        return json_response(
            {"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400
        )

    raw_options = payload.get("options")
    if not isinstance(raw_options, list) or not raw_options:
        return json_response(
            {
                "detail": "Debes enviar una lista de opciones bajo la clave 'options'.",
                "errors": {"options": "La lista de opciones es obligatoria."},
            },
            status=400,
        )

    # Validate every entry up-front so we can report a clean 400 instead of
    # surfacing a half-applied batch after the atomic block.
    cleaned = []
    aggregated_errors = {}
    seen_codigos = set()
    for index, raw in enumerate(raw_options):
        if not isinstance(raw, dict):
            aggregated_errors[f"options.{index}"] = "El elemento debe ser un objeto."
            continue
        data, errors = _validate_opcion_payload(raw, grupo_id=grupo_id)
        if errors:
            for key, message in errors.items():
                aggregated_errors[f"options.{index}.{key}"] = message
            continue
        if data["codigo"] in seen_codigos:
            aggregated_errors[f"options.{index}.codigo"] = (
                "Codigo duplicado dentro de la solicitud."
            )
            continue
        seen_codigos.add(data["codigo"])
        cleaned.append((index, data))

    if aggregated_errors:
        return json_response(
            {
                "detail": "Hay errores en el formulario.",
                "errors": aggregated_errors,
            },
            status=400,
        )

    # Reject if any codigo already exists in the database for this group.
    existing_codigos = set(
        OpcionCatalogo.objects.filter(
            grupo_id=grupo_id, codigo__in=[data["codigo"] for _, data in cleaned]
        ).values_list("codigo", flat=True)
    )
    if existing_codigos:
        for index, data in cleaned:
            if data["codigo"] in existing_codigos:
                aggregated_errors[f"options.{index}.codigo"] = (
                    "Ya existe una opcion con ese codigo en el grupo."
                )
        return json_response(
            {
                "detail": "Hay errores en el formulario.",
                "errors": aggregated_errors,
            },
            status=400,
        )

    # Compute the next available orden once so the whole batch is appended
    # after existing entries, even if some options omit `orden`.
    max_orden = (
        OpcionCatalogo.objects.filter(grupo_id=grupo_id).aggregate(Max("orden"))["orden__max"]
        or 0
    )

    created_items = []
    try:
        with transaction.atomic():
            running_orden = max_orden
            for _, data in cleaned:
                if data["orden"] is None:
                    running_orden += 1
                    orden = running_orden
                else:
                    orden = data["orden"]
                opcion = OpcionCatalogo.objects.create(
                    grupo_id=grupo_id,
                    codigo=data["codigo"],
                    nombre=data["nombre"],
                    valor=data["valor"],
                    orden=orden,
                    activo=data["activo"],
                )
                created_items.append(_serialize_opcion(opcion))
    except IntegrityError:
        return json_response(
            {"detail": "No se pudieron crear las opciones. Intenta nuevamente."},
            status=400,
        )

    return json_response(
        {
            "detail": "Opciones creadas correctamente.",
            "items": created_items,
        },
        status=201,
    )


@require_POST
@_admin_principal_required
def admin_grupo_opciones_opciones_actualizar(request, grupo_id, opcion_id):
    """Partial update of an existing `OpcionCatalogo`.

    The frontend modal never changes `codigo`, so we lock it via the validator
    and let the caller update only `nombre`, `valor`, `orden`, `activo`.
    """
    grupo = GrupoOpciones.objects.filter(pk=grupo_id).first()
    if not grupo:
        return json_response(
            {"detail": "No encontramos el grupo de opciones solicitado."}, status=404
        )

    opcion = OpcionCatalogo.objects.filter(pk=opcion_id, grupo_id=grupo_id).first()
    if not opcion:
        return json_response(
            {"detail": "No encontramos la opcion solicitada."}, status=404
        )

    payload = load_payload(request)
    if payload is None:
        return json_response(
            {"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400
        )

    # Partial update: only fields present in the payload are validated.
    partial_payload = {}
    errors = {}

    if "nombre" in payload:
        nombre = str(payload.get("nombre") or "").strip()
        if not nombre:
            errors["nombre"] = "El nombre es obligatorio."
        else:
            partial_payload["nombre"] = nombre

    if "valor" in payload:
        valor = str(payload.get("valor") or "").strip()
        if not valor:
            errors["valor"] = "El valor es obligatorio."
        else:
            partial_payload["valor"] = valor

    if "orden" in payload:
        raw_orden = payload.get("orden")
        if raw_orden is None or raw_orden == "":
            errors["orden"] = "El orden no puede estar vacio."
        else:
            try:
                orden = int(raw_orden)
                if orden < 0:
                    errors["orden"] = "El orden no puede ser negativo."
                else:
                    partial_payload["orden"] = orden
            except (TypeError, ValueError):
                errors["orden"] = "El orden debe ser un numero entero."

    if "activo" in payload:
        activo = payload.get("activo")
        if not isinstance(activo, bool):
            errors["activo"] = "El campo activo debe ser verdadero o falso."
        else:
            partial_payload["activo"] = activo

    if errors:
        return json_response(
            {"detail": "Hay errores en el formulario.", "errors": errors}, status=400
        )

    for field, value in partial_payload.items():
        setattr(opcion, field, value)
    opcion.save()

    return json_response(
        {
            "detail": "Opcion actualizada correctamente.",
            "item": _serialize_opcion(opcion),
        }
    )


@require_POST
@_admin_principal_required
def admin_grupo_opciones_opciones_estado(request, grupo_id, opcion_id):
    """Toggle the `activo` flag (soft-delete) of an `OpcionCatalogo`."""
    grupo = GrupoOpciones.objects.filter(pk=grupo_id).first()
    if not grupo:
        return json_response(
            {"detail": "No encontramos el grupo de opciones solicitado."}, status=404
        )

    opcion = OpcionCatalogo.objects.filter(pk=opcion_id, grupo_id=grupo_id).first()
    if not opcion:
        return json_response(
            {"detail": "No encontramos la opcion solicitada."}, status=404
        )

    payload = load_payload(request)
    if payload is None:
        return json_response(
            {"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400
        )

    active = payload.get("active")
    if not isinstance(active, bool):
        return json_response(
            {"detail": "Debes indicar si la opcion queda activa o inactiva."},
            status=400,
        )

    opcion.activo = active
    opcion.save(update_fields=["activo", "updated_at"])

    return json_response(
        {
            "detail": "Estado actualizado correctamente.",
            "item": _serialize_opcion(opcion),
        }
    )


# ---------------------------------------------------------------------------
# Admin Reports — branch-scoped, read-only datasets
# ---------------------------------------------------------------------------
#
# These endpoints back the admin Reports section. Each endpoint:
#   * requires an authenticated admin (via ``admin_required``),
#   * resolves the active branch from the session via ``get_user_branch``
#     (no client-supplied branch id is honoured, preventing tampering),
#   * caps the response at 500 rows to keep browser exports bounded, and
#   * returns a uniform envelope ``{branch, month?, year?, rows[]}``.
#
# The row payloads are produced by DRF serializers in
# ``config.api_serializers`` so the frontend never has to re-split or rename
# backend fields.

REPORT_ROW_CAP = 500


def _client_appointment_dates(cliente):
    """Return ``(last, next)`` appointment datetimes for the client.

    Looks at both ``Operacion``-bound appointments and free medical
    appointments (``CitaClienteLibre``) so clients who only have free medical
    appointments still report useful dates. Cancelled appointments are
    excluded. ``last`` is the most recent past or current datetime;
    ``next`` is the earliest future datetime relative to ``timezone.now()``.
    """
    now = timezone.now()
    last = None
    next_date = None

    def _consider(fecha):
        nonlocal last, next_date
        if fecha is None:
            return
        if fecha <= now:
            if last is None or fecha > last:
                last = fecha
        else:
            if next_date is None or fecha < next_date:
                next_date = fecha

    for operacion in cliente.operaciones.all():
        for cita in operacion.citas_medicas.all():
            if cita.estado == CitaMedica.Estado.CANCELADA:
                continue
            _consider(cita.fecha_hora)
    for cita in getattr(cliente, "citas_medicas_libres", []).all():
        if cita.estado == CitaClienteLibre.Estado.CANCELADA:
            continue
        _consider(cita.fecha_hora)
    return last, next_date


def _client_payment_dates(cliente):
    """Return ``(last, next)`` payment datetimes for the client.

    ``last`` is the most recent ``PagoRealizado.created_at`` (any status,
    matching the rest of the income report's "all payments" rule).
    ``next`` is the earliest pending ``CuotaPlanPago.fecha_vencimiento``
    for an unpaid cuota. Both are returned as ``datetime`` so the frontend
    can format them with a single ``DateTimeFormat``.
    """
    from datetime import datetime, time as _time

    last = None
    next_date = None
    for operacion in cliente.operaciones.all():
        for cuota in operacion.cuotas_plan_pagos.all():
            for pago in cuota.pagos_realizados.all():
                created = pago.created_at
                if last is None or created > last:
                    last = created
            if cuota.estado in {CuotaPlanPago.Estado.PENDIENTE, CuotaPlanPago.Estado.VENCIDA}:
                fecha = cuota.fecha_vencimiento
                if next_date is None or fecha < next_date:
                    next_date = fecha
    if next_date is not None and isinstance(next_date, datetime) is False:
        next_date = datetime.combine(next_date, _time.min)
    return last, next_date


def _prospect_appointment_dates(prospecto):
    """Return ``(last, next)`` ``CitaProspecto`` datetimes for the prospect."""
    now = timezone.now()
    last = None
    next_date = None
    for cita in getattr(prospecto, "citas_medicas", []).all():
        if cita.estado == CitaProspecto.Estado.CANCELADA:
            continue
        fecha = cita.fecha_hora
        if fecha <= now:
            if last is None or fecha > last:
                last = fecha
        else:
            if next_date is None or fecha < next_date:
                next_date = fecha
    return last, next_date


def _report_client_row(cliente):
    """Build a single ReportClient row from a ``Cliente`` instance."""
    usuario = cliente.usuario
    primer_nombre = (usuario.primer_nombre or "").strip()
    apellido_paterno = (usuario.apellido_paterno or "").strip()
    last_appointment, next_appointment = _client_appointment_dates(cliente)
    last_payment, next_payment = _client_payment_dates(cliente)
    return {
        "id": f"CLI-{cliente.pk:04d}",
        "rawId": cliente.pk,
        "clienteCodigo": cliente.cliente_codigo,
        "firstName": primer_nombre,
        "lastName": f"{apellido_paterno} {(usuario.apellido_materno or '').strip()}".strip(),
        "ci": cliente.ci or "",
        "status": cliente.get_estado_cliente_display(),
        "lastAppointmentDate": last_appointment.isoformat() if last_appointment else None,
        "nextAppointmentDate": next_appointment.isoformat() if next_appointment else None,
        "lastPaymentDate": last_payment.isoformat() if last_payment else None,
        "nextPaymentDate": next_payment.isoformat() if next_payment else None,
    }


def _report_prospect_row(prospecto):
    """Build a single ReportProspect row from a ``Prospecto`` instance."""
    last_appointment, next_appointment = _prospect_appointment_dates(prospecto)
    return {
        "id": f"PRO-{prospecto.pk:04d}",
        "rawId": prospecto.pk,
        "firstName": (prospecto.primer_nombre or "").strip(),
        "lastName": f"{prospecto.apellido_paterno or ''} {(prospecto.apellido_materno or '').strip()}".strip(),
        "phone": prospecto.telefono or "",
        "ci": getattr(prospecto, "ci", "") or "",
        "interest": _prospect_interest(prospecto),
        "state": prospecto.get_estado_display(),
        "createdAt": _datetime_label(prospecto.created_at),
        "registeredBy": full_name(prospecto.registrado_por),
        "lastAppointmentDate": last_appointment.isoformat() if last_appointment else None,
        "nextAppointmentDate": next_appointment.isoformat() if next_appointment else None,
    }


def _report_income_row(payment):
    """Build a single ReportIncome row from a ``PagoRealizado`` instance."""
    operacion = payment.cuota.operacion
    submitted = payment.created_at
    invoice_field = payment.comprobante_url
    return {
        "paymentId": payment.pk,
        "date": submitted.date().isoformat() if submitted else "",
        "time": submitted.strftime("%H:%M") if submitted else "",
        "amount": str(payment.monto_pagado),
        "clientName": full_name(operacion.paciente.usuario),
        "serviceName": procedure_name(operacion),
        "status": _payment_status(payment),
        "invoiceUrl": invoice_field.url if invoice_field else "",
        "invoiceName": PurePosixPath(invoice_field.name).name if invoice_field else "",
    }


@require_GET
@admin_required
def admin_report_clients(request):
    """Branch-scoped read-only client dataset for the admin reports area."""
    from config.api_serializers import ReportClientSerializer

    branch = get_user_branch(request)
    clientes_qs = _admin_client_queryset()
    if branch:
        clientes_qs = clientes_qs.filter(usuario__sucursal_id=branch)

    # Stable ordering so the same row set is returned across requests.
    clientes_qs = clientes_qs.order_by(
        "usuario__primer_nombre", "usuario__apellido_paterno", "pk"
    )

    full_count = clientes_qs.count()
    rows = [_report_client_row(cliente) for cliente in clientes_qs[:REPORT_ROW_CAP]]
    serialized = ReportClientSerializer(rows, many=True).data

    return json_response(
        {
            "branch": {"id": branch.pk, "name": branch.nombre} if branch else None,
            "rows": serialized,
            "cap": REPORT_ROW_CAP,
            "truncated": full_count > REPORT_ROW_CAP,
        }
    )


@require_GET
@admin_required
def admin_report_prospects(request):
    """Branch-scoped read-only prospect dataset for the admin reports area."""
    from config.api_serializers import ReportProspectSerializer

    branch = get_user_branch(request)
    prospectos_qs = Prospecto.objects.select_related("registrado_por").prefetch_related(
        Prefetch(
            "citas_medicas",
            queryset=CitaProspecto.objects.select_related().order_by("fecha_hora"),
        ),
    )
    if branch:
        prospectos_qs = prospectos_qs.filter(sucursal_registro=branch)

    prospectos_qs = prospectos_qs.order_by("-created_at")
    rows = [_report_prospect_row(prospecto) for prospecto in prospectos_qs[:REPORT_ROW_CAP]]
    serialized = ReportProspectSerializer(rows, many=True).data

    return json_response(
        {
            "branch": {"id": branch.pk, "name": branch.nombre} if branch else None,
            "rows": serialized,
            "cap": REPORT_ROW_CAP,
            "truncated": prospectos_qs.count() > REPORT_ROW_CAP,
        }
    )


@require_GET
@admin_required
def admin_report_income(request):
    """Branch-scoped read-only monthly income dataset for the admin reports area."""
    from config.api_serializers import ReportIncomeSerializer

    branch = get_user_branch(request)
    today = timezone.localdate()
    try:
        month = int(request.GET.get("month") or today.month)
        year = int(request.GET.get("year") or today.year)
    except (TypeError, ValueError):
        return json_response({"detail": "Mes o anio invalido."}, status=400)

    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    start = date(year, month, 1)

    pagos_qs = (
        PagoRealizado.objects.select_related(
            "cuota__operacion__paciente__usuario",
            "cuota__operacion__servicio_config__proc_estetico",
            "cuota__operacion__servicio_config__tipo_servicio",
            "verificado_por",
        )
        .filter(cuota__fecha_vencimiento__range=(start, end))
        .order_by("-created_at")
    )
    if branch:
        pagos_qs = pagos_qs.filter(
            cuota__operacion__paciente__usuario__sucursal_id=branch
        ).distinct()

    rows = [_report_income_row(payment) for payment in pagos_qs[:REPORT_ROW_CAP]]
    serialized = ReportIncomeSerializer(rows, many=True).data

    return json_response(
        {
            "branch": {"id": branch.pk, "name": branch.nombre} if branch else None,
            "month": month,
            "year": year,
            "rows": serialized,
            "cap": REPORT_ROW_CAP,
            "truncated": pagos_qs.count() > REPORT_ROW_CAP,
        }
    )
