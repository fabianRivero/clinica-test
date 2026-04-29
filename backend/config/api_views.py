import json
from pathlib import PurePosixPath
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import Rol, Usuario
from billing.models import ConfiguracionPagoQR, CuotaPlanPago, PagoRealizado
from catalogs.models import (
    GrupoOpciones,
    OpcionCatalogo,
    PatologiaCutanea,
    ProcEstetico,
    ProcEsteticosTipo,
    ServicioConfig,
    TipoServicio,
)
from customers.models import Cliente, Prospecto
from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualEspecialista,
    CitaMedica,
    DisponibilidadCita,
    FichaCampo,
    FichaSeccion,
    Operacion,
)
from staff.models import Especialidad, Especialista, EspecialistaEspecialidad


def _json(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


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


def _currency(amount):
    return f"Bs {amount:.2f}"


def _date_label(value):
    if not value:
        return "Sin fecha"
    return value.strftime("%d/%m/%Y")


def _datetime_label(value):
    if not value:
        return "Sin fecha"
    return timezone.localtime(value).strftime("%d/%m %H:%M")


def _full_name(user):
    if not user:
        return "Sin asignar"
    return user.nombre_completo or user.username


def _procedure_name(operacion):
    procedimiento = operacion.servicio_config.proc_estetico
    if procedimiento:
        return procedimiento.proceso
    return operacion.servicio_config.tipo_servicio.tipo


def _payment_status(payment):
    if payment.estado_verificacion == PagoRealizado.EstadoVerificacion.APROBADO:
        return "aprobado"
    if payment.estado_verificacion == PagoRealizado.EstadoVerificacion.RECHAZADO:
        return "observado"
    return "pendiente"


def _agenda_status(cita):
    if cita.estado == CitaMedica.Estado.CONFIRMADA:
        return "confirmada"
    if cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA:
        return "biometria"
    return "programada"


def _prospect_stage(prospecto):
    if prospecto.estado == Prospecto.Estado.CONVERTIDO:
        return "convertido"
    if prospecto.created_at >= timezone.now() - timedelta(days=2):
        return "nuevo"
    return "seguimiento"


def _prospect_interest(prospecto):
    if prospecto.estado == Prospecto.Estado.CONVERTIDO:
        return "Cliente convertido"
    if prospecto.observaciones:
        return prospecto.observaciones
    return "Consulta general"


def _quota_status(operacion):
    cuotas = list(operacion.cuotas_plan_pagos.all())
    if not cuotas:
        return "Sin plan de pagos"

    has_observed = any(
        pago.estado_verificacion == PagoRealizado.EstadoVerificacion.RECHAZADO
        for cuota in cuotas
        for pago in cuota.pagos_realizados.all()
    )
    if has_observed:
        return "Pago observado"

    pending_payments = sum(
        1
        for cuota in cuotas
        for pago in cuota.pagos_realizados.all()
        if pago.estado_verificacion == PagoRealizado.EstadoVerificacion.PENDIENTE
    )
    if pending_payments:
        return f"{pending_payments} pago(s) pendientes"

    pending_quotas = sum(1 for cuota in cuotas if cuota.estado != CuotaPlanPago.Estado.PAGADO)
    if pending_quotas:
        return f"{pending_quotas} cuota(s) pendientes"

    return "Cuotas al dia"


def _operation_specialist(operacion):
    citas = list(operacion.citas_medicas.all())
    if not citas:
        return "Sin asignar"

    now = timezone.now()
    upcoming = [cita for cita in citas if cita.fecha_hora >= now]
    if upcoming:
        return _full_name(upcoming[0].medico.usuario)
    return _full_name(citas[-1].medico.usuario)


def _operation_next_appointment(operacion):
    citas = list(operacion.citas_medicas.all())
    if not citas:
        return "Sin cita programada"

    now = timezone.now()
    upcoming = [cita for cita in citas if cita.fecha_hora >= now]
    cita = upcoming[0] if upcoming else citas[-1]
    return _datetime_label(cita.fecha_hora)


def _operation_card(operacion):
    return {
        "id": f"OP-{operacion.pk:04d}",
        "rawId": operacion.pk,
        "patient": _full_name(operacion.paciente.usuario),
        "procedure": _procedure_name(operacion),
        "specialist": _operation_specialist(operacion),
        "sessions": (
            f"{operacion.sesiones_totales} total | "
            f"{operacion.sesiones_confirmadas} confirmadas | "
            f"{operacion.reservas_activas} reservadas | "
            f"{operacion.sesiones_disponibles} libres"
        ),
        "nextAppointment": _operation_next_appointment(operacion),
        "quotaStatus": _quota_status(operacion),
        "status": operacion.get_estado_display(),
        "price": _currency(operacion.precio_total),
    }


def _operation_detail(operacion):
    ficha = getattr(operacion, "ficha_clinica", None)
    procedure = operacion.servicio_config.proc_estetico
    document_field = ficha.documento_escaneado_pdf if ficha else None
    document_url = document_field.url if document_field else ""
    document_name = PurePosixPath(document_field.name).name if document_field else ""

    return {
        "id": f"OP-{operacion.pk:04d}",
        "rawId": operacion.pk,
        "patient": _full_name(operacion.paciente.usuario),
        "procedure": _procedure_name(operacion),
        "serviceType": operacion.servicio_config.tipo_servicio.tipo,
        "procedureType": procedure.tipo_p_estetico.tipo if procedure else "Sin tipo",
        "specialist": _operation_specialist(operacion),
        "sessions": (
            f"{operacion.sesiones_totales} total | "
            f"{operacion.sesiones_confirmadas} confirmadas | "
            f"{operacion.reservas_activas} reservadas | "
            f"{operacion.sesiones_disponibles} libres"
        ),
        "nextAppointment": _operation_next_appointment(operacion),
        "quotaStatus": _quota_status(operacion),
        "status": operacion.get_estado_display(),
        "price": _currency(operacion.precio_total),
        "startDate": _date_label(operacion.fecha_inicio),
        "endDate": _date_label(operacion.fecha_final),
        "zonaGeneral": operacion.zona_general or "Sin especificar",
        "zonaEspecifica": operacion.zona_especifica or "Sin especificar",
        "detallesOperacion": operacion.detalles_op or "Sin detalles registrados.",
        "recomendaciones": operacion.recomendaciones or "Sin recomendaciones registradas.",
        "medicalRecordDate": _date_label(ficha.fecha_ficha) if ficha else "Sin ficha registrada",
        "medicalRecordReason": ficha.motivo_consulta if ficha and ficha.motivo_consulta else "Sin motivo registrado.",
        "medicalRecordNotes": ficha.observaciones if ficha and ficha.observaciones else "Sin observaciones registradas.",
        "consentAccepted": bool(ficha and ficha.consentimiento_aceptado),
        "documentPdfUrl": document_url,
        "documentPdfName": document_name,
        "appointments": [
            {
                "id": f"CIT-{cita.pk:04d}",
                "dateTime": _datetime_label(cita.fecha_hora),
                "specialist": _full_name(cita.medico.usuario),
                "status": cita.get_estado_display(),
                "biometricStatus": "Validada" if cita.verif_biometria else "Pendiente",
            }
            for cita in operacion.citas_medicas.all()
        ],
        "quotas": [
            {
                "id": f"CUO-{cuota.pk:04d}",
                "number": cuota.nro_cuota,
                "dueDate": _date_label(cuota.fecha_vencimiento),
                "status": cuota.get_estado_display(),
                "paymentsCount": cuota.pagos_realizados.count(),
            }
            for cuota in operacion.cuotas_plan_pagos.all()
        ],
    }


def _prospect_item(prospecto):
    return {
        "id": f"PRO-{prospecto.pk:04d}",
        "rawId": prospecto.pk,
        "name": str(prospecto),
        "phone": prospecto.telefono or "Sin telefono",
        "interest": _prospect_interest(prospecto),
        "registeredBy": _full_name(prospecto.registrado_por),
        "stage": _prospect_stage(prospecto),
        "state": prospecto.get_estado_display(),
        "createdAt": _datetime_label(prospecto.created_at),
        "convertedAt": _datetime_label(prospecto.fecha_conversion) if prospecto.fecha_conversion else "-",
    }


def _client_item(cliente):
    analisis = next(iter(cliente.analisis_esteticos.all()), None)
    return {
        "id": f"CLI-{cliente.pk:04d}",
        "name": _full_name(cliente.usuario),
        "phone": cliente.telefono or "Sin telefono",
        "status": cliente.get_estado_cliente_display(),
        "activeOperations": cliente.operaciones.filter(estado=Operacion.Estado.EN_PROCESO).count(),
        "totalOperations": cliente.operaciones.count(),
        "lastAnalysis": _date_label(analisis.fecha_analisis) if analisis else "Sin analisis",
    }


def _payment_item(payment):
    operacion = payment.cuota.operacion
    return {
        "id": f"PAY-{payment.pk:04d}",
        "rawId": payment.pk,
        "patient": _full_name(operacion.paciente.usuario),
        "operation": _procedure_name(operacion),
        "amount": _currency(payment.monto_pagado),
        "submittedAt": _datetime_label(payment.created_at),
        "bank": "Transferencia",
        "status": _payment_status(payment),
        "quota": f"Cuota {payment.cuota.nro_cuota}",
        "dueDate": _date_label(payment.cuota.fecha_vencimiento),
        "verifier": _full_name(payment.verificado_por) if payment.verificado_por else "Sin revisar",
        "receiptUrl": payment.comprobante_url.url if payment.comprobante_url else "",
        "note": payment.observacion_verificacion or payment.detalles_pago or "",
    }


def _payment_qr_config_item(config):
    return {
        "hasQr": bool(config and config.imagen_qr),
        "qrImageUrl": config.imagen_qr.url if config and config.imagen_qr else "",
        "instructions": (
            config.instrucciones
            if config
            else "Escanea el QR de pago y luego adjunta tu comprobante para revision administrativa."
        ),
    }


def _catalog_item(identifier, name, count, note):
    return {
        "id": identifier,
        "name": name,
        "count": count,
        "note": note,
    }


def _catalog_field(
    name,
    label,
    input_type,
    *,
    required=False,
    options=None,
    placeholder="",
    hint="",
    value_type="string",
    allow_empty=False,
    min_value=None,
):
    payload = {
        "name": name,
        "label": label,
        "inputType": input_type,
        "required": required,
        "placeholder": placeholder,
        "hint": hint,
        "valueType": value_type,
        "allowEmpty": allow_empty,
    }
    if options is not None:
        payload["options"] = options
    if min_value is not None:
        payload["minValue"] = min_value
    return payload


def _catalog_option(value, label, secondary_label=""):
    payload = {"value": value, "label": label}
    if secondary_label:
        payload["secondaryLabel"] = secondary_label
    return payload


def _catalog_entry(item_id, title, subtitle, active, metadata, values):
    return {
        "id": item_id,
        "title": title,
        "subtitle": subtitle,
        "active": active,
        "activeLabel": "Activo" if active else "Inactivo",
        "metadata": metadata,
        "values": values,
    }


def _catalog_metric_set(active_count, inactive_count, total_count, relation_label):
    return [
        _metric("catalog-active", "Activos", active_count, "Visibles para nuevas operaciones", "success"),
        _metric("catalog-inactive", "Inactivos", inactive_count, "Preservados para historico y reactivacion", "warning"),
        _metric("catalog-total", "Total", total_count, relation_label, "primary"),
    ]


def _catalog_key_to_slug(catalog_key):
    if catalog_key in {
        "todos-los-servicios",
        "procedimientos-esteticos",
        "tipos-servicio",
        "campos-ficha",
        "patologias-cutaneas",
        "especialidades",
        "grupos-opciones",
    }:
        return catalog_key
    raise KeyError(catalog_key)


def _catalog_summary_descriptor():
    return [
        {
            "key": "todos-los-servicios",
            "title": "Todos los servicios",
            "description": "Configuraciones completas de servicio con su precio base y procedimiento asociado.",
        },
        {
            "key": "procedimientos-esteticos",
            "title": "Procedimientos esteticos",
            "description": "Catalogo operativo de procedimientos disponibles para las ventas y fichas clinicas.",
        },
        {
            "key": "tipos-servicio",
            "title": "Tipos de servicio",
            "description": "Categorias comerciales utilizadas al crear configuraciones de servicio y operaciones.",
        },
        {
            "key": "campos-ficha",
            "title": "Campos de ficha",
            "description": "Preguntas configurables por procedimiento dentro de la ficha clinica.",
        },
        {
            "key": "patologias-cutaneas",
            "title": "Patologias cutaneas",
            "description": "Catalogo de patologias usado en el analisis estetico del paciente.",
        },
        {
            "key": "especialidades",
            "title": "Especialidades",
            "description": "Especialidades disponibles para especialistas y asignacion de agenda.",
        },
        {
            "key": "grupos-opciones",
            "title": "Grupos de opciones",
            "description": "Grupos reutilizables para respuestas de seleccion unica o multiple.",
        },
    ]


def _catalog_page_data(catalog_key):
    catalog_key = _catalog_key_to_slug(catalog_key)

    if catalog_key == "todos-los-servicios":
        queryset = (
            ServicioConfig.objects.select_related(
                "tipo_servicio",
                "proc_estetico",
                "proc_estetico__tipo_p_estetico",
            )
            .order_by("tipo_servicio__tipo", "proc_estetico__proceso", "pk")
        )
        items = [
            _catalog_entry(
                item.pk,
                str(item),
                f"Precio base: {_currency(item.precio_base)}",
                item.activo,
                [
                    {"label": "Tipo de servicio", "value": item.tipo_servicio.tipo},
                    {
                        "label": "Procedimiento",
                        "value": item.proc_estetico.proceso if item.proc_estetico else "Sin procedimiento",
                    },
                    {
                        "label": "Tipo de procedimiento",
                        "value": item.proc_estetico.tipo_p_estetico.tipo if item.proc_estetico else "No aplica",
                    },
                    {
                        "label": "Operaciones vinculadas",
                        "value": str(item.operaciones.count()),
                    },
                ],
                {
                    "serviceTypeId": item.tipo_servicio_id,
                    "procedureId": item.proc_estetico_id,
                    "basePrice": str(item.precio_base),
                },
            )
            for item in queryset
        ]
        active_count = queryset.filter(activo=True).count()
        total_count = queryset.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Todos los servicios",
                "description": "Administra cada servicio disponible con su precio base y el procedimiento estetico asociado.",
                "createLabel": "Crear servicio",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{Operacion.objects.count()} operacion(es) usan este catalogo",
            ),
            "fields": [
                _catalog_field(
                    "serviceTypeId",
                    "Tipo de servicio",
                    "select",
                    required=True,
                    value_type="number",
                    options=[
                        _catalog_option(tipo.pk, tipo.tipo)
                        for tipo in TipoServicio.objects.filter(activo=True).order_by("orden", "tipo")
                    ],
                ),
                _catalog_field(
                    "procedureId",
                    "Procedimiento estetico",
                    "select",
                    value_type="number",
                    allow_empty=True,
                    options=[
                        _catalog_option(
                            procedimiento.pk,
                            procedimiento.proceso,
                            secondary_label=procedimiento.tipo_p_estetico.tipo,
                        )
                        for procedimiento in ProcEstetico.objects.select_related("tipo_p_estetico")
                        .filter(activo=True)
                        .order_by("tipo_p_estetico__tipo", "orden", "proceso")
                    ],
                    hint="Deja este campo vacio para servicios generales como la cita de consulta.",
                ),
                _catalog_field(
                    "basePrice",
                    "Precio base",
                    "number",
                    required=True,
                    value_type="number",
                    min_value=0,
                ),
            ],
            "items": items,
        }

    if catalog_key == "procedimientos-esteticos":
        queryset = ProcEstetico.objects.select_related("tipo_p_estetico").order_by("orden", "proceso")
        items = [
            _catalog_entry(
                item.pk,
                item.proceso,
                f"Tipo: {item.tipo_p_estetico.tipo}",
                item.activo,
                [
                    {"label": "Orden", "value": str(item.orden)},
                    {"label": "Descripcion", "value": item.descripcion or "Sin descripcion"},
                    {
                        "label": "Servicios vinculados",
                        "value": str(item.servicios_config.count()),
                    },
                ],
                {
                    "procedureTypeId": item.tipo_p_estetico_id,
                    "name": item.proceso,
                    "description": item.descripcion,
                    "order": item.orden,
                },
            )
            for item in queryset
        ]
        active_count = queryset.filter(activo=True).count()
        total_count = queryset.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Procedimientos esteticos",
                "description": "Crea, edita y desactiva procedimientos especificos que luego pueden vincularse a servicios.",
                "createLabel": "Crear procedimiento",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{ServicioConfig.objects.filter(proc_estetico__isnull=False).count()} configuracion(es) de servicio vinculadas",
            ),
            "fields": [
                _catalog_field(
                    "procedureTypeId",
                    "Tipo de procedimiento",
                    "select",
                    required=True,
                    value_type="number",
                    options=[
                        _catalog_option(tipo.pk, tipo.tipo)
                        for tipo in ProcEsteticosTipo.objects.filter(activo=True).order_by("orden", "tipo")
                    ],
                ),
                _catalog_field("name", "Procedimiento", "text", required=True, placeholder="Ej. Borrado de tatuajes"),
                _catalog_field("description", "Descripcion", "textarea", placeholder="Notas internas del procedimiento"),
                _catalog_field("order", "Orden", "number", value_type="number", min_value=0),
            ],
            "items": items,
        }

    if catalog_key == "tipos-servicio":
        queryset = TipoServicio.objects.order_by("orden", "tipo")
        items = [
            _catalog_entry(
                item.pk,
                item.tipo,
                "Base comercial del servicio",
                item.activo,
                [
                    {"label": "Orden", "value": str(item.orden)},
                    {"label": "Descripcion", "value": item.descripcion or "Sin descripcion"},
                    {
                        "label": "Configuraciones activas",
                        "value": str(item.servicios_config.filter(activo=True).count()),
                    },
                ],
                {
                    "name": item.tipo,
                    "description": item.descripcion,
                    "order": item.orden,
                },
            )
            for item in queryset
        ]
        active_count = queryset.filter(activo=True).count()
        total_count = queryset.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Tipos de servicio",
                "description": "Administra las categorias comerciales que se usan al vender tratamientos y consultas.",
                "createLabel": "Crear tipo de servicio",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{ServicioConfig.objects.filter(activo=True).count()} configuracion(es) de servicio activas",
            ),
            "fields": [
                _catalog_field("name", "Tipo de servicio", "text", required=True, placeholder="Ej. Cita de consulta"),
                _catalog_field("description", "Descripcion", "textarea", placeholder="Notas internas del tipo de servicio"),
                _catalog_field("order", "Orden", "number", value_type="number", min_value=0),
            ],
            "items": items,
        }

    if catalog_key == "campos-ficha":
        queryset = (
            FichaCampo.objects.select_related("seccion__proc_estetico", "grupo_opciones")
            .order_by("seccion__proc_estetico__proceso", "seccion__orden", "orden", "etiqueta")
        )
        items = [
            _catalog_entry(
                item.pk,
                item.etiqueta,
                f"{item.seccion.proc_estetico.proceso} · {item.seccion.nombre}",
                item.activo,
                [
                    {"label": "Codigo", "value": item.codigo},
                    {"label": "Tipo", "value": item.get_tipo_campo_display()},
                    {
                        "label": "Grupo de opciones",
                        "value": item.grupo_opciones.nombre if item.grupo_opciones else "Sin grupo",
                    },
                    {"label": "Orden", "value": str(item.orden)},
                    {"label": "Requerido", "value": "Si" if item.requerido else "No"},
                    {"label": "Detalle", "value": "Permitido" if item.permite_detalle else "No"},
                ],
                {
                    "sectionId": item.seccion_id,
                    "code": item.codigo,
                    "label": item.etiqueta,
                    "fieldType": item.tipo_campo,
                    "optionGroupId": item.grupo_opciones_id,
                    "isMultiple": item.es_multiple,
                    "allowsDetail": item.permite_detalle,
                    "required": item.requerido,
                    "order": item.orden,
                },
            )
            for item in queryset
        ]
        active_count = queryset.filter(activo=True).count()
        total_count = queryset.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Campos de ficha",
                "description": "Gestiona las preguntas configurables que aparecen en las fichas clinicas por procedimiento.",
                "createLabel": "Crear campo de ficha",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{FichaSeccion.objects.filter(activo=True).count()} seccion(es) disponibles",
            ),
            "fields": [
                _catalog_field(
                    "sectionId",
                    "Seccion",
                    "select",
                    required=True,
                    value_type="number",
                    options=[
                        _catalog_option(
                            seccion.pk,
                            seccion.nombre,
                            secondary_label=seccion.proc_estetico.proceso,
                        )
                        for seccion in FichaSeccion.objects.select_related("proc_estetico").filter(activo=True).order_by(
                            "proc_estetico__proceso",
                            "orden",
                            "nombre",
                        )
                    ],
                ),
                _catalog_field("code", "Codigo interno", "text", required=True, placeholder="Ej. BRONCEADO"),
                _catalog_field("label", "Etiqueta visible", "text", required=True, placeholder="Ej. Bronceado reciente"),
                _catalog_field(
                    "fieldType",
                    "Tipo de campo",
                    "select",
                    required=True,
                    options=[
                        _catalog_option(choice_value, choice_label)
                        for choice_value, choice_label in FichaCampo.TipoCampo.choices
                    ],
                ),
                _catalog_field(
                    "optionGroupId",
                    "Grupo de opciones",
                    "select",
                    value_type="number",
                    allow_empty=True,
                    options=[
                        _catalog_option(grupo.pk, grupo.nombre, secondary_label=grupo.codigo)
                        for grupo in GrupoOpciones.objects.order_by("nombre")
                    ],
                    hint="Solo aplica a campos de seleccion.",
                ),
                _catalog_field("order", "Orden", "number", value_type="number", min_value=0),
                _catalog_field("isMultiple", "Permite multiples respuestas", "checkbox", value_type="boolean"),
                _catalog_field("allowsDetail", "Permite detalle adicional", "checkbox", value_type="boolean"),
                _catalog_field("required", "Campo obligatorio", "checkbox", value_type="boolean"),
            ],
            "items": items,
        }

    if catalog_key == "patologias-cutaneas":
        queryset = PatologiaCutanea.objects.order_by("orden", "nombre")
        items = [
            _catalog_entry(
                item.pk,
                item.nombre,
                "Catalogo clinico",
                item.activo,
                [
                    {"label": "Orden", "value": str(item.orden)},
                    {"label": "Descripcion", "value": item.descripcion or "Sin descripcion"},
                ],
                {
                    "name": item.nombre,
                    "description": item.descripcion,
                    "order": item.orden,
                },
            )
            for item in queryset
        ]
        active_count = queryset.filter(activo=True).count()
        total_count = queryset.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Patologias cutaneas",
                "description": "Administra las patologias disponibles para el analisis estetico y sus reportes.",
                "createLabel": "Crear patologia cutanea",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                "Utilizadas en analisis esteticos historicos",
            ),
            "fields": [
                _catalog_field("name", "Patologia cutanea", "text", required=True, placeholder="Ej. Rosacea"),
                _catalog_field("description", "Descripcion", "textarea", placeholder="Notas internas o alcance"),
                _catalog_field("order", "Orden", "number", value_type="number", min_value=0),
            ],
            "items": items,
        }

    if catalog_key == "especialidades":
        queryset = Especialidad.objects.order_by("orden", "nombre")
        items = [
            _catalog_entry(
                item.pk,
                item.nombre,
                "Especialidad del equipo",
                item.activo,
                [
                    {"label": "Orden", "value": str(item.orden)},
                    {"label": "Descripcion", "value": item.descripcion or "Sin descripcion"},
                    {
                        "label": "Especialistas vinculados",
                        "value": str(item.especialistas_rel.count()),
                    },
                ],
                {
                    "name": item.nombre,
                    "description": item.descripcion,
                    "order": item.orden,
                },
            )
            for item in queryset
        ]
        active_count = queryset.filter(activo=True).count()
        total_count = queryset.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Especialidades",
                "description": "Administra las especialidades disponibles para asignar al equipo medico y tecnico.",
                "createLabel": "Crear especialidad",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{Especialista.objects.count()} especialista(s) registrados",
            ),
            "fields": [
                _catalog_field("name", "Especialidad", "text", required=True, placeholder="Ej. Laser terapeutico"),
                _catalog_field("description", "Descripcion", "textarea", placeholder="Notas internas sobre la especialidad"),
                _catalog_field("order", "Orden", "number", value_type="number", min_value=0),
            ],
            "items": items,
        }

    if catalog_key == "grupos-opciones":
        queryset = GrupoOpciones.objects.prefetch_related("opciones").order_by("nombre")
        items = [
            _catalog_entry(
                item.pk,
                item.nombre,
                item.codigo,
                item.activo,
                [
                    {"label": "Descripcion", "value": item.descripcion or "Sin descripcion"},
                    {"label": "Opciones activas", "value": str(item.opciones.filter(activo=True).count())},
                    {"label": "Opciones totales", "value": str(item.opciones.count())},
                ],
                {
                    "code": item.codigo,
                    "name": item.nombre,
                    "description": item.descripcion,
                },
            )
            for item in queryset
        ]
        active_count = queryset.filter(activo=True).count()
        total_count = queryset.count()
        return {
            "catalog": {
                "key": catalog_key,
                "title": "Grupos de opciones",
                "description": "Agrupa respuestas reutilizables para campos de ficha y otros formularios dinamicos.",
                "createLabel": "Crear grupo de opciones",
            },
            "metrics": _catalog_metric_set(
                active_count,
                total_count - active_count,
                total_count,
                f"{OpcionCatalogo.objects.filter(activo=True).count()} opcion(es) activas asociadas",
            ),
            "fields": [
                _catalog_field("code", "Codigo", "text", required=True, placeholder="Ej. SI_NO"),
                _catalog_field("name", "Nombre", "text", required=True, placeholder="Ej. Si / No"),
                _catalog_field("description", "Descripcion", "textarea", placeholder="Describe el uso del grupo"),
            ],
            "items": items,
        }

    raise KeyError(catalog_key)


def _catalog_parse_payload(catalog_key, payload, instance=None):
    catalog_key = _catalog_key_to_slug(catalog_key)
    errors = {}

    def text_value(field_name):
        return (payload.get(field_name) or "").strip()

    def int_value(field_name, *, required=False, minimum=0, allow_empty=False):
        raw = payload.get(field_name)
        if raw in (None, ""):
            if required and not allow_empty:
                errors[field_name] = "Este campo es obligatorio."
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            errors[field_name] = "Debes enviar un numero valido."
            return None
        if value < minimum:
            errors[field_name] = f"El valor minimo permitido es {minimum}."
            return None
        return value

    def decimal_value(field_name, *, required=False, minimum=Decimal("0")):
        raw = payload.get(field_name)
        if raw in (None, ""):
            if required:
                errors[field_name] = "Este campo es obligatorio."
            return None
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError):
            errors[field_name] = "Debes enviar un monto valido."
            return None
        if value < minimum:
            errors[field_name] = f"El valor minimo permitido es {minimum}."
            return None
        return value

    def bool_value(field_name):
        return bool(payload.get(field_name))

    if catalog_key == "todos-los-servicios":
        service_type_id = int_value("serviceTypeId", required=True, minimum=1)
        procedure_id = int_value("procedureId", minimum=1, allow_empty=True)
        base_price = decimal_value("basePrice", required=True)
        if errors:
            raise ValidationError(errors)

        service_type = TipoServicio.objects.filter(pk=service_type_id).first()
        if not service_type:
            raise ValidationError({"serviceTypeId": "Selecciona un tipo de servicio valido."})

        procedure = None
        if procedure_id:
            procedure = ProcEstetico.objects.filter(pk=procedure_id).first()
            if not procedure:
                raise ValidationError({"procedureId": "Selecciona un procedimiento valido."})

        obj = instance or ServicioConfig()
        obj.tipo_servicio = service_type
        obj.proc_estetico = procedure
        obj.precio_base = base_price
        return obj

    if catalog_key == "procedimientos-esteticos":
        procedure_type_id = int_value("procedureTypeId", required=True, minimum=1)
        name = text_value("name")
        if not name:
            errors["name"] = "El nombre del procedimiento es obligatorio."
        order = int_value("order", minimum=0, allow_empty=True)
        if errors:
            raise ValidationError(errors)
        procedure_type = ProcEsteticosTipo.objects.filter(pk=procedure_type_id).first()
        if not procedure_type:
            raise ValidationError({"procedureTypeId": "Selecciona un tipo de procedimiento valido."})
        obj = instance or ProcEstetico()
        obj.tipo_p_estetico = procedure_type
        obj.proceso = name
        obj.descripcion = text_value("description")
        obj.orden = order or 0
        return obj

    if catalog_key == "tipos-servicio":
        name = text_value("name")
        if not name:
            errors["name"] = "El nombre del tipo de servicio es obligatorio."
        order = int_value("order", minimum=0, allow_empty=True)
        if errors:
            raise ValidationError(errors)
        obj = instance or TipoServicio()
        obj.tipo = name
        obj.descripcion = text_value("description")
        obj.orden = order or 0
        return obj

    if catalog_key == "campos-ficha":
        section_id = int_value("sectionId", required=True, minimum=1)
        code = text_value("code")
        label = text_value("label")
        field_type = text_value("fieldType")
        option_group_id = int_value("optionGroupId", minimum=1, allow_empty=True)
        order = int_value("order", minimum=0, allow_empty=True)

        if not code:
            errors["code"] = "El codigo interno es obligatorio."
        if not label:
            errors["label"] = "La etiqueta visible es obligatoria."
        if field_type not in {choice for choice, _ in FichaCampo.TipoCampo.choices}:
            errors["fieldType"] = "Selecciona un tipo de campo valido."
        if errors:
            raise ValidationError(errors)

        section = FichaSeccion.objects.filter(pk=section_id).first()
        if not section:
            raise ValidationError({"sectionId": "Selecciona una seccion valida."})

        option_group = None
        if option_group_id:
            option_group = GrupoOpciones.objects.filter(pk=option_group_id).first()
            if not option_group:
                raise ValidationError({"optionGroupId": "Selecciona un grupo de opciones valido."})

        obj = instance or FichaCampo()
        obj.seccion = section
        obj.codigo = code
        obj.etiqueta = label
        obj.tipo_campo = field_type
        obj.grupo_opciones = option_group
        obj.es_multiple = bool_value("isMultiple")
        obj.permite_detalle = bool_value("allowsDetail")
        obj.requerido = bool_value("required")
        obj.orden = order or 0
        return obj

    if catalog_key == "patologias-cutaneas":
        name = text_value("name")
        if not name:
            errors["name"] = "El nombre de la patologia es obligatorio."
        order = int_value("order", minimum=0, allow_empty=True)
        if errors:
            raise ValidationError(errors)
        obj = instance or PatologiaCutanea()
        obj.nombre = name
        obj.descripcion = text_value("description")
        obj.orden = order or 0
        return obj

    if catalog_key == "especialidades":
        name = text_value("name")
        if not name:
            errors["name"] = "El nombre de la especialidad es obligatorio."
        order = int_value("order", minimum=0, allow_empty=True)
        if errors:
            raise ValidationError(errors)
        obj = instance or Especialidad()
        obj.nombre = name
        obj.descripcion = text_value("description")
        obj.orden = order or 0
        return obj

    if catalog_key == "grupos-opciones":
        code = text_value("code")
        name = text_value("name")
        if not code:
            errors["code"] = "El codigo es obligatorio."
        if not name:
            errors["name"] = "El nombre es obligatorio."
        if errors:
            raise ValidationError(errors)
        obj = instance or GrupoOpciones()
        obj.codigo = code
        obj.nombre = name
        obj.descripcion = text_value("description")
        return obj

    raise KeyError(catalog_key)


def _catalog_get_instance(catalog_key, item_id):
    catalog_key = _catalog_key_to_slug(catalog_key)
    model_map = {
        "todos-los-servicios": ServicioConfig,
        "procedimientos-esteticos": ProcEstetico,
        "tipos-servicio": TipoServicio,
        "campos-ficha": FichaCampo,
        "patologias-cutaneas": PatologiaCutanea,
        "especialidades": Especialidad,
        "grupos-opciones": GrupoOpciones,
    }
    return model_map[catalog_key].objects.filter(pk=item_id).first()


def _staff_item(especialista):
    citas = list(especialista.citas_medicas.all())
    now = timezone.now()
    upcoming = [cita for cita in citas if cita.fecha_hora >= now]
    pending_biometric = sum(
        1
        for cita in citas
        if cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA
    )
    active_operations = {
        cita.operacion_id
        for cita in citas
        if cita.operacion.estado == Operacion.Estado.EN_PROCESO
    }
    load = min(100, len(active_operations) * 25 + len(upcoming[:7]) * 15)
    specialties = [rel.especialidad.nombre for rel in especialista.especialidades_rel.all()]

    return {
        "id": f"STF-{especialista.pk:04d}",
        "rawId": especialista.pk,
        "specialist": _full_name(especialista.usuario),
        "specialty": ", ".join(specialties) if specialties else "Sin especialidad",
        "specialtyIds": [rel.especialidad_id for rel in especialista.especialidades_rel.all()],
        "load": load,
        "pendingValidations": pending_biometric,
        "username": especialista.usuario.username,
        "email": especialista.usuario.email or "",
        "primerNombre": especialista.usuario.primer_nombre,
        "segundoNombre": especialista.usuario.segundo_nombre,
        "apellidoPaterno": especialista.usuario.apellido_paterno,
        "apellidoMaterno": especialista.usuario.apellido_materno,
        "ci": especialista.ci or "",
        "phone": especialista.telefono or "",
        "status": "Activo" if especialista.usuario.is_active else "Inactivo",
        "isActive": bool(especialista.usuario.is_active),
        "activeOperations": len(active_operations),
        "upcomingAppointments": len(upcoming),
        "observations": especialista.observaciones or "",
    }


def _metric(identifier, label, value, delta, tone):
    return {
        "id": identifier,
        "label": label,
        "value": str(value),
        "delta": delta,
        "tone": tone,
    }


def _staff_specialty_option(item):
    return {
        "id": item.pk,
        "label": item.nombre,
    }


def _get_worker_role():
    role, _ = Rol.objects.get_or_create(rol="TRABAJADOR")
    return role


def _clear_specialist_availability(especialista):
    DisponibilidadCita.objects.filter(especialista=especialista).delete()
    AgendaHabitualEspecialista.objects.filter(especialista=especialista).delete()
    AgendaExcepcionEspecialista.objects.filter(especialista=especialista).delete()


def _parse_staff_payload(payload, errors, *, instance=None):
    username = (payload.get("username") or "").strip()
    email = (payload.get("email") or "").strip()
    primer_nombre = (payload.get("primerNombre") or "").strip()
    segundo_nombre = (payload.get("segundoNombre") or "").strip()
    apellido_paterno = (payload.get("apellidoPaterno") or "").strip()
    apellido_materno = (payload.get("apellidoMaterno") or "").strip()
    ci = (payload.get("ci") or "").strip()
    telefono = (payload.get("telefono") or "").strip()
    observaciones = (payload.get("observaciones") or "").strip()
    password = payload.get("password") or ""
    specialty_ids = payload.get("specialtyIds") or []

    if not username:
        errors["username"] = "El nombre de usuario es obligatorio."
    if not primer_nombre:
        errors["primerNombre"] = "El primer nombre es obligatorio."
    if not apellido_paterno:
        errors["apellidoPaterno"] = "El apellido paterno es obligatorio."
    if not specialty_ids:
        errors["specialtyIds"] = "Debes seleccionar al menos una especialidad."
    if instance is None and not password:
        errors["password"] = "La contraseña inicial es obligatoria."

    specialties = list(Especialidad.objects.filter(pk__in=specialty_ids, activo=True))
    if len(specialties) != len(set(specialty_ids)):
        errors["specialtyIds"] = "Alguna de las especialidades ya no está disponible."

    if errors:
        return None

    usuario = instance.usuario if instance else Usuario()
    usuario.username = username
    usuario.email = email
    usuario.primer_nombre = primer_nombre
    usuario.segundo_nombre = segundo_nombre
    usuario.apellido_paterno = apellido_paterno
    usuario.apellido_materno = apellido_materno
    usuario.rol = _get_worker_role()
    if instance is None:
        usuario.is_active = True
    if password:
        usuario.set_password(password)

    especialista = instance or Especialista(usuario=usuario)
    especialista.ci = ci
    especialista.telefono = telefono
    especialista.observaciones = observaciones

    return {
        "usuario": usuario,
        "especialista": especialista,
        "specialties": specialties,
    }


def _dashboard_alerts():
    now = timezone.now()
    overdue_pending = PagoRealizado.objects.filter(
        estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
        created_at__lt=now - timedelta(hours=24),
    ).count()
    operations_without_capacity = sum(
        1
        for operacion in Operacion.objects.filter(estado=Operacion.Estado.EN_PROCESO)
        if operacion.sesiones_disponibles == 0
    )
    procedures_without_sections = ProcEstetico.objects.filter(activo=True, secciones_ficha__isnull=True).count()

    alerts = []
    if overdue_pending:
        alerts.append(
            {
                "id": "alert-payments",
                "title": "Pagos pendientes por mas de 24 horas",
                "description": f"Hay {overdue_pending} comprobante(s) que aun no fueron revisados.",
                "severity": "high",
                "action": "Revisar cola de pagos",
            }
        )
    else:
        alerts.append(
            {
                "id": "alert-payments-ok",
                "title": "Cola de pagos controlada",
                "description": "No hay comprobantes vencidos esperando revision administrativa.",
                "severity": "low",
                "action": "Ver pagos recientes",
            }
        )

    if operations_without_capacity:
        alerts.append(
            {
                "id": "alert-capacity",
                "title": "Operaciones sin sesiones disponibles",
                "description": (
                    f"{operations_without_capacity} operacion(es) activas ya no admiten nuevas reservas."
                ),
                "severity": "medium",
                "action": "Revisar operaciones",
            }
        )
    else:
        alerts.append(
            {
                "id": "alert-capacity-ok",
                "title": "Reservas con capacidad disponible",
                "description": "Las operaciones activas aun tienen sesiones para agendar sin bloqueo.",
                "severity": "low",
                "action": "Monitorear agenda",
            }
        )

    if procedures_without_sections:
        alerts.append(
            {
                "id": "alert-catalogs",
                "title": "Procedimientos sin ficha configurada",
                "description": (
                    f"Hay {procedures_without_sections} procedimiento(s) activos sin secciones de ficha clinica."
                ),
                "severity": "medium",
                "action": "Completar catalogos",
            }
        )

    return alerts


@require_GET
@_admin_required
def admin_dashboard(request):
    today = timezone.localdate()
    pending_payments_qs = (
        PagoRealizado.objects.select_related(
            "cuota__operacion__paciente__usuario",
            "cuota__operacion__servicio_config__proc_estetico",
        )
        .order_by("-created_at")
    )
    agenda_qs = (
        CitaMedica.objects.select_related(
            "operacion__paciente__usuario",
            "operacion__servicio_config__proc_estetico",
            "medico__usuario",
        )
        .filter(fecha_hora__date__gte=today)
        .order_by("fecha_hora")
    )
    if not agenda_qs.exists():
        agenda_qs = (
            CitaMedica.objects.select_related(
                "operacion__paciente__usuario",
                "operacion__servicio_config__proc_estetico",
                "medico__usuario",
            )
            .order_by("-fecha_hora")
        )

    operations_qs = (
        Operacion.objects.select_related(
            "paciente__usuario",
            "servicio_config__tipo_servicio",
            "servicio_config__proc_estetico",
        )
        .prefetch_related(
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.select_related("medico__usuario").order_by("fecha_hora"),
            ),
            Prefetch(
                "cuotas_plan_pagos",
                queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
            ),
        )
        .filter(estado=Operacion.Estado.EN_PROCESO)
        .order_by("-created_at")
    )
    prospectos_qs = Prospecto.objects.select_related("registrado_por").order_by("-created_at")
    staff_qs = (
        Especialista.objects.select_related("usuario")
        .prefetch_related(
            "especialidades_rel__especialidad",
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.select_related("operacion").order_by("fecha_hora"),
            ),
        )
        .order_by("usuario__primer_nombre", "usuario__apellido_paterno")
    )

    pending_payments = pending_payments_qs.filter(
        estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE
    )
    payments_today = pending_payments.filter(created_at__date=today).count()
    operations_started_this_month = Operacion.objects.filter(
        created_at__year=today.year,
        created_at__month=today.month,
    ).count()
    converted_prospects = Prospecto.objects.filter(estado=Prospecto.Estado.CONVERTIDO).count()
    total_prospects = Prospecto.objects.count()
    prospect_delta = (
        f"{round((converted_prospects / total_prospects) * 100)}% convertidos"
        if total_prospects
        else "Sin conversiones aun"
    )
    appointments_today = CitaMedica.objects.filter(fecha_hora__date=today).count()
    pending_biometric = CitaMedica.objects.filter(
        estado=CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA
    ).count()

    data = {
        "metrics": [
            _metric(
                "payments",
                "Pagos por verificar",
                pending_payments.count(),
                f"{payments_today} subidos hoy",
                "warning",
            ),
            _metric(
                "operations",
                "Tratamientos activos",
                operations_qs.count(),
                f"{operations_started_this_month} iniciadas este mes",
                "primary",
            ),
            _metric(
                "prospects",
                "Prospectos en seguimiento",
                prospectos_qs.filter(estado=Prospecto.Estado.PASAJERO).count(),
                prospect_delta,
                "success",
            ),
            _metric(
                "appointments",
                "Citas del dia",
                appointments_today,
                f"{pending_biometric} pendientes de biometria",
                "danger" if pending_biometric else "success",
            ),
        ],
        "payments": [_payment_item(payment) for payment in pending_payments_qs[:5]],
        "agenda": [
            {
                "id": f"CIT-{cita.pk:04d}",
                "time": timezone.localtime(cita.fecha_hora).strftime("%H:%M"),
                "patient": _full_name(cita.operacion.paciente.usuario),
                "procedure": _procedure_name(cita.operacion),
                "specialist": _full_name(cita.medico.usuario),
                "status": _agenda_status(cita),
            }
            for cita in agenda_qs[:4]
        ],
        "prospects": [_prospect_item(prospecto) for prospecto in prospectos_qs[:4]],
        "alerts": _dashboard_alerts(),
        "operations": [_operation_card(operacion) for operacion in operations_qs[:4]],
        "catalogHealth": [
            _catalog_item(
                "procedures",
                "Procedimientos esteticos",
                ProcEstetico.objects.filter(activo=True).count(),
                f"{ServicioConfig.objects.filter(activo=True).count()} servicio(s) activos configurados",
            ),
            _catalog_item(
                "fields",
                "Campos clinicos",
                FichaCampo.objects.filter(activo=True).count(),
                f"{GrupoOpciones.objects.filter(activo=True).count()} grupo(s) de opciones disponibles",
            ),
            _catalog_item(
                "specialties",
                "Especialidades",
                Especialidad.objects.filter(activo=True).count(),
                f"{staff_qs.count()} especialista(s) con carga operativa",
            ),
            _catalog_item(
                "skin",
                "Patologias cutaneas",
                PatologiaCutanea.objects.filter(activo=True).count(),
                f"{OpcionCatalogo.objects.filter(activo=True).count()} opciones catalogadas en total",
            ),
        ],
        "staffCapacity": [_staff_item(especialista) for especialista in staff_qs[:4]],
    }
    return _json(data)


@require_GET
@_admin_required
def admin_prospectos(request):
    prospectos_qs = Prospecto.objects.select_related("registrado_por").order_by("-created_at")
    clientes_qs = (
        Cliente.objects.select_related("usuario")
        .prefetch_related("operaciones", "analisis_esteticos")
        .order_by("usuario__primer_nombre", "usuario__apellido_paterno")
    )

    data = {
        "metrics": [
            _metric(
                "prospects-open",
                "Prospectos abiertos",
                prospectos_qs.filter(estado=Prospecto.Estado.PASAJERO).count(),
                "Registrados internamente por el equipo",
                "primary",
            ),
            _metric(
                "prospects-converted",
                "Prospectos convertidos",
                prospectos_qs.filter(estado=Prospecto.Estado.CONVERTIDO).count(),
                "Ya cuentan con tratamiento activo o historico",
                "success",
            ),
            _metric(
                "clients-active",
                "Clientes activos",
                clientes_qs.filter(estado_cliente=Cliente.Estado.ACTIVO).count(),
                "Con al menos una operacion vigente",
                "warning",
            ),
            _metric(
                "clients-inactive",
                "Clientes inactivos",
                clientes_qs.filter(estado_cliente=Cliente.Estado.INACTIVO).count(),
                "Con historial disponible en portal",
                "danger",
            ),
        ],
        "prospects": [_prospect_item(prospecto) for prospecto in prospectos_qs],
        "clients": [_client_item(cliente) for cliente in clientes_qs],
    }
    return _json(data)


@require_POST
@_admin_required
def admin_crear_prospecto(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    nombres = (payload.get("nombres") or "").strip()
    apellidos = (payload.get("apellidos") or "").strip()
    telefono = (payload.get("telefono") or "").strip()
    observaciones = (payload.get("observaciones") or "").strip()
    estado = (payload.get("estado") or Prospecto.Estado.PASAJERO).strip()

    errors = {}
    if not nombres:
        errors["nombres"] = "Los nombres son obligatorios."
    if not apellidos:
        errors["apellidos"] = "Los apellidos son obligatorios."
    if estado not in {Prospecto.Estado.PASAJERO, Prospecto.Estado.DESCARTADO}:
        errors["estado"] = "Solo puedes crear prospectos en estado pasajero o descartado."

    if errors:
        return _json({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)

    prospecto = Prospecto.objects.create(
        nombres=nombres,
        apellidos=apellidos,
        telefono=telefono,
        estado=estado,
        observaciones=observaciones,
        registrado_por=request.user,
    )

    return _json(
        {
            "detail": "Prospecto registrado correctamente.",
            "prospect": _prospect_item(prospecto),
        },
        status=201,
    )


@require_GET
@_admin_required
def admin_operaciones(request):
    operaciones_qs = (
        Operacion.objects.select_related(
            "paciente__usuario",
            "servicio_config__tipo_servicio",
            "servicio_config__proc_estetico",
        )
        .prefetch_related(
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.select_related("medico__usuario").order_by("fecha_hora"),
            ),
            Prefetch(
                "cuotas_plan_pagos",
                queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
            ),
        )
        .order_by("-created_at")
    )
    blocked_reservations = sum(
        1
        for operacion in operaciones_qs
        if operacion.estado == Operacion.Estado.EN_PROCESO and not operacion.puede_reservar
    )

    data = {
        "metrics": [
            _metric(
                "operations-active",
                "Operaciones en proceso",
                operaciones_qs.filter(estado=Operacion.Estado.EN_PROCESO).count(),
                "Tratamientos actualmente vigentes",
                "primary",
            ),
            _metric(
                "operations-draft",
                "Operaciones en borrador",
                operaciones_qs.filter(estado=Operacion.Estado.BORRADOR).count(),
                "Pendientes de activacion o venta",
                "warning",
            ),
            _metric(
                "operations-finished",
                "Operaciones finalizadas",
                operaciones_qs.filter(estado=Operacion.Estado.FINALIZADA).count(),
                "Historial clinico consolidado",
                "success",
            ),
            _metric(
                "operations-blocked",
                "Reservas bloqueadas",
                blocked_reservations,
                "Sin sesiones libres para reservar",
                "danger",
            ),
        ],
        "operations": [_operation_card(operacion) for operacion in operaciones_qs],
    }
    return _json(data)


@require_GET
@_admin_required
def admin_operacion_detalle(request, operacion_id):
    operacion = (
        Operacion.objects.select_related(
            "paciente__usuario",
            "servicio_config__tipo_servicio",
            "servicio_config__proc_estetico__tipo_p_estetico",
            "ficha_clinica",
        )
        .prefetch_related(
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.select_related("medico__usuario").order_by("fecha_hora"),
            ),
            Prefetch(
                "cuotas_plan_pagos",
                queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
            ),
        )
        .filter(pk=operacion_id)
        .first()
    )

    if not operacion:
        return _json({"detail": "No encontramos la operacion solicitada."}, status=404)

    return _json({"operation": _operation_detail(operacion)})


@require_GET
@_admin_required
def admin_pagos(request):
    pagos_qs = (
        PagoRealizado.objects.select_related(
            "cuota__operacion__paciente__usuario",
            "cuota__operacion__servicio_config__proc_estetico",
            "verificado_por",
        )
        .order_by("-created_at")
    )
    pending_amount = sum(
        payment.monto_pagado
        for payment in pagos_qs
        if payment.estado_verificacion == PagoRealizado.EstadoVerificacion.PENDIENTE
    )

    data = {
        "metrics": [
            _metric(
                "payments-pending",
                "Pendientes de revision",
                pagos_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE).count(),
                _currency(pending_amount),
                "warning",
            ),
            _metric(
                "payments-approved",
                "Pagos aprobados",
                pagos_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO).count(),
                "Impactan el estado de cuotas",
                "success",
            ),
            _metric(
                "payments-observed",
                "Pagos observados",
                pagos_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.RECHAZADO).count(),
                "Requieren seguimiento administrativo",
                "danger",
            ),
            _metric(
                "payments-total",
                "Pagos registrados",
                pagos_qs.count(),
                "Incluye historico completo del sistema",
                "primary",
            ),
        ],
        "paymentQrConfig": _payment_qr_config_item(ConfiguracionPagoQR.objects.order_by("-updated_at").first()),
        "payments": [_payment_item(payment) for payment in pagos_qs],
    }
    return _json(data)


@require_POST
@_admin_required
def admin_update_payment_qr_config(request):
    qr_file = request.FILES.get("qrImage")
    instructions = (request.POST.get("instructions") or "").strip()

    config = ConfiguracionPagoQR.objects.order_by("-updated_at").first()
    if not config:
        config = ConfiguracionPagoQR()

    if qr_file:
        config.imagen_qr = qr_file
    elif not config.imagen_qr:
        return _json({"detail": "Debes adjuntar una imagen QR para guardar la configuracion."}, status=400)

    if instructions:
        config.instrucciones = instructions

    config.full_clean()
    config.save()

    return _json(
        {
            "detail": "El QR de pago fue actualizado correctamente.",
            "paymentQrConfig": _payment_qr_config_item(config),
        }
    )


@require_POST
@_admin_required
def admin_update_payment_status(request, payment_id):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    payment = (
        PagoRealizado.objects.select_related(
            "cuota__operacion__paciente__usuario",
            "cuota__operacion__servicio_config__proc_estetico",
            "verificado_por",
        )
        .filter(pk=payment_id)
        .first()
    )
    if not payment:
        return _json({"detail": "No encontramos el pago solicitado."}, status=404)

    status_value = (payload.get("status") or "").strip().upper()
    note = (payload.get("note") or "").strip()
    valid_statuses = {
        PagoRealizado.EstadoVerificacion.PENDIENTE,
        PagoRealizado.EstadoVerificacion.APROBADO,
        PagoRealizado.EstadoVerificacion.RECHAZADO,
    }
    if status_value not in valid_statuses:
        return _json({"detail": "El estado solicitado no es valido."}, status=400)

    payment.estado_verificacion = status_value
    if status_value == PagoRealizado.EstadoVerificacion.PENDIENTE:
        payment.observacion_verificacion = ""
    else:
        payment.verificado_por = request.user
        payment.fecha_verificacion = timezone.now()
        payment.observacion_verificacion = note

    payment.save()
    payment = (
        PagoRealizado.objects.select_related(
            "cuota__operacion__paciente__usuario",
            "cuota__operacion__servicio_config__proc_estetico",
            "verificado_por",
        )
        .get(pk=payment.pk)
    )

    detail_map = {
        PagoRealizado.EstadoVerificacion.PENDIENTE: "El pago volvio a estado pendiente.",
        PagoRealizado.EstadoVerificacion.APROBADO: "El pago fue aprobado correctamente.",
        PagoRealizado.EstadoVerificacion.RECHAZADO: "El pago fue observado correctamente.",
    }

    return _json(
        {
            "detail": detail_map[status_value],
            "payment": _payment_item(payment),
        }
    )


@require_GET
@_admin_required
def admin_catalogos(request):
    active_services = ServicioConfig.objects.filter(activo=True).count()
    active_service_types = TipoServicio.objects.filter(activo=True).count()
    active_groups = GrupoOpciones.objects.filter(activo=True).count()
    active_options = OpcionCatalogo.objects.filter(activo=True).count()

    data = {
        "catalogs": [
            _catalog_item(
                "todos-los-servicios",
                "Todos los servicios",
                ServicioConfig.objects.filter(activo=True).count(),
                "Servicios completos con precio base y procedimiento asociado",
            ),
            _catalog_item(
                "procedimientos-esteticos",
                "Procedimientos esteticos",
                ProcEstetico.objects.filter(activo=True).count(),
                f"{ServicioConfig.objects.filter(activo=True).count()} configuraciones activas de servicio",
            ),
            _catalog_item(
                "tipos-servicio",
                "Tipos de servicio",
                active_service_types,
                "Categorias comerciales visibles en operaciones y ventas",
            ),
            _catalog_item(
                "campos-ficha",
                "Campos de ficha",
                FichaCampo.objects.filter(activo=True).count(),
                f"{FichaCampo.objects.filter(activo=False).count()} campo(s) inactivos preservados",
            ),
            _catalog_item(
                "grupos-opciones",
                "Grupos de opciones",
                active_groups,
                f"{active_options} opcion(es) activas asociadas",
            ),
            _catalog_item(
                "patologias-cutaneas",
                "Patologias cutaneas",
                PatologiaCutanea.objects.filter(activo=True).count(),
                "Disponibles para analisis estetico y reportes",
            ),
            _catalog_item(
                "especialidades",
                "Especialidades",
                Especialidad.objects.filter(activo=True).count(),
                "Catalogo usado para especialistas y asignaciones del equipo",
            ),
        ],
    }
    return _json(data)


@require_GET
@_admin_required
def admin_catalogo_detalle(request, catalog_key):
    try:
        data = _catalog_page_data(catalog_key)
    except KeyError:
        return _json({"detail": "El catalogo solicitado no existe."}, status=404)
    return _json(data)


@require_POST
@_admin_required
def admin_catalogo_crear(request, catalog_key):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    try:
        obj = _catalog_parse_payload(catalog_key, payload)
        obj.full_clean()
        obj.save()
    except KeyError:
        return _json({"detail": "El catalogo solicitado no existe."}, status=404)
    except ValidationError as exc:
        return _json({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)
    except IntegrityError:
        return _json({"detail": "Ya existe un registro con esos datos clave."}, status=400)

    return _json(
        {
            "detail": "Registro creado correctamente.",
            "item": next(item for item in _catalog_page_data(catalog_key)["items"] if item["id"] == obj.pk),
        },
        status=201,
    )


@require_POST
@_admin_required
def admin_catalogo_actualizar(request, catalog_key, item_id):
    instance = _catalog_get_instance(catalog_key, item_id)
    if not instance:
        return _json({"detail": "No encontramos el registro solicitado."}, status=404)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    try:
        obj = _catalog_parse_payload(catalog_key, payload, instance=instance)
        obj.full_clean()
        obj.save()
    except KeyError:
        return _json({"detail": "El catalogo solicitado no existe."}, status=404)
    except ValidationError as exc:
        return _json({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)
    except IntegrityError:
        return _json({"detail": "Ya existe un registro con esos datos clave."}, status=400)

    return _json(
        {
            "detail": "Registro actualizado correctamente.",
            "item": next(item for item in _catalog_page_data(catalog_key)["items"] if item["id"] == obj.pk),
        }
    )


@require_POST
@_admin_required
def admin_catalogo_estado(request, catalog_key, item_id):
    instance = _catalog_get_instance(catalog_key, item_id)
    if not instance:
        return _json({"detail": "No encontramos el registro solicitado."}, status=404)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    active = payload.get("active")
    if not isinstance(active, bool):
        return _json({"detail": "Debes indicar si el registro queda activo o inactivo."}, status=400)

    instance.activo = active
    instance.save(update_fields=["activo", "updated_at"])

    return _json(
        {
            "detail": "Estado actualizado correctamente.",
            "item": next(item for item in _catalog_page_data(catalog_key)["items"] if item["id"] == instance.pk),
        }
    )


@require_GET
@_admin_required
def admin_equipo(request):
    staff_qs = (
        Especialista.objects.select_related("usuario")
        .prefetch_related(
            "especialidades_rel__especialidad",
            Prefetch(
                "citas_medicas",
                queryset=CitaMedica.objects.select_related("operacion").order_by("fecha_hora"),
            ),
        )
        .order_by("-usuario__is_active", "usuario__primer_nombre", "usuario__apellido_paterno")
    )
    upcoming_appointments = CitaMedica.objects.filter(fecha_hora__gte=timezone.now()).count()
    pending_biometric = CitaMedica.objects.filter(
        estado=CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA
    ).count()
    active_staff = staff_qs.filter(usuario__is_active=True).count()
    inactive_staff = staff_qs.filter(usuario__is_active=False).count()

    data = {
        "metrics": [
            _metric(
                "team-specialists",
                "Especialistas activos",
                active_staff,
                "Usuarios con perfil operativo asignado",
                "primary",
            ),
            _metric(
                "team-specialties",
                "Especialidades",
                Especialidad.objects.filter(activo=True).count(),
                "Catalogo editable desde administracion",
                "success",
            ),
            _metric(
                "team-agenda",
                "Citas futuras",
                upcoming_appointments,
                "Carga agendada a partir de hoy",
                "warning",
            ),
            _metric(
                "team-biometric",
                "Pendientes de biometria",
                pending_biometric,
                "Citas realizadas sin cierre final",
                "danger",
            ),
            _metric(
                "team-inactive",
                "Especialistas inactivos",
                inactive_staff,
                "Sin disponibilidad publicada",
                "warning",
            ),
        ],
        "staff": [_staff_item(especialista) for especialista in staff_qs],
        "specialtyOptions": [
            _staff_specialty_option(item)
            for item in Especialidad.objects.filter(activo=True).order_by("orden", "nombre")
        ],
    }
    return _json(data)


@require_POST
@_admin_required
@transaction.atomic
def admin_crear_especialista(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    errors = {}
    parsed = _parse_staff_payload(payload, errors)
    if errors:
        return _json({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)

    usuario = parsed["usuario"]
    especialista = parsed["especialista"]
    specialties = parsed["specialties"]

    try:
        usuario.full_clean()
        usuario.save()
        especialista.usuario = usuario
        especialista.full_clean()
        especialista.save()
    except ValidationError as exc:
        return _json({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)
    except IntegrityError:
        return _json({"detail": "Ya existe un especialista o usuario con esos datos."}, status=400)

    EspecialistaEspecialidad.objects.bulk_create(
        [
            EspecialistaEspecialidad(especialista=especialista, especialidad=especialidad)
            for especialidad in specialties
        ]
    )

    especialista = (
        Especialista.objects.select_related("usuario")
        .prefetch_related("especialidades_rel__especialidad", "citas_medicas")
        .get(pk=especialista.pk)
    )

    return _json(
        {
            "detail": "Especialista creado correctamente.",
            "staffMember": _staff_item(especialista),
        },
        status=201,
    )


@require_POST
@_admin_required
@transaction.atomic
def admin_actualizar_especialista(request, specialist_id):
    especialista = (
        Especialista.objects.select_related("usuario")
        .prefetch_related("especialidades_rel")
        .filter(pk=specialist_id)
        .first()
    )
    if not especialista:
        return _json({"detail": "No encontramos el especialista solicitado."}, status=404)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    errors = {}
    parsed = _parse_staff_payload(payload, errors, instance=especialista)
    if errors:
        return _json({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)

    usuario = parsed["usuario"]
    especialista = parsed["especialista"]
    specialties = parsed["specialties"]

    try:
        usuario.full_clean()
        usuario.save()
        especialista.full_clean()
        especialista.save()
    except ValidationError as exc:
        return _json({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)
    except IntegrityError:
        return _json({"detail": "Ya existe un especialista o usuario con esos datos."}, status=400)

    especialista.especialidades_rel.all().delete()
    EspecialistaEspecialidad.objects.bulk_create(
        [
            EspecialistaEspecialidad(especialista=especialista, especialidad=especialidad)
            for especialidad in specialties
        ]
    )

    especialista = (
        Especialista.objects.select_related("usuario")
        .prefetch_related("especialidades_rel__especialidad", "citas_medicas")
        .get(pk=especialista.pk)
    )

    return _json(
        {
            "detail": "Especialista actualizado correctamente.",
            "staffMember": _staff_item(especialista),
        }
    )


@require_POST
@_admin_required
@transaction.atomic
def admin_estado_especialista(request, specialist_id):
    especialista = Especialista.objects.select_related("usuario").filter(pk=specialist_id).first()
    if not especialista:
        return _json({"detail": "No encontramos el especialista solicitado."}, status=404)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    active = payload.get("active")
    if not isinstance(active, bool):
        return _json({"detail": "Debes indicar si el especialista quedará activo o inactivo."}, status=400)

    especialista.usuario.is_active = active
    especialista.usuario.save(update_fields=["is_active"])
    if not active:
        _clear_specialist_availability(especialista)

    especialista = (
        Especialista.objects.select_related("usuario")
        .prefetch_related("especialidades_rel__especialidad", "citas_medicas")
        .get(pk=especialista.pk)
    )

    return _json(
        {
            "detail": "Especialista activado correctamente."
            if active
            else "Especialista desactivado y disponibilidad eliminada correctamente.",
            "staffMember": _staff_item(especialista),
        }
    )
