from datetime import datetime, time
from django.db.models import Q
from django.utils import timezone
from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualEspecialista,
    CitaClienteLibre,
    CitaMedica,
    CitaProspecto,
)
from staff.models import Especialista

BLOCKING_RESERVATION_STATES = [
    CitaMedica.Estado.PROGRAMADA,
    CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA,
    CitaMedica.Estado.CONFIRMADA,
]

def check_specialist_presence(especialista_id, sucursal_id, fecha, hora_inicio, hora_fin):
    """
    Checks if a specialist is present at the given branch during the time block.
    """
    # 1. Check if there are blocking exceptions
    blocking_exceptions = AgendaExcepcionEspecialista.objects.filter(
        especialista_id=especialista_id,
        fecha=fecha,
        tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.BLOQUEAR,
        activo=True,
    )
    
    for exc in blocking_exceptions:
        # Check for any overlap
        if max(hora_inicio, exc.hora_inicio) < min(hora_fin, exc.hora_fin):
            return False # Blocked by an exception that overlaps with the requested block

    # 2. Check for adding exceptions
    adding_exceptions = AgendaExcepcionEspecialista.objects.filter(
        especialista_id=especialista_id,
        sucursal_id=sucursal_id,
        fecha=fecha,
        tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.AGREGAR,
        activo=True,
        hora_inicio__lte=hora_inicio,
        hora_fin__gte=hora_fin
    )
    if adding_exceptions.exists():
        return True # Present due to an adding exception covering the time block

    # 3. Check regular schedule (AgendaHabitualEspecialista)
    dia_semana_python = fecha.weekday()
    # 0=Lunes, ..., 6=Domingo in Python
    # Django model uses 0=Domingo, 1=Lunes, 2=Martes, 3=Miercoles, 4=Jueves, 5=Viernes, 6=Sabado
    dia_semana_mapping = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 0}
    dia_semana_django = dia_semana_mapping[dia_semana_python]

    habitual_agendas = AgendaHabitualEspecialista.objects.filter(
        especialista_id=especialista_id,
        sucursal_id=sucursal_id,
        fecha_inicio__lte=fecha,
        fecha_fin__gte=fecha,
        activo=True,
        dias__dia_semana=dia_semana_django,
        hora_inicio__lte=hora_inicio,
        hora_fin__gte=hora_fin
    ).distinct()

    return habitual_agendas.exists()

def get_concurrency(sucursal_id, fecha, hora_inicio, hora_fin):
    """
    Returns a summary of all appointments overlapping with the given time block in the branch.
    Useful for the administrator to gauge concurrency.
    """
    # Create aware datetime bounds
    start_dt = timezone.make_aware(datetime.combine(fecha, hora_inicio))
    end_dt = timezone.make_aware(datetime.combine(fecha, hora_fin))

    # Assuming appointments are point-in-time, we count those that fall inside the interval.
    # If appointments get a duration in the future, we would check for overlapping ranges instead.
    
    citas_medicas = CitaMedica.objects.filter(
        sucursal_id=sucursal_id,
        fecha_hora__gte=start_dt,
        fecha_hora__lt=end_dt,
        estado__in=BLOCKING_RESERVATION_STATES
    ).count()

    citas_prospecto = CitaProspecto.objects.filter(
        sucursal_id=sucursal_id,
        fecha_hora__gte=start_dt,
        fecha_hora__lt=end_dt,
        estado=CitaProspecto.Estado.PROGRAMADA
    ).count()

    citas_libre = CitaClienteLibre.objects.filter(
        sucursal_id=sucursal_id,
        fecha_hora__gte=start_dt,
        fecha_hora__lt=end_dt,
        estado=CitaClienteLibre.Estado.PROGRAMADA
    ).count()

    return citas_medicas + citas_prospecto + citas_libre

def get_specialists_present(sucursal_id, fecha, hora_inicio, hora_fin):
    """
    Returns a list of Specialist IDs present at the branch during the given time block.
    """
    especialistas = Especialista.objects.filter(activo=True)
    presentes = []
    for esp in especialistas:
        if check_specialist_presence(esp.id, sucursal_id, fecha, hora_inicio, hora_fin):
            presentes.append(esp.id)
    return presentes


def mark_expired_programmed_appointments_as_no_show(*args, **kwargs):
    pass

