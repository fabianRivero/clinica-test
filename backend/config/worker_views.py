from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone

from config.api_helpers import json_response
from operations.models import AgendaExcepcionEspecialista, AgendaHabitualEspecialista, DiaSemana
from staff.models import Especialista


# Python weekday (0=Mon..6=Sun) → Django DiaSemana (0=Sun,1=Mon..6=Sat)
PYTHON_TO_DJANGO_WEEKDAY = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 0}

WEEKDAY_LABELS = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]


def worker_availability(request):
    """
    GET /api/trabajador/disponibilidad/

    Returns the current week's availability for the authenticated specialist.
    Combines habitual schedules (AgendaHabitualEspecialista) with
    exception overrides (AgendaExcepcionEspecialista).

    Auth: session-based, requires es_trabajador=True on the user.
    """
    if not request.user.is_authenticated:
        return json_response({"detail": "Autenticacion requerida."}, status=401)

    if not getattr(request.user, "es_trabajador", False):
        return json_response({"detail": "No tienes acceso a esta informacion."}, status=403)

    try:
        especialista = Especialista.objects.select_related("sucursal_base").get(usuario=request.user)
    except Especialista.DoesNotExist:
        return json_response({"detail": "No tienes acceso a esta informacion."}, status=403)

    branch_name = especialista.sucursal_base.nombre if especialista.sucursal_base else ""

    # Week boundaries: Monday (weekday 0) to Sunday (weekday 6)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    days = []
    for offset in range(7):
        current_date = monday + timedelta(days=offset)
        python_weekday = current_date.weekday()  # 0=Mon .. 6=Sun
        django_weekday = PYTHON_TO_DJANGO_WEEKDAY[python_weekday]

        day_shifts = []
        day_blocks = []

        # Check for BLOQUEAR exception first — it overrides habitual shifts
        bloquear_exs = AgendaExcepcionEspecialista.objects.filter(
            especialista=especialista,
            fecha=current_date,
            activo=True,
            tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.BLOQUEAR,
        )
        bloquear_found = bloquear_exs.exists()

        if bloquear_found:
            # BLOQUEAR overrides — clear shifts, add block per exception
            for exc in bloquear_exs:
                day_blocks.append({
                    "reason": exc.detalle or "Bloqueo",
                    "type": "BLOQUEAR",
                })
        else:
            # No BLOQUEAR — aggregate HABITUAL shifts
            habitual_agendas = AgendaHabitualEspecialista.objects.filter(
                especialista=especialista,
                activo=True,
                fecha_inicio__lte=current_date,
                fecha_fin__gte=current_date,
            ).prefetch_related("dias")

            for agenda in habitual_agendas:
                # Check if this agenda covers the current weekday via dias relation
                if agenda.dias.filter(dia_semana=django_weekday).exists():
                    if agenda.hora_inicio and agenda.hora_fin:
                        day_shifts.append({
                            "start": agenda.hora_inicio.strftime("%H:%M"),
                            "end": agenda.hora_fin.strftime("%H:%M"),
                            "source": "HABITUAL",
                        })

            # AGREGAR exceptions — append to shifts
            agregar_exs = AgendaExcepcionEspecialista.objects.filter(
                especialista=especialista,
                fecha=current_date,
                activo=True,
                tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.AGREGAR,
            )
            for exc in agregar_exs:
                if exc.hora_inicio and exc.hora_fin:
                    day_shifts.append({
                        "start": exc.hora_inicio.strftime("%H:%M"),
                        "end": exc.hora_fin.strftime("%H:%M"),
                        "source": "EXCEPTION_AGREGAR",
                    })

        # Empty state: no shifts and no blocks → block with default reason
        if not day_shifts and not day_blocks:
            day_blocks.append({
                "reason": "Sin agenda configurada",
                "type": "BLOQUEAR",
            })

        days.append({
            "date": current_date.isoformat(),
            "weekdayLabel": WEEKDAY_LABELS[python_weekday],
            "weekdayCode": python_weekday,
            "branchName": branch_name,
            "shifts": day_shifts,
            "blocks": day_blocks,
        })

    return json_response({
        "weekStart": monday.isoformat(),
        "weekEnd": sunday.isoformat(),
        "days": days,
    })