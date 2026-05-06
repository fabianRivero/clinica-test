import json
from datetime import datetime
from functools import wraps

from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from catalogs.models import ProcEstetico, ProcEsteticosTipo, TipoServicio
from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualDia,
    AgendaHabitualEspecialista,
    CitaClienteLibre,
    CitaMedica,
    CitaProspecto,
    DiaBloqueadoAgendaGlobal,
    DiaSemana,
    DisponibilidadCita,
    HorarioDisponibilidad,
)
from operations.scheduling import BLOCKING_RESERVATION_STATES, sync_disponibilidad_citas
from staff.models import Especialista


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


def _date_label(value):
    return value.strftime("%d/%m/%Y")


def _parse_payload(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _parse_date(date_value):
    return datetime.strptime(str(date_value), "%Y-%m-%d").date()


def _parse_time(time_value):
    return datetime.strptime(str(time_value), "%H:%M").time()


def _scope_labels(instance):
    labels = []
    labels.extend([f"Tipo de servicio: {item.tipo}" for item in instance.tipos_servicio.all()])
    labels.extend([f"Tipo de procedimiento: {item.tipo}" for item in instance.tipos_proc_estetico.all()])
    labels.extend([f"Procedimiento: {item.proceso}" for item in instance.procedimientos_esteticos.all()])
    return labels


def _weekday_labels(rule):
    label_map = dict(DiaSemana.choices)
    return [label_map.get(code, str(code)) for code in rule.dias_semana]


def _find_blocking_booking(slot):
    client_booking = next(
        (
            cita
            for cita in slot.citas_origen.all()
            if cita.estado in BLOCKING_RESERVATION_STATES
        ),
        None,
    )
    if client_booking:
        return client_booking
    free_client_booking = next(
        (
            cita
            for cita in slot.citas_clientes_libres_origen.all()
            if cita.estado == CitaClienteLibre.Estado.PROGRAMADA
        ),
        None,
    )
    if free_client_booking:
        return free_client_booking
    return next(
        (
            cita
            for cita in slot.citas_prospectos_origen.all()
            if cita.estado == CitaProspecto.Estado.PROGRAMADA
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


def _slot_item(slot):
    booking = _find_blocking_booking(slot)
    operation = getattr(booking, "operacion", None) if booking else None
    prospect = getattr(booking, "prospecto", None) if booking else None
    free_client = getattr(booking, "cliente", None) if booking else None
    patient = operation.paciente if operation else None
    return {
        "id": f"AVL-{slot.pk:04d}",
        "rawId": slot.pk,
        "specialistId": slot.especialista_id,
        "specialist": _full_name(slot.especialista.usuario),
        "dateTime": _datetime_label(slot.fecha_hora),
        "date": timezone.localtime(slot.fecha_hora).date().isoformat(),
        "time": timezone.localtime(slot.fecha_hora).strftime("%H:%M"),
        "timeRange": slot.rango_horario,
        "timeSlotId": slot.horario_base_id,
        "status": _slot_status(slot, booking),
        "coverage": _scope_labels(slot),
        "patient": _full_name(patient.usuario) if patient else str(free_client) if free_client else str(prospect) if prospect else "",
        "operation": (
            operation.servicio_config.proc_estetico.proceso
            if operation and operation.servicio_config.proc_estetico
            else operation.servicio_config.tipo_servicio.tipo
            if operation
            else booking.servicio_config.tipo_servicio.tipo
            if prospect or free_client
            else ""
        ),
        "appointmentId": booking.pk if booking else None,
        "appointmentCanCancel": bool(
            booking and hasattr(booking, "operacion") and booking.estado == CitaMedica.Estado.PROGRAMADA
        ),
        "reservationState": booking.get_estado_display() if booking else "",
        "active": slot.activo,
        "detail": slot.detalle,
    }


def _time_slot_item(slot):
    future_slots = slot.disponibilidades_cita.filter(fecha_hora__gt=timezone.now())
    return {
        "id": slot.pk,
        "label": slot.etiqueta,
        "startTime": slot.hora_inicio.strftime("%H:%M"),
        "endTime": slot.hora_fin.strftime("%H:%M"),
        "detail": slot.descripcion,
        "active": slot.activo,
        "futureSlots": future_slots.count(),
        "reservedFutureSlots": future_slots.filter(
            citas_origen__estado__in=BLOCKING_RESERVATION_STATES
        ).distinct().count()
        + future_slots.filter(citas_prospectos_origen__estado=CitaProspecto.Estado.PROGRAMADA)
        .distinct()
        .count()
        + future_slots.filter(citas_clientes_libres_origen__estado=CitaClienteLibre.Estado.PROGRAMADA)
        .distinct()
        .count(),
    }


def _habitual_rule_item(rule):
    return {
        "id": rule.pk,
        "specialistId": rule.especialista_id,
        "specialist": _full_name(rule.especialista.usuario),
        "startDate": rule.fecha_inicio.isoformat(),
        "endDate": rule.fecha_fin.isoformat(),
        "weekdayCodes": rule.dias_semana,
        "weekdayLabels": _weekday_labels(rule),
        "timeSlotIds": list(rule.horarios.values_list("id", flat=True).order_by("hora_inicio", "hora_fin")),
        "timeSlotLabels": [item.etiqueta for item in rule.horarios.all()],
        "scope": _scope_labels(rule),
        "serviceTypeIds": list(rule.tipos_servicio.values_list("id", flat=True)),
        "procedureTypeIds": list(rule.tipos_proc_estetico.values_list("id", flat=True)),
        "procedureIds": list(rule.procedimientos_esteticos.values_list("id", flat=True)),
        "active": rule.activo,
        "detail": rule.detalle,
    }


def _exception_item(exception):
    return {
        "id": exception.pk,
        "specialistId": exception.especialista_id,
        "specialist": _full_name(exception.especialista.usuario),
        "date": exception.fecha.isoformat(),
        "dateLabel": _date_label(exception.fecha),
        "type": exception.tipo_excepcion,
        "typeLabel": exception.get_tipo_excepcion_display(),
        "timeSlotIds": list(
            exception.horarios.values_list("id", flat=True).order_by("hora_inicio", "hora_fin")
        ),
        "timeSlotLabels": [item.etiqueta for item in exception.horarios.all()],
        "scope": _scope_labels(exception),
        "serviceTypeIds": list(exception.tipos_servicio.values_list("id", flat=True)),
        "procedureTypeIds": list(exception.tipos_proc_estetico.values_list("id", flat=True)),
        "procedureIds": list(exception.procedimientos_esteticos.values_list("id", flat=True)),
        "active": exception.activo,
        "detail": exception.detalle,
    }


def _global_block_item(block):
    return {
        "id": block.pk,
        "date": block.fecha.isoformat(),
        "dateLabel": _date_label(block.fecha),
        "active": block.activo,
        "detail": block.detalle,
    }


def _specialist_summary_item(specialist, slots, habitual_count, exception_count):
    next_slot = slots[0] if slots else None
    return {
        "id": specialist.pk,
        "label": _full_name(specialist.usuario),
        "secondaryLabel": ", ".join(
            rel.especialidad.nombre for rel in specialist.especialidades_rel.all()
        )
        or "Sin especialidad",
        "futureSlots": len(slots),
        "nextSlot": _datetime_label(next_slot.fecha_hora) if next_slot else "Sin cupos publicados",
        "habitualRules": habitual_count,
        "exceptions": exception_count,
    }


def _weekday_options():
    return [{"value": value, "label": label} for value, label in DiaSemana.choices]


def _resolve_scope(payload, errors, require_scope=True):
    service_type_ids = payload.get("serviceTypeIds") or []
    procedure_type_ids = payload.get("procedureTypeIds") or []
    procedure_ids = payload.get("procedureIds") or []

    service_types = list(TipoServicio.objects.filter(pk__in=service_type_ids, activo=True))
    procedure_types = list(ProcEsteticosTipo.objects.filter(pk__in=procedure_type_ids, activo=True))
    procedures = list(ProcEstetico.objects.filter(pk__in=procedure_ids, activo=True))

    if require_scope and not (service_type_ids or procedure_type_ids or procedure_ids):
        errors["scope"] = (
            "Debes asociar al menos un tipo de servicio, tipo de procedimiento o procedimiento."
        )
    if len(service_types) != len(set(service_type_ids)):
        errors["serviceTypeIds"] = "Alguno de los tipos de servicio ya no esta disponible."
    if len(procedure_types) != len(set(procedure_type_ids)):
        errors["procedureTypeIds"] = "Alguno de los tipos de procedimiento ya no esta disponible."
    if len(procedures) != len(set(procedure_ids)):
        errors["procedureIds"] = "Alguno de los procedimientos ya no esta disponible."

    return service_types, procedure_types, procedures


def _resolve_specialist(payload, errors):
    specialist_id = payload.get("specialistId")
    if not specialist_id:
        errors["specialistId"] = "Debes seleccionar un especialista."
        return None

    specialist = (
        Especialista.objects.select_related("usuario")
        .filter(pk=specialist_id, usuario__is_active=True)
        .first()
    )
    if not specialist:
        errors["specialistId"] = "El especialista seleccionado no esta disponible."
    return specialist


def _resolve_time_slots(slot_ids, errors, field_name="timeSlotIds"):
    if not slot_ids:
        errors[field_name] = "Debes seleccionar al menos un horario."
        return []

    slots = list(HorarioDisponibilidad.objects.filter(pk__in=slot_ids, activo=True))
    if len(slots) != len(set(slot_ids)):
        errors[field_name] = "Alguno de los horarios seleccionados ya no esta disponible."
    return slots


def _weekday_code_for_date(target_date):
    return (target_date.weekday() + 1) % 7


def _first_common_slot(slot_ids, slots):
    slot_map = {slot.id: slot for slot in slots}
    common_ids = sorted(set(slot_ids) & set(slot_map.keys()))
    if not common_ids:
        return None
    return slot_map[common_ids[0]]


def _build_availability_overlap_message(specialist, target_date, slot):
    return (
        f"Ya existe disponibilidad para {_full_name(specialist.usuario)} "
        f"el {_date_label(target_date)} en el horario {slot.etiqueta}."
    )


def _validate_habitual_schedule_overlap(
    specialist,
    start_date,
    end_date,
    weekday_codes,
    time_slots,
    exclude_rule_id=None,
):
    slot_ids = {slot.id for slot in time_slots}
    weekday_code_set = set(weekday_codes)

    existing_rules = (
        AgendaHabitualEspecialista.objects.filter(
            especialista=specialist,
            activo=True,
        )
        .exclude(pk=exclude_rule_id)
        .prefetch_related("dias", "horarios")
    )
    for rule in existing_rules:
        first_date = max(start_date, rule.fecha_inicio)
        last_date = min(end_date, rule.fecha_fin)
        if first_date > last_date:
            continue

        existing_weekday_codes = {item.dia_semana for item in rule.dias.all()}
        overlapping_slot = _first_common_slot(slot_ids, rule.horarios.all())
        if not overlapping_slot:
            continue

        current = first_date
        while current <= last_date:
            day_code = _weekday_code_for_date(current)
            if day_code in weekday_code_set and day_code in existing_weekday_codes:
                return _build_availability_overlap_message(
                    specialist,
                    current,
                    overlapping_slot,
                )
            current = current.fromordinal(current.toordinal() + 1)

    existing_exceptions = (
        AgendaExcepcionEspecialista.objects.filter(
            especialista=specialist,
            activo=True,
            tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.AGREGAR,
            fecha__gte=start_date,
            fecha__lte=end_date,
        ).prefetch_related("horarios")
    )
    for exception in existing_exceptions:
        if _weekday_code_for_date(exception.fecha) not in weekday_code_set:
            continue

        overlapping_slot = _first_common_slot(slot_ids, exception.horarios.all())
        if overlapping_slot:
            return _build_availability_overlap_message(
                specialist,
                exception.fecha,
                overlapping_slot,
            )

    return None


def _validate_exception_overlap(specialist, dates, time_slots):
    slot_ids = {slot.id for slot in time_slots}
    date_set = set(dates)

    existing_rules = (
        AgendaHabitualEspecialista.objects.filter(
            especialista=specialist,
            activo=True,
            fecha_fin__gte=min(dates),
            fecha_inicio__lte=max(dates),
        ).prefetch_related("dias", "horarios")
    )
    for target_date in sorted(date_set):
        day_code = _weekday_code_for_date(target_date)
        for rule in existing_rules:
            if not (rule.fecha_inicio <= target_date <= rule.fecha_fin):
                continue
            if day_code not in {item.dia_semana for item in rule.dias.all()}:
                continue

            overlapping_slot = _first_common_slot(slot_ids, rule.horarios.all())
            if overlapping_slot:
                return _build_availability_overlap_message(
                    specialist,
                    target_date,
                    overlapping_slot,
                )

    existing_exceptions = (
        AgendaExcepcionEspecialista.objects.filter(
            especialista=specialist,
            activo=True,
            tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.AGREGAR,
            fecha__in=dates,
        ).prefetch_related("horarios")
    )
    for exception in existing_exceptions:
        overlapping_slot = _first_common_slot(slot_ids, exception.horarios.all())
        if overlapping_slot:
            return _build_availability_overlap_message(
                specialist,
                exception.fecha,
                overlapping_slot,
            )

    return None


def _time_slot_affects_schedule(slot):
    return (
        slot.agendas_habituales.exists()
        or slot.excepciones_agenda.exists()
        or slot.disponibilidades_cita.filter(fecha_hora__gt=timezone.now()).exists()
    )


def _sync_and_success(message, status=201):
    print("[admin_availability] sync:start", timezone.now().isoformat())
    sync_summary = sync_disponibilidad_citas()
    print("[admin_availability] sync:done", sync_summary)
    return _json(
        {
            "detail": message,
            "syncSummary": sync_summary,
        },
        status=status,
    )


def _success_without_sync(message, status=201):
    print("[admin_availability] sync:skipped")
    return _json(
        {
            "detail": message,
            "syncSummary": {
                "created": 0,
                "updated": 0,
                "deactivated": 0,
            },
        },
        status=status,
    )


@require_POST
@transaction.atomic
@_admin_required
def admin_remove_visible_slot(request, slot_id):
    slot = (
        DisponibilidadCita.objects.select_related("especialista__usuario", "horario_base")
        .prefetch_related("citas_origen", "citas_prospectos_origen", "citas_clientes_libres_origen")
        .filter(pk=slot_id)
        .first()
    )
    if not slot:
        return _json({"detail": "El cupo seleccionado ya no existe."}, status=404)

    booking = _find_blocking_booking(slot)
    status_label = _slot_status(slot, booking)
    if status_label != "disponible":
        return _json(
            {
                "detail": "Solo puedes quitar cupos que sigan disponibles y sin reserva.",
            },
            status=400,
        )

    if not slot.horario_base_id:
        slot.activo = False
        slot.save(update_fields=["activo", "updated_at"])
        return _success_without_sync("Cupo retirado correctamente.")

    slot_date = timezone.localtime(slot.fecha_hora).date()
    existing_exception = (
        AgendaExcepcionEspecialista.objects.filter(
            especialista_id=slot.especialista_id,
            fecha=slot_date,
            tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.BLOQUEAR,
            activo=True,
            horarios=slot.horario_base,
        )
        .first()
    )
    if not existing_exception:
        existing_exception = AgendaExcepcionEspecialista.objects.create(
            especialista=slot.especialista,
            fecha=slot_date,
            tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.BLOQUEAR,
            activo=True,
            detalle="Bloqueado manualmente desde dias y horarios visibles.",
        )
        existing_exception.horarios.add(slot.horario_base)

    return _sync_and_success("Disponibilidad retirada correctamente.")


@require_GET
@_admin_required
def admin_availability(request):
    slots = list(
        DisponibilidadCita.objects.select_related("especialista__usuario", "horario_base")
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
            Prefetch(
                "citas_clientes_libres_origen",
                queryset=CitaClienteLibre.objects.select_related(
                    "cliente__usuario",
                    "servicio_config__tipo_servicio",
                ).order_by("-created_at"),
            ),
            Prefetch(
                "citas_prospectos_origen",
                queryset=CitaProspecto.objects.select_related(
                    "prospecto",
                    "servicio_config__tipo_servicio",
                ).order_by("-created_at"),
            ),
        )
        .order_by("especialista__usuario__primer_nombre", "fecha_hora")
    )
    slot_items = [_slot_item(slot) for slot in slots]
    active_slots = [item for item in slot_items if item["status"] == "disponible"]
    reserved_slots = [item for item in slot_items if item["status"] == "reservado"]
    blocked_days = DiaBloqueadoAgendaGlobal.objects.filter(activo=True).count()

    specialists = list(
        Especialista.objects.select_related("usuario")
        .prefetch_related("especialidades_rel__especialidad")
        .filter(usuario__is_active=True)
        .order_by("usuario__primer_nombre", "usuario__apellido_paterno")
    )
    slots_by_specialist = {}
    for specialist in specialists:
        slots_by_specialist[specialist.pk] = [slot for slot in slots if slot.especialista_id == specialist.pk]

    habitual_qs = (
        AgendaHabitualEspecialista.objects.select_related("especialista__usuario")
        .prefetch_related(
            "dias",
            "horarios",
            "tipos_servicio",
            "tipos_proc_estetico",
            "procedimientos_esteticos",
        )
        .order_by("especialista__usuario__primer_nombre", "fecha_inicio")
    )
    exceptions_qs = (
        AgendaExcepcionEspecialista.objects.select_related("especialista__usuario")
        .prefetch_related(
            "horarios",
            "tipos_servicio",
            "tipos_proc_estetico",
            "procedimientos_esteticos",
        )
        .order_by("-fecha", "especialista__usuario__primer_nombre")
    )

    habitual_counts = {
        specialist_id: total
        for specialist_id, total in (
            AgendaHabitualEspecialista.objects.filter(activo=True)
            .values_list("especialista_id")
            .annotate(total=Count("id"))
        )
    }
    exception_counts = {
        specialist_id: total
        for specialist_id, total in (
            AgendaExcepcionEspecialista.objects.filter(activo=True, fecha__gte=timezone.localdate())
            .values_list("especialista_id")
            .annotate(total=Count("id"))
        )
    }

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
    time_slots = [
        _time_slot_item(item)
        for item in HorarioDisponibilidad.objects.order_by("hora_inicio", "hora_fin", "id")
    ]

    data = {
        "metrics": [
            _metric(
                "availability-open",
                "Cupos publicados",
                len(active_slots),
                "Disponibles hoy para reserva de clientes",
                "success",
            ),
            _metric(
                "availability-booked",
                "Cupos reservados",
                len(reserved_slots),
                "Ya tienen una cita asociada",
                "primary",
            ),
            _metric(
                "availability-habitual",
                "Horarios habituales",
                habitual_qs.count(),
                "Reglas recurrentes actualmente activas",
                "warning",
            ),
        ],
        "filters": {
            "specialists": [
                {
                    "id": specialist.pk,
                    "label": _full_name(specialist.usuario),
                    "secondaryLabel": ", ".join(
                        rel.especialidad.nombre for rel in specialist.especialidades_rel.all()
                    )
                    or "Sin especialidad",
                }
                for specialist in specialists
            ],
            "serviceTypes": service_types,
            "procedureTypes": procedure_types,
            "procedures": procedures,
            "timeSlots": time_slots,
            "weekdayOptions": _weekday_options(),
        },
        "specialistSummaries": [
            _specialist_summary_item(
                specialist,
                slots_by_specialist.get(specialist.pk, []),
                habitual_counts.get(specialist.pk, 0),
                exception_counts.get(specialist.pk, 0),
            )
            for specialist in specialists
        ],
        "habitualRules": [_habitual_rule_item(rule) for rule in habitual_qs],
        "exceptions": [_exception_item(item) for item in exceptions_qs],
        "globalBlocks": [
            _global_block_item(item)
            for item in DiaBloqueadoAgendaGlobal.objects.order_by("fecha")
        ],
        "slots": slot_items,
    }
    return _json(data)


@require_POST
@_admin_required
@transaction.atomic
def admin_create_time_slot(request):
    print("[admin_create_time_slot] start", timezone.now().isoformat())
    payload = _parse_payload(request)
    if payload is None:
        print("[admin_create_time_slot] invalid_json")
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)
    print("[admin_create_time_slot] payload", payload)

    errors = {}
    start_time = payload.get("startTime")
    end_time = payload.get("endTime")
    if not start_time:
        errors["startTime"] = "Debes indicar la hora de inicio."
    if not end_time:
        errors["endTime"] = "Debes indicar la hora de fin."

    try:
        parsed_start = _parse_time(start_time)
        parsed_end = _parse_time(end_time)
    except Exception:
        errors["time"] = "Debes indicar horas validas."
        parsed_start = None
        parsed_end = None

    if not errors and parsed_end <= parsed_start:
        errors["endTime"] = "La hora de fin debe ser posterior a la hora de inicio."

    if errors:
        print("[admin_create_time_slot] validation_errors", errors)
        return _json({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)

    print("[admin_create_time_slot] saving_slot", {
        "start": str(parsed_start),
        "end": str(parsed_end),
    })
    slot = HorarioDisponibilidad(
        hora_inicio=parsed_start,
        hora_fin=parsed_end,
        descripcion=(payload.get("detail") or "").strip(),
        orden=payload.get("order") or 0,
        activo=True,
    )
    try:
        slot.full_clean()
    except Exception as exc:
        print("[admin_create_time_slot] full_clean_error", repr(exc))
        return _json({"detail": str(exc)}, status=400)
    slot.save()
    print("[admin_create_time_slot] slot_saved", {
        "slot_id": slot.pk,
        "label": slot.etiqueta,
    })

    print("[admin_create_time_slot] sync_not_required_for_new_base_slot")
    return _success_without_sync(f"Horario base {slot.etiqueta} creado correctamente.")


@require_POST
@_admin_required
@transaction.atomic
def admin_update_time_slot(request, slot_id):
    slot = HorarioDisponibilidad.objects.filter(pk=slot_id).first()
    if not slot:
        return _json({"detail": "No encontramos el horario solicitado."}, status=404)

    payload = _parse_payload(request)
    if payload is None:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    errors = {}
    start_time = payload.get("startTime")
    end_time = payload.get("endTime")
    if not start_time:
        errors["startTime"] = "Debes indicar la hora de inicio."
    if not end_time:
        errors["endTime"] = "Debes indicar la hora de fin."

    try:
        parsed_start = _parse_time(start_time)
        parsed_end = _parse_time(end_time)
    except Exception:
        errors["time"] = "Debes indicar horas validas."
        parsed_start = None
        parsed_end = None

    if not errors and parsed_end <= parsed_start:
        errors["endTime"] = "La hora de fin debe ser posterior a la hora de inicio."

    has_reserved_future_slots = slot.disponibilidades_cita.filter(
        fecha_hora__gt=timezone.now(),
        citas_origen__estado__in=BLOCKING_RESERVATION_STATES,
    ).exists() or slot.disponibilidades_cita.filter(
        fecha_hora__gt=timezone.now(),
        citas_prospectos_origen__estado=CitaProspecto.Estado.PROGRAMADA,
    ).exists() or slot.disponibilidades_cita.filter(
        fecha_hora__gt=timezone.now(),
        citas_clientes_libres_origen__estado=CitaClienteLibre.Estado.PROGRAMADA,
    ).exists()
    if has_reserved_future_slots and (
        parsed_start != slot.hora_inicio or parsed_end != slot.hora_fin
    ):
        errors["time"] = (
            "No puedes cambiar un horario base mientras tenga reservas futuras asociadas."
        )

    if errors:
        return _json({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)

    slot.hora_inicio = parsed_start
    slot.hora_fin = parsed_end
    slot.descripcion = (payload.get("detail") or "").strip()
    slot.activo = bool(payload.get("active", True))
    slot.orden = payload.get("order") or 0
    slot.full_clean()
    slot.save()

    if _time_slot_affects_schedule(slot):
        return _sync_and_success(f"Horario base {slot.etiqueta} actualizado correctamente.", status=200)
    return _success_without_sync(f"Horario base {slot.etiqueta} actualizado correctamente.", status=200)


@require_POST
@_admin_required
@transaction.atomic
def admin_delete_time_slot(request, slot_id):
    slot = HorarioDisponibilidad.objects.filter(pk=slot_id).first()
    if not slot:
        return _json({"detail": "No encontramos el horario solicitado."}, status=404)

    if slot.disponibilidades_cita.filter(
        fecha_hora__gt=timezone.now(),
        citas_origen__estado__in=BLOCKING_RESERVATION_STATES,
    ).exists() or slot.disponibilidades_cita.filter(
        fecha_hora__gt=timezone.now(),
        citas_prospectos_origen__estado=CitaProspecto.Estado.PROGRAMADA,
    ).exists() or slot.disponibilidades_cita.filter(
        fecha_hora__gt=timezone.now(),
        citas_clientes_libres_origen__estado=CitaClienteLibre.Estado.PROGRAMADA,
    ).exists():
        return _json(
            {
                "detail": (
                    "No puedes eliminar este horario base porque ya tiene reservas futuras asociadas."
                )
            },
            status=400,
        )

    affects_schedule = _time_slot_affects_schedule(slot)
    slot.delete()
    if affects_schedule:
        return _sync_and_success("Horario base eliminado correctamente.", status=200)
    return _success_without_sync("Horario base eliminado correctamente.", status=200)


@require_POST
@_admin_required
@transaction.atomic
def admin_create_habitual_schedule(request):
    payload = _parse_payload(request)
    if payload is None:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    errors = {}
    specialist = _resolve_specialist(payload, errors)
    time_slots = _resolve_time_slots(payload.get("timeSlotIds") or [], errors)
    weekday_codes = sorted({int(value) for value in (payload.get("weekdayCodes") or [])})
    if not weekday_codes:
        errors["weekdayCodes"] = "Debes seleccionar al menos un dia de la semana."
    if any(value not in dict(DiaSemana.choices) for value in weekday_codes):
        errors["weekdayCodes"] = "Alguno de los dias seleccionados no es valido."

    try:
        start_date = _parse_date(payload.get("startDate"))
        end_date = _parse_date(payload.get("endDate"))
    except Exception:
        errors["dateRange"] = "Debes indicar fechas validas para el rango habitual."
        start_date = None
        end_date = None

    if start_date and end_date and end_date < start_date:
        errors["endDate"] = "La fecha final no puede ser anterior a la fecha inicial."

    service_types, procedure_types, procedures = _resolve_scope(payload, errors)

    overlap_error = None
    if not errors:
        overlap_error = _validate_habitual_schedule_overlap(
            specialist=specialist,
            start_date=start_date,
            end_date=end_date,
            weekday_codes=weekday_codes,
            time_slots=time_slots,
        )
        if overlap_error:
            errors["timeSlotIds"] = overlap_error

    if errors:
        return _json(
            {"detail": overlap_error or "Hay errores en el formulario.", "errors": errors},
            status=400,
        )

    rule = AgendaHabitualEspecialista.objects.create(
        especialista=specialist,
        fecha_inicio=start_date,
        fecha_fin=end_date,
        activo=True,
        detalle=(payload.get("detail") or "").strip(),
    )
    rule.horarios.set(time_slots)
    rule.tipos_servicio.set(service_types)
    rule.tipos_proc_estetico.set(procedure_types)
    rule.procedimientos_esteticos.set(procedures)
    AgendaHabitualDia.objects.bulk_create(
        [AgendaHabitualDia(agenda=rule, dia_semana=day) for day in weekday_codes]
    )

    return _sync_and_success("Horario habitual guardado correctamente.")


@require_POST
@_admin_required
@transaction.atomic
def admin_update_habitual_schedule(request, rule_id):
    rule = (
        AgendaHabitualEspecialista.objects.prefetch_related("dias", "horarios")
        .filter(pk=rule_id)
        .first()
    )
    if not rule:
        return _json({"detail": "No encontramos el horario habitual solicitado."}, status=404)

    payload = _parse_payload(request)
    if payload is None:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    errors = {}
    specialist = _resolve_specialist(payload, errors)
    time_slots = _resolve_time_slots(payload.get("timeSlotIds") or [], errors)
    weekday_codes = sorted({int(value) for value in (payload.get("weekdayCodes") or [])})
    if not weekday_codes:
        errors["weekdayCodes"] = "Debes seleccionar al menos un dia de la semana."
    if any(value not in dict(DiaSemana.choices) for value in weekday_codes):
        errors["weekdayCodes"] = "Alguno de los dias seleccionados no es valido."

    try:
        start_date = _parse_date(payload.get("startDate"))
        end_date = _parse_date(payload.get("endDate"))
    except Exception:
        errors["dateRange"] = "Debes indicar fechas validas para el rango habitual."
        start_date = None
        end_date = None

    if start_date and end_date and end_date < start_date:
        errors["endDate"] = "La fecha final no puede ser anterior a la fecha inicial."

    service_types, procedure_types, procedures = _resolve_scope(payload, errors)

    overlap_error = None
    if not errors:
        overlap_error = _validate_habitual_schedule_overlap(
            specialist=specialist,
            start_date=start_date,
            end_date=end_date,
            weekday_codes=weekday_codes,
            time_slots=time_slots,
            exclude_rule_id=rule.pk,
        )
        if overlap_error:
            errors["timeSlotIds"] = overlap_error

    if errors:
        return _json(
            {"detail": overlap_error or "Hay errores en el formulario.", "errors": errors},
            status=400,
        )

    rule.especialista = specialist
    rule.fecha_inicio = start_date
    rule.fecha_fin = end_date
    rule.activo = bool(payload.get("active", True))
    rule.detalle = (payload.get("detail") or "").strip()
    rule.full_clean()
    rule.save()
    rule.horarios.set(time_slots)
    rule.tipos_servicio.set(service_types)
    rule.tipos_proc_estetico.set(procedure_types)
    rule.procedimientos_esteticos.set(procedures)
    rule.dias.all().delete()
    AgendaHabitualDia.objects.bulk_create(
        [AgendaHabitualDia(agenda=rule, dia_semana=day) for day in weekday_codes]
    )

    return _sync_and_success("Horario habitual actualizado correctamente.", status=200)


@require_POST
@_admin_required
@transaction.atomic
def admin_delete_habitual_schedule(request, rule_id):
    rule = AgendaHabitualEspecialista.objects.filter(pk=rule_id).first()
    if not rule:
        return _json({"detail": "No encontramos el horario habitual solicitado."}, status=404)

    rule.delete()
    return _sync_and_success("Horario habitual eliminado correctamente.", status=200)


@require_POST
@_admin_required
@transaction.atomic
def admin_create_specialist_exception(request):
    payload = _parse_payload(request)
    if payload is None:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    errors = {}
    specialist = _resolve_specialist(payload, errors)
    time_slots = _resolve_time_slots(payload.get("timeSlotIds") or [], errors)
    exception_type = payload.get("type")
    if exception_type not in {
        AgendaExcepcionEspecialista.TipoExcepcion.AGREGAR,
        AgendaExcepcionEspecialista.TipoExcepcion.BLOQUEAR,
    }:
        errors["type"] = "Debes indicar si la excepcion agrega o bloquea disponibilidad."

    raw_dates = payload.get("dates") or []
    try:
        dates = sorted({_parse_date(value) for value in raw_dates})
    except Exception:
        errors["dates"] = "Debes indicar fechas validas para la excepcion."
        dates = []
    if not dates:
        errors["dates"] = "Debes indicar al menos una fecha para la excepcion."

    require_scope = exception_type == AgendaExcepcionEspecialista.TipoExcepcion.AGREGAR
    service_types, procedure_types, procedures = _resolve_scope(payload, errors, require_scope=require_scope)

    overlap_error = None
    if (
        not errors
        and exception_type == AgendaExcepcionEspecialista.TipoExcepcion.AGREGAR
    ):
        overlap_error = _validate_exception_overlap(
            specialist=specialist,
            dates=dates,
            time_slots=time_slots,
        )
        if overlap_error:
            errors["timeSlotIds"] = overlap_error

    if errors:
        return _json(
            {"detail": overlap_error or "Hay errores en el formulario.", "errors": errors},
            status=400,
        )

    created = []
    for target_date in dates:
        exception = AgendaExcepcionEspecialista.objects.create(
            especialista=specialist,
            fecha=target_date,
            tipo_excepcion=exception_type,
            activo=True,
            detalle=(payload.get("detail") or "").strip(),
        )
        exception.horarios.set(time_slots)
        if require_scope:
            exception.tipos_servicio.set(service_types)
            exception.tipos_proc_estetico.set(procedure_types)
            exception.procedimientos_esteticos.set(procedures)
        created.append(exception.pk)

    return _sync_and_success(
        f"Se registraron {len(created)} excepcion(es) para el especialista seleccionado."
    )


@require_POST
@_admin_required
@transaction.atomic
def admin_delete_specialist_exception(request, exception_id):
    exception = AgendaExcepcionEspecialista.objects.filter(pk=exception_id).first()
    if not exception:
        return _json({"detail": "No encontramos la excepcion solicitada."}, status=404)

    exception.delete()
    return _sync_and_success("Excepcion eliminada correctamente.", status=200)


@require_POST
@_admin_required
@transaction.atomic
def admin_manage_global_day(request):
    payload = _parse_payload(request)
    if payload is None:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    action = payload.get("action")
    try:
        target_date = _parse_date(payload.get("date"))
    except Exception:
        return _json({"detail": "Debes indicar una fecha valida."}, status=400)

    detail = (payload.get("detail") or "").strip()

    if action == "BLOQUEAR":
        block, created = DiaBloqueadoAgendaGlobal.objects.update_or_create(
            fecha=target_date,
            defaults={"activo": True, "detalle": detail},
        )
        return _sync_and_success(
            "El dia se marco como libre para todos los especialistas."
            if created
            else "El bloqueo global del dia fue actualizado."
        )

    if action == "RESTAURAR":
        block = DiaBloqueadoAgendaGlobal.objects.filter(fecha=target_date, activo=True).first()
        if not block:
            return _json(
                {"detail": "Ese dia no estaba bloqueado globalmente."},
                status=400,
            )
        block.activo = False
        block.save(update_fields=["activo", "updated_at"])
        return _sync_and_success(
            "El dia fue restaurado y los horarios habituales volvieron a aplicarse.",
            status=200,
        )

    return _json({"detail": "Debes indicar una accion global valida."}, status=400)
