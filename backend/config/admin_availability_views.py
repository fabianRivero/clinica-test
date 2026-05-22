import json
from functools import wraps
from datetime import datetime, timedelta
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from catalogs.models import Sucursal
from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualDia,
    AgendaHabitualEspecialista,
    DiaBloqueadoAgendaGlobal,
    DiaSemana,
)
from staff.models import Especialista
from operations.scheduling import get_concurrency, get_specialists_present

def _json(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})

def _load_payload(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None

def _admin_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return _json({"detail": "Autenticacion requerida."}, status=401)
        if not (user.is_superuser or user.es_administrador):
            return _json({"detail": "No tienes permisos para acceder a esta vista."}, status=403)
        if not (user.is_superuser or user.es_admin_principal):
            if not user.sucursal or not user.sucursal.activa:
                return _json(
                    {"detail": "Tu sucursal esta inactiva. Contacta al administrador principal."},
                    status=403,
                )
        return view_func(request, *args, **kwargs)
    return wrapped


def _get_user_branch(request):
    user = request.user
    if not (user.is_superuser or user.es_admin_principal):
        return user.sucursal

    branch_id = (
        request.headers.get("X-Selected-Branch-Id")
        or request.GET.get("branchId")
        or request.POST.get("branchId")
    )
    if branch_id:
        try:
            branch = Sucursal.objects.filter(pk=int(branch_id), activa=True).first()
            if branch:
                request.session["selected_branch_id"] = branch.pk
                return branch
        except (TypeError, ValueError):
            pass

    session_branch_id = request.session.get("selected_branch_id")
    if session_branch_id:
        branch = Sucursal.objects.filter(pk=session_branch_id, activa=True).first()
        if branch:
            return branch

    branch = Sucursal.objects.filter(es_principal=True, activa=True).first()
    if branch:
        request.session["selected_branch_id"] = branch.pk
    return branch


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
@_admin_required
def admin_availability(request):
    """
    Returns data aligned with frontend AdminAvailabilityResponse type.
    """
    branch = _get_user_branch(request)

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

    return _json({
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
@_admin_required
def admin_create_habitual_schedule(request):
    try:
        data = json.loads(request.body)
        specialist_ids = data.get("specialistIds", [])
        if not specialist_ids and data.get("specialistId"):
            specialist_ids = [data["specialistId"]]

        if not specialist_ids:
            return _json({"detail": "Debes seleccionar al menos un especialista."}, status=400)

        branch = _get_user_branch(request)
        if not branch:
            return _json({"detail": "Debes seleccionar una sucursal activa."}, status=400)
        if int(data.get("branchId") or 0) != branch.pk:
            return _json({"detail": "La sucursal enviada no coincide con la sucursal activa."}, status=400)
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
        return _json({"detail": "Agenda(s) habitual(es) creada(s) exitosamente"})
    except Exception as e:
        return _json({"detail": str(e)}, status=400)

@require_POST
@_admin_required
def admin_update_habitual_schedule(request, rule_id):
    try:
        data = json.loads(request.body)
        branch = _get_user_branch(request)
        agenda = AgendaHabitualEspecialista.objects.get(pk=rule_id, sucursal=branch)
        if agenda.especialista.sucursal_base_id != branch.pk:
            return _json({"detail": "Solo puedes gestionar especialistas de la sucursal activa."}, status=400)
        with transaction.atomic():
            if "branchId" in data and int(data["branchId"]) != branch.pk:
                return _json({"detail": "No puedes mover una agenda a otra sucursal desde esta pantalla."}, status=400)
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
        return _json({"detail": "Agenda habitual actualizada exitosamente"})
    except Exception as e:
        return _json({"detail": str(e)}, status=400)

@require_POST
@_admin_required
def admin_delete_habitual_schedule(request, rule_id):
    try:
        branch = _get_user_branch(request)
        AgendaHabitualEspecialista.objects.filter(pk=rule_id, sucursal=branch).delete()
        return _json({"detail": "Agenda eliminada"})
    except Exception as e:
        return _json({"detail": str(e)}, status=400)

@require_POST
@_admin_required
def admin_create_specialist_exception(request):
    try:
        data = json.loads(request.body)
        specialist_ids = data.get("specialistIds", [])
        if not specialist_ids and data.get("specialistId"):
            specialist_ids = [data["specialistId"]]
        
        if not specialist_ids:
            return _json({"detail": "Debes seleccionar al menos un especialista."}, status=400)

        branch = _get_user_branch(request)
        if not branch:
            return _json({"detail": "Debes seleccionar una sucursal activa."}, status=400)
        if int(data.get("branchId") or 0) != branch.pk:
            return _json({"detail": "La sucursal enviada no coincide con la sucursal activa."}, status=400)
        _validate_branch_specialists(branch, specialist_ids)

        dates = set(data.get("dates", []))

        range_start = data.get("rangeStartDate")
        range_end = data.get("rangeEndDate")
        weekday_codes = data.get("weekdayCodes") or []

        if range_start or range_end or weekday_codes:
            if not (range_start and range_end and weekday_codes):
                return _json({"detail": "Para usar rango debes enviar fecha inicio, fecha fin y dias de semana."}, status=400)
            start_date = datetime.strptime(range_start, "%Y-%m-%d").date()
            end_date = datetime.strptime(range_end, "%Y-%m-%d").date()
            if start_date > end_date:
                return _json({"detail": "La fecha inicio no puede ser mayor que la fecha fin."}, status=400)
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
            return _json({"detail": "Debes enviar al menos una fecha valida."}, status=400)

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
        return _json({"detail": "Excepcion(es) creada(s)"})
    except Exception as e:
        return _json({"detail": str(e)}, status=400)

@require_POST
@_admin_required
def admin_delete_specialist_exception(request, exception_id):
    try:
        branch = _get_user_branch(request)
        AgendaExcepcionEspecialista.objects.filter(pk=exception_id, sucursal=branch).delete()
        return _json({"detail": "Excepcion eliminada"})
    except Exception as e:
        return _json({"detail": str(e)}, status=400)

@require_POST
@_admin_required
def admin_manage_global_day(request):
    try:
        data = json.loads(request.body)
        action = data.get("action", "BLOQUEAR")
        date = data["date"]
        branch = _get_user_branch(request)
        if not branch:
            return _json({"detail": "Debes seleccionar una sucursal activa."}, status=400)

        specialists = list(_specialists_for_branch(branch))
        detail = f"[CIERRE_SUCURSAL] {data.get('detail', '')}".strip()
        if action == "BLOQUEAR":
            if not specialists:
                return _json({"detail": "No hay especialistas activos en esta sucursal para aplicar el cierre."}, status=400)
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
        return _json({"detail": "Dia de cierre de sucursal actualizado"})
    except Exception as e:
        return _json({"detail": str(e)}, status=400)

@require_POST
@_admin_required
def admin_check_concurrency(request):
    try:
        from datetime import timedelta
        data = json.loads(request.body)
        sucursal_id = data["sucursal_id"]
        fecha = datetime.strptime(data["fecha"], "%Y-%m-%d").date()
        hora_inicio = datetime.strptime(data["hora_inicio"], "%H:%M").time()
        
        # Calcular ventana de 1 hora antes y 1 hora despues para la concurrencia
        dt_inicio = datetime.combine(fecha, hora_inicio)
        dt_ventana_inicio = dt_inicio - timedelta(hours=1)
        dt_ventana_fin = dt_inicio + timedelta(hours=1)
        
        hora_ventana_inicio = dt_ventana_inicio.time()
        hora_ventana_fin = dt_ventana_fin.time()

        # Concurrencia en la ventana de 2 horas ( -1h a +1h )
        concurrency = get_concurrency(sucursal_id, fecha, hora_ventana_inicio, hora_ventana_fin)
        
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
            
        return _json({
            "concurrency": concurrency, 
            "presentes": especialistas,
            "hora_inicio": hora_ventana_inicio.strftime("%H:%M"),
            "hora_fin": hora_ventana_fin.strftime("%H:%M"),
            "hora_seleccionada": hora_inicio.strftime("%H:%M")
        })
    except Exception as e:
        return _json({"detail": str(e)}, status=400)

@_admin_required
def admin_get_branches(request):
    sucursales = list(Sucursal.objects.values('id', 'nombre', 'es_principal'))
    return _json({'branches': sucursales})
