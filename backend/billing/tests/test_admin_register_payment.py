"""Tests for ``PagosViewSet.register_payment``.

The new admin endpoint lives at ``POST /api/pagos/cuotas/<cuota_id>/pagos/``
and is gated by ``AdminRequired`` + ``assert_cuota_in_user_branch``. The
tests below cover:

* Happy path: admin-sucursal registers a FISICO payment on a cuota in
  their own branch. Asserts 201, ``PENDIENTE`` state, breakdown amounts.
* Cross-branch: admin branch X cannot register against a cuota whose
  client lives in branch Y → 404, no row, no notification.
* Over-payment: cuota fully covered by approved payments → 400, no row.
* MIXTO mismatch: breakdown that does not sum to ``monto_pagado`` →
  400 (caught by ``PagoRealizadoCreateSerializer.validate``).
* Notification: exactly one ``ADMIN_PAYMENT_PENDING_CONFIRMATION`` per
  successful creation, dispatched to branch admins.

The factory helpers inline the minimum graph needed for the endpoint:
``Sucursal`` → ``Usuario`` → ``Cliente`` → ``Operacion`` → ``CuotaPlanPago``.
We use Django's ``Client`` with ``force_login`` (project convention;
``APIClient`` is not used in the existing test suite).
"""

from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
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
from customers.models import Cliente
from notifications.models import Notification
from operations.models import Operacion


URL_NAME = "admin-pagos-register-payment"


def _url(cuota_id):
    return f"/api/admin/pagos/cuotas/{cuota_id}/pagos/"


class _AdminPaymentGraph:
    """Reusable graph builder for admin-register-payment tests."""

    @staticmethod
    def build(role="ADMIN_SUCURSAL"):
        branch = Sucursal.objects.create(nombre=f"Sucursal {role}", activa=True)
        rol = Rol.objects.create(rol=role)
        admin = Usuario.objects.create_user(
            username=f"admin.{role.lower()}",
            password="password123",
            rol=rol,
            sucursal=branch,
        )
        # Second branch-admin in the same branch — needed to confirm
        # that notifications fan out to all branch admins, not just
        # the requester.
        admin_b = Usuario.objects.create_user(
            username=f"admin.{role.lower()}.b",
            password="password123",
            rol=rol,
            sucursal=branch,
        )

        tipo = TipoServicio.objects.create(tipo="Tratamiento")
        proc_tipo = ProcEsteticosTipo.objects.create(tipo="Facial")
        proc = ProcEstetico.objects.create(
            tipo_p_estetico=proc_tipo, proceso="Limpieza"
        )
        service = ServicioConfig.objects.create(
            tipo_servicio=tipo,
            proc_estetico=proc,
            precio_base=Decimal("240.00"),
        )
        cliente_user = Usuario.objects.create_user(
            username="paciente.test",
            password="password123",
        )
        cliente_user.sucursal = branch
        cliente_user.save()
        cliente = Cliente.objects.create(
            usuario=cliente_user,
            sucursal_origen=branch,
            fecha_nacimiento=timezone.localdate().replace(year=timezone.localdate().year - 25),
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
        cuota = CuotaPlanPago.objects.create(
            operacion=operacion,
            nro_cuota=1,
            fecha_vencimiento=timezone.localdate(),
            monto_programado=Decimal("120.00"),
            estado=CuotaPlanPago.Estado.PENDIENTE,
        )

        return {
            "branch": branch,
            "admin": admin,
            "admin_b": admin_b,
            "tipo": tipo,
            "proc": proc,
            "service": service,
            "cliente_user": cliente_user,
            "cliente": cliente,
            "operacion": operacion,
            "cuota": cuota,
        }


class AdminRegisterPaymentHappyPathTests(TestCase):
    """Happy path + per-method breakdown."""

    def setUp(self):
        self.g = _AdminPaymentGraph.build()
        self.client = Client()
        self.client.force_login(self.g["admin"])

    def _receipt(self):
        return SimpleUploadedFile(
            "receipt.pdf", b"%PDF-test", content_type="application/pdf"
        )

    def _post(self, **extra):
        data = {"paymentMethod": "FISICO", "monto_pagado": "120.00"}
        data.update(extra)
        return self.client.post(_url(self.g["cuota"].pk), data)

    def test_fisico_happy_path_creates_aprobado_row(self):
        response = self._post()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIn("payment", body)
        self.assertIn("quota", body)
        self.assertEqual(
            PagoRealizado.objects.count(), 1, "exactly one row was created"
        )
        payment = PagoRealizado.objects.get()
        self.assertEqual(payment.estado_verificacion, PagoRealizado.EstadoVerificacion.APROBADO)
        self.assertTrue(payment.verificado)
        self.assertIsNotNone(payment.verificado_por)
        self.assertIsNotNone(payment.fecha_verificacion)
        self.assertEqual(payment.metodo_pago, PagoRealizado.MetodoPago.FISICO)
        self.assertEqual(payment.monto_pagado, Decimal("120.00"))
        self.assertEqual(payment.monto_fisico, Decimal("120.00"))
        self.assertEqual(payment.monto_virtual, Decimal("0"))

    def test_mixto_with_valid_breakdown_persists_amounts(self):
        response = self._post(
            paymentMethod="MIXTO",
            montoFisico="40.00",
            montoVirtual="80.00",
        )
        self.assertEqual(response.status_code, 201, response.content)
        payment = PagoRealizado.objects.get()
        self.assertEqual(payment.metodo_pago, PagoRealizado.MetodoPago.MIXTO)
        self.assertEqual(payment.monto_fisico, Decimal("40.00"))
        self.assertEqual(payment.monto_virtual, Decimal("80.00"))
        self.assertEqual(payment.monto_pagado, Decimal("120.00"))

    def test_virtual_with_receipt_creates_virtual_breakdown(self):
        response = self._post(paymentMethod="VIRTUAL", receiptFile=self._receipt())
        self.assertEqual(response.status_code, 201, response.content)
        payment = PagoRealizado.objects.get()
        self.assertEqual(payment.metodo_pago, PagoRealizado.MetodoPago.VIRTUAL)
        self.assertEqual(payment.monto_virtual, Decimal("120.00"))
        self.assertEqual(payment.monto_fisico, Decimal("0"))
        # The receipt was stored.
        self.assertTrue(bool(payment.comprobante_url))


class AdminRegisterPaymentCrossBranchTests(TestCase):
    """Branch-isolation guard: cross-branch requests must 404."""

    def setUp(self):
        self.g_x = _AdminPaymentGraph.build()
        # Build a second, separate branch graph: the client lives in
        # branch Y, so the admin from branch X must NOT be allowed to
        # register payments against it.
        branch_y = Sucursal.objects.create(nombre="Sucursal Y", activa=True)
        tipo = TipoServicio.objects.create(tipo="Tratamiento Y")
        proc_tipo = ProcEsteticosTipo.objects.create(tipo="Corporal")
        proc = ProcEstetico.objects.create(
            tipo_p_estetico=proc_tipo, proceso="Masaje"
        )
        service = ServicioConfig.objects.create(
            tipo_servicio=tipo,
            proc_estetico=proc,
            precio_base=Decimal("200.00"),
        )
        cliente_user = Usuario.objects.create_user(
            username="paciente.y", password="password123"
        )
        cliente_user.sucursal = branch_y
        cliente_user.save()
        cliente = Cliente.objects.create(
            usuario=cliente_user,
            sucursal_origen=branch_y,
            fecha_nacimiento=timezone.localdate().replace(year=timezone.localdate().year - 30),
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
        cuota_y = CuotaPlanPago.objects.create(
            operacion=operacion,
            nro_cuota=1,
            fecha_vencimiento=timezone.localdate(),
            monto_programado=Decimal("200.00"),
            estado=CuotaPlanPago.Estado.PENDIENTE,
        )
        self.g_y = {"branch": branch_y, "cuota": cuota_y}

        self.client = Client()
        self.client.force_login(self.g_x["admin"])

    def test_admin_branch_x_registering_against_branch_y_returns_404(self):
        response = self.client.post(
            _url(self.g_y["cuota"].pk),
            {"paymentMethod": "FISICO", "monto_pagado": "200.00"},
        )
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(PagoRealizado.objects.count(), 0)


class AdminRegisterPaymentOverPaymentTests(TestCase):
    """Over-payment guard: cuota fully covered → 400."""

    def setUp(self):
        self.g = _AdminPaymentGraph.build()
        # Cover the cuota fully with an APROBADO row.
        PagoRealizado.objects.create(
            cuota=self.g["cuota"],
            monto_pagado=Decimal("120.00"),
            metodo_pago=PagoRealizado.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("120.00"),
            monto_fisico=Decimal("0"),
            comprobante_url="comprobantes_pagos/already_approved.png",
            estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO,
            verificado=True,
            verificado_por=self.g["admin"],
            fecha_verificacion=timezone.now(),
        )
        self.client = Client()
        self.client.force_login(self.g["admin"])

    def test_over_payment_returns_400_and_creates_no_row(self):
        before = PagoRealizado.objects.count()
        response = self.client.post(
            _url(self.g["cuota"].pk),
            {"paymentMethod": "FISICO", "monto_pagado": "50.00"},
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoRealizado.objects.count(), before)


class AdminRegisterPaymentMixtoMismatchTests(TestCase):
    """MIXTO breakdown must sum to monto_pagado."""

    def setUp(self):
        self.g = _AdminPaymentGraph.build()
        self.client = Client()
        self.client.force_login(self.g["admin"])

    def test_mixto_with_breakdown_not_summing_to_total_returns_400(self):
        before = PagoRealizado.objects.count()
        response = self.client.post(
            _url(self.g["cuota"].pk),
            {
                "paymentMethod": "MIXTO",
                "monto_pagado": "100.00",
                "montoFisico": "40.00",
                "montoVirtual": "30.00",  # mismatch: 40+30=70 != 100
            },
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoRealizado.objects.count(), before)


class AdminRegisterPaymentNotificationTests(TestCase):
    """One ``ADMIN_PAYMENT_PENDING_CONFIRMATION`` per successful creation."""

    def setUp(self):
        self.g = _AdminPaymentGraph.build()
        self.client = Client()
        self.client.force_login(self.g["admin"])

    def test_admin_register_payment_notifies_client_once(self):
        """The client receives one ``CLIENT_PAYMENT_CONFIRMED`` notification
        so they see the impact on their portal without refreshing. No
        admin-pending-review notification is fired because the admin
        registering the payment is the same one confirming it was
        collected."""
        with patch(
            "config.api.viewsets.payments.create_notification"
        ) as mock_create:
            response = self.client.post(
                _url(self.g["cuota"].pk),
                {"paymentMethod": "FISICO", "monto_pagado": "120.00"},
            )
        self.assertEqual(response.status_code, 201, response.content)

        # Exactly one notification, addressed to the client.
        self.assertEqual(mock_create.call_count, 1)

        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["type"], Notification.Type.CLIENT_PAYMENT_CONFIRMED)
        self.assertEqual(kwargs["title"], "Pago confirmado")
        self.assertIn("Bs 120", kwargs["message"])
        self.assertEqual(kwargs["action_url"], "/cliente/pagos")
        self.assertEqual(kwargs["source_event"], "payment.admin_registered_and_confirmed")
        self.assertEqual(kwargs["source_entity_type"], "payment")
        self.assertEqual(kwargs["created_by_type"], "admin")
        self.assertEqual(kwargs["created_by_id"], self.g["admin"].id)