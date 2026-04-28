from collections import defaultdict
from datetime import datetime

from django.db import IntegrityError
from django.db.models import Count, Prefetch
from django.utils import timezone

from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualEspecialista,
    CitaMedica,
    DiaBloqueadoAgendaGlobal,
    DisponibilidadCita,
)


BLOCKING_RESERVATION_STATES = {
    CitaMedica.Estado.PROGRAMADA,
    CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA,
    CitaMedica.Estado.CONFIRMADA,
}


def weekday_code_for_date(target_date):
    return (target_date.weekday() + 1) % 7


def combine_slot_datetime(target_date, slot_time):
    return timezone.make_aware(datetime.combine(target_date, slot_time)).replace(
        second=0,
        microsecond=0,
    )


def _scope_id_dict(instance):
    return {
        "service_type_ids": set(instance.tipos_servicio.values_list("id", flat=True)),
        "procedure_type_ids": set(instance.tipos_proc_estetico.values_list("id", flat=True)),
        "procedure_ids": set(instance.procedimientos_esteticos.values_list("id", flat=True)),
    }


def _merge_scope_ids(target, source):
    target["service_type_ids"].update(source["service_type_ids"])
    target["procedure_type_ids"].update(source["procedure_type_ids"])
    target["procedure_ids"].update(source["procedure_ids"])


def _iter_rule_dates(start_date, end_date, weekday_codes):
    current = start_date
    while current <= end_date:
        if weekday_code_for_date(current) in weekday_codes:
            yield current
        current = current.fromordinal(current.toordinal() + 1)


def build_desired_availability_map():
    blocked_dates = set(
        DiaBloqueadoAgendaGlobal.objects.filter(activo=True).values_list("fecha", flat=True)
    )

    desired = {}
    today = timezone.localdate()

    habitual_rules = (
        AgendaHabitualEspecialista.objects.filter(activo=True, fecha_fin__gte=today)
        .select_related("especialista__usuario")
        .prefetch_related(
            "horarios",
            "dias",
            "tipos_servicio",
            "tipos_proc_estetico",
            "procedimientos_esteticos",
        )
    )

    for rule in habitual_rules:
        weekday_codes = set(rule.dias.values_list("dia_semana", flat=True))
        horarios = list(rule.horarios.filter(activo=True))
        if not weekday_codes or not horarios:
            continue

        scope_ids = _scope_id_dict(rule)
        if not any(scope_ids.values()):
            continue

        start_date = max(rule.fecha_inicio, today)
        for target_date in _iter_rule_dates(start_date, rule.fecha_fin, weekday_codes):
            if target_date in blocked_dates:
                continue
            for horario in horarios:
                slot_dt = combine_slot_datetime(target_date, horario.hora_inicio)
                key = (rule.especialista_id, slot_dt)
                if key not in desired:
                    desired[key] = {
                        "specialist_id": rule.especialista_id,
                        "horario_base_id": horario.id,
                        "datetime": slot_dt,
                        "detail": rule.detalle,
                        "scope": {
                            "service_type_ids": set(scope_ids["service_type_ids"]),
                            "procedure_type_ids": set(scope_ids["procedure_type_ids"]),
                            "procedure_ids": set(scope_ids["procedure_ids"]),
                        },
                    }
                else:
                    _merge_scope_ids(desired[key]["scope"], scope_ids)

    exceptions = (
        AgendaExcepcionEspecialista.objects.filter(activo=True, fecha__gte=today)
        .select_related("especialista__usuario")
        .prefetch_related(
            "horarios",
            "tipos_servicio",
            "tipos_proc_estetico",
            "procedimientos_esteticos",
        )
    )

    for exception in exceptions:
        horarios = list(exception.horarios.filter(activo=True))
        if not horarios or exception.fecha in blocked_dates:
            continue

        scope_ids = _scope_id_dict(exception)
        for horario in horarios:
            slot_dt = combine_slot_datetime(exception.fecha, horario.hora_inicio)
            key = (exception.especialista_id, slot_dt)
            if exception.tipo_excepcion == AgendaExcepcionEspecialista.TipoExcepcion.BLOQUEAR:
                desired.pop(key, None)
                continue

            if not any(scope_ids.values()):
                continue

            if key not in desired:
                desired[key] = {
                    "specialist_id": exception.especialista_id,
                    "horario_base_id": horario.id,
                    "datetime": slot_dt,
                    "detail": exception.detalle,
                    "scope": {
                        "service_type_ids": set(scope_ids["service_type_ids"]),
                        "procedure_type_ids": set(scope_ids["procedure_type_ids"]),
                        "procedure_ids": set(scope_ids["procedure_ids"]),
                    },
                }
            else:
                desired[key]["detail"] = exception.detalle or desired[key]["detail"]
                _merge_scope_ids(desired[key]["scope"], scope_ids)

    return desired


def sync_disponibilidad_citas():
    print("[sync_disponibilidad_citas] start", timezone.now().isoformat())
    desired_map = build_desired_availability_map()
    print("[sync_disponibilidad_citas] desired_map_built", {"count": len(desired_map)})
    now = timezone.now()

    existing_slots = (
        DisponibilidadCita.objects.filter(fecha_hora__gte=now)
        .select_related("horario_base", "especialista__usuario")
        .prefetch_related(
            "tipos_servicio",
            "tipos_proc_estetico",
            "procedimientos_esteticos",
            Prefetch(
                "citas_origen",
                queryset=CitaMedica.objects.only("id", "estado", "disponibilidad_id"),
            ),
        )
    )
    print(
        "[sync_disponibilidad_citas] existing_slots_loaded",
        {"count": existing_slots.count()},
    )

    existing_by_key = {(slot.especialista_id, slot.fecha_hora): slot for slot in existing_slots}
    print(
        "[sync_disponibilidad_citas] existing_by_key_ready",
        {"count": len(existing_by_key)},
    )
    created_count = 0
    updated_count = 0
    deactivated_count = 0

    for key, slot in existing_by_key.items():
        desired = desired_map.get(key)
        has_blocking_booking = any(
            cita.estado in BLOCKING_RESERVATION_STATES for cita in slot.citas_origen.all()
        )

        if desired:
            changed_fields = []
            if slot.horario_base_id != desired["horario_base_id"]:
                slot.horario_base_id = desired["horario_base_id"]
                changed_fields.append("horario_base")
            if not slot.activo:
                slot.activo = True
                changed_fields.append("activo")
            if slot.detalle != desired["detail"]:
                slot.detalle = desired["detail"]
                changed_fields.append("detalle")
            if changed_fields:
                changed_fields.append("updated_at")
                slot.save(update_fields=changed_fields)
                updated_count += 1

            current_service_type_ids = {item.id for item in slot.tipos_servicio.all()}
            current_procedure_type_ids = {item.id for item in slot.tipos_proc_estetico.all()}
            current_procedure_ids = {item.id for item in slot.procedimientos_esteticos.all()}

            if current_service_type_ids != desired["scope"]["service_type_ids"]:
                slot.tipos_servicio.set(sorted(desired["scope"]["service_type_ids"]))
            if current_procedure_type_ids != desired["scope"]["procedure_type_ids"]:
                slot.tipos_proc_estetico.set(sorted(desired["scope"]["procedure_type_ids"]))
            if current_procedure_ids != desired["scope"]["procedure_ids"]:
                slot.procedimientos_esteticos.set(sorted(desired["scope"]["procedure_ids"]))
            desired_map.pop(key, None)
            continue

        if has_blocking_booking or not slot.activo:
            continue

        slot.activo = False
        slot.save(update_fields=["activo", "updated_at"])
        deactivated_count += 1

    for desired in desired_map.values():
        defaults = {
            "horario_base_id": desired["horario_base_id"],
            "activo": True,
            "detalle": desired["detail"],
        }
        try:
            slot, created = DisponibilidadCita.objects.get_or_create(
                especialista_id=desired["specialist_id"],
                fecha_hora=desired["datetime"],
                defaults=defaults,
            )
        except IntegrityError:
            slot = DisponibilidadCita.objects.get(
                especialista_id=desired["specialist_id"],
                fecha_hora=desired["datetime"],
            )
            created = False

        changed_fields = []
        if slot.horario_base_id != desired["horario_base_id"]:
            slot.horario_base_id = desired["horario_base_id"]
            changed_fields.append("horario_base")
        if not slot.activo:
            slot.activo = True
            changed_fields.append("activo")
        if slot.detalle != desired["detail"]:
            slot.detalle = desired["detail"]
            changed_fields.append("detalle")
        if changed_fields:
            changed_fields.append("updated_at")
            slot.save(update_fields=changed_fields)

        slot.tipos_servicio.set(sorted(desired["scope"]["service_type_ids"]))
        slot.tipos_proc_estetico.set(sorted(desired["scope"]["procedure_type_ids"]))
        slot.procedimientos_esteticos.set(sorted(desired["scope"]["procedure_ids"]))
        if created:
            created_count += 1
        else:
            updated_count += 1

    summary = {
        "created": created_count,
        "updated": updated_count,
        "deactivated": deactivated_count,
    }
    print("[sync_disponibilidad_citas] finish", summary)
    return summary


def specialist_schedule_summary():
    today = timezone.localdate()
    slots = (
        DisponibilidadCita.objects.filter(activo=True, fecha_hora__date__gte=today)
        .select_related("especialista__usuario", "horario_base")
        .order_by("especialista__usuario__primer_nombre", "fecha_hora")
    )
    data = defaultdict(
        lambda: {
            "future_slot_count": 0,
            "next_slot": "",
            "habitual_rule_count": 0,
            "exception_count": 0,
        }
    )
    for slot in slots:
        summary = data[slot.especialista_id]
        summary["future_slot_count"] += 1
        if not summary["next_slot"]:
            summary["next_slot"] = timezone.localtime(slot.fecha_hora).strftime("%d/%m/%Y %H:%M")

    for specialist_id, count in (
        AgendaHabitualEspecialista.objects.filter(activo=True)
        .values_list("especialista_id")
        .annotate(total_count=Count("id"))
    ):
        data[specialist_id]["habitual_rule_count"] = count

    for specialist_id, count in (
        AgendaExcepcionEspecialista.objects.filter(activo=True, fecha__gte=today)
        .values_list("especialista_id")
        .annotate(total_count=Count("id"))
    ):
        data[specialist_id]["exception_count"] = count

    return data
