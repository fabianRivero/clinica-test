import json
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago
from catalogs.models import (
    AntecedenteMedico,
    CirugiaEstetica,
    GradoDeshidratacion,
    GrosorPiel,
    ImplanteInjerto,
    PatologiaCutanea,
    ServicioConfig,
    TipoPiel,
)
from clinical.models import AnalisisEstetico, PatologiaPorAnalisis
from config.api_views import _admin_required, _prospect_item
from customers.models import Cliente, Prospecto, ProspectoConversionBorrador
from operations.models import (
    FichaAntecedenteMedico,
    FichaCampo,
    FichaCirugiaEstetica,
    FichaClinica,
    FichaImplanteInjerto,
    FichaRespuestaCampo,
    FichaRespuestaOpcion,
    FichaSeccion,
    Operacion,
)


def _json(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _load_payload(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _parse_date(value, field_name, errors, *, required=False):
    raw = (value or "").strip() if isinstance(value, str) else value
    if not raw:
        if required:
            errors[field_name] = "Este campo es obligatorio."
        return None

    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        errors[field_name] = "La fecha no tiene un formato valido."
        return None


def _parse_positive_int(value, field_name, errors, *, required=True, min_value=0):
    raw = "" if value is None else str(value).strip()
    if not raw:
        if required:
            errors[field_name] = "Este campo es obligatorio."
        return None

    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        errors[field_name] = "Debes ingresar un numero entero valido."
        return None

    if parsed < min_value:
        errors[field_name] = f"El valor minimo permitido es {min_value}."
        return None

    return parsed


def _parse_decimal(value, field_name, errors, *, required=True, min_value=Decimal("0")):
    raw = "" if value is None else str(value).strip()
    if not raw:
        if required:
            errors[field_name] = "Este campo es obligatorio."
        return None

    try:
        parsed = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError):
        errors[field_name] = "Debes ingresar un monto valido."
        return None

    if parsed < min_value:
        errors[field_name] = f"El valor minimo permitido es {min_value}."
        return None

    return parsed.quantize(Decimal("0.01"))


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}
    return bool(value)


def _add_months(base_date, months):
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, monthrange(year, month)[1])
    return date(year, month, day)


def _build_initial_user_data(prospecto):
    return {
        "primerNombre": prospecto.nombres,
        "segundoNombre": "",
        "apellidoPaterno": prospecto.apellidos,
        "apellidoMaterno": "",
        "username": "",
        "email": "",
        "telefono": prospecto.telefono,
        "ci": "",
        "codBiometrico": "",
        "fechaNacimiento": "",
        "nroHijos": 0,
        "direccionDomicilio": "",
        "ocupacion": "",
        "observacionesCliente": prospecto.observaciones or "",
        "hasPassword": False,
    }


def _blank_medical_data():
    return {
        "fechaFicha": str(timezone.localdate()),
        "motivoConsulta": "",
        "observaciones": "",
        "consentimientoAceptado": False,
        "firmaPacienteCi": "",
        "analisisEstetico": {
            "tipoPielId": "",
            "gradoDeshidratacionId": "",
            "grosorPielId": "",
            "patologiaIds": [],
        },
        "antecedentes": [],
        "implantes": [],
        "cirugias": [],
        "fieldResponses": {},
    }


def _field_response_has_value(field, response):
    if field.tipo_campo == FichaCampo.TipoCampo.TEXTO:
        return bool((response.get("valueText") or "").strip())
    if field.tipo_campo == FichaCampo.TipoCampo.NUMERO:
        return str(response.get("valueNumber") or "").strip() != ""
    if field.tipo_campo == FichaCampo.TipoCampo.FECHA:
        return bool(str(response.get("valueDate") or "").strip())
    if field.tipo_campo == FichaCampo.TipoCampo.BOOLEANO:
        return response.get("valueBoolean") is not None
    return bool(response.get("optionIds"))


def _serialize_draft(draft):
    user_data = dict(draft.datos_usuario or {})
    user_data.pop("passwordHash", None)
    user_data["hasPassword"] = bool((draft.datos_usuario or {}).get("passwordHash"))
    default_medical_data = _blank_medical_data()
    saved_medical_data = dict(draft.datos_ficha or {})
    medical_data = {
        **default_medical_data,
        **saved_medical_data,
        "analisisEstetico": {
            **default_medical_data["analisisEstetico"],
            **(saved_medical_data.get("analisisEstetico") or {}),
        },
    }

    return {
        "currentStep": draft.paso_actual,
        "stepUserCompleted": draft.paso_usuario_completado,
        "stepOperationCompleted": draft.paso_operacion_completado,
        "stepMedicalCompleted": draft.paso_ficha_completado,
        "userData": user_data or _build_initial_user_data(draft.prospecto),
        "operationData": draft.datos_operacion or {
            "serviceConfigId": "",
            "zonaGeneral": "",
            "zonaEspecifica": "",
            "precioTotal": "",
            "cuotasTotales": 1,
            "sesionesTotales": 1,
            "fechaInicio": "",
            "fechaFinal": "",
            "estado": Operacion.Estado.EN_PROCESO,
            "detallesOperacion": "",
            "recomendaciones": "",
            "primeraFechaVencimiento": "",
        },
        "medicalData": medical_data,
    }


def _serialize_service_configs():
    service_configs = (
        ServicioConfig.objects.select_related("tipo_servicio", "proc_estetico")
        .filter(activo=True)
        .order_by("tipo_servicio__tipo", "proc_estetico__proceso")
    )
    return [
        {
            "id": item.id,
            "label": str(item),
            "serviceType": item.tipo_servicio.tipo,
            "procedureName": item.proc_estetico.proceso if item.proc_estetico else "",
            "procedureId": item.proc_estetico_id,
            "basePrice": f"{item.precio_base:.2f}",
        }
        for item in service_configs
    ]


def _serialize_medical_config(service_config):
    shared_config = {
        "antecedentes": [
            {"id": item.id, "nombre": item.nombre}
            for item in AntecedenteMedico.objects.filter(activo=True).order_by("orden", "nombre")
        ],
        "implantes": [
            {"id": item.id, "nombre": item.nombre}
            for item in ImplanteInjerto.objects.filter(activo=True).order_by("orden", "nombre")
        ],
        "cirugias": [
            {"id": item.id, "nombre": item.nombre}
            for item in CirugiaEstetica.objects.filter(activo=True).order_by("orden", "nombre")
        ],
        "tiposPiel": [
            {"id": item.id, "nombre": item.nombre}
            for item in TipoPiel.objects.filter(activo=True).order_by("orden", "nombre")
        ],
        "gradosDeshidratacion": [
            {"id": item.id, "nombre": item.nombre}
            for item in GradoDeshidratacion.objects.filter(activo=True).order_by("orden", "nombre")
        ],
        "grosoresPiel": [
            {"id": item.id, "nombre": item.nombre}
            for item in GrosorPiel.objects.filter(activo=True).order_by("orden", "nombre")
        ],
        "patologiasCutaneas": [
            {"id": item.id, "nombre": item.nombre}
            for item in PatologiaCutanea.objects.filter(activo=True).order_by("orden", "nombre")
        ],
    }

    if not service_config or not service_config.proc_estetico_id:
        return {
            "procedureId": None,
            "procedureName": "",
            "sections": [],
            **shared_config,
        }

    sections = (
        FichaSeccion.objects.filter(proc_estetico=service_config.proc_estetico, activo=True)
        .prefetch_related("campos__grupo_opciones__opciones")
        .order_by("orden", "nombre")
    )

    return {
        "procedureId": service_config.proc_estetico_id,
        "procedureName": service_config.proc_estetico.proceso,
        "sections": [
            {
                "id": section.id,
                "code": section.codigo,
                "name": section.nombre,
                "fields": [
                    {
                        "id": field.id,
                        "code": field.codigo,
                        "label": field.etiqueta,
                        "type": field.tipo_campo,
                        "isMultiple": field.es_multiple,
                        "allowsDetail": field.permite_detalle,
                        "required": field.requerido,
                        "options": [
                            {
                                "id": option.id,
                                "code": option.codigo,
                                "name": option.nombre,
                                "value": option.valor,
                            }
                            for option in (
                                field.grupo_opciones.opciones.filter(activo=True).order_by("orden", "nombre")
                                if field.grupo_opciones_id
                                else []
                            )
                        ],
                    }
                    for field in section.campos.filter(activo=True).order_by("orden", "etiqueta")
                ],
            }
            for section in sections
        ],
        **shared_config,
    }


def _get_prospecto_convertible(prospecto_id):
    prospecto = Prospecto.objects.select_related("registrado_por", "convertido_a_cliente").filter(pk=prospecto_id).first()
    if not prospecto:
        return None, _json({"detail": "No encontramos el prospecto solicitado."}, status=404)
    if prospecto.estado == Prospecto.Estado.CONVERTIDO:
        return None, _json({"detail": "Este prospecto ya fue convertido a cliente."}, status=400)
    if prospecto.estado != Prospecto.Estado.PASAJERO:
        return None, _json({"detail": "Solo los prospectos pasajeros pueden iniciar este flujo."}, status=400)
    return prospecto, None


def _get_or_create_draft(prospecto, user):
    draft, _ = ProspectoConversionBorrador.objects.get_or_create(
        prospecto=prospecto,
        defaults={
            "iniciado_por": user,
            "datos_usuario": _build_initial_user_data(prospecto),
        },
    )
    if not draft.iniciado_por_id:
        draft.iniciado_por = user
        draft.save(update_fields=["iniciado_por", "updated_at"])
    return draft


def _serialize_conversion_payload(prospecto, draft):
    service_config = None
    service_config_id = (draft.datos_operacion or {}).get("serviceConfigId")
    if service_config_id:
        service_config = (
            ServicioConfig.objects.select_related("tipo_servicio", "proc_estetico")
            .filter(pk=service_config_id)
            .first()
        )

    return {
        "prospect": _prospect_item(prospecto),
        "draft": _serialize_draft(draft),
        "serviceConfigs": _serialize_service_configs(),
        "operationStates": [
            {"value": value, "label": label}
            for value, label in Operacion.Estado.choices
        ],
        "medicalConfig": _serialize_medical_config(service_config),
    }


def _validate_user_step(payload, draft):
    errors = {}
    primer_nombre = (payload.get("primerNombre") or "").strip()
    apellido_paterno = (payload.get("apellidoPaterno") or "").strip()
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    if not primer_nombre:
        errors["primerNombre"] = "El primer nombre es obligatorio."
    if not apellido_paterno:
        errors["apellidoPaterno"] = "El apellido paterno es obligatorio."
    if not username:
        errors["username"] = "El nombre de usuario es obligatorio."
    elif Usuario.objects.filter(username=username).exists():
        errors["username"] = "Ya existe una cuenta con este nombre de usuario."

    existing_hash = (draft.datos_usuario or {}).get("passwordHash")
    if not password and not existing_hash:
        errors["password"] = "La contraseña es obligatoria."

    cod_biometrico = (payload.get("codBiometrico") or "").strip()
    if cod_biometrico and Cliente.objects.filter(cod_biometrico=cod_biometrico).exists():
        errors["codBiometrico"] = "Ya existe un cliente con este codigo biometrico."

    fecha_nacimiento = _parse_date(payload.get("fechaNacimiento"), "fechaNacimiento", errors, required=False)
    nro_hijos = _parse_positive_int(payload.get("nroHijos"), "nroHijos", errors, required=False, min_value=0)

    if errors:
        return None, errors

    return {
        "primerNombre": primer_nombre,
        "segundoNombre": (payload.get("segundoNombre") or "").strip(),
        "apellidoPaterno": apellido_paterno,
        "apellidoMaterno": (payload.get("apellidoMaterno") or "").strip(),
        "username": username,
        "email": (payload.get("email") or "").strip(),
        "telefono": (payload.get("telefono") or "").strip(),
        "ci": (payload.get("ci") or "").strip(),
        "codBiometrico": cod_biometrico,
        "fechaNacimiento": fecha_nacimiento.isoformat() if fecha_nacimiento else "",
        "nroHijos": 0 if nro_hijos is None else nro_hijos,
        "direccionDomicilio": (payload.get("direccionDomicilio") or "").strip(),
        "ocupacion": (payload.get("ocupacion") or "").strip(),
        "observacionesCliente": (payload.get("observacionesCliente") or "").strip(),
        "passwordHash": make_password(password) if password else existing_hash,
    }, None


def _validate_operation_step(payload):
    errors = {}

    service_config_id = _parse_positive_int(payload.get("serviceConfigId"), "serviceConfigId", errors, min_value=1)
    precio_total = _parse_decimal(payload.get("precioTotal"), "precioTotal", errors, min_value=Decimal("0.01"))
    cuotas_totales = _parse_positive_int(payload.get("cuotasTotales"), "cuotasTotales", errors, min_value=1)
    sesiones_totales = _parse_positive_int(payload.get("sesionesTotales"), "sesionesTotales", errors, min_value=1)
    fecha_inicio = _parse_date(payload.get("fechaInicio"), "fechaInicio", errors, required=True)
    fecha_final = _parse_date(payload.get("fechaFinal"), "fechaFinal", errors, required=False)
    primera_fecha_vencimiento = _parse_date(
        payload.get("primeraFechaVencimiento"),
        "primeraFechaVencimiento",
        errors,
        required=True,
    )
    estado = (payload.get("estado") or Operacion.Estado.EN_PROCESO).strip()
    if estado not in {choice[0] for choice in Operacion.Estado.choices}:
        errors["estado"] = "El estado seleccionado no es valido."

    service_config = None
    if service_config_id:
        service_config = (
            ServicioConfig.objects.select_related("tipo_servicio", "proc_estetico")
            .filter(pk=service_config_id, activo=True)
            .first()
        )
        if not service_config:
            errors["serviceConfigId"] = "Debes seleccionar un servicio activo valido."

    if fecha_inicio and fecha_final and fecha_final < fecha_inicio:
        errors["fechaFinal"] = "La fecha final no puede ser anterior a la fecha de inicio."

    if errors:
        return None, None, errors

    return (
        {
            "serviceConfigId": service_config_id,
            "zonaGeneral": (payload.get("zonaGeneral") or "").strip(),
            "zonaEspecifica": (payload.get("zonaEspecifica") or "").strip(),
            "precioTotal": f"{precio_total:.2f}",
            "cuotasTotales": cuotas_totales,
            "sesionesTotales": sesiones_totales,
            "fechaInicio": fecha_inicio.isoformat() if fecha_inicio else "",
            "fechaFinal": fecha_final.isoformat() if fecha_final else "",
            "estado": estado,
            "detallesOperacion": (payload.get("detallesOperacion") or "").strip(),
            "recomendaciones": (payload.get("recomendaciones") or "").strip(),
            "primeraFechaVencimiento": primera_fecha_vencimiento.isoformat() if primera_fecha_vencimiento else "",
        },
        service_config,
        None,
    )


def _validate_medical_step(payload, service_config):
    errors = {}
    fecha_ficha = _parse_date(payload.get("fechaFicha"), "fechaFicha", errors, required=True)
    analisis_payload = payload.get("analisisEstetico") or {}

    antecedentes_payload = payload.get("antecedentes") or []
    implantes_payload = payload.get("implantes") or []
    cirugias_payload = payload.get("cirugias") or []
    field_responses = payload.get("fieldResponses") or {}

    tipo_piel_id = _parse_positive_int(
        analisis_payload.get("tipoPielId"),
        "analisisEstetico.tipoPielId",
        errors,
        min_value=1,
    )
    grado_deshidratacion_id = _parse_positive_int(
        analisis_payload.get("gradoDeshidratacionId"),
        "analisisEstetico.gradoDeshidratacionId",
        errors,
        min_value=1,
    )
    grosor_piel_id = _parse_positive_int(
        analisis_payload.get("grosorPielId"),
        "analisisEstetico.grosorPielId",
        errors,
        min_value=1,
    )

    if tipo_piel_id and not TipoPiel.objects.filter(pk=tipo_piel_id, activo=True).exists():
        errors["analisisEstetico.tipoPielId"] = "El tipo de piel seleccionado no existe."
    if grado_deshidratacion_id and not GradoDeshidratacion.objects.filter(pk=grado_deshidratacion_id, activo=True).exists():
        errors["analisisEstetico.gradoDeshidratacionId"] = "El grado de deshidratacion seleccionado no existe."
    if grosor_piel_id and not GrosorPiel.objects.filter(pk=grosor_piel_id, activo=True).exists():
        errors["analisisEstetico.grosorPielId"] = "El grosor de piel seleccionado no existe."

    patologia_ids = []
    seen_patologia_ids = set()
    for raw_patologia_id in analisis_payload.get("patologiaIds") or []:
        patologia_id = _parse_positive_int(
            raw_patologia_id,
            "analisisEstetico.patologiaIds",
            errors,
            min_value=1,
        )
        if not patologia_id:
            continue
        if patologia_id in seen_patologia_ids:
            continue
        if not PatologiaCutanea.objects.filter(pk=patologia_id, activo=True).exists():
            errors["analisisEstetico.patologiaIds"] = "Una patologia seleccionada ya no esta disponible."
            continue
        seen_patologia_ids.add(patologia_id)
        patologia_ids.append(patologia_id)

    antecedentes_validated = []
    antecedentes_seen = set()
    for index, item in enumerate(antecedentes_payload):
        antecedente_id = _parse_positive_int(item.get("antecedenteId"), f"antecedentes.{index}.antecedenteId", errors, min_value=1)
        tipo_antecedente = (item.get("tipoAntecedente") or "").strip()
        if tipo_antecedente not in {
            FichaAntecedenteMedico.TipoAntecedente.FAMILIAR,
            FichaAntecedenteMedico.TipoAntecedente.PERSONAL,
        }:
            errors[f"antecedentes.{index}.tipoAntecedente"] = "Selecciona un tipo de antecedente valido."
        antecedente = AntecedenteMedico.objects.filter(pk=antecedente_id, activo=True).first() if antecedente_id else None
        if antecedente_id and not antecedente:
            errors[f"antecedentes.{index}.antecedenteId"] = "El antecedente seleccionado no existe."
        if antecedente:
            antecedente_key = (antecedente.id, tipo_antecedente)
            if antecedente_key in antecedentes_seen:
                errors[f"antecedentes.{index}.antecedenteId"] = "Este antecedente ya fue agregado para el mismo tipo."
                continue
            antecedentes_seen.add(antecedente_key)
            antecedentes_validated.append(
                {
                    "antecedenteId": antecedente.id,
                    "tipoAntecedente": tipo_antecedente,
                    "detalle": (item.get("detalle") or "").strip(),
                }
            )

    implantes_validated = []
    implantes_seen = set()
    for index, item in enumerate(implantes_payload):
        implante_id = _parse_positive_int(item.get("implanteId"), f"implantes.{index}.implanteId", errors, min_value=1)
        implante = ImplanteInjerto.objects.filter(pk=implante_id, activo=True).first() if implante_id else None
        if implante_id and not implante:
            errors[f"implantes.{index}.implanteId"] = "El implante seleccionado no existe."
        if implante:
            if implante.id in implantes_seen:
                errors[f"implantes.{index}.implanteId"] = "Este implante ya fue agregado."
                continue
            implantes_seen.add(implante.id)
            implantes_validated.append(
                {
                    "implanteId": implante.id,
                    "detalle": (item.get("detalle") or "").strip(),
                }
            )

    cirugias_validated = []
    cirugias_seen = set()
    for index, item in enumerate(cirugias_payload):
        cirugia_id = _parse_positive_int(item.get("cirugiaId"), f"cirugias.{index}.cirugiaId", errors, min_value=1)
        cirugia = CirugiaEstetica.objects.filter(pk=cirugia_id, activo=True).first() if cirugia_id else None
        if cirugia_id and not cirugia:
            errors[f"cirugias.{index}.cirugiaId"] = "La cirugia seleccionada no existe."
        if cirugia:
            if cirugia.id in cirugias_seen:
                errors[f"cirugias.{index}.cirugiaId"] = "Esta cirugia ya fue agregada."
                continue
            cirugias_seen.add(cirugia.id)
            cirugias_validated.append(
                {
                    "cirugiaId": cirugia.id,
                    "haceCuantoTiempo": (item.get("haceCuantoTiempo") or "").strip(),
                    "detalle": (item.get("detalle") or "").strip(),
                }
            )

    valid_field_ids = set()
    valid_option_ids = {}
    fields_by_id = {}
    if service_config and service_config.proc_estetico_id:
        for field in (
            FichaCampo.objects.filter(seccion__proc_estetico=service_config.proc_estetico, activo=True)
            .select_related("grupo_opciones")
            .prefetch_related("grupo_opciones__opciones")
        ):
            valid_field_ids.add(field.id)
            fields_by_id[field.id] = field
            valid_option_ids[field.id] = set(
                field.grupo_opciones.opciones.filter(activo=True).values_list("id", flat=True)
            ) if field.grupo_opciones_id else set()

    field_responses_validated = {}
    for raw_field_id, item in field_responses.items():
        field_id = _parse_positive_int(raw_field_id, f"fieldResponses.{raw_field_id}", errors, min_value=1)
        if not field_id:
            continue
        if field_id not in valid_field_ids:
            errors[f"fieldResponses.{raw_field_id}"] = "El campo enviado no pertenece al procedimiento seleccionado."
            continue

        field = fields_by_id[field_id]
        option_ids = item.get("optionIds") or []
        cleaned_option_ids = []
        seen_option_ids = set()
        for option_id in option_ids:
            parsed_option_id = _parse_positive_int(option_id, f"fieldResponses.{raw_field_id}.optionIds", errors, min_value=1)
            if parsed_option_id and parsed_option_id not in valid_option_ids.get(field_id, set()):
                errors[f"fieldResponses.{raw_field_id}.optionIds"] = "Una opcion no corresponde al campo seleccionado."
            elif parsed_option_id and parsed_option_id not in seen_option_ids:
                seen_option_ids.add(parsed_option_id)
                cleaned_option_ids.append(parsed_option_id)

        if field.tipo_campo == FichaCampo.TipoCampo.SELECCION and len(cleaned_option_ids) > 1:
            errors[f"fieldResponses.{raw_field_id}.optionIds"] = "Este campo solo acepta una opcion."

        cleaned_response = {
            "valueText": (item.get("valueText") or "").strip(),
            "valueNumber": str(item.get("valueNumber") or "").strip(),
            "valueDate": str(item.get("valueDate") or "").strip(),
            "valueBoolean": bool(item.get("valueBoolean")) if item.get("valueBoolean") is not None else None,
            "detail": (item.get("detail") or "").strip(),
            "optionIds": cleaned_option_ids,
        }
        field_responses_validated[str(field_id)] = cleaned_response

        if field.requerido and not _field_response_has_value(field, cleaned_response):
            errors[f"fieldResponses.{raw_field_id}.required"] = f"Debes completar el campo {field.etiqueta}."

    for field_id, field in fields_by_id.items():
        if not field.requerido:
            continue
        response = field_responses_validated.get(str(field_id))
        if not response or not _field_response_has_value(field, response):
            errors[f"fieldResponses.{field_id}.required"] = f"Debes completar el campo {field.etiqueta}."

    if errors:
        return None, errors

    return {
        "fechaFicha": fecha_ficha.isoformat() if fecha_ficha else "",
        "motivoConsulta": (payload.get("motivoConsulta") or "").strip(),
        "observaciones": (payload.get("observaciones") or "").strip(),
        "consentimientoAceptado": _parse_bool(payload.get("consentimientoAceptado")),
        "firmaPacienteCi": (payload.get("firmaPacienteCi") or "").strip(),
        "analisisEstetico": {
            "tipoPielId": str(tipo_piel_id or ""),
            "gradoDeshidratacionId": str(grado_deshidratacion_id or ""),
            "grosorPielId": str(grosor_piel_id or ""),
            "patologiaIds": patologia_ids,
        },
        "antecedentes": antecedentes_validated,
        "implantes": implantes_validated,
        "cirugias": cirugias_validated,
        "fieldResponses": field_responses_validated,
    }, None


@require_GET
@_admin_required
def admin_prospect_conversion_detail(request, prospecto_id):
    prospecto, error_response = _get_prospecto_convertible(prospecto_id)
    if error_response:
        return error_response

    draft = _get_or_create_draft(prospecto, request.user)
    return _json(_serialize_conversion_payload(prospecto, draft))


@require_POST
@_admin_required
def admin_prospect_conversion_cancel(request, prospecto_id):
    prospecto, error_response = _get_prospecto_convertible(prospecto_id)
    if error_response:
        return error_response

    deleted_count, _ = ProspectoConversionBorrador.objects.filter(prospecto=prospecto).delete()
    if deleted_count:
        return _json({"detail": "El borrador de conversion fue descartado correctamente."})

    return _json({"detail": "No habia un borrador activo para este prospecto."})


@require_POST
@_admin_required
def admin_prospect_conversion_user_step(request, prospecto_id):
    prospecto, error_response = _get_prospecto_convertible(prospecto_id)
    if error_response:
        return error_response

    payload = _load_payload(request)
    if payload is None:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    draft = _get_or_create_draft(prospecto, request.user)
    user_data, errors = _validate_user_step(payload, draft)
    if errors:
        return _json({"detail": "Corrige los errores del paso 1.", "errors": errors}, status=400)

    draft.datos_usuario = user_data
    draft.paso_usuario_completado = True
    draft.paso_actual = max(draft.paso_actual, ProspectoConversionBorrador.Paso.OPERACION)
    draft.save(
        update_fields=[
            "datos_usuario",
            "paso_usuario_completado",
            "paso_actual",
            "updated_at",
        ]
    )
    return _json(_serialize_conversion_payload(prospecto, draft))


@require_POST
@_admin_required
def admin_prospect_conversion_operation_step(request, prospecto_id):
    prospecto, error_response = _get_prospecto_convertible(prospecto_id)
    if error_response:
        return error_response

    payload = _load_payload(request)
    if payload is None:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    draft = _get_or_create_draft(prospecto, request.user)
    if not draft.paso_usuario_completado:
        return _json({"detail": "Debes completar primero los datos de usuario."}, status=400)

    previous_service_config_id = (draft.datos_operacion or {}).get("serviceConfigId")
    operation_data, service_config, errors = _validate_operation_step(payload)
    if errors:
        return _json({"detail": "Corrige los errores del paso 2.", "errors": errors}, status=400)

    draft.datos_operacion = operation_data
    draft.paso_operacion_completado = True
    draft.paso_actual = max(draft.paso_actual, ProspectoConversionBorrador.Paso.FICHA_MEDICA)
    if str(previous_service_config_id or "") != str(operation_data["serviceConfigId"]):
        draft.datos_ficha = _blank_medical_data()
        draft.paso_ficha_completado = False
    draft.save(
        update_fields=[
            "datos_operacion",
            "datos_ficha",
            "paso_operacion_completado",
            "paso_ficha_completado",
            "paso_actual",
            "updated_at",
        ]
    )
    return _json(_serialize_conversion_payload(prospecto, draft))


@require_POST
@_admin_required
def admin_prospect_conversion_medical_step(request, prospecto_id):
    prospecto, error_response = _get_prospecto_convertible(prospecto_id)
    if error_response:
        return error_response

    payload = _load_payload(request)
    if payload is None:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    draft = _get_or_create_draft(prospecto, request.user)
    if not draft.paso_operacion_completado:
        return _json({"detail": "Debes completar primero los datos de la operacion."}, status=400)

    service_config_id = (draft.datos_operacion or {}).get("serviceConfigId")
    service_config = (
        ServicioConfig.objects.select_related("tipo_servicio", "proc_estetico").filter(pk=service_config_id).first()
        if service_config_id
        else None
    )

    medical_data, errors = _validate_medical_step(payload, service_config)
    if errors:
        return _json({"detail": "Corrige los errores del paso 3.", "errors": errors}, status=400)

    draft.datos_ficha = medical_data
    draft.paso_ficha_completado = True
    draft.paso_actual = ProspectoConversionBorrador.Paso.FICHA_MEDICA
    draft.save(
        update_fields=[
            "datos_ficha",
            "paso_ficha_completado",
            "paso_actual",
            "updated_at",
        ]
    )
    return _json(_serialize_conversion_payload(prospecto, draft))


@require_POST
@_admin_required
@transaction.atomic
def admin_prospect_conversion_finalize(request, prospecto_id):
    prospecto, error_response = _get_prospecto_convertible(prospecto_id)
    if error_response:
        return error_response

    draft = ProspectoConversionBorrador.objects.select_for_update().filter(prospecto=prospecto).first()
    if not draft:
        return _json({"detail": "No existe un borrador de conversion para este prospecto."}, status=400)
    if not (draft.paso_usuario_completado and draft.paso_operacion_completado and draft.paso_ficha_completado):
        return _json({"detail": "Debes completar los tres pasos antes de finalizar la conversion."}, status=400)

    user_data = draft.datos_usuario or {}
    operation_data = draft.datos_operacion or {}
    medical_data = draft.datos_ficha or {}
    analisis_data = medical_data.get("analisisEstetico") or {}

    service_config = (
        ServicioConfig.objects.select_related("tipo_servicio", "proc_estetico")
        .filter(pk=operation_data.get("serviceConfigId"), activo=True)
        .first()
    )
    if not service_config:
        return _json({"detail": "El servicio seleccionado ya no esta disponible."}, status=400)

    client_role = Rol.objects.filter(rol="CLIENTE").first()
    if not client_role:
        return _json({"detail": "No existe el rol CLIENTE configurado en el sistema."}, status=500)
    if not user_data.get("passwordHash"):
        return _json({"detail": "El borrador no tiene una contraseña valida para crear la cuenta."}, status=400)
    if Usuario.objects.filter(username=user_data.get("username", "")).exists():
        return _json({"detail": "Ya existe una cuenta con el usuario seleccionado. Actualiza el paso 1 antes de continuar."}, status=400)
    cod_biometrico = user_data.get("codBiometrico") or None
    if cod_biometrico and Cliente.objects.filter(cod_biometrico=cod_biometrico).exists():
        return _json({"detail": "El codigo biometrico indicado ya pertenece a otro cliente. Corrigelo en el paso 1."}, status=400)

    user = Usuario.objects.create(
        username=user_data["username"],
        email=user_data.get("email", ""),
        primer_nombre=user_data["primerNombre"],
        segundo_nombre=user_data.get("segundoNombre", ""),
        apellido_paterno=user_data["apellidoPaterno"],
        apellido_materno=user_data.get("apellidoMaterno", ""),
        rol=client_role,
        is_active=True,
        is_staff=False,
        is_superuser=False,
        password=user_data["passwordHash"],
    )

    cliente = Cliente.objects.create(
        usuario=user,
        ci=user_data.get("ci", ""),
        cod_biometrico=cod_biometrico,
        fecha_nacimiento=date.fromisoformat(user_data["fechaNacimiento"]) if user_data.get("fechaNacimiento") else None,
        nro_hijos=int(user_data.get("nroHijos") or 0),
        direccion_domicilio=user_data.get("direccionDomicilio", ""),
        telefono=user_data.get("telefono", ""),
        ocupacion=user_data.get("ocupacion", ""),
        observaciones=user_data.get("observacionesCliente", ""),
    )

    analisis = AnalisisEstetico.objects.create(
        paciente=cliente,
        fecha_analisis=date.fromisoformat(medical_data["fechaFicha"]) if medical_data.get("fechaFicha") else timezone.localdate(),
        tipo_piel_id=int(analisis_data["tipoPielId"]),
        grado_deshidratacion_id=int(analisis_data["gradoDeshidratacionId"]),
        grosor_piel_id=int(analisis_data["grosorPielId"]),
        observaciones=medical_data.get("observaciones", ""),
    )
    for patologia_id in analisis_data.get("patologiaIds") or []:
        PatologiaPorAnalisis.objects.create(
            analisis=analisis,
            patologia_id=patologia_id,
        )

    operacion = Operacion.objects.create(
        paciente=cliente,
        servicio_config=service_config,
        zona_general=operation_data.get("zonaGeneral", ""),
        zona_especifica=operation_data.get("zonaEspecifica", ""),
        precio_total=Decimal(operation_data["precioTotal"]),
        cuotas_totales=int(operation_data["cuotasTotales"]),
        sesiones_totales=int(operation_data["sesionesTotales"]),
        fecha_inicio=date.fromisoformat(operation_data["fechaInicio"]) if operation_data.get("fechaInicio") else None,
        fecha_final=date.fromisoformat(operation_data["fechaFinal"]) if operation_data.get("fechaFinal") else None,
        estado=operation_data.get("estado") or Operacion.Estado.EN_PROCESO,
        detalles_op=operation_data.get("detallesOperacion", ""),
        recomendaciones=operation_data.get("recomendaciones", ""),
    )

    primera_fecha_vencimiento = date.fromisoformat(operation_data["primeraFechaVencimiento"])
    for cuota_index in range(int(operation_data["cuotasTotales"])):
        CuotaPlanPago.objects.create(
            operacion=operacion,
            nro_cuota=cuota_index + 1,
            fecha_vencimiento=_add_months(primera_fecha_vencimiento, cuota_index),
        )

    ficha = FichaClinica.objects.create(
        operacion=operacion,
        fecha_ficha=date.fromisoformat(medical_data["fechaFicha"]) if medical_data.get("fechaFicha") else timezone.localdate(),
        motivo_consulta=medical_data.get("motivoConsulta", ""),
        observaciones=medical_data.get("observaciones", ""),
        firma_paciente_ci=medical_data.get("firmaPacienteCi") or user_data.get("ci", ""),
        consentimiento_aceptado=bool(medical_data.get("consentimientoAceptado")),
    )

    for antecedente in medical_data.get("antecedentes", []):
        FichaAntecedenteMedico.objects.create(
            ficha=ficha,
            antecedente_id=antecedente["antecedenteId"],
            tipo_antecedente=antecedente["tipoAntecedente"],
            detalle=antecedente.get("detalle", ""),
        )

    for implante in medical_data.get("implantes", []):
        FichaImplanteInjerto.objects.create(
            ficha=ficha,
            implante_id=implante["implanteId"],
            detalle=implante.get("detalle", ""),
        )

    for cirugia in medical_data.get("cirugias", []):
        FichaCirugiaEstetica.objects.create(
            ficha=ficha,
            cirugia_id=cirugia["cirugiaId"],
            hace_cuanto_tiempo=cirugia.get("haceCuantoTiempo", ""),
            detalle=cirugia.get("detalle", ""),
        )

    for field_id, response_data in (medical_data.get("fieldResponses") or {}).items():
        respuesta = FichaRespuestaCampo.objects.create(
            ficha=ficha,
            campo_id=int(field_id),
            valor_texto=response_data.get("valueText", ""),
            valor_numero=Decimal(response_data["valueNumber"]) if response_data.get("valueNumber") else None,
            valor_fecha=date.fromisoformat(response_data["valueDate"]) if response_data.get("valueDate") else None,
            valor_booleano=response_data.get("valueBoolean"),
            detalle=response_data.get("detail", ""),
        )
        for option_id in response_data.get("optionIds", []):
            FichaRespuestaOpcion.objects.create(
                respuesta=respuesta,
                opcion_id=option_id,
            )

    prospecto.marcar_como_convertido(cliente, save=True)
    draft.delete()

    return _json(
        {
            "detail": "El prospecto fue convertido correctamente a cliente.",
            "client": {
                "id": cliente.id,
                "name": cliente.usuario.nombre_completo,
            },
            "operation": {
                "id": operacion.id,
                "procedure": service_config.proc_estetico.proceso if service_config.proc_estetico else service_config.tipo_servicio.tipo,
            },
        },
        status=201,
    )
