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
        # If any of the exception times is None, it's a whole day block
        if exc.hora_inicio is None or exc.hora_fin is None:
            return False
            
        # Check for any overlap. If point-in-time check, see if time falls in range.
        if hora_inicio == hora_fin:
            if exc.hora_inicio <= hora_inicio <= exc.hora_fin:
                return False
        else:
            if max(hora_inicio, exc.hora_inicio) < min(hora_fin, exc.hora_fin):
                return False # Blocked by an exception that overlaps with the requested block

    # 2. Check for adding exceptions
    adding_exceptions = AgendaExcepcionEspecialista.objects.filter(
        especialista_id=especialista_id,
        sucursal_id=sucursal_id,
        fecha=fecha,
        tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.AGREGAR,
        activo=True,
    )
    
    for exc in adding_exceptions:
        # If whole day added
        if exc.hora_inicio is None or exc.hora_fin is None:
            return True
            
        if exc.hora_inicio <= hora_inicio and (exc.hora_fin >= hora_fin if hora_inicio != hora_fin else exc.hora_fin >= hora_inicio):
            return True

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
    )
    
    if hora_inicio == hora_fin:
        habitual_agendas = habitual_agendas.filter(hora_fin__gte=hora_inicio)
    else:
        habitual_agendas = habitual_agendas.filter(hora_fin__gte=hora_fin)

    return habitual_agendas.distinct().exists()

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
    especialistas = Especialista.objects.filter(usuario__is_active=True)
    presentes = []
    for esp in especialistas:
        if check_specialist_presence(esp.id, sucursal_id, fecha, hora_inicio, hora_fin):
            presentes.append(esp.id)
    return presentes


def get_available_dates(sucursal_id, start_date, end_date):
    """
    Returns a set of dates that have at least one specialist potentially present.
    This is an optimization to avoid thousands of queries when building a calendar.
    """
    available_dates = set()
    
    # 1. Dates with 'AGREGAR' exceptions
    exceptions = AgendaExcepcionEspecialista.objects.filter(
        sucursal_id=sucursal_id,
        fecha__gte=start_date,
        fecha__lte=end_date,
        tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.AGREGAR,
        activo=True,
    ).values_list('fecha', flat=True)
    available_dates.update(exceptions)
    
    # 2. Dates covered by habitual agendas
    habitual = AgendaHabitualEspecialista.objects.filter(
        sucursal_id=sucursal_id,
        fecha_inicio__lte=end_date,
        fecha_fin__gte=start_date,
        activo=True,
    ).prefetch_related('dias')
    
    for h in habitual:
        # Calculate intersection of [start_date, end_date] and [h.fecha_inicio, h.fecha_fin]
        actual_start = max(start_date, h.fecha_inicio)
        actual_end = min(end_date, h.fecha_fin)
        
        allowed_weekdays = set(h.dias.values_list('dia_semana', flat=True))
        
        # Mapping from Django weekday to Python weekday (0=Mon...6=Sun)
        # Django: 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat
        # Python: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
        django_to_python = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
        python_allowed = {django_to_python[d] for d in allowed_weekdays}
        
        from datetime import timedelta
        curr = actual_start
        while curr <= actual_end:
            if curr.weekday() in python_allowed:
                available_dates.add(curr)
            curr += timedelta(days=1)
            
    return available_dates


def mark_expired_programmed_appointments_as_no_show(*args, **kwargs):
    """
    Automatically changes the status of PROGRAMADA appointments to NO_ASISTIO 
     if they are more than 24 hours old.
    """
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(days=1)
    
    # Update CitaProspecto
    CitaProspecto.objects.filter(
        estado=CitaProspecto.Estado.PROGRAMADA,
        fecha_hora__lt=cutoff
    ).update(estado=CitaProspecto.Estado.NO_ASISTIO)
    
    # Update CitaMedica (clients)
    CitaMedica.objects.filter(
        estado=CitaMedica.Estado.PROGRAMADA,
        fecha_hora__lt=cutoff
    ).update(estado=CitaMedica.Estado.NO_ASISTIO)
