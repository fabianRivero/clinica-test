import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago
from billing.models import PagoRealizado
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
from config.api_helpers import (
    admin_required,
    get_user_branch,
    json_response,
    load_payload,
    split_amount,
)
from config.api_views import _prospect_item
from customers.models import Cliente, HuellaBiometricaCliente, Prospecto, ProspectoConversionBorrador
from operations.models import Operacion
from clinical.models import (
    FichaAntecedenteMedico,
    FichaCampo,
    FichaCirugiaEstetica,
    FichaClinica,
    FichaImplanteInjerto,
    FichaRespuestaCampo,
    FichaRespuestaOpcion,
    FichaSeccion,
)


logger = logging.getLogger(__name__)


def _get_branch_for_scope_check(request):
    """Sucursal para control de alcance en conversiones (sin depender de sesión)."""
    user = request.user
    if user.is_superuser or user.es_admin_principal:
        return None
    return user.sucursal


def _check_cross_city_procedures(request, prospecto=None, cliente=None):
    current_branch = get_user_branch(request)
    if not current_branch or not current_branch.ciudad:
        return None

    # Si es prospecto, buscamos si ya existe como cliente por CI
    if prospecto and not cliente:
        prospect_ci = getattr(prospecto, "ci", "")
        if not prospect_ci:
            return None
        cliente = Cliente.objects.filter(ci=prospect_ci).first()
    
    if not cliente:
        return None

    # Buscamos operaciones activas en otras ciudades
    active_ops = Operacion.objects.filter(
        paciente=cliente,
        estado=Operacion.Estado.EN_PROCESO
    ).exclude(citas_medicas__sucursal__ciudad=current_branch.ciudad).distinct()

    if active_ops.exists():
        other_cities = list(active_ops.values_list("citas_medicas__sucursal__ciudad", flat=True).distinct())
        cities_str = ", ".join([c for c in other_cities if c])
        return f"Atencion: Este paciente tiene procedimientos activos en otra ciudad ({cities_str})."
    
    return None


def _get_required_pdf_file(request, draft=None):
    document = request.FILES.get("documento_escaneado_pdf") or request.FILES.get("documentoFichaPdf")
    if not document and draft and draft.documento_pdf:
        document = draft.documento_pdf

    if not document:
        return None, json_response({"detail": "Debes adjuntar el PDF escaneado de la ficha medica."}, status=400)

    filename = (document.name or "").lower()
    if not filename.endswith(".pdf"):
        return None, json_response({"detail": "El documento adjunto debe estar en formato PDF."}, status=400)

    return document, None


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


def _cap(text):
    if not text:
        return ""
    raw = str(text).strip()
    if not raw:
        return ""
    return raw[0].upper() + raw[1:]
def _build_initial_user_data(prospecto):
    return {
        "primerNombre": prospecto.primer_nombre,
        "segundoNombre": prospecto.segundo_nombre,
        "apellidoPaterno": prospecto.apellido_paterno,
        "apellidoMaterno": prospecto.apellido_materno,
        "username": getattr(prospecto, "username", "") or "",
        "email": getattr(prospecto, "email", "") or "",
        "telefono": prospecto.telefono or "",
        "ci": getattr(prospecto, "ci", "") or "",
        "fechaNacimiento": "",
        "nroHijos": 0,
        "direccionDomicilio": "",
        "ocupacion": "",
        "observacionesCliente": prospecto.observaciones or "",
        "hasPassword": False,
    }



def _build_initial_client_user_data(cliente):
    user = cliente.usuario
    return {
        "primerNombre": user.primer_nombre,
        "segundoNombre": user.segundo_nombre,
        "apellidoPaterno": user.apellido_paterno,
        "apellidoMaterno": user.apellido_materno,
        "username": user.username,
        "email": user.email or "",
        "telefono": cliente.telefono or user.username, # Fallback to username if phone is empty
        "ci": cliente.ci,
        "fechaNacimiento": str(cliente.fecha_nacimiento) if cliente.fecha_nacimiento else "",
        "nroHijos": cliente.nro_hijos,
        "direccionDomicilio": cliente.direccion_domicilio,
        "ocupacion": cliente.ocupacion,
        "observacionesCliente": cliente.observaciones,
        "hasPassword": True,
    }


def _build_initial_client_medical_data(cliente):
    prioritized_qs = (
        cliente.operaciones.filter(
            estado__in=[Operacion.Estado.EN_PROCESO, Operacion.Estado.FINALIZADA],
            ficha_clinica__isnull=False,
        )
        .select_related("ficha_clinica")
        .order_by("-ficha_clinica__fecha_ficha", "-created_at")
    )

    ultima_operacion = prioritized_qs.first()

    # Fallback legacy: si no hay estados relevantes con ficha, usar cualquier operacion con ficha.
    if not ultima_operacion:
        fallback_qs = (
            cliente.operaciones.filter(ficha_clinica__isnull=False)
            .select_related("ficha_clinica")
            .order_by("-ficha_clinica__fecha_ficha", "-created_at")
        )
        ultima_operacion = fallback_qs.first()

    data = _blank_medical_data()
    
    if ultima_operacion and hasattr(ultima_operacion, "ficha_clinica"):
        ficha = ultima_operacion.ficha_clinica
        logger.warning(
            "[PREFILL] ficha counts antecedentes=%s implantes=%s cirugias=%s",
            ficha.antecedentes.count(),
            ficha.implantes.count(),
            ficha.cirugias.count(),
        )
        
        # Mapear antecedentes
        data["antecedentes"] = [
            {
                "id": f"{ant.pk}",
                "antecedenteId": ant.antecedente_id,
                "tipoAntecedente": ant.tipo_antecedente,
                "detalle": ant.detalle
            }
            for ant in ficha.antecedentes.all()
        ]
        
        # Mapear implantes
        data["implantes"] = [
            {
                "id": f"{imp.pk}",
                "implanteId": imp.implante_id,
                "detalle": imp.detalle
            }
            for imp in ficha.implantes.all()
        ]
        
        # Mapear cirugias
        data["cirugias"] = [
            {
                "id": f"{cir.pk}",
                "cirugiaId": cir.cirugia_id,
                "haceCuantoTiempo": cir.hace_cuanto_tiempo,
                "detalle": cir.detalle
            }
            for cir in ficha.cirugias.all()
        ]

    logger.warning(
        "[PREFILL] mapped data antecedentes=%s implantes=%s cirugias=%s",
        len(data.get("antecedentes", [])),
        len(data.get("implantes", [])),
        len(data.get("cirugias", [])),
    )

    return data


def _build_initial_client_biometric_data(cliente):
    data = _blank_biometric_data()
    if hasattr(cliente, "huella_biometrica") and cliente.huella_biometrica.activo:
        huella = cliente.huella_biometrica
        data["provider"] = huella.proveedor
        data["template"] = huella.template_biometrico
        data["quality"] = huella.calidad_captura
        data["deviceSerial"] = huella.device_serial
        data["consentAccepted"] = huella.consentimiento_aceptado
        data["capturedAt"] = str(huella.fecha_registro)
    return data


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


def _blank_biometric_data():
    return {
        "provider": "MOCK",
        "template": "",
        "quality": 0,
        "deviceSerial": "",
        "consentAccepted": True,
        "capturedAt": "",
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


def _is_effectively_empty_medical_data(medical_data):
    if not medical_data:
        return True

    if not isinstance(medical_data, dict):
        return False

    antecedentes = medical_data.get("antecedentes") or []
    implantes = medical_data.get("implantes") or []
    cirugias = medical_data.get("cirugias") or []
    field_responses = medical_data.get("fieldResponses") or {}

    analisis = medical_data.get("analisisEstetico") or {}
    analisis_vacio = not any(
        [
            analisis.get("tipoPielId"),
            analisis.get("gradoDeshidratacionId"),
            analisis.get("grosorPielId"),
            analisis.get("patologiaIds"),
        ]
    )

    return (
        len(antecedentes) == 0
        and len(implantes) == 0
        and len(cirugias) == 0
        and len(field_responses) == 0
        and analisis_vacio
    )


def _serialize_draft(draft):
    # Obtener los datos guardados en el borrador
    saved_user_data = dict(draft.datos_usuario or {})
    saved_user_data.pop("passwordHash", None)
    saved_user_data.pop("codBiometrico", None)
    
    # Determinar si el borrador ya tiene una contraseña (del cliente o puesta por admin)
    has_password = bool((draft.datos_usuario or {}).get("passwordHash"))
    if not has_password and draft.cliente:
        has_password = bool(draft.cliente.usuario.password)

    # Datos iniciales (si es cliente reactivado o prospecto)
    initial_user_data = {}
    if draft.cliente:
        initial_user_data = _build_initial_client_user_data(draft.cliente)
    elif draft.prospecto:
        initial_user_data = _build_initial_user_data(draft.prospecto)
    
    # Combinar: los datos guardados en el borrador sobrescriben los iniciales,
    # excepto si el dato guardado esta vacio.
    user_data = {**initial_user_data}
    for key, val in saved_user_data.items():
        if val not in (None, ""):
            user_data[key] = val
    
    user_data["hasPassword"] = has_password

    logger.warning(
        "[PREFILL] _serialize_draft draft_id=%s cliente_id=%s datos_ficha_type=%s datos_ficha_keys=%s",
        getattr(draft, "id", None),
        getattr(draft, "cliente_id", None),
        type(draft.datos_ficha).__name__,
        list((draft.datos_ficha or {}).keys()) if isinstance(draft.datos_ficha, dict) else None,
    )

    default_medical_data = _blank_medical_data()
    is_empty_medical_data = _is_effectively_empty_medical_data(draft.datos_ficha)

    if draft.cliente and is_empty_medical_data:
        default_medical_data = _build_initial_client_medical_data(draft.cliente)
    else:
        pass  # no historical prefill needed

    saved_medical_data = dict(draft.datos_ficha or {})
    if is_empty_medical_data:
        # Evitar que arreglos vacios del borrador pisen el prefill historico.
        for key in ("antecedentes", "implantes", "cirugias"):
            if not saved_medical_data.get(key):
                saved_medical_data.pop(key, None)
    saved_operation_data = dict(draft.datos_operacion or {})
    cuotas_totales = int(saved_operation_data.get("cuotasTotales") or 1)
    due_dates = saved_operation_data.get("fechasVencimientoCuotas")
    if due_dates is None:
        legacy_due_date = saved_operation_data.get("primeraFechaVencimiento") or ""
        due_dates = [legacy_due_date] + [""] * max(cuotas_totales - 1, 0)

    medical_data = {
        **default_medical_data,
        **saved_medical_data,
        "analisisEstetico": {
            **default_medical_data["analisisEstetico"],
            **(saved_medical_data.get("analisisEstetico") or {}),
        },
    }
    initial_biometric_data = _blank_biometric_data()
    if not draft.datos_biometria and draft.cliente:
        initial_biometric_data = _build_initial_client_biometric_data(draft.cliente)

    return {
        "currentStep": draft.paso_actual,
        "stepUserCompleted": draft.paso_usuario_completado,
        "stepOperationCompleted": draft.paso_operacion_completado,
        "stepMedicalCompleted": draft.paso_ficha_completado,
        "stepBiometricCompleted": draft.paso_biometria_completado,
        "userData": user_data,
        "operationData": {
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
            "fechasVencimientoCuotas": [""],
            **saved_operation_data,
            "fechasVencimientoCuotas": due_dates,
        },
        "medicalData": medical_data,
        "biometricData": {
            **initial_biometric_data,
            **dict(draft.datos_biometria or {}),
        },
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

    if service_config is None:
        return {
            "procedureId": None,
            "procedureName": "",
            "sections": [],
            **shared_config,
        }

    if service_config.sector_id is not None:
        sections = (
            FichaSeccion.objects
            .filter(sector=service_config.sector_id, activo=True)
            .prefetch_related("campos__grupo_opciones__opciones")
            .order_by("orden", "nombre")
        )
    elif service_config.proc_estetico_id is not None:
        sections = (
            FichaSeccion.objects
            .filter(proc_estetico=service_config.proc_estetico_id, activo=True)
            .prefetch_related("campos__grupo_opciones__opciones")
            .order_by("orden", "nombre")
        )
    else:
        sections = []

    return {
        "procedureId": service_config.proc_estetico_id,
        "procedureName": service_config.proc_estetico.proceso if service_config.proc_estetico else "",
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


def _get_draft_convertible(request, prospecto_id=None, cliente_id=None):
    user = request.user
    branch = _get_branch_for_scope_check(request)
    enforce_branch = bool(branch)

    if prospecto_id:
        prospecto = Prospecto.objects.filter(pk=prospecto_id).first()
        if not prospecto:
            return None, "No encontramos el prospecto solicitado."
        if enforce_branch and prospecto.sucursal_registro_id != branch.id:
            return None, "No tienes permisos para procesar prospectos de otra sucursal."
        if prospecto.estado != Prospecto.Estado.PASAJERO:
            return None, "Este prospecto ya fue procesado."
        draft, _ = ProspectoConversionBorrador.objects.get_or_create(
            prospecto=prospecto,
            defaults={"iniciado_por": request.user}
        )
        return draft, None
    elif cliente_id:
        cliente = Cliente.objects.select_related("usuario", "sucursal_registro").filter(pk=cliente_id).first()
        if not cliente:
            return None, "No encontramos el cliente solicitado."
        if enforce_branch and cliente.sucursal_registro_id != branch.id:
            return None, "No tienes permisos para procesar clientes de otra sucursal."
        draft, created = ProspectoConversionBorrador.objects.get_or_create(
            cliente=cliente,
            defaults={"iniciado_por": request.user}
        )
        if created:
            # Pre-poblamos el hash de contraseña para reactivacion
            draft.datos_usuario = {"passwordHash": cliente.usuario.password}
            draft.save(update_fields=["datos_usuario"])
        return draft, None
    return None, "Se requiere un ID de prospecto o cliente."


@require_GET
@admin_required
def admin_prospect_conversion_initialize(request, prospecto_id):
    draft, error = _get_draft_convertible(request, prospecto_id=prospecto_id)
    if error:
        return json_response({"detail": error}, status=400)

    warning = _check_cross_city_procedures(request, prospecto=draft.prospecto)

    return json_response(
        {
            "draft": _serialize_draft(draft),
            "crossCityWarning": warning,
            "catalogs": {
                "serviceConfigs": _serialize_service_configs(),
            },
        }
    )


@require_GET
@admin_required
def admin_client_reactivation_initialize(request, cliente_id):
    draft, error = _get_draft_convertible(request, cliente_id=cliente_id)
    if error:
        return json_response({"detail": error}, status=400)

    warning = _check_cross_city_procedures(request, cliente=draft.cliente)
    detail = _admin_conversion_detail(draft)
    detail["crossCityWarning"] = warning

    return json_response(detail)


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
    if password == "********":
        password = ""

    if not primer_nombre:
        errors["primerNombre"] = "El primer nombre es obligatorio."
    if not apellido_paterno:
        errors["apellidoPaterno"] = "El apellido paterno es obligatorio."
    
    if not username:
        errors["username"] = "El nombre de usuario es obligatorio."
    else:
        existing_user = Usuario.objects.filter(username=username).first()
        if existing_user:
            # Si es reactivacion de cliente, permitimos su propio username
            is_own_username = draft.cliente and draft.cliente.usuario_id == existing_user.pk
            if not is_own_username:
                errors["username"] = "Ya existe una cuenta con este nombre de usuario."

    ci = (payload.get("ci") or "").strip()
    if ci:
        existing_client = Cliente.objects.filter(ci=ci).first()
        if existing_client:
            is_own_ci = draft.cliente and draft.cliente.pk == existing_client.pk
            if not is_own_ci:
                branch_name = existing_client.sucursal_registro.nombre if existing_client.sucursal_registro else "el sistema"
                errors["ci"] = f"Ya existe un cliente registrado con este CI en {branch_name}."

    existing_hash = (draft.datos_usuario or {}).get("passwordHash")
    if not password and not existing_hash:
        errors["password"] = "La contraseña es obligatoria."

    fecha_nacimiento = _parse_date(payload.get("fechaNacimiento"), "fechaNacimiento", errors, required=True)
    nro_hijos = _parse_positive_int(payload.get("nroHijos"), "nroHijos", errors, required=False, min_value=0)

    if errors:
        return None, errors

    return {
        "primerNombre": _cap(primer_nombre),
        "segundoNombre": _cap(payload.get("segundoNombre")),
        "apellidoPaterno": _cap(apellido_paterno),
        "apellidoMaterno": _cap(payload.get("apellidoMaterno")),
        "username": username,
        "email": (payload.get("email") or "").strip(),
        "telefono": (payload.get("telefono") or "").strip(),
        "ci": (payload.get("ci") or "").strip(),
        "fechaNacimiento": fecha_nacimiento.isoformat() if fecha_nacimiento else "",
        "nroHijos": 0 if nro_hijos is None else nro_hijos,
        "direccionDomicilio": _cap(payload.get("direccionDomicilio")),
        "ocupacion": _cap(payload.get("ocupacion")),
        "observacionesCliente": _cap(payload.get("observacionesCliente")),
        "passwordHash": make_password(password) if password else existing_hash,
    }, None


def _validate_operation_step(payload):
    errors = {}

    service_config_id = _parse_positive_int(payload.get("serviceConfigId"), "serviceConfigId", errors, min_value=1)
    precio_total = _parse_decimal(payload.get("precioTotal"), "precioTotal", errors, min_value=Decimal("0.01"))
    cuotas_totales = _parse_positive_int(payload.get("cuotasTotales"), "cuotasTotales", errors, min_value=1)
    sesiones_totales = _parse_positive_int(payload.get("sesionesTotales"), "sesionesTotales", errors, min_value=1)
    fecha_inicio = _parse_date(payload.get("fechaInicio"), "fechaInicio", errors, required=True)
    today = timezone.localdate()
    fecha_final = _parse_date(payload.get("fechaFinal"), "fechaFinal", errors, required=False)
    estado = (payload.get("estado") or Operacion.Estado.EN_PROCESO).strip()
    if estado not in {choice[0] for choice in Operacion.Estado.choices}:
        errors["estado"] = "El estado seleccionado no es valido."

    zona_general = (payload.get("zonaGeneral") or "").strip()
    if not zona_general:
        errors["zonaGeneral"] = "La zona general es obligatoria."

    zona_especifica = (payload.get("zonaEspecifica") or "").strip()
    if not zona_especifica:
        errors["zonaEspecifica"] = "La zona especifica es obligatoria."

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

    raw_due_dates = payload.get("fechasVencimientoCuotas") or []
    due_dates = []
    seen_due_dates = set()
    if cuotas_totales:
        if len(raw_due_dates) != cuotas_totales:
            errors["fechasVencimientoCuotas"] = (
                "Debes indicar una fecha de vencimiento para cada cuota."
            )

        for index in range(cuotas_totales):
            raw_value = raw_due_dates[index] if index < len(raw_due_dates) else ""
            parsed_due_date = _parse_date(
                raw_value,
                f"fechasVencimientoCuotas.{index}",
                errors,
                required=True,
            )
            if not parsed_due_date:
                continue
            if parsed_due_date < today:
                errors[f"fechasVencimientoCuotas.{index}"] = (
                    "La fecha de vencimiento debe ser hoy o en el futuro."
                )
            if parsed_due_date in seen_due_dates:
                errors[f"fechasVencimientoCuotas.{index}"] = (
                    "Las fechas de vencimiento no pueden repetirse."
                )
                continue
            seen_due_dates.add(parsed_due_date)
            due_dates.append(parsed_due_date)

    if errors:
        return None, None, errors

    return (
        {
            "serviceConfigId": service_config_id,
            "zonaGeneral": _cap(payload.get("zonaGeneral")),
            "zonaEspecifica": _cap(payload.get("zonaEspecifica")),
            "precioTotal": f"{precio_total:.2f}",
            "cuotasTotales": cuotas_totales,
            "sesionesTotales": sesiones_totales,
            "fechaInicio": fecha_inicio.isoformat() if fecha_inicio else "",
            "fechaFinal": fecha_final.isoformat() if fecha_final else "",
            "estado": estado,
            "detallesOperacion": _cap(payload.get("detallesOperacion")),
            "recomendaciones": _cap(payload.get("recomendaciones")),
            "fechasVencimientoCuotas": [item.isoformat() for item in due_dates],
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
        # Mandatory if entry exists
        antecedente_id = _parse_positive_int(item.get("antecedenteId"), f"antecedentes.{index}.antecedenteId", errors, required=True, min_value=1)
        tipo_antecedente = (item.get("tipoAntecedente") or "").strip()
        if not tipo_antecedente:
            errors[f"antecedentes.{index}.tipoAntecedente"] = "Este campo es obligatorio."
        elif tipo_antecedente not in {
            FichaAntecedenteMedico.TipoAntecedente.FAMILIAR,
            FichaAntecedenteMedico.TipoAntecedente.PERSONAL,
        }:
            errors[f"antecedentes.{index}.tipoAntecedente"] = "Selecciona un tipo de antecedente valido."
        
        if errors.get(f"antecedentes.{index}.antecedenteId") or errors.get(f"antecedentes.{index}.tipoAntecedente"):
            continue

        antecedente = AntecedenteMedico.objects.filter(pk=antecedente_id, activo=True).first()
        if not antecedente:
            errors[f"antecedentes.{index}.antecedenteId"] = "El antecedente seleccionado no existe."
            continue

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
        # Mandatory if entry exists
        implante_id = _parse_positive_int(item.get("implanteId"), f"implantes.{index}.implanteId", errors, required=True, min_value=1)
        
        if errors.get(f"implantes.{index}.implanteId"):
            continue

        implante = ImplanteInjerto.objects.filter(pk=implante_id, activo=True).first()
        if not implante:
            errors[f"implantes.{index}.implanteId"] = "El implante seleccionado no existe."
            continue

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
        # Mandatory if entry exists
        cirugia_id = _parse_positive_int(item.get("cirugiaId"), f"cirugias.{index}.cirugiaId", errors, required=True, min_value=1)
        hace_cuanto_tiempo = (item.get("haceCuantoTiempo") or "").strip()
        if not hace_cuanto_tiempo:
            errors[f"cirugias.{index}.haceCuantoTiempo"] = "Este campo es obligatorio."

        if errors.get(f"cirugias.{index}.cirugiaId") or errors.get(f"cirugias.{index}.haceCuantoTiempo"):
            continue

        cirugia = CirugiaEstetica.objects.filter(pk=cirugia_id, activo=True).first()
        if not cirugia:
            errors[f"cirugias.{index}.cirugiaId"] = "La cirugia seleccionada no existe."
            continue

        if cirugia.id in cirugias_seen:
            errors[f"cirugias.{index}.cirugiaId"] = "Esta cirugia ya fue agregada."
            continue
        
        cirugias_seen.add(cirugia.id)
        cirugias_validated.append(
            {
                "cirugiaId": cirugia.id,
                "haceCuantoTiempo": hace_cuanto_tiempo,
                "detalle": (item.get("detalle") or "").strip(),
            }
        )

    valid_field_ids = set()
    valid_option_ids = {}
    fields_by_id = {}
    if service_config and service_config.sector_id:
        campos_qs = FichaCampo.objects.filter(
            seccion__sector=service_config.sector_id,
            seccion__activo=True,
            activo=True,
        )
    elif service_config and service_config.proc_estetico_id:
        campos_qs = FichaCampo.objects.filter(
            seccion__proc_estetico=service_config.proc_estetico_id,
            seccion__activo=True,
            activo=True,
        )
    else:
        campos_qs = FichaCampo.objects.none()

    for field in (
        campos_qs
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
            "valueText": _cap(item.get("valueText")),
            "valueNumber": str(item.get("valueNumber") or "").strip(),
            "valueDate": str(item.get("valueDate") or "").strip(),
            "valueBoolean": bool(item.get("valueBoolean")) if item.get("valueBoolean") is not None else None,
            "detail": (item.get("detail") or "").strip(),
            "optionIds": cleaned_option_ids,
        }
        field_responses_validated[str(field_id)] = cleaned_response

        if not _field_response_has_value(field, cleaned_response):
            errors[f"fieldResponses.{raw_field_id}.required"] = f"Debes completar el campo {field.etiqueta}."

    # Todos los campos de la ficha especifica del procedimiento son obligatorios
    for field_id, field in fields_by_id.items():
        response = field_responses_validated.get(str(field_id))
        if not response or not _field_response_has_value(field, response):
            errors[f"fieldResponses.{field_id}.required"] = f"Debes completar el campo {field.etiqueta}."

    if errors:
        return None, errors

    return {
        "fechaFicha": fecha_ficha.isoformat() if fecha_ficha else "",
        "motivoConsulta": _cap(payload.get("motivoConsulta")),
        "observaciones": _cap(payload.get("observaciones")),
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


def _validate_biometric_step(payload):
    errors = {}
    provider = (payload.get("provider") or "MOCK").strip().upper()
    template = (payload.get("template") or "").strip()
    device_serial = (payload.get("deviceSerial") or "").strip()
    consent_accepted = _parse_bool(payload.get("consentAccepted"))
    captured_at = (payload.get("capturedAt") or "").strip()
    quality = _parse_positive_int(payload.get("quality"), "quality", errors, required=True, min_value=1)

    if provider not in {choice[0] for choice in HuellaBiometricaCliente.Proveedor.choices}:
        errors["provider"] = "El proveedor biometrico no es valido."
    if not template:
        errors["template"] = "Debes capturar una huella antes de continuar."
    if quality is not None and quality < 60:
        errors["quality"] = "La calidad simulada debe ser de al menos 60."

    if errors:
        return None, errors

    return {
        "provider": provider,
        "template": template,
        "quality": quality,
        "deviceSerial": device_serial,
        "consentAccepted": consent_accepted,
        "capturedAt": captured_at,
    }, None


def _admin_conversion_detail(draft):
    prospecto = draft.prospecto
    cliente = draft.cliente
    
    service_config = None
    service_config_id = (draft.datos_operacion or {}).get("serviceConfigId")
    if service_config_id:
        service_config = (
            ServicioConfig.objects.select_related("tipo_servicio", "proc_estetico")
            .filter(pk=service_config_id)
            .first()
        )

    return {
        "prospect": _prospect_item(prospecto) if prospecto else None,
        "client": {
            "id": cliente.pk,
            "name": cliente.usuario.nombre_completo,
            "ci": cliente.ci,
            "status": cliente.estado_cliente,
        } if cliente else None,
        "draft": _serialize_draft(draft),
        "serviceConfigs": _serialize_service_configs(),
        "operationStates": [
            {"value": value, "label": label}
            for value, label in Operacion.Estado.choices
        ],
        "medicalConfig": _serialize_medical_config(service_config),
    }


@require_GET
@admin_required
def admin_prospect_conversion_detail(request, prospecto_id):
    draft, error = _get_draft_convertible(request, prospecto_id=prospecto_id)
    if error:
        return json_response({"detail": error}, status=400)
    payload = _admin_conversion_detail(draft)
    logger.warning(
        "[PREFILL] response(prospect) draft_id=%s antecedentes=%s implantes=%s cirugias=%s",
        getattr(draft, "id", None),
        len((payload.get("medicalData") or {}).get("antecedentes", [])),
        len((payload.get("medicalData") or {}).get("implantes", [])),
        len((payload.get("medicalData") or {}).get("cirugias", [])),
    )
    return json_response(payload)


@require_GET
@admin_required
def admin_client_reactivation_detail(request, cliente_id):
    draft, error = _get_draft_convertible(request, cliente_id=cliente_id)
    if error:
        return json_response({"detail": error}, status=400)
    payload = _admin_conversion_detail(draft)
    logger.warning(
        "[PREFILL] response(client) draft_id=%s cliente_id=%s antecedentes=%s implantes=%s cirugias=%s",
        getattr(draft, "id", None),
        cliente_id,
        len((payload.get("medicalData") or {}).get("antecedentes", [])),
        len((payload.get("medicalData") or {}).get("implantes", [])),
        len((payload.get("medicalData") or {}).get("cirugias", [])),
    )
    return json_response(payload)


@require_POST
@admin_required
def admin_prospect_conversion_cancel(request, prospecto_id=None, cliente_id=None):
    draft, error = _get_draft_convertible(request, prospecto_id=prospecto_id, cliente_id=cliente_id)
    if error:
        return json_response({"detail": error}, status=400)

    draft.delete()
    return json_response({"detail": "El borrador de conversion fue descartado correctamente."})


@require_POST
@admin_required
def admin_prospect_conversion_user_step(request, prospecto_id=None, cliente_id=None):
    draft, error = _get_draft_convertible(request, prospecto_id=prospecto_id, cliente_id=cliente_id)
    if error:
        return json_response({"detail": error}, status=400)

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    user_data, errors = _validate_user_step(payload, draft)
    if errors:
        return json_response({"detail": "Corrige los errores del paso 1.", "errors": errors}, status=400)

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
    return json_response(_admin_conversion_detail(draft))


@require_POST
@admin_required
def admin_prospect_conversion_operation_step(request, prospecto_id=None, cliente_id=None):
    draft, error = _get_draft_convertible(request, prospecto_id=prospecto_id, cliente_id=cliente_id)
    if error:
        return json_response({"detail": error}, status=400)

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    if not draft.paso_usuario_completado:
        return json_response({"detail": "Debes completar primero los datos de usuario."}, status=400)

    previous_service_config_id = (draft.datos_operacion or {}).get("serviceConfigId")
    operation_data, service_config, errors = _validate_operation_step(payload)
    if errors:
        return json_response({"detail": "Corrige los errores del paso 2.", "errors": errors}, status=400)

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
    return json_response(_admin_conversion_detail(draft))


@require_POST
@admin_required
def admin_prospect_conversion_medical_step(request, prospecto_id=None, cliente_id=None):
    draft, error = _get_draft_convertible(request, prospecto_id=prospecto_id, cliente_id=cliente_id)
    if error:
        return json_response({"detail": error}, status=400)

    if request.content_type and request.content_type.startswith("multipart/form-data"):
        payload_raw = request.POST.get("payload")
        if not payload_raw:
            return json_response({"detail": "Falta el campo 'payload' en el form-data."}, status=400)
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            return json_response({"detail": "El campo 'payload' no es JSON valido."}, status=400)
        
        # Guardamos el PDF si viene
        pdf_file = request.FILES.get("documento_escaneado_pdf")
        if pdf_file:
            draft.documento_pdf = pdf_file
            draft.save(update_fields=["documento_pdf"])
    else:
        payload = load_payload(request)
        if payload is None:
            return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    if not draft.paso_operacion_completado:
        return json_response({"detail": "Debes completar primero los datos de la operacion."}, status=400)

    service_config_id = (draft.datos_operacion or {}).get("serviceConfigId")
    service_config = (
        ServicioConfig.objects.select_related("tipo_servicio", "proc_estetico").filter(pk=service_config_id).first()
        if service_config_id
        else None
    )

    medical_data, errors = _validate_medical_step(payload, service_config)
    if errors:
        return json_response({"detail": "Corrige los errores del paso 3.", "errors": errors}, status=400)

    draft.datos_ficha = medical_data
    draft.paso_ficha_completado = True
    draft.paso_actual = max(draft.paso_actual, ProspectoConversionBorrador.Paso.BIOMETRIA)
    draft.save(
        update_fields=[
            "datos_ficha",
            "paso_ficha_completado",
            "paso_actual",
            "updated_at",
        ]
    )
    return json_response(_admin_conversion_detail(draft))


@require_POST
@admin_required
def admin_prospect_conversion_biometric_step(request, prospecto_id=None, cliente_id=None):
    draft, error = _get_draft_convertible(request, prospecto_id=prospecto_id, cliente_id=cliente_id)
    if error:
        return json_response({"detail": error}, status=400)

    payload = load_payload(request)
    if payload is None:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    if not draft.paso_ficha_completado:
        return json_response({"detail": "Debes completar primero la ficha medica."}, status=400)

    biometric_data, errors = _validate_biometric_step(payload)
    if errors:
        return json_response({"detail": "Corrige los errores del paso 4.", "errors": errors}, status=400)

    draft.datos_biometria = biometric_data
    draft.paso_biometria_completado = True
    draft.paso_actual = ProspectoConversionBorrador.Paso.BIOMETRIA
    draft.save(
        update_fields=[
            "datos_biometria",
            "paso_biometria_completado",
            "paso_actual",
            "updated_at",
        ]
    )
    return json_response(_admin_conversion_detail(draft))


@require_POST
@admin_required
@transaction.atomic
def admin_prospect_conversion_finalize(request, prospecto_id=None, cliente_id=None):
    draft, error = _get_draft_convertible(request, prospecto_id=prospecto_id, cliente_id=cliente_id)
    if error:
        return json_response({"detail": error}, status=400)

    document_file, document_error = _get_required_pdf_file(request, draft=draft)
    if document_error:
        return document_error

    if not (
        draft.paso_usuario_completado
        and draft.paso_operacion_completado
        and draft.paso_ficha_completado
        and draft.paso_biometria_completado
    ):
        return json_response({"detail": "Debes completar los cuatro pasos antes de finalizar."}, status=400)

    user_data = draft.datos_usuario or {}
    operation_data = draft.datos_operacion or {}
    medical_data = draft.datos_ficha or {}
    biometric_data = draft.datos_biometria or {}
    analisis_data = medical_data.get("analisisEstetico") or {}

    service_config = (
        ServicioConfig.objects.select_related("tipo_servicio", "proc_estetico")
        .filter(pk=operation_data.get("serviceConfigId"), activo=True)
        .first()
    )
    if not service_config:
        return json_response({"detail": "El servicio seleccionado ya no esta disponible."}, status=400)

    client_role = Rol.objects.filter(rol="CLIENTE").first()
    if not client_role:
        return json_response({"detail": "No existe el rol CLIENTE configurado en el sistema."}, status=500)

    if draft.prospecto:
        # Nueva cuenta para prospecto
        if not user_data.get("passwordHash"):
            return json_response({"detail": "El borrador no tiene una contraseña valida para crear la cuenta."}, status=400)
        
        username = user_data.get("username", "")
        if Usuario.objects.filter(username=username).exists():
            return json_response({"detail": "Ya existe una cuenta con el usuario seleccionado. Actualiza el paso 1 antes de continuar."}, status=400)

        user = Usuario.objects.create(
            username=username,
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

        target_branch = draft.prospecto.sucursal_registro or _get_branch_for_scope_check(request)
        if not target_branch:
            return json_response({"detail": "No encontramos una sucursal activa para completar la conversión."}, status=400)

        cliente = Cliente.objects.create(
            usuario=user,
            sucursal_registro=target_branch,
            ci=user_data.get("ci", ""),
            fecha_nacimiento=date.fromisoformat(user_data["fechaNacimiento"]),
            nro_hijos=int(user_data.get("nroHijos") or 0),
            direccion_domicilio=user_data.get("direccionDomicilio", ""),
            telefono=user_data.get("telefono", ""),
            ocupacion=user_data.get("ocupacion", ""),
            observaciones=user_data.get("observacionesCliente", ""),
        )
    else:
        # Actualizacion de cliente existente (reactivacion)
        cliente = draft.cliente
        user = cliente.usuario
        
        # Actualizamos datos del usuario
        user.primer_nombre = user_data["primerNombre"]
        user.segundo_nombre = user_data.get("segundoNombre", "")
        user.apellido_paterno = user_data["apellidoPaterno"]
        user.apellido_materno = user_data.get("apellidoMaterno", "")
        user.email = user_data.get("email", "")
        if user_data.get("passwordHash"):
            user.password = user_data["passwordHash"]
        user.save()
        
        # Actualizamos datos del cliente
        cliente.ci = user_data.get("ci", "")
        cliente.fecha_nacimiento = date.fromisoformat(user_data["fechaNacimiento"])
        cliente.nro_hijos = int(user_data.get("nroHijos") or 0)
        cliente.direccion_domicilio = user_data.get("direccionDomicilio", "")
        cliente.telefono = user_data.get("telefono", "")
        cliente.ocupacion = user_data.get("ocupacion", "")
        cliente.observaciones = user_data.get("observacionesCliente", "")
        cliente.save()

    HuellaBiometricaCliente.objects.update_or_create(
        cliente=cliente,
        defaults={
            "proveedor": biometric_data.get("provider") or HuellaBiometricaCliente.Proveedor.MOCK,
            "template_biometrico": biometric_data.get("template", ""),
            "device_serial": biometric_data.get("deviceSerial", ""),
            "calidad_captura": int(biometric_data.get("quality") or 0),
            "consentimiento_aceptado": bool(biometric_data.get("consentAccepted")),
            "registrado_por": request.user,
        }
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

    quota_amounts = split_amount(Decimal(operation_data["precioTotal"]), int(operation_data["cuotasTotales"]))
    for cuota_index, fecha_vencimiento in enumerate(operation_data.get("fechasVencimientoCuotas") or []):
        CuotaPlanPago.objects.create(
            operacion=operacion,
            nro_cuota=cuota_index + 1,
            fecha_vencimiento=date.fromisoformat(fecha_vencimiento),
            monto_programado=quota_amounts[cuota_index] if cuota_index < len(quota_amounts) else Decimal("0.00"),
        )
    primer_pago_comprobante = request.FILES.get("primerPagoComprobante")
    primer_pago_monto = (request.POST.get("primerPagoMonto") or "").strip()
    primer_pago_detalle = (request.POST.get("primerPagoDetalle") or "").strip()
    if (primer_pago_monto or primer_pago_detalle) and not primer_pago_comprobante:
        return json_response(
            {"detail": "Debes adjuntar el comprobante para registrar el primer pago en este paso."},
            status=400,
        )
    if primer_pago_comprobante:
        primera_cuota = operacion.cuotas_plan_pagos.order_by("nro_cuota", "fecha_vencimiento").first()
        if primera_cuota:
            try:
                monto_primer_pago = Decimal(primer_pago_monto) if primer_pago_monto else primera_cuota.monto_programado
            except Exception:
                return json_response({"detail": "El monto del primer pago no es válido."}, status=400)
            PagoRealizado.objects.create(
                cuota=primera_cuota,
                monto_pagado=monto_primer_pago,
                comprobante_url=primer_pago_comprobante,
                detalles_pago=primer_pago_detalle or "Comprobante de primer pago registrado durante la conversión.",
                estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO,
                verificado_por=request.user,
                fecha_verificacion=timezone.now(),
                observacion_verificacion="Pago confirmado durante la conversión.",
            )

    ficha = FichaClinica.objects.create(
        operacion=operacion,
        fecha_ficha=date.fromisoformat(medical_data["fechaFicha"]) if medical_data.get("fechaFicha") else timezone.localdate(),
        motivo_consulta=medical_data.get("motivoConsulta", ""),
        observaciones=medical_data.get("observaciones", ""),
        firma_paciente_ci=medical_data.get("firmaPacienteCi") or user_data.get("ci", ""),
        documento_escaneado_pdf=document_file,
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

    is_reactivation = draft.cliente is not None
    if draft.prospecto:
        draft.prospecto.marcar_como_convertido(cliente, save=True)
    elif is_reactivation:
        # La reactivacion debe dejar al cliente habilitado para nuevos procedimientos.
        cliente.cambiar_estado(Cliente.Estado.ACTIVO, save=True, manual=True)

    draft.delete()

    return json_response(
        {
            "detail": "El proceso finalizo correctamente." if is_reactivation else "El prospecto fue convertido correctamente a cliente.",
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
