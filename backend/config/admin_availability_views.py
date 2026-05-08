import json
from functools import wraps
from datetime import datetime
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
        return view_func(request, *args, **kwargs)
    return wrapped

@require_GET
@_admin_required
def admin_availability(request):
    """
    Returns data aligned with frontend AdminAvailabilityResponse type.
    """
    # 1. Branches
    branches = list(Sucursal.objects.filter(activa=True).values("id", "nombre", "es_principal"))

    # 2. Filters
    specialists = []
    for sp in Especialista.objects.select_related("usuario").filter(usuario__is_active=True):
        specialists.append({
            "id": sp.id,
            "label": f"{sp.usuario.primer_nombre} {sp.usuario.apellido_paterno}",
            "secondaryLabel": sp.usuario.email
        })

    weekday_options = [
        {"value": d.value, "label": d.label} for d in DiaSemana
    ]

    # 3. Global Blocks
    global_blocks = []
    for gb in DiaBloqueadoAgendaGlobal.objects.all().order_by("-fecha"):
        global_blocks.append({
            "id": gb.id,
            "date": str(gb.fecha),
            "dateLabel": gb.fecha.strftime("%d/%m/%Y"),
            "active": gb.activo,
            "detail": gb.detalle
        })

    # 4. Habitual Rules
    habitual_rules = []
    rules = AgendaHabitualEspecialista.objects.filter(activo=True).prefetch_related("dias")
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
    exs = AgendaExcepcionEspecialista.objects.filter(activo=True)
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
        agenda = AgendaHabitualEspecialista.objects.get(pk=rule_id)
        with transaction.atomic():
            if "branchId" in data: agenda.sucursal_id = data["branchId"]
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
        AgendaHabitualEspecialista.objects.filter(pk=rule_id).delete()
        return _json({"detail": "Agenda eliminada"})
    except Exception as e:
        return _json({"detail": str(e)}, status=400)

@require_POST
@_admin_required
def admin_create_specialist_exception(request):
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            for d_str in data.get("dates", []):
                AgendaExcepcionEspecialista.objects.create(
                    especialista_id=data["specialistId"],
                    sucursal_id=data["branchId"],
                    fecha=d_str,
                    hora_inicio=data.get("startTime"),
                    hora_fin=data.get("endTime"),
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
        AgendaExcepcionEspecialista.objects.filter(pk=exception_id).delete()
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
        if action == "BLOQUEAR":
            DiaBloqueadoAgendaGlobal.objects.update_or_create(
                fecha=date,
                defaults={"activo": True, "detalle": data.get("detail", "")}
            )
        else:
            DiaBloqueadoAgendaGlobal.objects.filter(fecha=date).update(activo=False)
        return _json({"detail": "Dia global actualizado"})
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

