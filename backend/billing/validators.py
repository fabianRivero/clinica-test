"""Cross-cutting validators for the ``payment-physical-virtual`` capability.

Two helpers are exposed here so they can be reached from both the admin
endpoint (``PagosViewSet.register_payment``, landing in PR 2) and the
client upload path (``client_upload_payment_receipt``, also PR 2):

* ``assert_cuota_in_user_branch(request, cuota)`` — raises ``Http404``
  when the cuota's client is not in the admin's active branch. Used to
  scope the admin endpoint to a single branch.

* ``assert_not_over_payment(cuota, new_amount)`` — raises
  ``rest_framework.exceptions.ValidationError`` when the new payment,
  added to already-approved payments on the cuota, would exceed the
  scheduled amount. Enforces the spec's quota over-payment rule.

Both helpers are intentionally decoupled from the model ``clean()``
method: ``clean()`` only sees the row in memory, so cross-row aggregate
checks must live at the view layer.
"""

from decimal import Decimal

from django.db.models import Sum
from django.http import Http404

from rest_framework.exceptions import ValidationError as DRFValidationError

from billing.models import PagoRealizado
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
