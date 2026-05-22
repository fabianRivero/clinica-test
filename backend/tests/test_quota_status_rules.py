from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago, PagoRealizado
from catalogs.models import ProcEstetico, ServicioConfig, Sucursal, TipoServicio
from customers.models import Cliente
from operations.models import Operacion


class QuotaStatusRulesTests(TestCase):
    def setUp(self):
        self.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.branch = Sucursal.objects.create(nombre="Central", activa=True)
        self.admin = Usuario.objects.create_user(
            username="admin.test",
            password="password123",
            rol=self.rol_admin,
            sucursal=self.branch,
        )

        self.client = Client()
        self.client.login(username="admin.test", password="password123")

        self.tipo = TipoServicio.objects.create(tipo="Tratamiento", activa=True)
        self.proc = ProcEstetico.objects.create(proceso="Limpieza", activa=True)
        self.service = ServicioConfig.objects.create(
            tipo_servicio=self.tipo,
            proc_estetico=self.proc,
            precio_base=Decimal("120.00"),
            activa=True,
        )

        self.user = Usuario.objects.create_user(username="paciente.test", password="password123")
        self.customer = Cliente.objects.create(
            usuario=self.user,
            sucursal_registro=self.branch,
            fecha_nacimiento=timezone.localdate() - timedelta(days=9000),
            estado_cliente=Cliente.Estado.ACTIVO,
        )
        self.operation = Operacion.objects.create(
            paciente=self.customer,
            servicio_config=self.service,
            sucursal=self.branch,
            precio_total=Decimal("240.00"),
            cuotas_totales=2,
            sesiones_totales=1,
            estado=Operacion.Estado.EN_PROCESO,
        )

    def test_overdue_quota_with_pending_review_stays_pending(self):
        cuota = CuotaPlanPago.objects.create(
            operacion=self.operation,
            nro_cuota=1,
            fecha_vencimiento=timezone.localdate() - timedelta(days=1),
            monto_programado=Decimal("120.00"),
            estado=CuotaPlanPago.Estado.PENDIENTE,
        )
        PagoRealizado.objects.create(
            cuota=cuota,
            monto_pagado=Decimal("120.00"),
            comprobante_url="comprobantes_pagos/test.png",
            estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
        )

        cuota.refresh_from_db()
        self.assertEqual(cuota.estado, CuotaPlanPago.Estado.PENDIENTE)

    def test_overdue_quota_without_pending_review_becomes_vencida(self):
        cuota = CuotaPlanPago.objects.create(
            operacion=self.operation,
            nro_cuota=1,
            fecha_vencimiento=timezone.localdate() - timedelta(days=1),
            monto_programado=Decimal("120.00"),
            estado=CuotaPlanPago.Estado.PENDIENTE,
        )
        cuota.actualizar_estado_por_pagos()
        cuota.refresh_from_db()

        self.assertEqual(cuota.estado, CuotaPlanPago.Estado.VENCIDA)

    def test_inactivate_client_converts_pending_and_overdue_to_no_pagada(self):
        cuota_pending = CuotaPlanPago.objects.create(
            operacion=self.operation,
            nro_cuota=1,
            fecha_vencimiento=timezone.localdate() + timedelta(days=5),
            monto_programado=Decimal("120.00"),
            estado=CuotaPlanPago.Estado.PENDIENTE,
        )
        cuota_overdue = CuotaPlanPago.objects.create(
            operacion=self.operation,
            nro_cuota=2,
            fecha_vencimiento=timezone.localdate() - timedelta(days=5),
            monto_programado=Decimal("120.00"),
            estado=CuotaPlanPago.Estado.VENCIDA,
        )

        response = self.client.post(f"/api/admin/clientes/{self.customer.id}/inactivar/")
        self.assertEqual(response.status_code, 200)

        cuota_pending.refresh_from_db()
        cuota_overdue.refresh_from_db()
        self.assertEqual(cuota_pending.estado, CuotaPlanPago.Estado.NO_PAGADA)
        self.assertEqual(cuota_overdue.estado, CuotaPlanPago.Estado.NO_PAGADA)

    def test_inactivate_client_with_pending_review_payment_returns_400(self):
        cuota = CuotaPlanPago.objects.create(
            operacion=self.operation,
            nro_cuota=1,
            fecha_vencimiento=timezone.localdate() - timedelta(days=3),
            monto_programado=Decimal("120.00"),
            estado=CuotaPlanPago.Estado.VENCIDA,
        )
        PagoRealizado.objects.create(
            cuota=cuota,
            monto_pagado=Decimal("120.00"),
            comprobante_url="comprobantes_pagos/pending.png",
            estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
        )

        response = self.client.post(f"/api/admin/clientes/{self.customer.id}/inactivar/")
        self.assertEqual(response.status_code, 400)
        cuota.refresh_from_db()
        self.assertEqual(cuota.estado, CuotaPlanPago.Estado.PENDIENTE)
