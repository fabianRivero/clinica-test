import re

filepath = "config/api_views.py"
with open(filepath, "r") as f:
    content = f.read()

# Replace admin_cliente_reservation_availability
content = re.sub(
    r"def admin_cliente_reservation_availability\(request, client_id, operation_id\):.*?return _json\(\{\"operation\": _client_operation_item\(operacion\), \"calendar\": _client_operation_slot_map\(operacion\)\}\)",
    r"""def admin_cliente_reservation_availability(request, client_id, operation_id):
    cliente = Cliente.objects.filter(pk=client_id).first()
    if not cliente:
        return _json({"detail": "No encontramos el cliente solicitado."}, status=404)

    operacion = (
        Operacion.objects.filter(paciente=cliente, pk=operation_id)
        .select_related("servicio_config__tipo_servicio", "servicio_config__proc_estetico")
        .prefetch_related(
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.order_by("fecha_hora"),
            ),
            Prefetch("cuotas_plan_pagos", queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota")),
        )
        .first()
    )
    if not operacion:
        return _json({"detail": "No encontramos la operacion solicitada para este cliente."}, status=404)
    if operacion.estado != Operacion.Estado.EN_PROCESO:
        return _json({"detail": "Solo se pueden reservar citas para tratamientos en proceso."}, status=400)

    return _json({"operation": _client_operation_item(operacion)})""",
    content,
    flags=re.DOTALL
)

# Replace admin_cliente_create_reservation
content = re.sub(
    r"def admin_cliente_create_reservation\(request, client_id, operation_id\):.*?return _json\([\s\S]*?status=201,[\s\S]*?\)",
    r"""def admin_cliente_create_reservation(request, client_id, operation_id):
    cliente = Cliente.objects.filter(pk=client_id).first()
    if not cliente:
        return _json({"detail": "No encontramos el cliente solicitado."}, status=404)

    operacion = (
        Operacion.objects.select_for_update(of=("self",))
        .filter(paciente=cliente, pk=operation_id)
        .select_related("servicio_config__tipo_servicio", "servicio_config__proc_estetico")
        .prefetch_related(
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.order_by("fecha_hora"),
            ),
            Prefetch("cuotas_plan_pagos", queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota")),
        )
        .first()
    )
    if not operacion:
        return _json({"detail": "No encontramos la operacion solicitada para este cliente."}, status=404)
    if not operacion.puede_reservar:
        return _json(
            {"detail": operacion.motivo_bloqueo_reserva or "Esta operacion no permite nuevas reservas."},
            status=400,
        )

    payload = _load_payload(request)
    if payload is None:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    sucursal_id = payload.get("branchId")
    fecha_hora_str = payload.get("dateTime")
    
    if not sucursal_id or not fecha_hora_str:
        return _json({"detail": "Faltan datos de sucursal o fecha/hora."}, status=400)
        
    try:
        from django.utils import dateparse
        fecha_hora = dateparse.parse_datetime(fecha_hora_str)
        if not fecha_hora:
            raise ValueError
    except Exception:
        return _json({"detail": "Formato de fecha u hora invalido."}, status=400)

    cita = CitaMedica.objects.create(
        operacion=operacion,
        sucursal_id=sucursal_id,
        fecha_hora=fecha_hora,
        estado=CitaMedica.Estado.PROGRAMADA,
        detalles_cita="Reserva creada libremente por administracion.",
    )

    return _json(
        {
            "detail": "La cita fue reservada correctamente para el cliente.",
            "appointment": _client_appointment_item(cita),
            "operation": _client_operation_item(operacion),
        },
        status=201,
    )""",
    content,
    flags=re.DOTALL
)

# Let's fix admin_cliente_free_medical_availability
content = re.sub(
    r"def admin_cliente_free_medical_availability\(request, client_id\):.*?return _json\([\s\S]*?calendar.*?\}[\s\S]*?\)",
    r"""def admin_cliente_free_medical_availability(request, client_id):
    cliente = Cliente.objects.filter(pk=client_id).first()
    if not cliente:
        return _json({"detail": "No encontramos el cliente solicitado."}, status=404)

    service_config = _medical_appointment_service_config()
    if not service_config:
        return _json(
            {"detail": "No existe un servicio activo de cita medica o consulta para agendar clientes."},
            status=400,
        )

    return _json(
        {
            "client": _client_item(cliente),
            "service": {
                "rawId": service_config.pk,
                "name": service_config.tipo_servicio.tipo,
            },
        }
    )""",
    content,
    flags=re.DOTALL
)

# Fix admin_cliente_create_free_medical_appointment
content = re.sub(
    r"def admin_cliente_create_free_medical_appointment\(request, client_id\):.*?return _json\([\s\S]*?status=201,[\s\S]*?\)",
    r"""def admin_cliente_create_free_medical_appointment(request, client_id):
    cliente = Cliente.objects.select_for_update(of=("self",)).filter(pk=client_id).first()
    if not cliente:
        return _json({"detail": "No encontramos el cliente solicitado."}, status=404)

    service_config = _medical_appointment_service_config()
    if not service_config:
        return _json(
            {"detail": "No existe un servicio activo de cita medica o consulta para agendar clientes."},
            status=400,
        )

    payload = _load_payload(request)
    if payload is None:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)
        
    sucursal_id = payload.get("branchId")
    fecha_hora_str = payload.get("dateTime")
    if not sucursal_id or not fecha_hora_str:
        return _json({"detail": "Faltan datos de sucursal o fecha/hora."}, status=400)
        
    try:
        from django.utils import dateparse
        fecha_hora = dateparse.parse_datetime(fecha_hora_str)
        if not fecha_hora:
            raise ValueError
    except Exception:
        return _json({"detail": "Formato de fecha u hora invalido."}, status=400)

    appointment = CitaClienteLibre.objects.create(
        cliente=cliente,
        servicio_config=service_config,
        sucursal_id=sucursal_id,
        fecha_hora=fecha_hora,
        estado=CitaClienteLibre.Estado.PROGRAMADA,
        detalles_cita="Cita medica libre agendada por administracion.",
    )

    return _json(
        {
            "detail": "La cita medica libre fue agendada correctamente para el cliente.",
            "appointment": _free_client_appointment_item(appointment),
        },
        status=201,
    )""",
    content,
    flags=re.DOTALL
)

# Replace admin_prospect_medical_availability
content = re.sub(
    r"def admin_prospect_medical_availability\(request, prospecto_id\):.*?return _json\([\s\S]*?calendar.*?\}[\s\S]*?\)",
    r"""def admin_prospect_medical_availability(request, prospecto_id):
    prospecto = Prospecto.objects.filter(pk=prospecto_id).first()
    if not prospecto:
        return _json({"detail": "No encontramos el prospecto solicitado."}, status=404)
    if prospecto.estado != Prospecto.Estado.PASAJERO:
        return _json({"detail": "Solo se pueden agendar citas para prospectos no convertidos."}, status=400)

    service_config = _medical_appointment_service_config()
    if not service_config:
        return _json(
            {"detail": "No existe un servicio activo de cita medica o consulta para agendar prospectos."},
            status=400,
        )

    return _json(
        {
            "prospect": _prospect_item(prospecto),
            "service": {
                "rawId": service_config.pk,
                "name": service_config.tipo_servicio.tipo,
            },
        }
    )""",
    content,
    flags=re.DOTALL
)

# Fix admin_create_prospect_medical_appointment
content = re.sub(
    r"def admin_create_prospect_medical_appointment\(request, prospecto_id\):.*?return _json\([\s\S]*?status=201,[\s\S]*?\)",
    r"""def admin_create_prospect_medical_appointment(request, prospecto_id):
    prospecto = (
        Prospecto.objects.select_for_update(of=("self",))
        .prefetch_related("citas_medicas")
        .filter(pk=prospecto_id)
        .first()
    )
    if not prospecto:
        return _json({"detail": "No encontramos el prospecto solicitado."}, status=404)
    if prospecto.estado != Prospecto.Estado.PASAJERO:
        return _json({"detail": "Solo se pueden agendar citas para prospectos no convertidos."}, status=400)
    if prospecto.citas_medicas.filter(estado=CitaProspecto.Estado.PROGRAMADA).exists():
        return _json({"detail": "Este prospecto ya tiene una cita medica programada."}, status=400)

    service_config = _medical_appointment_service_config()
    if not service_config:
        return _json(
            {"detail": "No existe un servicio activo de cita medica o consulta para agendar prospectos."},
            status=400,
        )

    payload = _load_payload(request)
    if payload is None:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    sucursal_id = payload.get("branchId")
    fecha_hora_str = payload.get("dateTime")
    if not sucursal_id or not fecha_hora_str:
        return _json({"detail": "Faltan datos de sucursal o fecha/hora."}, status=400)
        
    try:
        from django.utils import dateparse
        fecha_hora = dateparse.parse_datetime(fecha_hora_str)
        if not fecha_hora:
            raise ValueError
    except Exception:
        return _json({"detail": "Formato de fecha u hora invalido."}, status=400)

    appointment = CitaProspecto.objects.create(
        prospecto=prospecto,
        servicio_config=service_config,
        sucursal_id=sucursal_id,
        fecha_hora=fecha_hora,
        estado=CitaProspecto.Estado.PROGRAMADA,
        detalles_cita="Cita medica agendada libremente por administracion.",
    )

    return _json(
        {
            "detail": "La cita medica fue agendada correctamente para el prospecto.",
            "appointment": _prospect_appointment_item(appointment),
        },
        status=201,
    )""",
    content,
    flags=re.DOTALL
)

with open(filepath, "w") as f:
    f.write(content)
print("api_views replaced")
