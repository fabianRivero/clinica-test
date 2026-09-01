"""
Helpers for operation and appointment-related API responses.

Extracted from config/api_views.py and config/api/viewsets/ to eliminate
duplication. All functions here are importable from both locations via
aliases in their respective modules.
"""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Prefetch, Sum
from django.utils import timezone

from billing.models import CuotaPlanPago, PagoRealizado
from operations.models import CitaMedica, Operacion


# ---------------------------------------------------------------------------
# Operation helpers
# ---------------------------------------------------------------------------

def operation_reference_appointment(operacion):
    """Return the reference appointment for an operation.

    Returns the first upcoming appointment, or the most recent past
    appointment if no future ones exist. Returns None if the operation
    has no appointments.
    """
    citas = list(operacion.citas_medicas.all())
    if not citas:
        return None
    now = timezone.now()
    upcoming = [c for c in citas if c.fecha_hora >= now]
    return upcoming[0] if upcoming else citas[-1]


def operation_branch(operacion):
    """Return the branch name for an operation as a formatted string.

    Prioridad: primera cita reservada -> fallback a la sede de origen
    del cliente (Cliente.sucursal_origen, ya persistida por el wizard
    de conversion o por la alta inicial). Solo si ninguna de las dos
    existe devolvemos "Por asignar".
    """
    cita = operation_reference_appointment(operacion)
    if cita:
        return f"Sede: {cita.sucursal.nombre}"

    cliente = getattr(operacion, "paciente", None)
    sucursal_origen = getattr(cliente, "sucursal_origen", None) if cliente else None
    if sucursal_origen is not None:
        return f"Sede: {sucursal_origen.nombre}"
    return "Por asignar"


def operation_branch_id(operacion):
    """Return the branch ID for an operation, or None if no appointments.

    Misma prioridad que ``operation_branch``: primera cita reservada,
    si no, sede de origen del cliente. Devuelve ``None`` si ninguna
    esta disponible (caso borde historico).
    """
    cita = operation_reference_appointment(operacion)
    if cita:
        return cita.sucursal_id

    cliente = getattr(operacion, "paciente", None)
    sucursal_origen = getattr(cliente, "sucursal_origen", None) if cliente else None
    if sucursal_origen is not None:
        return sucursal_origen.pk
    return None


def operation_next_appointment(operacion):
    """Return the datetime label for the next appointment, or a placeholder."""
    from config.api_helpers import datetime_label

    cita = operation_reference_appointment(operacion)
    if not cita:
        return "Sin cita programada"
    return datetime_label(cita.fecha_hora)


def quota_status(operacion):
    """Return a detailed status string for an operation's payment plan.

    Returns one of: "Sin plan de pagos", "Pago observado",
    "N pago(s) pendientes", "N cuota(s) pendientes", "Cuotas al dia".
    """
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

    pending_quotas = sum(
        1
        for cuota in cuotas
        if cuota.estado not in {CuotaPlanPago.Estado.PAGADO, CuotaPlanPago.Estado.NO_PAGADA}
    )
    if pending_quotas:
        return f"{pending_quotas} cuota(s) pendientes"

    return "Cuotas al dia"


def quota_programmed_amount(cuota):
    """Return the programmed amount for a quota.

    Uses the explicit monto_programado if set, otherwise divides the
    operation total by the number of cuotas.
    """
    if cuota.monto_programado:
        return cuota.monto_programado
    operacion = cuota.operacion
    if operacion.cuotas_totales:
        return (operacion.precio_total / Decimal(operacion.cuotas_totales)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    return operacion.precio_total


def quota_display_status(cuota):
    """Return a human-readable display status for a quota."""
    from config.api_helpers import currency

    if cuota.estado == CuotaPlanPago.Estado.PAGADO:
        return cuota.get_estado_display()

    if cuota.operacion.estado == Operacion.Estado.CANCELADA:
        return "Cancelado"

    pagos = list(cuota.pagos_realizados.all())
    if any(pago.estado_verificacion == PagoRealizado.EstadoVerificacion.RECHAZADO for pago in pagos):
        return "Observado"
    if any(pago.estado_verificacion == PagoRealizado.EstadoVerificacion.CANCELADO for pago in pagos):
        return "Cancelado"
    if any(pago.estado_verificacion == PagoRealizado.EstadoVerificacion.PENDIENTE for pago in pagos):
        return "Pendiente"

    result = cuota.get_estado_display()
    return result


def quota_paid_amount(cuota):
    """Return the sum of approved payments for a quota as a Decimal.

    Used by the operation detail endpoint to surface how much was actually
    paid vs. the scheduled amount — important for mixed/partial payments
    where the cuota may be in PENDIENTE state even after an approved row.
    """
    approved = cuota.pagos_realizados.filter(
        estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO
    ).aggregate(s=Sum("monto_pagado"))["s"]
    return (approved or Decimal("0")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def operation_card(operacion):
    """Return a card-shaped dict representation of an operation."""
    from config.api_helpers import currency, full_name, procedure_name

    return {
        "id": f"OP-{operacion.pk:04d}",
        "rawId": operacion.pk,
        "clienteCodigo": operacion.paciente.cliente_codigo,
        "patient": full_name(operacion.paciente.usuario),
        "procedure": procedure_name(operacion),
        "branch": operation_branch(operacion),
        "branchId": operation_branch_id(operacion),
        "sessions": (
            f"{operacion.sesiones_totales} total | "
            f"{operacion.sesiones_confirmadas} confirmadas | "
            f"{operacion.reservas_activas} reservadas | "
            f"{operacion.sesiones_disponibles} libres"
        ),
        "nextAppointment": operation_next_appointment(operacion),
        "quotaStatus": quota_status(operacion),
        "status": operacion.get_estado_display(),
        "price": currency(operacion.precio_total),
    }


def prospect_appointment_operation_card(appointment):
    """Return a card-shaped dict for a prospect appointment."""
    from config.api_helpers import datetime_label

    return {
        "id": f"PRO-CIT-{appointment.pk:04d}",
        "rawId": None,
        "patient": str(appointment.prospecto),
        "procedure": "Consulta medica (prospecto)",
        "branch": f"Sede: {appointment.sucursal.nombre}",
        "sessions": "No aplica",
        "nextAppointment": datetime_label(appointment.fecha_hora),
        "quotaStatus": "No aplica",
        "status": appointment.get_estado_display(),
        "price": "No aplica",
    }


def appointment_biometric_status(cita):
    """Return the biometric verification status label for a cita."""
    if cita.verif_biometria:
        return "Validada"

    if cita.estado in {
        CitaMedica.Estado.CANCELADA,
        CitaMedica.Estado.NO_ASISTIO,
    }:
        return "No aplica"

    if cita.estado in {
        CitaMedica.Estado.PROGRAMADA,
        CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
    }:
        return "Pendiente"

    return "No aplica"


# ---------------------------------------------------------------------------
# Agenda/status helpers (shared between api_views.py and dashboard viewset)
# ---------------------------------------------------------------------------

def agenda_status(cita):
    """Return a simplified status label for a medical appointment."""
    if cita.estado == CitaMedica.Estado.CONFIRMADA:
        return "confirmada"
    if cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
        return "biometria"
    return "programada"


def agenda_appointment_status(cita):
    """Return the appointment status string."""
    if cita.estado == CitaMedica.Estado.CONFIRMADA:
        return "confirmada"
    if cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
        return "pendiente_verificacion"
    return "programada"


def agenda_verification_status(cita):
    """Return the verification status label."""
    if cita.estado == CitaMedica.Estado.CONFIRMADA:
        return "verificada"
    if cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
        return "pendiente"
    return "no_requerida"


def agenda_verification_method(cita):
    """Return the verification method label (biometria, qr, or None)."""
    if cita.metodo_confirmacion == CitaMedica.MetodoConfirmacion.BIOMETRICO:
        return "biometria"
    if cita.metodo_confirmacion == CitaMedica.MetodoConfirmacion.TABLET:
        return "qr"
    return None
