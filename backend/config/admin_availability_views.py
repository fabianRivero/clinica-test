import json
from datetime import datetime, timedelta
from django.db import transaction
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from config.api_helpers import (
    admin_required,
    get_user_branch,
    json_response,
)
from catalogs.models import Sucursal
from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualDia,
    AgendaHabitualEspecialista,
    DiaBloqueadoAgendaGlobal,
    DiaSemana,
)
from staff.models import Especialista
from operations.scheduling import get_concurrency, get_concurrency_detail, get_maquinaria_conflicts, get_specialists_present


def _specialists_for_branch(branch):
    qs = Especialista.objects.select_related("usuario").filter(usuario__is_active=True)
    if branch:
        qs = qs.filter(sucursal_base=branch)
    return qs.order_by("usuario__primer_nombre", "usuario__apellido_paterno")


def _validate_branch_specialists(branch, specialist_ids):
    valid_ids = set(_specialists_for_branch(branch).filter(pk__in=specialist_ids).values_list("id", flat=True))
    requested_ids = {int(item) for item in specialist_ids}
    if requested_ids != valid_ids:
        raise ValueError("Solo puedes gestionar especialistas de la sucursal activa.")

@require_GET
@admin_required
def admin_availability(request):
    """
    Returns data aligned with frontend AdminAvailabilityResponse type.
    """
    branch = get_user_branch(request)

    # 1. Branches
    branches = list(Sucursal.objects.filter(activa=True).values("id", "nombre", "es_principal"))

    # 2. Filters
    specialists = []
    for sp in _specialists_for_branch(branch):
        specialists.append({
            "id": sp.id,
            "label": f"{sp.usuario.primer_nombre} {sp.usuario.apellido_paterno}",
            "secondaryLabel": sp.usuario.email
        })

    weekday_options = [
        {"value": d.value, "label": d.label} for d in DiaSemana
    ]

    # 3. Branch Blocks
    global_blocks = []
    branch_block_qs = AgendaExcepcionEspecialista.objects.filter(
        activo=True,
        tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.BLOQUEAR,
        detalle__startswith="[CIERRE_SUCURSAL]",
    )
    if branch:
        branch_block_qs = branch_block_qs.filter(sucursal=branch)
    seen_block_dates = set()
    for gb in branch_block_qs.order_by("-fecha", "id"):
        if gb.fecha in seen_block_dates:
            continue
        seen_block_dates.add(gb.fecha)
        global_blocks.append({
            "id": gb.pk,
            "date": str(gb.fecha),
            "dateLabel": gb.fecha.strftime("%d/%m/%Y"),
            "active": gb.activo,
            "detail": gb.detalle.replace("[CIERRE_SUCURSAL]", "").strip(),
        })

    # 4. Habitual Rules
    habitual_rules = []
    rules = AgendaHabitualEspecialista.objects.filter(activo=True).prefetch_related("dias")
    if branch:
        rules = rules.filter(sucursal=branch, especialista__sucursal_base=branch)
    for r in rules:
        habitual_rules.append({
            "id": r.id,
            "specialistId": r.especialista_id,
            "branchId": r.sucursal_id,
            "startDate": str(r.fecha_inicio),
            "endDate": str(r.fecha_fin) if r.fecha_fin else None,
            "weekdayCodes": list(r.dias.values_list("dia_semana", flat=True)),
            "weekdayLabels": [DiaSemana(d).label for d in r.dias.values_list("dia_semana", flat=True)],
            "startTime": r.hora_inicio.strftime("%H:%M") if r.hora_inicio else "00:00",
            "endTime": r.hora_fin.strftime("%H:%M") if r.hora_fin else "00:00",
            "detail": r.detalle,
            "active": r.activo
        })

    # 5. Exceptions
    exceptions = []
    exs = AgendaExcepcionEspecialista.objects.filter(activo=True).exclude(
        detalle__startswith="[CIERRE_SUCURSAL]"
    )
    if branch:
        exs = exs.filter(sucursal=branch, especialista__sucursal_base=branch)
    for e in exs:
        exceptions.append({
            "id": e.id,
            "specialistId": e.especialista_id,
            "branchId": e.sucursal_id,
            "date": str(e.fecha),
            "dateLabel": e.fecha.strftime("%d/%m/%Y"),
            "type": e.tipo_excepcion,
            "typeLabel": "Bloqueo" if e.tipo_excepcion == "BLOQUEAR" else "Hora Extra",
            "startTime": e.hora_inicio.strftime("%H:%M") if e.hora_inicio else "00:00",
            "endTime": e.hora_fin.strftime("%H:%M") if e.hora_fin else "00:00",
            "detail": e.detalle,
            "active": e.activo
        })

    return json_response({
        "metrics": [], # TODO: add metrics if needed
        "branches": branches,
        "filters": {
            "specialists": specialists,
            "weekdayOptions": weekday_options
        },
        "habitualRules": habitual_rules,
        "exceptions": exceptions,
        "globalBlocks": global_blocks
    })

@require_POST
@admin_required
def admin_create_habitual_schedule(request):
    try:
        data = json.loads(request.body)
        specialist_ids = data.get("specialistIds", [])
        if not specialist_ids and data.get("specialistId"):
            specialist_ids = [data["specialistId"]]

        if not specialist_ids:
            return json_response({"detail": "Debes seleccionar al menos un especialista."}, status=400)

        branch = get_user_branch(request)
        if not branch:
            return json_response({"detail": "Debes seleccionar una sucursal activa."}, status=400)
        if int(data.get("branchId") or 0) != branch.pk:
            return json_response({"detail": "La sucursal enviada no coincide con la sucursal activa."}, status=400)
        _validate_branch_specialists(branch, specialist_ids)

        with transaction.atomic():
            for sp_id in specialist_ids:
                agenda = AgendaHabitualEspecialista.objects.create(
                    especialista_id=sp_id,
                    sucursal_id=data["branchId"],
                    fecha_inicio=data["startDate"],
                    fecha_fin=data.get("endDate"),
                    hora_inicio=data.get("startTime"),
                    hora_fin=data.get("endTime"),
                    detalle=data.get("detail", "")
                )
                for d in data.get("weekdayCodes", []):
                    AgendaHabitualDia.objects.create(agenda=agenda, dia_semana=d)
        return json_response({"detail": "Agenda(s) habitual(es) creada(s) exitosamente"})
    except Exception as e:
        return json_response({"detail": str(e)}, status=400)

@require_POST
@admin_required
def admin_update_habitual_schedule(request, rule_id):
    try:
        data = json.loads(request.body)
        branch = get_user_branch(request)
        agenda = AgendaHabitualEspecialista.objects.get(pk=rule_id, sucursal=branch)
        if agenda.especialista.sucursal_base_id != branch.pk:
            return json_response({"detail": "Solo puedes gestionar especialistas de la sucursal activa."}, status=400)
        with transaction.atomic():
            if "branchId" in data and int(data["branchId"]) != branch.pk:
                return json_response({"detail": "No puedes mover una agenda a otra sucursal desde esta pantalla."}, status=400)
            if "startDate" in data: agenda.fecha_inicio = data["startDate"]
            if "endDate" in data: agenda.fecha_fin = data["endDate"]
            if "startTime" in data: agenda.hora_inicio = data["startTime"]
            if "endTime" in data: agenda.hora_fin = data["endTime"]
            if "detail" in data: agenda.detalle = data["detail"]
            if "active" in data: agenda.activo = data["active"]
            agenda.save()
            if "weekdayCodes" in data:
                agenda.dias.all().delete()
                for d in data["weekdayCodes"]:
                    AgendaHabitualDia.objects.create(agenda=agenda, dia_semana=d)
        return json_response({"detail": "Agenda habitual actualizada exitosamente"})
    except Exception as e:
        return json_response({"detail": str(e)}, status=400)

@require_POST
@admin_required
def admin_delete_habitual_schedule(request, rule_id):
    try:
        branch = get_user_branch(request)
        AgendaHabitualEspecialista.objects.filter(pk=rule_id, sucursal=branch).delete()
        return json_response({"detail": "Agenda eliminada"})
    except Exception as e:
        return json_response({"detail": str(e)}, status=400)

@require_POST
@admin_required
def admin_create_specialist_exception(request):
    try:
        data = json.loads(request.body)
        specialist_ids = data.get("specialistIds", [])
        if not specialist_ids and data.get("specialistId"):
            specialist_ids = [data["specialistId"]]
        
        if not specialist_ids:
            return json_response({"detail": "Debes seleccionar al menos un especialista."}, status=400)

        branch = get_user_branch(request)
        if not branch:
            return json_response({"detail": "Debes seleccionar una sucursal activa."}, status=400)
        if int(data.get("branchId") or 0) != branch.pk:
            return json_response({"detail": "La sucursal enviada no coincide con la sucursal activa."}, status=400)
        _validate_branch_specialists(branch, specialist_ids)

        dates = set(data.get("dates", []))

        range_start = data.get("rangeStartDate")
        range_end = data.get("rangeEndDate")
        weekday_codes = data.get("weekdayCodes") or []

        if range_start or range_end or weekday_codes:
            if not (range_start and range_end and weekday_codes):
                return json_response({"detail": "Para usar rango debes enviar fecha inicio, fecha fin y dias de semana."}, status=400)
            start_date = datetime.strptime(range_start, "%Y-%m-%d").date()
            end_date = datetime.strptime(range_end, "%Y-%m-%d").date()
            if start_date > end_date:
                return json_response({"detail": "La fecha inicio no puede ser mayor que la fecha fin."}, status=400)
            weekdays = {int(w) for w in weekday_codes}
            cursor = start_date
            while cursor <= end_date:
                if cursor.weekday() == 6:
                    django_weekday = 0
                else:
                    django_weekday = cursor.weekday() + 1
                if django_weekday in weekdays:
                    dates.add(cursor.strftime("%Y-%m-%d"))
                cursor += timedelta(days=1)

        if not dates:
            return json_response({"detail": "Debes enviar al menos una fecha valida."}, status=400)

        with transaction.atomic():
            for sp_id in specialist_ids:
                for d_str in sorted(dates):
                    AgendaExcepcionEspecialista.objects.create(
                        especialista_id=sp_id,
                        sucursal_id=data["branchId"],
                        fecha=d_str,
                        hora_inicio=data.get("startTime") or None,
                        hora_fin=data.get("endTime") or None,
                        tipo_excepcion=data["type"],
                        detalle=data.get("detail", "")
                    )
        return json_response({"detail": "Excepcion(es) creada(s)"})
    except Exception as e:
        return json_response({"detail": str(e)}, status=400)

@require_POST
@admin_required
def admin_delete_specialist_exception(request, exception_id):
    try:
        branch = get_user_branch(request)
        AgendaExcepcionEspecialista.objects.filter(pk=exception_id, sucursal=branch).delete()
        return json_response({"detail": "Excepcion eliminada"})
    except Exception as e:
        return json_response({"detail": str(e)}, status=400)

@require_POST
@admin_required
def admin_manage_global_day(request):
    try:
        data = json.loads(request.body)
        action = data.get("action", "BLOQUEAR")
        date = data["date"]
        branch = get_user_branch(request)
        if not branch:
            return json_response({"detail": "Debes seleccionar una sucursal activa."}, status=400)

        specialists = list(_specialists_for_branch(branch))
        detail = f"[CIERRE_SUCURSAL] {data.get('detail', '')}".strip()
        if action == "BLOQUEAR":
            if not specialists:
                return json_response({"detail": "No hay especialistas activos en esta sucursal para aplicar el cierre."}, status=400)
            with transaction.atomic():
                for specialist in specialists:
                    AgendaExcepcionEspecialista.objects.update_or_create(
                        especialista=specialist,
                        sucursal=branch,
                        fecha=date,
                        tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.BLOQUEAR,
                        detalle__startswith="[CIERRE_SUCURSAL]",
                        defaults={
                            "hora_inicio": None,
                            "hora_fin": None,
                            "activo": True,
                            "detalle": detail,
                        },
                    )
        else:
            AgendaExcepcionEspecialista.objects.filter(
                sucursal=branch,
                fecha=date,
                tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.BLOQUEAR,
                detalle__startswith="[CIERRE_SUCURSAL]",
            ).update(activo=False)
        return json_response({"detail": "Dia de cierre de sucursal actualizado"})
    except Exception as e:
        return json_response({"detail": str(e)}, status=400)

@require_POST
@admin_required
def admin_check_concurrency(request):
    try:
        from datetime import timedelta
        data = json.loads(request.body)
        
        # Validar campos requeridos
        if "sucursal_id" not in data:
            return json_response({"detail": "Falta sucursal_id"}, status=400)
        if "fecha" not in data:
            return json_response({"detail": "Falta fecha"}, status=400)
        if "hora_inicio" not in data:
            return json_response({"detail": "Falta hora_inicio"}, status=400)
        
        sucursal_id = data["sucursal_id"]
        if not sucursal_id:
            return json_response({"detail": "sucursal_id no puede ser null o vacío"}, status=400)
        
        fecha = datetime.strptime(data["fecha"][:10], "%Y-%m-%d").date()
        hora_str = data["hora_inicio"][:5]
        hora_inicio = datetime.strptime(hora_str, "%H:%M").time()
        
        # Calcular ventana de 1 hora antes y 1 hora despues para la concurrencia
        dt_inicio = datetime.combine(fecha, hora_inicio)
        dt_ventana_inicio = dt_inicio - timedelta(hours=1)
        dt_ventana_fin = dt_inicio + timedelta(hours=1)
        
        hora_ventana_inicio = dt_ventana_inicio.time()
        hora_ventana_fin = dt_ventana_fin.time()

        # Concurrencia detallada en la ventana de 2 horas ( -1h a +1h )
        appointments_raw = get_concurrency_detail(sucursal_id, fecha, hora_ventana_inicio, hora_ventana_fin)
        appointments = [
            {
                "cliente_nombre": row["cliente_nombre"],
                "tratamiento_nombre": row["tratamiento_nombre"],
                "hora": row["hora"].strftime("%Y-%m-%dT%H:%M:%S%z"),
                "tipo": row["tipo"],
            }
            for row in appointments_raw
        ]
        concurrency = len(appointments)
        
        # Especialistas presentes en el momento exacto (hora_inicio)
        presentes = get_specialists_present(sucursal_id, fecha, hora_inicio, hora_inicio)
        
        especialistas = []
        for esp in Especialista.objects.filter(id__in=presentes).select_related("usuario"):
            especialistas.append({
                "id": esp.id,
                "usuario__primer_nombre": esp.usuario.primer_nombre,
                "usuario__apellido_paterno": esp.usuario.apellido_paterno,
                "especialidad": ", ".join(esp.especialidades_rel.values_list("especialidad__nombre", flat=True))
            })
            
        return json_response({
            "concurrency": concurrency, 
            "appointments": appointments,
            "presentes": especialistas,
            "hora_inicio": hora_ventana_inicio.strftime("%H:%M"),
            "hora_fin": hora_ventana_fin.strftime("%H:%M"),
            "hora_seleccionada": hora_inicio.strftime("%H:%M")
        })
    except Exception as e:
        return json_response({"detail": str(e)}, status=400)


@require_GET
@admin_required
def admin_check_maquinaria(request):
    """Detect overlapping reservations for a set of Maquinaria in a time window.

    Query params:
        sucursalId (int): branch id.
        fecha (YYYY-MM-DD): window date.
        hora (HH:MM): window start time.
        duracionMinutos (int): window length, 1..480.
        maquinariaIds (comma-separated int ids).

    Returns ``{"conflictos": [...]}``. Never blocks the reservation; the
    admin uses the result as a visibility hint per the appointment-reservation-
    redesign spec.
    """
    sucursal_id_raw = request.GET.get("sucursalId")
    fecha_raw = request.GET.get("fecha")
    hora_raw = request.GET.get("hora")
    duracion_raw = request.GET.get("duracionMinutos")
    maquinaria_raw = request.GET.get("maquinariaIds", "")

    if not sucursal_id_raw:
        return json_response({"detail": "Falta sucursalId."}, status=400)
    if not fecha_raw:
        return json_response({"detail": "Falta fecha."}, status=400)
    if not hora_raw:
        return json_response({"detail": "Falta hora."}, status=400)
    if not duracion_raw:
        return json_response({"detail": "Falta duracionMinutos."}, status=400)

    try:
        sucursal_id = int(sucursal_id_raw)
    except (TypeError, ValueError):
        return json_response({"detail": "sucursalId invalido."}, status=400)

    try:
        fecha = datetime.strptime(fecha_raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return json_response({"detail": "fecha invalida (YYYY-MM-DD)."}, status=400)

    try:
        hora = datetime.strptime(hora_raw[:5], "%H:%M").time()
    except ValueError:
        return json_response({"detail": "hora invalida (HH:MM)."}, status=400)

    try:
        duracion_minutos = int(duracion_raw)
    except (TypeError, ValueError):
        return json_response({"detail": "duracionMinutos invalido."}, status=400)
    if duracion_minutos < 1 or duracion_minutos > 480:
        return json_response(
            {"detail": "duracionMinutos debe estar entre 1 y 480."}, status=400
        )

    try:
        maquinaria_ids = [int(x) for x in maquinaria_raw.split(",") if x.strip()]
    except ValueError:
        return json_response({"detail": "maquinariaIds invalida."}, status=400)

    if not maquinaria_ids:
        return json_response({"conflictos": []})

    # We expect items to be a list of {maquinariaId, cantidad}. The frontend
    # can pass the cantidad via repeated params `cantidades=1,2,3` aligned to
    # maquinariaIds; if absent, default to 1.
    cantidades_raw = request.GET.get("cantidades", "")
    if cantidades_raw:
        try:
            cantidades = [int(x) for x in cantidades_raw.split(",") if x.strip()]
        except ValueError:
            return json_response({"detail": "cantidades invalida."}, status=400)
    else:
        cantidades = [1] * len(maquinaria_ids)

    if len(cantidades) < len(maquinaria_ids):
        cantidades = list(cantidades) + [1] * (len(maquinaria_ids) - len(cantidades))

    items = [
        {"maquinariaId": mid, "cantidad": cant}
        for mid, cant in zip(maquinaria_ids, cantidades)
    ]

    conflictos = get_maquinaria_conflicts(
        sucursal_id=sucursal_id,
        fecha=fecha,
        hora_inicio=hora,
        duracion_minutos=duracion_minutos,
        items=items,
    )
    return json_response({"conflictos": conflictos})

@admin_required
def admin_get_branches(request):
    sucursales = list(Sucursal.objects.values('id', 'nombre', 'es_principal'))
    return json_response({'branches': sucursales})
