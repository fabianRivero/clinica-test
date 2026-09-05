"""Tests for the refactored ``client_upload_payment_receipt`` endpoint.

The endpoint at ``POST /api/client/pagos/cuotas/<id>/comprobante/`` is
the client's only payment-submission path and is restricted to
``VIRTUAL`` (transfer + receipt). ``FISICO`` and ``MIXTO`` payments are
desk-only and must be captured by the admin via
``PagosViewSet.register_payment``. The restriction is enforced by
``PagoRealizadoClientCreateSerializer``, which coerces any inbound
``paymentMethod`` to ``VIRTUAL`` and requires the receipt file.

Tests below cover:

* VIRTUAL happy path: row created with receipt, breakdown, notification.
* VIRTUAL-without-receipt: 400, no row, legacy detail message.
* Smuggled ``FISICO`` / ``MIXTO`` methods: coerced to ``VIRTUAL`` (regression).
* Resubmission: a REJECTED row exists, the client re-uploads → row is
  reused (same pk), no new notification fires.
* Over-payment: existing APROBADO sum + new > ``monto_programado`` → 400.

The tests use Django's ``Client`` with ``force_login`` (project
convention; the orchestrator prompt mentioned ``APIClient`` /
``force_authenticate`` but the rest of the suite uses ``Client`` +
``force_login`` for compatibility with the project's auth decorators).
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
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


def _url(cuota_id):
    return f"/api/client/pagos/cuotas/{cuota_id}/comprobante/"


def _receipt():
    return SimpleUploadedFile(
        "receipt.pdf", b"%PDF-test", content_type="application/pdf"
    )


class _ClientPaymentGraph:
    """Reusable graph builder for client-upload-receipt tests."""

    @staticmethod
    def build():
        branch = Sucursal.objects.create(nombre="Sucursal Cliente", activa=True)
        rol_cliente = Rol.objects.create(rol="CLIENTE")
        rol_admin = Rol.objects.create(rol="ADMIN_SUCURSAL")

        cliente_user = Usuario.objects.create_user(
            username="cliente.test",
            password="password123",
            rol=rol_cliente,
            sucursal=branch,
        )
        # The branch admin lives in the SAME branch as the client — that's
        # who receives the ``ADMIN_PAYMENT_PENDING_CONFIRMATION`` notification.
        admin_user = Usuario.objects.create_user(
            username="admin.test",
            password="password123",
            rol=rol_admin,
            sucursal=branch,
        )

        tipo = TipoServicio.objects.create(tipo="Tratamiento Cliente")
        proc_tipo = ProcEsteticosTipo.objects.create(tipo="Facial")
        proc = ProcEstetico.objects.create(
            tipo_p_estetico=proc_tipo, proceso="Limpieza"
        )
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
        cuota = CuotaPlanPago.objects.create(
            operacion=operacion,
            nro_cuota=1,
            fecha_vencimiento=timezone.localdate(),
            monto_programado=Decimal("120.00"),
            estado=CuotaPlanPago.Estado.PENDIENTE,
        )
        return {
            "branch": branch,
            "cliente_user": cliente_user,
            "admin_user": admin_user,
            "service": service,
            "cliente": cliente,
            "operacion": operacion,
            "cuota": cuota,
        }


class ClientUploadPaymentReceiptHappyPathTests(TestCase):
    """Fresh-row creation path: VIRTUAL only (client portal restriction)."""

    def setUp(self):
        self.g = _ClientPaymentGraph.build()
        self.client = Client()
        self.client.force_login(self.g["cliente_user"])

    def test_virtual_with_receipt_creates_row_and_fires_notification(self):
        with patch(
            "config.client_api_views.create_notification"
        ) as mock_create:
            response = self.client.post(
                _url(self.g["cuota"].pk),
                {
                    "paymentMethod": "VIRTUAL",
                    "amount": "100.00",
                    "receiptFile": _receipt(),
                },
            )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIn("payment", body)
        self.assertIn("quota", body)
        self.assertEqual(PagoRealizado.objects.count(), 1)

        payment = PagoRealizado.objects.get()
        self.assertEqual(payment.metodo_pago, PagoRealizado.MetodoPago.VIRTUAL)
        self.assertEqual(payment.monto_pagado, Decimal("100.00"))
        self.assertEqual(payment.monto_virtual, Decimal("100.00"))
        self.assertEqual(payment.monto_fisico, Decimal("0"))
        self.assertEqual(
            payment.estado_verificacion,
            PagoRealizado.EstadoVerificacion.PENDIENTE,
        )

        # Exactly one notification per branch admin (1 admin in this branch).
        self.assertEqual(mock_create.call_count, 1)
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(
            kwargs["type"], Notification.Type.ADMIN_PAYMENT_PENDING_CONFIRMATION
        )
        self.assertEqual(kwargs["source_event"], "payment.pending_submission")
        self.assertEqual(kwargs["created_by_type"], "client")


class ClientUploadPaymentReceiptValidationTests(TestCase):
    """Error paths surface as 400 with the legacy detail messages."""

    def setUp(self):
        self.g = _ClientPaymentGraph.build()
        self.client = Client()
        self.client.force_login(self.g["cliente_user"])

    def test_virtual_without_receipt_returns_400(self):
        """The serializer maps VIRTUAL-without-receipt to the legacy
        'Debes adjuntar el comprobante del pago.' message so existing
        client error toasts keep working."""
        before = PagoRealizado.objects.count()
        response = self.client.post(
            _url(self.g["cuota"].pk),
            {"paymentMethod": "VIRTUAL", "amount": "100.00"},
        )
        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertIn("detail", body)
        self.assertIn("comprobante", body["detail"].lower())
        self.assertEqual(PagoRealizado.objects.count(), before)


class ClientUploadPaymentReceiptChannelRestrictionTests(TestCase):
    """The client portal is VIRTUAL-only — FISICO/MIXTO are desk-only.

    The dedicated ``PagoRealizadoClientCreateSerializer`` coerces any
    inbound ``paymentMethod`` to ``VIRTUAL`` and overwrites the breakdown
    so a stale tab or hand-crafted curl cannot smuggle a cash or split
    payment through the client endpoint.
    """

    def setUp(self):
        self.g = _ClientPaymentGraph.build()
        self.client = Client()
        self.client.force_login(self.g["cliente_user"])

    def test_fisico_method_is_coerced_to_virtual(self):
        response = self.client.post(
            _url(self.g["cuota"].pk),
            {
                "paymentMethod": "FISICO",
                "amount": "120.00",
                "receiptFile": _receipt(),
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        payment = PagoRealizado.objects.get()
        self.assertEqual(payment.metodo_pago, PagoRealizado.MetodoPago.VIRTUAL)
        self.assertEqual(payment.monto_virtual, Decimal("120.00"))
        self.assertEqual(payment.monto_fisico, Decimal("0"))

    def test_mixto_method_is_coerced_to_virtual(self):
        # The inbound breakdown is intentionally inconsistent (40 + 30
        # != 100) to prove the client serializer does NOT honor it. The
        # row lands VIRTUAL with monto_virtual == monto_pagado.
        response = self.client.post(
            _url(self.g["cuota"].pk),
            {
                "paymentMethod": "MIXTO",
                "amount": "100.00",
                "montoFisico": "40.00",
                "montoVirtual": "30.00",
                "receiptFile": _receipt(),
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        payment = PagoRealizado.objects.get()
        self.assertEqual(payment.metodo_pago, PagoRealizado.MetodoPago.VIRTUAL)
        self.assertEqual(payment.monto_pagado, Decimal("100.00"))
        self.assertEqual(payment.monto_virtual, Decimal("100.00"))
        self.assertEqual(payment.monto_fisico, Decimal("0"))


class ClientUploadPaymentReceiptResubmissionTests(TestCase):
    """Rejected/pending row reuse — spec decision: skip over-payment guard."""

    def setUp(self):
        self.g = _ClientPaymentGraph.build()
        self.client = Client()
        self.client.force_login(self.g["cliente_user"])

    def test_resubmit_rejected_row_reuses_pk_and_does_not_re_notify(self):
        # Pre-existing REJECTED row with the same monto_pagado.
        existing = PagoRealizado.objects.create(
            cuota=self.g["cuota"],
            monto_pagado=Decimal("120.00"),
            metodo_pago=PagoRealizado.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("120.00"),
            monto_fisico=Decimal("0"),
            comprobante_url="comprobantes_pagos/old_receipt.pdf",
            estado_verificacion=PagoRealizado.EstadoVerificacion.RECHAZADO,
            observacion_verificacion="Comprobante ilegible",
            verificado_por=self.g["admin_user"],
            fecha_verificacion=timezone.now(),
        )
        existing_pk = existing.pk

        with patch(
            "config.client_api_views.create_notification"
        ) as mock_create:
            response = self.client.post(
                _url(self.g["cuota"].pk),
                {
                    "paymentMethod": "VIRTUAL",
                    "amount": "120.00",
                    "receiptFile": _receipt(),
                },
            )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(PagoRealizado.objects.count(), 1, "row reused, not duplicated")
        existing.refresh_from_db()
        self.assertEqual(existing.pk, existing_pk)
        self.assertEqual(
            existing.estado_verificacion,
            PagoRealizado.EstadoVerificacion.PENDIENTE,
        )
        self.assertFalse(mock_create.called, "no notification on resubmission")


class ClientUploadPaymentReceiptOverPaymentTests(TestCase):
    """Over-payment guard: rejected for new rows; not re-checked on reuse."""

    def setUp(self):
        self.g = _ClientPaymentGraph.build()
        # Cover the cuota fully with an APROBADO row.
        PagoRealizado.objects.create(
            cuota=self.g["cuota"],
            monto_pagado=Decimal("120.00"),
            metodo_pago=PagoRealizado.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("120.00"),
            monto_fisico=Decimal("0"),
            comprobante_url="comprobantes_pagos/already_approved.pdf",
            estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO,
            verificado=True,
            verificado_por=self.g["admin_user"],
            fecha_verificacion=timezone.now(),
        )
        self.client = Client()
        self.client.force_login(self.g["cliente_user"])

    def test_over_payment_returns_400_and_creates_no_row(self):
        before = PagoRealizado.objects.count()
        response = self.client.post(
            _url(self.g["cuota"].pk),
            {
                "paymentMethod": "VIRTUAL",
                "amount": "50.00",
                "receiptFile": _receipt(),
            },
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoRealizado.objects.count(), before)
