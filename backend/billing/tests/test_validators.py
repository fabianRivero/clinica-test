"""Tests for the cita-side helpers in ``billing.validators``.

* ``assert_cita_in_user_branch`` — silent on same branch, raises
  ``PermissionDenied`` (HTTP 403) on cross-branch.
* ``assert_not_over_cita_payment`` — silent when the new payment fits
  inside the cita's ``precio``, raises ``DRFValidationError`` on
  over-payment.

These helpers are decoupled from any viewset so they can be unit-tested
without standing up a DRF client. The tests use ``RequestFactory`` for
the branch check (mirrors the pattern other tests in the suite already
use for ``get_user_branch``) and the cita reverse-manager ``pagos_cita``
for the over-payment aggregation.
"""

from decimal import Decimal

from django.http import HttpRequest
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import PagoCita
from billing.validators import (
    assert_cita_in_user_branch,
    assert_not_over_cita_payment,
)
from catalogs.models import (
    ProcEstetico,
    ProcEsteticosTipo,
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from customers.models import Cliente
from operations.models import CitaMedica, Operacion
from rest_framework.exceptions import (
    PermissionDenied,
    ValidationError as DRFValidationError,
)


def _build_graph():
    branch_a = Sucursal.objects.create(nombre="Sucursal A", activa=True)
    branch_b = Sucursal.objects.create(nombre="Sucursal B", activa=True)
    rol = Rol.objects.create(rol="ADMIN_SUCURSAL")
    admin_a = Usuario.objects.create_user(
        username="admin.a",
        password="password123",
        rol=rol,
        sucursal=branch_a,
    )
    admin_b = Usuario.objects.create_user(
        username="admin.b",
        password="password123",
        rol=rol,
        sucursal=branch_b,
    )

    tipo = TipoServicio.objects.create(tipo="Consulta")
    proc_tipo = ProcEsteticosTipo.objects.create(tipo="General")
    proc = ProcEstetico.objects.create(
        tipo_p_estetico=proc_tipo, proceso="Consulta"
    )
    service = ServicioConfig.objects.create(
        tipo_servicio=tipo,
        proc_estetico=proc,
        precio_base=Decimal("200.00"),
    )

    cliente_user = Usuario.objects.create_user(
        username="paciente.test",
        password="password123",
    )
    cliente_user.sucursal = branch_a
    cliente_user.save()
    cliente = Cliente.objects.create(
        usuario=cliente_user,
        sucursal_origen=branch_a,
        fecha_nacimiento=timezone.localdate().replace(
            year=timezone.localdate().year - 30
        ),
        estado_cliente=Cliente.Estado.ACTIVO,
    )
    operacion = Operacion.objects.create(
        paciente=cliente,
        servicio_config=service,
        precio_total=Decimal("200.00"),
        cuotas_totales=1,
        sesiones_totales=1,
        estado=Operacion.Estado.EN_PROCESO,
    )
    cita_a = CitaMedica.objects.create(
        operacion=operacion,
        sucursal=branch_a,
        fecha_hora=timezone.now() + timezone.timedelta(days=1),
        estado=CitaMedica.Estado.PROGRAMADA,
        precio=Decimal("100.00"),
    )
    return {
        "branch_a": branch_a,
        "branch_b": branch_b,
        "admin_a": admin_a,
        "admin_b": admin_b,
        "cita_a": cita_a,
    }


def _make_request(user):
    """Build a minimal request object carrying the given user."""
    request = HttpRequest()
    request.user = user
    # Session dict — required by ``get_user_branch`` for super admins.
    request.session = {}
    return request


class ValidatorsTests(TestCase):
    """Unit tests for the cita-side helpers in ``billing.validators``."""

    def setUp(self):
        self.g = _build_graph()
        self.factory = RequestFactory()

    # -------------------------------------------------------------------------
    # assert_cita_in_user_branch
    # -------------------------------------------------------------------------

    def test_assert_cita_in_user_branch_same_branch_silent(self):
        request = _make_request(self.g["admin_a"])
        # Same branch — must not raise. The helper returns the effective
        # branch so callers can re-use it.
        result = assert_cita_in_user_branch(request, self.g["cita_a"])
        self.assertEqual(result, self.g["branch_a"])

    def test_assert_cita_in_user_branch_cross_branch_raises_403(self):
        request = _make_request(self.g["admin_b"])
        with self.assertRaises(PermissionDenied):
            assert_cita_in_user_branch(request, self.g["cita_a"])

    def test_assert_cita_in_user_branch_permission_denied_message(self):
        request = _make_request(self.g["admin_b"])
        with self.assertRaises(PermissionDenied) as ctx:
            assert_cita_in_user_branch(request, self.g["cita_a"])
        # The 403 must mention the branch mismatch so admins can self-correct.
        self.assertIn("sucursal", str(ctx.exception).lower())

    # -------------------------------------------------------------------------
    # assert_not_over_cita_payment
    # -------------------------------------------------------------------------

    def test_assert_not_over_cita_payment_accepts_when_no_prior_payments(self):
        # No APROBADO rows, new_amount = 50, precio = 100 → silent.
        assert_not_over_cita_payment(self.g["cita_a"], Decimal("50.00"))

    def test_assert_not_over_cita_payment_accepts_at_boundary(self):
        # precio = 100, one APROBADO of 80, new_amount = 20 → 100 == 100,
        # boundary is inclusive (greater-than rejects).
        PagoCita.objects.create(
            cita_medica=self.g["cita_a"],
            monto_pagado=Decimal("80.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("80.00"),
            monto_virtual=Decimal("0"),
            estado_verificacion=PagoCita.EstadoVerificacion.APROBADO,
            verificado_por=self.g["admin_a"],
            fecha_verificacion=timezone.now(),
        )
        assert_not_over_cita_payment(self.g["cita_a"], Decimal("20.00"))

    def test_assert_not_over_cita_payment_rejects_overpay(self):
        PagoCita.objects.create(
            cita_medica=self.g["cita_a"],
            monto_pagado=Decimal("80.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("80.00"),
            monto_virtual=Decimal("0"),
            estado_verificacion=PagoCita.EstadoVerificacion.APROBADO,
            verificado_por=self.g["admin_a"],
            fecha_verificacion=timezone.now(),
        )
        with self.assertRaises(DRFValidationError) as ctx:
            assert_not_over_cita_payment(self.g["cita_a"], Decimal("50.00"))
        self.assertIn("detail", ctx.exception.detail)

    def test_assert_not_over_cita_payment_ignores_pending_rows(self):
        # A PENDIENTE row must NOT count toward the APROBADO sum —
        # pending rows are the admin's "still to be verified" queue.
        PagoCita.objects.create(
            cita_medica=self.g["cita_a"],
            monto_pagado=Decimal("80.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("80.00"),
            monto_virtual=Decimal("0"),
            estado_verificacion=PagoCita.EstadoVerificacion.PENDIENTE,
        )
        # 50 fits inside precio=100 → silent.
        assert_not_over_cita_payment(self.g["cita_a"], Decimal("50.00"))

    def test_assert_not_over_cita_payment_zero_or_none_amount_silent(self):
        # Guards so callers can pass None or 0 without explicit checks.
        assert_not_over_cita_payment(self.g["cita_a"], None)
        assert_not_over_cita_payment(self.g["cita_a"], Decimal("0"))
        assert_not_over_cita_payment(self.g["cita_a"], Decimal("-5"))