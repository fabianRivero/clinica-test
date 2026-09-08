"""Regression matrix for the manual-suspension lock + reactivacion flow.

Covers the bug where SUSPENDIDA operations still accepted mutations
on their citas and cuotas (cancelar / reprogramar / pendiente-biometria /
cobrar cita / registrar pago). All such calls must now return 409 with
``{detail, estado: "SUSPENDIDA"}`` so the frontend can prompt the admin
to reactivate the treatment before retrying.

Also covers the new ``POST /api/admin/operaciones/<id>/reactivar/``
endpoint: ``SUSPENDIDA -> EN_PROCESO`` clears the closure audit fields
so a subsequent ``cerrar_como_*`` call stamps them fresh.
"""
import json
from decimal import Decimal
from datetime import date, timedelta

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago, PagoRealizado
from catalogs.models import ServicioConfig, Sucursal, TipoServicio
from customers.models import Cliente
from operations.models import CitaMedica, Operacion


SUSPENDER_URL = "/api/admin/operaciones/{op_id}/suspender/"
REACTIVAR_URL = "/api/admin/operaciones/{op_id}/reactivar/"
CANCELAR_CITA_URL = "/api/admin/citas/{cita_id}/cancelar/"
PENDIENTE_BIOMETRIA_URL = "/api/admin/citas/{cita_id}/pendiente-biometria/"
REPROGRAMAR_CITA_URL = "/api/admin/citas/{cita_id}/reprogramar/"
COBRAR_CITA_URL = "/api/admin/operaciones/{op_id}/citas/{cita_id}/cobrar/"
PAGAR_CUOTA_URL = "/api/admin/pagos/cuotas/{cuota_id}/pagos/"


def _post(client, url, payload=None):
    body = json.dumps(payload or {})
    return client.post(url, data=body, content_type="application/json")


class OperationSuspensionBlocksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        # ``es_principal=True`` so ``get_user_branch`` returns this
        # sucursal when the test client doesn't send an
        # ``X-Selected-Branch-Id`` header (default in unit tests).
        cls.sucursal = Sucursal.objects.create(
            nombre="Central Suspension Blocks",
            activa=True,
            es_principal=True,
        )
        cls.admin = Usuario.objects.create_user(
            username="admin.suspension.blocks",
            password="password123",
            primer_nombre="Admin",
            apellido_paterno="Suspension",
            rol=cls.rol_admin,
            sucursal=cls.sucursal,
        )
        tipo_servicio = TipoServicio.objects.create(tipo="Consulta Suspension Blocks")
        cls.servicio = ServicioConfig.objects.create(
            tipo_servicio=tipo_servicio,
            precio_base=Decimal("100.00"),
        )
        cls.cliente_user = Usuario.objects.create_user(
            username="paciente.suspension.blocks",
            password="password123",
        )
        cls.cliente_user.sucursal = cls.sucursal
        cls.cliente_user.save()
        cls.cliente = Cliente.objects.create(
            usuario=cls.cliente_user,
            sucursal_origen=cls.sucursal,
            fecha_nacimiento=date(1990, 1, 1),
        )

    def setUp(self):
        self.client_http = Client()
        self.operacion = Operacion.objects.create(
            paciente=self.cliente,
            servicio_config=self.servicio,
            precio_total=Decimal("100.00"),
            sesiones_totales=5,
            cuotas_totales=1,
            estado=Operacion.Estado.EN_PROCESO,
        )
        self.cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=timezone.now() + timedelta(days=1),
            estado=CitaMedica.Estado.PROGRAMADA,
            precio=Decimal("50.00"),
        )
        self.cuota = CuotaPlanPago.objects.create(
            operacion=self.operacion,
            nro_cuota=1,
            fecha_vencimiento=timezone.localdate() + timedelta(days=30),
            monto_programado=Decimal("100.00"),
            estado=CuotaPlanPago.Estado.PENDIENTE,
        )

    def _suspend(self):
        """Move the operacion to SUSPENDIDA via the public endpoint."""
        self.client_http.force_login(self.admin)
        response = _post(self.client_http, SUSPENDER_URL.format(op_id=self.operacion.pk))
        self.assertEqual(response.status_code, 200, response.content)
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.Estado.SUSPENDIDA)

    # ---- reactivar endpoint ----

    def test_reactivar_suspended_returns_200_and_clears_audit(self):
        self.client_http.force_login(self.admin)
        self._suspend()
        self.operacion.refresh_from_db()
        self.assertEqual(
            self.operacion.finalization_kind,
            Operacion.FinalizationKind.MANUAL_SUSPENDIDA,
        )
        self.assertIsNotNone(self.operacion.finalized_by_id)

        response = _post(self.client_http, REACTIVAR_URL.format(op_id=self.operacion.pk))

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIn("detail", body)
        self.assertIn("operation", body)
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.Estado.EN_PROCESO)
        # Closure audit trail cleared so the next cerrar_como_* stamps fresh.
        self.assertIsNone(self.operacion.finalized_by_id)
        self.assertIsNone(self.operacion.finalized_at)
        self.assertIsNone(self.operacion.finalization_kind)

    def test_reactivar_from_wrong_source_returns_409(self):
        self.client_http.force_login(self.admin)
        # Operacion is still EN_PROCESO (default setUp); reactivation
        # must reject the source-state mismatch.
        response = _post(self.client_http, REACTIVAR_URL.format(op_id=self.operacion.pk))

        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertIn("detail", body)
        self.assertEqual(body["estado"], Operacion.Estado.EN_PROCESO)
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.Estado.EN_PROCESO)

    def test_reactivar_missing_operacion_returns_404(self):
        self.client_http.force_login(self.admin)
        response = _post(self.client_http, REACTIVAR_URL.format(op_id=99999))
        self.assertEqual(response.status_code, 404, response.content)

    def test_reactivar_non_admin_returns_403(self):
        # Set up a non-admin staff user; ensure 403 not 200.
        rol_cliente = Rol.objects.create(rol="CLIENTE_REACT")
        non_admin = Usuario.objects.create_user(
            username="cliente.react",
            password="password123",
            rol=rol_cliente,
        )
        self.client_http.force_login(non_admin)
        response = _post(self.client_http, REACTIVAR_URL.format(op_id=self.operacion.pk))
        self.assertEqual(response.status_code, 403, response.content)

    # ---- bloqueo de endpoints cuando operacion SUSPENDIDA ----

    def test_cancelar_cita_blocked_when_suspended(self):
        self.client_http.force_login(self.admin)
        self._suspend()

        response = _post(self.client_http, CANCELAR_CITA_URL.format(cita_id=self.cita.pk))

        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertIn("detail", body)
        self.assertEqual(body["estado"], Operacion.Estado.SUSPENDIDA)
        # State preserved: cita still PROGRAMADA.
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.PROGRAMADA)

    def test_pendiente_biometria_blocked_when_suspended(self):
        self.client_http.force_login(self.admin)
        self._suspend()

        response = _post(self.client_http, PENDIENTE_BIOMETRIA_URL.format(cita_id=self.cita.pk))

        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertEqual(body["estado"], Operacion.Estado.SUSPENDIDA)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.PROGRAMADA)

    def test_reprogramar_cita_blocked_when_suspended(self):
        self.client_http.force_login(self.admin)
        self._suspend()

        payload = {"dateTime": (timezone.now() + timedelta(days=2)).isoformat()}
        response = _post(self.client_http, REPROGRAMAR_CITA_URL.format(cita_id=self.cita.pk), payload)

        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertEqual(body["estado"], Operacion.Estado.SUSPENDIDA)
        self.cita.refresh_from_db()
        # ``fecha_hora`` is the discriminator that would change; assert
        # it survived by reading the original delta-day-1 value.
        self.assertAlmostEqual(
            (self.cita.fecha_hora - timezone.now()).total_seconds(),
            timedelta(days=1).total_seconds(),
            delta=2,
        )

    def test_cobrar_cita_blocked_when_suspended(self):
        self.client_http.force_login(self.admin)
        self._suspend()

        payload = {
            "paymentMethod": "FISICO",
            "montoFisico": "50.00",
            "montoVirtual": "0.00",
            "amount": "50.00",
        }
        response = _post(
            self.client_http,
            COBRAR_CITA_URL.format(op_id=self.operacion.pk, cita_id=self.cita.pk),
            payload,
        )

        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertEqual(body["estado"], Operacion.Estado.SUSPENDIDA)
        self.assertEqual(PagoRealizado.objects.filter(cuota__operacion=self.operacion).count(), 0)

    def test_registrar_pago_cuota_blocked_when_suspended(self):
        self.client_http.force_login(self.admin)
        self._suspend()

        payload = {
            "paymentMethod": "FISICO",
            "montoFisico": "100.00",
            "montoVirtual": "0.00",
            "montoPagado": "100.00",
        }
        response = _post(self.client_http, PAGAR_CUOTA_URL.format(cuota_id=self.cuota.pk), payload)

        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertEqual(body["estado"], Operacion.Estado.SUSPENDIDA)
        self.assertEqual(PagoRealizado.objects.filter(cuota=self.cuota).count(), 0)

    def test_operacion_reactivated_then_mutaciones_work_again(self):
        # After reactivating, the same calls must succeed (the lock is
        # a state-machine property, not a permanent flag).
        self.client_http.force_login(self.admin)
        self._suspend()

        response = _post(self.client_http, REACTIVAR_URL.format(op_id=self.operacion.pk))
        self.assertEqual(response.status_code, 200, response.content)

        response = _post(self.client_http, CANCELAR_CITA_URL.format(cita_id=self.cita.pk))
        self.assertEqual(response.status_code, 200, response.content)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.CANCELADA)