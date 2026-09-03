"""Tests for ``PagoRealizadoSerializer`` field exposure.

The serializer is a read-only view over ``PagoRealizado`` rows. The
``payment-physical-virtual`` change adds three new fields to the model
(``metodo_pago``, ``monto_fisico``, ``monto_virtual``) and the read
serializer must expose them so the client / admin payment history can
render the breakdown.

The tests build a fully-fledged ``PagoRealizado`` row through the model
``save()`` path so the serializer runs against a real persisted instance
rather than a detached one.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago, PagoRealizado
from catalogs.models import ProcEstetico, ProcEsteticosTipo, ServicioConfig, Sucursal, TipoServicio
from config.api.serializers.payments import PagoRealizadoSerializer
from customers.models import Cliente
from operations.models import Operacion


class PagoRealizadoSerializerTests(TestCase):
    """Verify the read serializer exposes metodo_pago + breakdown fields."""

    def setUp(self):
        self.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.branch = Sucursal.objects.create(nombre="Central", activa=True)
        self.admin = Usuario.objects.create_user(
            username="admin.test",
            password="password123",
            rol=self.rol_admin,
            sucursal=self.branch,
        )
        self.tipo = TipoServicio.objects.create(tipo="Tratamiento", activo=True)
        self.tipo_proc = ProcEsteticosTipo.objects.create(tipo="Estetico")
        self.proc = ProcEstetico.objects.create(
            tipo_p_estetico=self.tipo_proc,
            proceso="Limpieza",
            activo=True,
        )
        self.service = ServicioConfig.objects.create(
            tipo_servicio=self.tipo,
            proc_estetico=self.proc,
            precio_base=Decimal("120.00"),
            activo=True,
        )
        self.user = Usuario.objects.create_user(
            username="paciente.test", password="password123"
        )
        self.customer = Cliente.objects.create(
            usuario=self.user,
            sucursal_origen=self.branch,
            fecha_nacimiento=timezone.localdate() - timedelta(days=9000),
            estado_cliente=Cliente.Estado.ACTIVO,
        )
        self.operation = Operacion.objects.create(
            paciente=self.customer,
            servicio_config=self.service,
            precio_total=Decimal("240.00"),
            cuotas_totales=2,
            sesiones_totales=1,
            estado=Operacion.Estado.EN_PROCESO,
        )
        self.cuota = CuotaPlanPago.objects.create(
            operacion=self.operation,
            nro_cuota=1,
            fecha_vencimiento=timezone.localdate(),
            monto_programado=Decimal("120.00"),
            estado=CuotaPlanPago.Estado.PENDIENTE,
        )

    def _make_payment(self, **overrides):
        defaults = dict(
            cuota=self.cuota,
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoRealizado.MetodoPago.MIXTO,
            monto_fisico=Decimal("40.00"),
            monto_virtual=Decimal("60.00"),
            comprobante_url=SimpleUploadedFile(
                "r.pdf", b"%PDF-test", content_type="application/pdf"
            ),
            estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
        )
        defaults.update(overrides)
        return PagoRealizado.objects.create(**defaults)

    def test_serializer_exposes_method_and_breakdown_fields(self):
        payment = self._make_payment()
        data = PagoRealizadoSerializer(payment).data
        self.assertEqual(data["metodo_pago"], PagoRealizado.MetodoPago.MIXTO)
        self.assertEqual(Decimal(data["monto_fisico"]), Decimal("40.00"))
        self.assertEqual(Decimal(data["monto_virtual"]), Decimal("60.00"))
        self.assertEqual(Decimal(data["monto_pagado"]), Decimal("100.00"))

    def test_serializer_exposes_virtual_payment(self):
        payment = self._make_payment(
            metodo_pago=PagoRealizado.MetodoPago.VIRTUAL,
            monto_fisico=Decimal("0"),
            monto_virtual=Decimal("100.00"),
        )
        data = PagoRealizadoSerializer(payment).data
        self.assertEqual(data["metodo_pago"], PagoRealizado.MetodoPago.VIRTUAL)
        self.assertEqual(Decimal(data["monto_fisico"]), Decimal("0"))
        self.assertEqual(Decimal(data["monto_virtual"]), Decimal("100.00"))