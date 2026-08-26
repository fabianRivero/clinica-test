from datetime import datetime, time, timedelta
from django.db.models import Q, Value, CharField, F, Case, When
from django.db.models.functions import Coalesce, Concat
from django.utils import timezone
from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualEspecialista,
    CitaClienteLibre,
    CitaMedica,
    CitaMaquinaria,
    CitaProspecto,
)
from staff.models import Especialista
from notifications.services import create_notification

BLOCKING_RESERVATION_STATES = [
    CitaMedica.Estado.PROGRAMADA,
    CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
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
        activo=True,
        dias__dia_semana=dia_semana_django,
        hora_inicio__lte=hora_inicio,
    ).filter(
        Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha)
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

def get_concurrency_detail(sucursal_id, fecha, hora_inicio, hora_fin):
    """
    Returns detailed appointment list overlapping with the given time block in the branch.
    Includes client name, treatment name, time, and appointment type.
    """
    start_dt = timezone.make_aware(datetime.combine(fecha, hora_inicio))
    end_dt = timezone.make_aware(datetime.combine(fecha, hora_fin))

    citas_medicas_qs = CitaMedica.objects.filter(
        sucursal_id=sucursal_id,
        fecha_hora__gte=start_dt,
        fecha_hora__lt=end_dt,
        estado__in=BLOCKING_RESERVATION_STATES
    ).values(
        cliente_nombre=Case(
            When(operacion__paciente__usuario__primer_nombre__isnull=False,
                 then=Concat(
                     F('operacion__paciente__usuario__primer_nombre'),
                     Value(' '),
                     F('operacion__paciente__usuario__apellido_paterno'),
                 )),
            default=Value('Cliente no registrado'),
            output_field=CharField(),
        ),
        tratamiento_nombre=F('operacion__servicio_config__proc_estetico__proceso'),
        hora=F('fecha_hora'),
        tipo=Value('CitasMedicas', output_field=CharField()),
    )

    citas_prospecto_qs = CitaProspecto.objects.filter(
        sucursal_id=sucursal_id,
        fecha_hora__gte=start_dt,
        fecha_hora__lt=end_dt,
        estado=CitaProspecto.Estado.PROGRAMADA
    ).values(
        cliente_nombre=F('prospecto__primer_nombre'),
        tratamiento_nombre=F('servicio_config__proc_estetico__proceso'),
        hora=F('fecha_hora'),
        tipo=Value('CitasProspectos', output_field=CharField()),
    )

    citas_libre_qs = CitaClienteLibre.objects.filter(
        sucursal_id=sucursal_id,
        fecha_hora__gte=start_dt,
        fecha_hora__lt=end_dt,
        estado=CitaClienteLibre.Estado.PROGRAMADA
    ).values(
        cliente_nombre=Case(
            When(cliente__usuario__primer_nombre__isnull=False,
                 then=Concat(
                     F('cliente__usuario__primer_nombre'),
                     Value(' '),
                     F('cliente__usuario__apellido_paterno'),
                 )),
            default=Value('Cliente no registrado'),
            output_field=CharField(),
        ),
        tratamiento_nombre=F('servicio_config__proc_estetico__proceso'),
        hora=F('fecha_hora'),
        tipo=Value('CitasClientesLibres', output_field=CharField()),
    )

    # Execute queries and combine in Python to avoid SQLite ORDER BY limitation in UNION
    result = list(citas_medicas_qs) + list(citas_prospecto_qs) + list(citas_libre_qs)
    # Sort by hora (datetime field)
    result.sort(key=lambda x: x['hora'])
    return result

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
        activo=True,
    ).filter(
        Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=start_date)
    ).prefetch_related('dias')
    
    for h in habitual:
        # Calculate intersection of [start_date, end_date] and [h.fecha_inicio, h.fecha_fin]
        actual_start = max(start_date, h.fecha_inicio)
        # h.fecha_fin NULL = agenda "abierta": cubre hasta end_date
        actual_end = min(end_date, h.fecha_fin) if h.fecha_fin else end_date
        
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
            
    if not available_dates:
        return available_dates

    # 3. Keep only dates with at least one specialist effectively present.
    # This guarantees consistency when:
    # - all specialists are blocked by BLOQUEAR exceptions (date must disappear), or
    # - a date without habitual schedule is opened via AGREGAR (date must appear).
    specialist_ids = list(
        Especialista.objects.filter(usuario__is_active=True).values_list("id", flat=True)
    )
    if not specialist_ids:
        return set()

    present_dates = set()
    for current_date in available_dates:
        for specialist_id in specialist_ids:
            # Build smart checkpoints for the day from explicit configured boundaries,
            # so we don't require full-day coverage and don't depend on coarse hourly buckets.
            checkpoints = {time(12, 0)}

            habitual_ranges = AgendaHabitualEspecialista.objects.filter(
                especialista_id=specialist_id,
                sucursal_id=sucursal_id,
                fecha_inicio__lte=current_date,
                activo=True,
            ).filter(
                Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=current_date)
            ).prefetch_related("dias")

            dia_semana_python = current_date.weekday()
            dia_semana_mapping = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 0}
            dia_semana_django = dia_semana_mapping[dia_semana_python]

            for habitual_range in habitual_ranges:
                if habitual_range.dias.filter(dia_semana=dia_semana_django).exists():
                    checkpoints.add(habitual_range.hora_inicio)
                    checkpoints.add(habitual_range.hora_fin)

            day_exceptions = AgendaExcepcionEspecialista.objects.filter(
                especialista_id=specialist_id,
                sucursal_id=sucursal_id,
                fecha=current_date,
                activo=True,
            )
            for exc in day_exceptions:
                if exc.hora_inicio:
                    checkpoints.add(exc.hora_inicio)
                if exc.hora_fin:
                    checkpoints.add(exc.hora_fin)

            specialist_has_any_range = any(
                check_specialist_presence(
                    specialist_id,
                    sucursal_id,
                    current_date,
                    checkpoint,
                    checkpoint,
                )
                for checkpoint in checkpoints
            )
            if specialist_has_any_range:
                present_dates.add(current_date)
                break

    return present_dates


def get_maquinaria_conflicts(sucursal_id, fecha, hora_inicio, duracion_minutos, items):
    """Detect overlapping reservations for a set of Maquinaria in a time window.

    Args:
        sucursal_id: branch where the new cita would be created.
        fecha: date of the window.
        hora_inicio: time of the window start.
        duracion_minutos: window length in minutes.
        items: iterable of ``{"maquinariaId": int, "cantidad": int}``.

    Returns:
        A list of conflicts, one entry per maquinaría that has at least one
        overlapping reservation that, summed with the requested cantidad,
        exceeds ``Maquinaria.cantidad_total``. Each entry is shaped as::

            {
                "maquinariaId": int,
                "nombre": str,
                "cantidadSolicitada": int,
                "cantidadDisponible": int,
                "citasQueLaUsan": [
                    {
                        "citaId": int,
                        "cliente": str,
                        "fecha": str (YYYY-MM-DD),
                        "horaInicio": str (HH:MM),
                        "horaFin": str (HH:MM),
                        "planificada": bool,
                    },
                    ...
                ],
            }

        Items in ``items`` without overlap are omitted from the result.
    """
    from catalogs.models import Maquinaria

    if duracion_minutos <= 0:
        return []
    try:
        duracion_minutos = int(duracion_minutos)
    except (TypeError, ValueError):
        return []

    if not items:
        return []

    start_dt = timezone.make_aware(datetime.combine(fecha, hora_inicio))
    end_dt = start_dt + timedelta(minutes=duracion_minutos)

    # Pre-fetch maquinaría referenced by the items, scoped to the branch.
    # Globlales (sucursal=None) and own-branch rows are both visible.
    by_id = {
        m.pk: m
        for m in Maquinaria.objects.filter(
            Q(sucursal_id=sucursal_id) | Q(sucursal__isnull=True)
        )
    }

    conflicts = []
    for item in items:
        maquinaria_id = item.get("maquinariaId")
        try:
            cantidad_solicitada = int(item.get("cantidad") or 0)
        except (TypeError, ValueError):
            cantidad_solicitada = 0
        if cantidad_solicitada <= 0:
            continue

        maquinaria = by_id.get(maquinaria_id)
        if not maquinaria:
            # Caller asked about a maquinaría outside the branch's scope;
            # we cannot compute availability. Skip silently — the UI should
            # have filtered it out before calling this helper.
            continue

        overlapping_rows = (
            CitaMaquinaria.objects
            .filter(maquinaria=maquinaria, planificada=True)
            .select_related("cita", "cita__operacion__paciente__usuario")
        )

        citas_que_la_usan = []
        suma = 0
        for row in overlapping_rows:
            cita = row.cita
            # Consider only citas that block the slot:
            #   - in the same branch
            #   - in a non-blocking state
            #   - whose fecha_hora falls inside the requested window
            if cita.sucursal_id != sucursal_id:
                continue
            if cita.estado not in BLOCKING_RESERVATION_STATES:
                continue
            if not (start_dt <= cita.fecha_hora < end_dt):
                continue

            # Per-cita duration: cita.duracion_estimada_minutos defaults to
            # None, so we use the explicit duration when present and a 0
            # fallback otherwise (point-in-time).
            cita_duracion = cita.duracion_estimada_minutos or 0
            cita_fin = cita.fecha_hora + timedelta(minutes=cita_duracion)
            cita_inicio_local = timezone.localtime(cita.fecha_hora)
            cita_fin_local = timezone.localtime(cita_fin)

            cliente_nombre = "Cliente no registrado"
            if cita.operacion and getattr(cita.operacion, "paciente", None):
                usuario = getattr(cita.operacion.paciente, "usuario", None)
                if usuario:
                    partes = [
                        usuario.primer_nombre or "",
                        usuario.apellido_paterno or "",
                    ]
                    full = " ".join(p for p in partes if p).strip()
                    if full:
                        cliente_nombre = full

            citas_que_la_usan.append(
                {
                    "citaId": cita.pk,
                    "cliente": cliente_nombre,
                    "fecha": cita_inicio_local.strftime("%Y-%m-%d"),
                    "horaInicio": cita_inicio_local.strftime("%H:%M"),
                    "horaFin": cita_fin_local.strftime("%H:%M"),
                    "planificada": row.planificada,
                }
            )
            suma += row.cantidad

        if cantidad_solicitada + suma > maquinaria.cantidad_total:
            cantidad_disponible = max(maquinaria.cantidad_total - suma, 0)
            conflicts.append(
                {
                    "maquinariaId": maquinaria.pk,
                    "nombre": str(maquinaria),
                    "cantidadSolicitada": cantidad_solicitada,
                    "cantidadDisponible": cantidad_disponible,
                    "citasQueLaUsan": citas_que_la_usan,
                }
            )

    return conflicts


def mark_expired_programmed_appointments_as_no_show(reference_time=None):
    """
    Changes PROGRAMADA appointments to NO_ASISTIO once the appointment day has passed.
    Rule: any PROGRAMADA appointment with local date < current local date becomes NO_ASISTIO.
    """
    current_time = reference_time or timezone.now()
    today = timezone.localdate(current_time)

    prospect_no_show = CitaProspecto.objects.filter(
        estado=CitaProspecto.Estado.PROGRAMADA,
        fecha_hora__date__lt=today,
    ).update(estado=CitaProspecto.Estado.NO_ASISTIO)

    stale_medical_appointments = list(
        CitaMedica.objects.filter(
            estado=CitaMedica.Estado.PROGRAMADA,
            fecha_hora__date__lt=today,
        )
        .select_related("operacion__paciente__usuario", "sucursal")
    )
    medical_no_show = CitaMedica.objects.filter(
        estado=CitaMedica.Estado.PROGRAMADA,
        fecha_hora__date__lt=today,
    ).update(estado=CitaMedica.Estado.NO_ASISTIO)

    for appointment in stale_medical_appointments:
        cliente = getattr(appointment.operacion, "paciente", None)
        recipient = getattr(cliente, "usuario", None) if cliente else None
        if not recipient:
            continue
        proc_estetico = getattr(appointment.operacion.servicio_config, "proc_estetico", None)
        procedimiento = proc_estetico.proceso if proc_estetico else (
            getattr(appointment.operacion.servicio_config.tipo_servicio, "tipo", "Procedimiento") if hasattr(appointment.operacion.servicio_config, "tipo_servicio") else "Procedimiento"
        )
        fecha_cita = timezone.localtime(appointment.fecha_hora).strftime('%d/%m/%Y')
        hora_cita = timezone.localtime(appointment.fecha_hora).strftime('%H:%M')
        create_notification(
            recipient=recipient,
            branch=appointment.sucursal,
            type="CLIENT_APPOINTMENT_CANCELLED",
            title="No asististe a tu cita",
            message=f"No asististe a la cita con la fecha {fecha_cita}, a la hora {hora_cita}, para el procedimiento {procedimiento}. Puedes verlo en tu registro de citas.",
            action_url="/cliente/reservas",
            payload={
                "appointmentType": "cita_medica",
                "appointmentId": appointment.pk,
                "newStatus": CitaMedica.Estado.NO_ASISTIO,
            },
            source_event="appointment_marked_no_show",
            source_entity_type="cita_medica",
            source_entity_id=appointment.pk,
        )

    return {
        "no_show": prospect_no_show + medical_no_show,
        "citas_prospecto": prospect_no_show,
        "citas_medicas": medical_no_show,
    }
