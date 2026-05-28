"""
Item helper functions for serializing domain objects to dict responses.

Extracted from config/api_views.py to serve as canonical implementations
used across api_views, viewsets, and serializer modules.
"""

from pathlib import PurePosixPath

from django.db.models import Prefetch
from django.utils import timezone

from billing.models import CuotaPlanPago, PagoRealizado
from config.api_helpers import currency, date_label, datetime_label, full_name, procedure_name
from config.api.helpers_operations import quota_programmed_amount, quota_status


# ---------------------------------------------------------------------------
# Prospect helpers
# ---------------------------------------------------------------------------

def prospect_item(prospecto):
    """Return a dict representation of a prospect for API responses."""
    from operations.models import CitaProspecto

    active_appointment = next(
        (
            cita
            for cita in prospecto.citas_medicas.all()
            if cita.estado == CitaProspecto.Estado.PROGRAMADA
        ),
        None,
    )
    citas = prospecto.citas_medicas.order_by("-fecha_hora").all()

    from config.api_views import _prospect_interest, _prospect_stage

    return {
        "id": f"PRO-{prospecto.pk:04d}",
        "rawId": prospecto.pk,
        "name": str(prospecto),
        "firstName": prospecto.primer_nombre,
        "lastName": prospecto.apellido_paterno,
        "primerNombre": prospecto.primer_nombre,
        "segundoNombre": prospecto.segundo_nombre,
        "apellidoPaterno": prospecto.apellido_paterno,
        "apellidoMaterno": prospecto.apellido_materno,
        "phone": prospecto.telefono or "Sin telefono",
        "interest": _prospect_interest(prospecto),
        "registeredBy": full_name(prospecto.registrado_por),
        "stage": _prospect_stage(prospecto),
        "state": prospecto.get_estado_display(),
        "stateValue": prospecto.estado,
        "observations": prospecto.observaciones,
        "createdAt": datetime_label(prospecto.created_at),
        "convertedAt": datetime_label(prospecto.fecha_conversion) if prospecto.fecha_conversion else "-",
        "medicalAppointments": [prospect_appointment_item(c) for c in citas],
    }


def prospect_appointment_item(appointment):
    """Return a dict representation of a prospect appointment."""
    if not appointment:
        return None
    return {
        "id": f"CPR-{appointment.pk:04d}",
        "rawId": appointment.pk,
        "prospectRawId": appointment.prospecto_id,
        "dateTime": datetime_label(appointment.fecha_hora),
        "specialist": "Sin asignar",
        "service": appointment.servicio_config.tipo_servicio.tipo,
        "status": appointment.get_estado_display(),
        "statusValue": appointment.estado,
        "statusTone": (
            "approved" if appointment.estado == "PROGRAMADA"
            else "danger" if appointment.estado == "CANCELADA"
            else "observed"
        ),
        "canCancel": appointment.estado == "PROGRAMADA" and appointment.fecha_hora > timezone.now(),
    }


# ---------------------------------------------------------------------------
# Payment helpers
# ---------------------------------------------------------------------------

def payment_item(payment):
    """Return a dict representation of a payment for API responses."""
    from config.api_views import _payment_status

    operacion = payment.cuota.operacion
    return {
        "id": f"PAY-{payment.pk:04d}",
        "rawId": payment.pk,
        "patient": full_name(operacion.paciente.usuario),
        "operation": procedure_name(operacion),
        "amount": currency(payment.monto_pagado),
        "submittedAt": datetime_label(payment.created_at),
        "bank": "Transferencia",
        "status": _payment_status(payment),
        "quota": f"Cuota {payment.cuota.nro_cuota}",
        "dueDate": date_label(payment.cuota.fecha_vencimiento),
        "verifier": full_name(payment.verificado_por) if payment.verificado_por else "Sin revisar",
        "receiptUrl": payment.comprobante_url.url if payment.comprobante_url else "",
        "note": payment.observacion_verificacion or payment.detalles_pago or "",
    }


def quota_item(cuota):
    """Return a dict representation of a payment quota for admin API responses."""
    operacion = cuota.operacion
    return {
        "id": f"CUO-{cuota.pk:04d}",
        "rawId": cuota.pk,
        "patient": full_name(operacion.paciente.usuario),
        "operation": procedure_name(operacion),
        "quotaNumber": cuota.nro_cuota,
        "amount": currency(quota_programmed_amount(cuota)),
        "dueDate": date_label(cuota.fecha_vencimiento),
        "status": cuota.get_estado_display(),
        "paymentsCount": cuota.pagos_realizados.count(),
    }


# ---------------------------------------------------------------------------
# Expense helpers
# ---------------------------------------------------------------------------

def expense_item(expense):
    """Return a dict representation of an expense for API responses."""
    return {
        "id": f"GAS-{expense.pk:04d}",
        "rawId": expense.pk,
        "date": expense.fecha.isoformat(),
        "dateLabel": date_label(expense.fecha),
        "categoryId": expense.categoria_id,
        "category": expense.categoria.nombre,
        "concept": expense.concepto,
        "units": str(expense.unidades),
        "unitCost": str(expense.costo_unidad),
        "total": str(expense.gasto_total),
        "totalLabel": currency(expense.gasto_total),
        "provider": expense.proveedor,
        "invoiceUrl": expense.factura.url if expense.factura else "",
        "invoiceName": PurePosixPath(expense.factura.name).name if expense.factura else "",
        "details": expense.detalles,
        "branchId": expense.sucursal_id,
        "branchName": expense.sucursal.nombre,
        "registeredBy": full_name(expense.registrado_por) if expense.registrado_por else "Sin registrar",
    }
