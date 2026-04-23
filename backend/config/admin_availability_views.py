import json
from datetime import datetime
from functools import wraps

from django.db import transaction
from django.db.models import Prefetch
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from catalogs.models import ProcEstetico, ProcEsteticosTipo, TipoServicio
from operations.models import CitaMedica, DisponibilidadCita
from staff.models import Especialista


BLOCKING_RESERVATION_STATES = {
    CitaMedica.Estado.PROGRAMADA,
    CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA,
    CitaMedica.Estado.CONFIRMADA,
}


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


def _metric(identifier, label, value, delta, tone):
    return {
        "id": identifier,
        "label": label,
        "value": str(value),
        "delta": delta,
        "tone": tone,
    }


def _full_name(user):
    return user.nombre_completo or user.username


def _datetime_label(value):
    return timezone.localtime(value).strftime("%d/%m/%Y %H:%M")


def _find_blocking_booking(slot):
    return next(
        (
            cita
            for cita in slot.citas_origen.all()
            if cita.estado in BLOCKING_RESERVATION_STATES
        ),
        None,
    )


def _slot_status(slot, booking):
    if not slot.activo:
        return "inactivo"
    if slot.fecha_hora <= timezone.now():
        return "expirado"
    if booking:
        return "reservado"
    return "disponible"


def _scope_labels(slot):
    labels = []
    labels.extend([f"Tipo de servicio: {item.tipo}" for item in slot.tipos_servicio.all()])
    labels.extend([f"Tipo de procedimiento: {item.tipo}" for item in slot.tipos_proc_estetico.all()])
    labels.extend([f"Procedimiento: {item.proceso}" for item in slot.procedimientos_esteticos.all()])
    return labels


def _slot_item(slot):
    booking = _find_blocking_booking(slot)
    operation = booking.operacion if booking else None
    patient = operation.paciente if operation else None
    return {
        "id": f"AVL-{slot.pk:04d}",
        "rawId": slot.pk,
        "specialist": _full_name(slot.especialista.usuario),
        "dateTime": _datetime_label(slot.fecha_hora),
        "date": timezone.localtime(slot.fecha_hora).date().isoformat(),
        "time": timezone.localtime(slot.fecha_hora).strftime("%H:%M"),
        "status": _slot_status(slot, booking),
        "coverage": _scope_labels(slot),
        "patient": _full_name(patient.usuario) if patient else "",
        "operation": (
            operation.servicio_config.proc_estetico.proceso
            if operation and operation.servicio_config.proc_estetico
            else operation.servicio_config.tipo_servicio.tipo
            if operation
            else ""
        ),
        "reservationState": booking.get_estado_display() if booking else "",
        "active": slot.activo,
    }


def _parse_payload(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _parse_date(date_value):
    return datetime.strptime(date_value, "%Y-%m-%d").date()


def _parse_time(time_value):
    return datetime.strptime(time_value, "%H:%M").time()


def _build_slot_datetime(slot_date, slot_time):
    return timezone.make_aware(datetime.combine(slot_date, slot_time)).replace(second=0, microsecond=0)


@require_GET
@_admin_required
def admin_availability(request):
    slots_qs = (
        DisponibilidadCita.objects.select_related("especialista__usuario")
        .prefetch_related(
            "tipos_servicio",
            "tipos_proc_estetico",
            "procedimientos_esteticos",
            Prefetch(
                "citas_origen",
                queryset=CitaMedica.objects.select_related(
                    "operacion__paciente__usuario",
                    "operacion__servicio_config__tipo_servicio",
                    "operacion__servicio_config__proc_estetico",
                ).order_by("-created_at"),
            ),
        )
        .order_by("fecha_hora", "especialista__usuario__primer_nombre")
    )

    slot_items = [_slot_item(slot) for slot in slots_qs]
    available_slots = sum(1 for item in slot_items if item["status"] == "disponible")
    reserved_slots = sum(1 for item in slot_items if item["status"] == "reservado")
    future_slots = [item for item in slot_items if item["status"] in {"disponible", "reservado"}]
    open_specialists = len({slot.especialista_id for slot in slots_qs if slot.activo and slot.fecha_hora > timezone.now()})

    specialists = [
        {
            "id": specialist.pk,
            "label": _full_name(specialist.usuario),
            "secondaryLabel": ", ".join(
                rel.especialidad.nombre for rel in specialist.especialidades_rel.all()
            )
            or "Sin especialidad",
        }
        for specialist in Especialista.objects.select_related("usuario")
        .prefetch_related("especialidades_rel__especialidad")
        .filter(usuario__is_active=True)
        .order_by("usuario__primer_nombre", "usuario__apellido_paterno")
    ]
    service_types = [
        {"id": item.pk, "label": item.tipo}
        for item in TipoServicio.objects.filter(activo=True).order_by("orden", "tipo")
    ]
    procedure_types = [
        {"id": item.pk, "label": item.tipo}
        for item in ProcEsteticosTipo.objects.filter(activo=True).order_by("orden", "tipo")
    ]
    procedures = [
        {
            "id": item.pk,
            "label": item.proceso,
            "secondaryLabel": item.tipo_p_estetico.tipo,
        }
        for item in ProcEstetico.objects.select_related("tipo_p_estetico")
        .filter(activo=True)
        .order_by("orden", "proceso")
    ]

    data = {
        "metrics": [
            _metric(
                "availability-open",
                "Horarios publicados",
                available_slots,
                "Aun pueden reservarse desde el portal",
                "success",
            ),
            _metric(
                "availability-booked",
                "Horarios reservados",
                reserved_slots,
                "Ya fueron tomados por pacientes",
                "primary",
            ),
            _metric(
                "availability-specialists",
                "Especialistas con agenda",
                open_specialists,
                "Tienen al menos un horario activo futuro",
                "warning",
            ),
            _metric(
                "availability-total",
                "Bloques registrados",
                len(slot_items),
                f"{len(future_slots)} vigentes entre disponibles y reservados",
                "danger",
            ),
        ],
        "filters": {
            "specialists": specialists,
            "serviceTypes": service_types,
            "procedureTypes": procedure_types,
            "procedures": procedures,
        },
        "slots": slot_items,
    }
    return _json(data)


@require_POST
@_admin_required
@transaction.atomic
def admin_create_availability(request):
    payload = _parse_payload(request)
    if payload is None:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    specialist_id = payload.get("specialistId")
    raw_dates = payload.get("dates") or []
    raw_times = payload.get("times") or []
    service_type_ids = payload.get("serviceTypeIds") or []
    procedure_type_ids = payload.get("procedureTypeIds") or []
    procedure_ids = payload.get("procedureIds") or []

    errors = {}
    if not specialist_id:
        errors["specialistId"] = "Debes seleccionar un especialista."
    if not raw_dates:
        errors["dates"] = "Debes agregar al menos una fecha."
    if not raw_times:
        errors["times"] = "Debes agregar al menos una hora."
    if not (service_type_ids or procedure_type_ids or procedure_ids):
        errors["scope"] = "Debes asociar al menos un tipo de servicio, tipo de procedimiento o procedimiento."

    specialist = None
    if specialist_id:
        specialist = (
            Especialista.objects.select_related("usuario")
            .filter(pk=specialist_id, usuario__is_active=True)
            .first()
        )
        if not specialist:
            errors["specialistId"] = "El especialista seleccionado no esta disponible."

    try:
        unique_dates = sorted({_parse_date(str(value)) for value in raw_dates})
    except ValueError:
        errors["dates"] = "Alguna de las fechas no tiene un formato valido."
        unique_dates = []

    try:
        unique_times = sorted({_parse_time(str(value)) for value in raw_times})
    except ValueError:
        errors["times"] = "Alguna de las horas no tiene un formato valido."
        unique_times = []

    service_types = list(TipoServicio.objects.filter(pk__in=service_type_ids, activo=True))
    procedure_types = list(ProcEsteticosTipo.objects.filter(pk__in=procedure_type_ids, activo=True))
    procedures = list(ProcEstetico.objects.filter(pk__in=procedure_ids, activo=True))

    if len(service_types) != len(set(service_type_ids)):
        errors["serviceTypeIds"] = "Alguno de los tipos de servicio ya no esta disponible."
    if len(procedure_types) != len(set(procedure_type_ids)):
        errors["procedureTypeIds"] = "Alguno de los tipos de procedimiento ya no esta disponible."
    if len(procedures) != len(set(procedure_ids)):
        errors["procedureIds"] = "Alguno de los procedimientos ya no esta disponible."

    if errors:
        return _json({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)

    now = timezone.now()
    created_count = 0
    updated_count = 0
    conflicts = []

    for slot_date in unique_dates:
        for slot_time in unique_times:
            slot_datetime = _build_slot_datetime(slot_date, slot_time)
            if slot_datetime <= now:
                conflicts.append(slot_datetime.strftime("%d/%m/%Y %H:%M"))
                continue

            slot, created = DisponibilidadCita.objects.get_or_create(
                especialista=specialist,
                fecha_hora=slot_datetime,
                defaults={"activo": True},
            )
            has_blocking_booking = slot.citas_origen.filter(
                estado__in=BLOCKING_RESERVATION_STATES
            ).exists()
            if not created and has_blocking_booking:
                conflicts.append(slot_datetime.strftime("%d/%m/%Y %H:%M"))
                continue

            if not created:
                slot.activo = True
                slot.save(update_fields=["activo", "updated_at"])
                updated_count += 1
            else:
                created_count += 1

            slot.tipos_servicio.set(service_types)
            slot.tipos_proc_estetico.set(procedure_types)
            slot.procedimientos_esteticos.set(procedures)

    if created_count == 0 and updated_count == 0:
        detail = "No pudimos crear horarios nuevos con la seleccion enviada."
        if conflicts:
            detail += " Conflictos detectados en: " + ", ".join(conflicts[:6])
        return _json({"detail": detail}, status=400)

    detail_parts = []
    if created_count:
        detail_parts.append(f"{created_count} horario(s) creado(s)")
    if updated_count:
        detail_parts.append(f"{updated_count} horario(s) actualizado(s)")
    if conflicts:
        detail_parts.append(f"{len(conflicts)} conflicto(s) omitido(s)")

    return _json(
        {
            "detail": "Disponibilidad guardada correctamente: " + ", ".join(detail_parts) + ".",
            "createdCount": created_count,
            "updatedCount": updated_count,
            "conflictCount": len(conflicts),
        },
        status=201,
    )
