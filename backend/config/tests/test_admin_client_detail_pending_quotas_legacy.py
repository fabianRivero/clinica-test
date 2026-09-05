"""Tests for the admin client detail endpoint around the
"cuotas vs. pagos pendientes" split.

Business rule:

* ``pendingQuotas`` (the "Cuotas pendientes" block) holds the cuotas
  that are still unpaid AND have NO ``PagoRealizado`` waiting for
  review. Once the client uploads a receipt from the portal, the
  resulting ``PagoRealizado`` lands in ``estado_verificacion=PENDIENTE``
  and that quota must disappear from ``pendingQuotas`` — the admin
  reviews the payment from the dedicated payments table instead.
* If the admin rejects the payment, the quota reappears in
  ``pendingQuotas`` because there is no longer a pending payment.
* Approved payments do not count against the cuota being pending
  because the admin's action flips the quota to ``PAGADO`` (or
  ``PAGADO_PARCIAL`` if partial) on the same transaction.

This module targets the **legacy** ``config.api_views._admin_client_detail``
helper — the one wired to the actual ``/api/admin/clientes/<id>/``
URL via ``admin_cliente_detalle``. The DRF viewset equivalent
(``config.api.viewsets.clientes._admin_client_detail``) reuses the
same filter; coverage of the legacy helper is what guards the live
path.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago, PagoRealizado
from catalogs.models import (
    ProcEstetico,
    ProcEsteticosTipo,
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from config.api_views import _admin_client_detail
from customers.models import Cliente
from operations.models import Operacion


def _build_graph():
    branch = Sucursal.objects.create(nombre="Sucursal Test", activa=True)
    rol_cliente = Rol.objects.create(rol="CLIENTE")
    rol_admin = Rol.objects.create(rol="ADMIN_SUCURSAL")
    cliente_user = Usuario.objects.create_user(
        username="cliente.detalle",
        password="password123",
        rol=rol_cliente,
        sucursal=branch,
    )
    admin_user = Usuario.objects.create_user(
        username="admin.detalle",
        password="password123",
        rol=rol_admin,
        sucursal=branch,
    )
    tipo = TipoServicio.objects.create(tipo="Tratamiento")
    proc_tipo = ProcEsteticosTipo.objects.create(tipo="Facial")
    proc = ProcEstetico.objects.create(tipo_p_estetico=proc_tipo, proceso="Limpieza")
    service = ServicioConfig.objects.create(
        tipo_servicio=tipo,
        proc_estetico=proc,
        precio_base=Decimal("240.00"),
    )
    cliente = Cliente.objects.create(
        usuario=cliente_user,
        sucursal_origen=branch,
        fecha_nacimiento=date(1990, 1, 1),
        estado_cliente=Cliente.Estado.ACTIVO,
    )
    operacion = Operacion.objects.create(
        paciente=cliente,
        servicio_config=service,
        precio_total=Decimal("240.00"),
        cuotas_totales=2,
        sesiones_totales=1,
        estado=Operacion.Estado.EN_PROCESO,
    )
    cuota1 = CuotaPlanPago.objects.create(
        operacion=operacion,
        nro_cuota=1,
        fecha_vencimiento=timezone.localdate(),
        monto_programado=Decimal("120.00"),
        estado=CuotaPlanPago.Estado.PENDIENTE,
    )
    cuota2 = CuotaPlanPago.objects.create(
        operacion=operacion,
        nro_cuota=2,
        fecha_vencimiento=timezone.localdate(),
        monto_programado=Decimal("120.00"),
        estado=CuotaPlanPago.Estado.PENDIENTE,
    )
    return {
        "branch": branch,
        "admin": admin_user,
        "cliente": cliente,
        "operacion": operacion,
        "cuota1": cuota1,
        "cuota2": cuota2,
    }


class AdminClientDetailPendingQuotasTests(TestCase):
    """``pendingQuotas`` excludes cuotas with a payment awaiting review."""

    def setUp(self):
        self.g = _build_graph()

    def _cuota_ids(self, data):
        # The serializer renders ids as ``CUO-NNNN`` strings; strip
        # the prefix to compare against the cuota pk.
        return [int(q["id"].rsplit("-", 1)[1]) for q in data["pendingQuotas"]]

    def test_both_quotas_pending_appear_in_pending_quotas(self):
        data = _admin_client_detail(self.g["cliente"])
        ids = self._cuota_ids(data)
        self.assertIn(self.g["cuota1"].pk, ids)
        self.assertIn(self.g["cuota2"].pk, ids)

    def test_quota_with_pending_payment_disappears_from_pending_quotas(self):
        """When the client uploads a receipt, the resulting PagoRealizado
        in PENDIENTE hides the cuota from the unpaid list — the admin
        reviews the payment from the payments table instead."""
        PagoRealizado.objects.create(
            cuota=self.g["cuota1"],
            monto_pagado=Decimal("120.00"),
            metodo_pago=PagoRealizado.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("120.00"),
            monto_fisico=Decimal("0"),
            comprobante_url="comprobantes_pagos/c1.pdf",
            estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
        )
        data = _admin_client_detail(self.g["cliente"])
        ids = self._cuota_ids(data)
        self.assertNotIn(self.g["cuota1"].pk, ids)
        self.assertIn(self.g["cuota2"].pk, ids)

    def test_quota_with_rejected_payment_reappears_in_pending_quotas(self):
        """A REJECTED payment does not hide the cuota — the admin
        expects to see the cuota again so they can decide to register
        a new payment, re-open the case, or wait for the client to
        re-upload."""
        PagoRealizado.objects.create(
            cuota=self.g["cuota1"],
            monto_pagado=Decimal("120.00"),
            metodo_pago=PagoRealizado.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("120.00"),
            monto_fisico=Decimal("0"),
            comprobante_url="comprobantes_pagos/c1_illegible.pdf",
            estado_verificacion=PagoRealizado.EstadoVerificacion.RECHAZADO,
            verificado_por=self.g["admin"],
            fecha_verificacion=timezone.now(),
            observacion_verificacion="Comprobante ilegible",
        )
        data = _admin_client_detail(self.g["cliente"])
        ids = self._cuota_ids(data)
        self.assertIn(self.g["cuota1"].pk, ids)
        self.assertIn(self.g["cuota2"].pk, ids)

    def test_quota_with_approved_payment_is_excluded(self):
        """An APROBADO payment flips the cuota to PAGADO, so it should
        not be in pendingQuotas at all (the existing PAGADO filter
        already handles it, but we re-assert the regression)."""
        PagoRealizado.objects.create(
            cuota=self.g["cuota1"],
            monto_pagado=Decimal("120.00"),
            metodo_pago=PagoRealizado.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("120.00"),
            monto_fisico=Decimal("0"),
            comprobante_url="comprobantes_pagos/c1_ok.pdf",
            estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO,
            verificado=True,
            verificado_por=self.g["admin"],
            fecha_verificacion=timezone.now(),
        )
        data = _admin_client_detail(self.g["cliente"])
        ids = self._cuota_ids(data)
        self.assertNotIn(self.g["cuota1"].pk, ids)
        self.assertIn(self.g["cuota2"].pk, ids)
