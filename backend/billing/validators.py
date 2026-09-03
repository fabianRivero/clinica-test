"""Cross-cutting validators for the ``payment-physical-virtual`` and
``appointment-payment`` capabilities.

Helpers exposed here are reachable from both the admin endpoint
(``PagosViewSet.register_payment``, landing in PR 2 of
``pagos-fisicos-virtuales``) and the new cita cobrar endpoints
(``OperacionesViewSet.cobrar_cita`` / ``FreeMedicalAppointmentViewSet.cobrar``,
landing in PR 2 of ``citas-pagos``):

* ``assert_cuota_in_user_branch(request, cuota)`` — raises ``Http404``
  when the cuota's client is not in the admin's active branch. Used to
  scope the cuota admin endpoint to a single branch.

* ``assert_not_over_payment(cuota, new_amount)`` — raises
  ``rest_framework.exceptions.ValidationError`` when the new payment,
  added to already-approved payments on the cuota, would exceed the
  scheduled amount. Enforces the spec's cuota over-payment rule.

* ``assert_cita_in_user_branch(request, cita)`` — raises
  ``rest_framework.exceptions.PermissionDenied`` (HTTP 403) when the
  cita's ``sucursal`` is not the admin's active branch. Used by both
  cita cobrar endpoints. Distinct from the cuota helper: the cita
  spec mandates 403 so admins can distinguish cross-branch (config
  error) from missing cita (404).

* ``assert_not_over_cita_payment(cita, new_amount)`` — raises
  ``rest_framework.exceptions.ValidationError`` when the new payment,
  added to already-approved ``PagoCita`` rows, would exceed the
  cita's ``precio``.

All helpers are intentionally decoupled from the model ``clean()``
method: ``clean()`` only sees the row in memory, so cross-row aggregate
checks must live at the view layer.
"""

from decimal import Decimal

from django.db.models import Sum
from django.http import Http404

from rest_framework.exceptions import (
    PermissionDenied,
    ValidationError as DRFValidationError,
)

from billing.models import PagoCita, PagoRealizado
from config.api_helpers import get_user_branch


def assert_cuota_in_user_branch(request, cuota):
    """Raise ``Http404`` if the cuota's client is not in the admin's branch.

    Mirrors the existing branch-isolation pattern used by
    ``PagosViewSet.update_qr_config`` so super admins with no selected
    branch fall through to the principal branch via ``get_user_branch``.

    The returned branch is the effective branch for the request so callers
    can re-use it without calling ``get_user_branch`` twice.
    """
    branch = get_user_branch(request)
    if branch is None:
        raise Http404("No encontramos la cuota solicitada.")
    cuota_branch_id = (
        getattr(cuota.operacion.paciente.usuario, "sucursal_id", None)
        if cuota and cuota.operacion and cuota.operacion.paciente
        else None
    )
    if cuota_branch_id != branch.id:
        raise Http404("No encontramos la cuota solicitada.")
    return branch


def assert_not_over_payment(cuota, new_amount):
    """Raise ``DRFValidationError`` when the cuota would be over-paid.

    Sums already-approved payments on the cuota and adds ``new_amount``.
    If the sum exceeds ``cuota.monto_programado`` the cuota is considered
    fully covered (or over-paid) and the new payment is rejected. This
    helper is only called for NEW payments — rejected/pending row
    resubmissions skip it because the row was already accepted on its
    first save.

    A ``monto_programado`` of 0 means the cuota has been auto-created to
    host a single full payment (e.g. the conversion wizard path). The
    cuota will then be marked PAGADO immediately and any further
    payments on it must be rejected.
    """
    if new_amount is None:
        return
    new_amount = Decimal(str(new_amount))
    if new_amount <= 0:
        return
    approved_sum = (
        cuota.pagos_realizados.filter(
            estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO
        ).aggregate(s=Sum("monto_pagado"))["s"]
        or Decimal("0")
    )
    if approved_sum + new_amount > cuota.monto_programado:
        raise DRFValidationError(
            {"detail": "El pago supera el saldo pendiente de la cuota."}
        )


def assert_cita_in_user_branch(request, cita):
    """Raise ``PermissionDenied`` (HTTP 403) when the cita is cross-branch.

    Both ``CitaMedica`` and ``CitaClienteLibre`` carry a direct
    ``sucursal`` FK, so the check does not have to walk through the
    cita's parent operation. Super admins with no selected branch fall
    through to the principal branch via ``get_user_branch`` so the
    helper stays consistent with the cuota flavour.

    The cita spec mandates HTTP 403 (not 404) on cross-branch so admins
    can tell "you tried the wrong branch" apart from "the cita does
    not exist at all".
    """
    branch = get_user_branch(request)
    if branch is None:
        raise PermissionDenied("No tienes una sucursal activa seleccionada.")
    cita_branch_id = getattr(cita, "sucursal_id", None)
    if cita_branch_id != branch.id:
        raise PermissionDenied(
            "No puedes cobrar citas de una sucursal distinta a la tuya."
        )
    return branch


def assert_not_over_cita_payment(cita, new_amount):
    """Raise ``DRFValidationError`` when the cita would be over-paid.

    Sums already-approved ``PagoCita`` rows on the cita (either kind)
    and adds ``new_amount``. If the sum exceeds ``cita.precio`` the
    cita is considered fully covered and the new payment is rejected.
    Mirrors ``assert_not_over_payment`` but scopes the aggregation to
    the new ``PagoCita`` table so the two flows stay independent.

    Uses the ``pagos_cita`` reverse relation declared on both cita
    models, so a single helper works for ``CitaMedica`` and
    ``CitaClienteLibre`` without caring which FK side is set.
    """
    if new_amount is None:
        return
    new_amount = Decimal(str(new_amount))
    if new_amount <= 0:
        return
    approved_sum = (
        cita.pagos_cita.filter(
            estado_verificacion=PagoCita.EstadoVerificacion.APROBADO
        ).aggregate(s=Sum("monto_pagado"))["s"]
        or Decimal("0")
    )
    if approved_sum + new_amount > Decimal(str(cita.precio)):
        raise DRFValidationError(
            {"detail": "El pago supera el saldo pendiente de la cita."}
        )
