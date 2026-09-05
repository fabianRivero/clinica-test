"""Endpoint tests for ``POST /api/admin/operaciones/<id>/finalizar/``
and ``POST /api/admin/operaciones/<id>/suspender/`` (operation-manual-closure).

Covers:
* 200 finalize on a fully-reconciled operation; audit fields persisted.
* 409 finalize when a precondition fails (citas pending, cuotas
  pendiente/vencida, monto mismatch) -> structured ``preconditions``
  payload in the body.
* 409 finalize from a non-EN_PROCESO source state -> plain ``detail``.
* 200 suspend unconditionally (no preconditions).
* 409 suspend from non-EN_PROCESO -> ``detail``.
* 403 non-admin caller.

Uses Django's ``Client`` + ``force_login`` (project convention —
``APIClient`` is not used in this suite).
"""

import json
from decimal import Decimal
from datetime import date, timedelta

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago
from catalogs.models import ServicioConfig, Sucursal, TipoServicio
from customers.models import Cliente
from operations.models import CitaMedica, Operacion


FINALIZAR_URL = "/api/admin/operaciones/{op_id}/finalizar/"
SUSPENDER_URL = "/api/admin/operaciones/{op_id}/suspender/"


def _post(client, url, payload=None):
    body = json.dumps(payload or {})
    return client.post(url, data=body, content_type="application/json")


class OperationClosureEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.rol_cliente = Rol.objects.create(rol="CLIENTE")
        cls.sucursal = Sucursal.objects.create(nombre="Central Closure API", activa=True)
        cls.admin = Usuario.objects.create_user(
            username="admin.closure.api",
            password="password123",
            primer_nombre="Admin",
            apellido_paterno="Closure",
            rol=cls.rol_admin,
            sucursal=cls.sucursal,
        )
        cls.non_admin = Usuario.objects.create_user(
            username="cliente.closure.api",
            password="password123",
            primer_nombre="Cliente",
            apellido_paterno="Closure",
            rol=cls.rol_cliente,
            sucursal=cls.sucursal,
        )
        tipo_servicio = TipoServicio.objects.create(tipo="Consulta Closure API")
        cls.servicio = ServicioConfig.objects.create(
            tipo_servicio=tipo_servicio,
            precio_base=Decimal("100.00"),
        )
        cls.cliente_user = Usuario.objects.create_user(
            username="paciente.closure.api",
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

    # ---- helpers ----

    def _add_cita(self, estado, sesiones_consume=True):
        cita = CitaMedica(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=timezone.now() + timedelta(days=1),
            estado=estado,
        )
        if estado == CitaMedica.Estado.CONFIRMADA:
            cita.metodo_confirmacion = CitaMedica.MetodoConfirmacion.MANUAL
        # The ``clean()`` guard rejects creates that would push sesiones
        # beyond ``operacion.sesiones_totales``. For tests that want a
        # "stuck" cita without bumping the total, use NO_ASISTIO (it
        # does not consume a session slot).
        cita.save()
        return cita

    def _add_cuota(self, nro, monto, estado):
        return CuotaPlanPago.objects.create(
            operacion=self.operacion,
            nro_cuota=nro,
            fecha_vencimiento=timezone.localdate() + timedelta(days=30 * nro),
            monto_programado=monto,
            estado=estado,
        )

    def _ready_operacion(self):
        """Create 5 CONFIRMADA citas + 1 PAGADO cuota so the operacion is
        finalize-ready."""
        for _ in range(5):
            self._add_cita(CitaMedica.Estado.CONFIRMADA)
        self._add_cuota(1, Decimal("100.00"), CuotaPlanPago.Estado.PAGADO)

    # ---- finalize success ----

    def test_finalize_success_returns_200_and_audit_fields(self):
        self.client_http.force_login(self.admin)
        self._ready_operacion()

        response = _post(
            self.client_http,
            FINALIZAR_URL.format(op_id=self.operacion.pk),
        )

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIn("detail", body)
        self.assertIn("operation", body)
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.Estado.FINALIZADA)
        self.assertEqual(self.operacion.finalized_by_id, self.admin.pk)
        self.assertEqual(
            self.operacion.finalization_kind,
            Operacion.FinalizationKind.MANUAL_FINALIZADA,
        )
        self.assertIsNotNone(self.operacion.finalized_at)

    # ---- finalize precondition failure ----

    def test_finalize_pending_cuota_returns_409_with_preconditions(self):
        self.client_http.force_login(self.admin)
        # 1 CONFIRMADA + 4 PROGRAMADA + 1 PENDIENTE cuota. With the
        # "only CONFIRMADA counts" rule, sesiones would also fail
        # (1 of 5 = MISSING 4), but this test specifically asserts the
        # cuota failure path. The 409 carries the full precondition
        # report so the frontend re-renders the modal.
        self._add_cita(CitaMedica.Estado.CONFIRMADA)
        for _ in range(4):
            self._add_cita(CitaMedica.Estado.PROGRAMADA)
        self._add_cuota(1, Decimal("100.00"), CuotaPlanPago.Estado.PENDIENTE)

        response = _post(
            self.client_http,
            FINALIZAR_URL.format(op_id=self.operacion.pk),
        )

        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertEqual(body["estado"], Operacion.Estado.EN_PROCESO)
        self.assertIn("preconditions", body)
        report = body["preconditions"]
        self.assertFalse(report["ok"])
        self.assertFalse(report["cuotas"]["ok"])
        self.assertEqual(len(report["cuotas"]["pending"]), 1)
        self.assertEqual(report["cuotas"]["pending"][0]["estado"], "PENDIENTE")
        # The PROGRAMADA citas are exposed in the diagnostic counts even
        # though they don't contribute to ``consumed``.
        self.assertEqual(report["sesiones"]["reserved"], 4)
        # Operacion state must NOT have mutated.
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.Estado.EN_PROCESO)
        self.assertIsNone(self.operacion.finalized_by_id)

    def test_finalize_sum_mismatch_returns_409_with_diff(self):
        self.client_http.force_login(self.admin)
        for _ in range(5):
            self._add_cita(CitaMedica.Estado.CONFIRMADA)
        self._add_cuota(1, Decimal("95.00"), CuotaPlanPago.Estado.NO_PAGADA)

        response = _post(
            self.client_http,
            FINALIZAR_URL.format(op_id=self.operacion.pk),
        )

        self.assertEqual(response.status_code, 409, response.content)
        report = response.json()["preconditions"]
        self.assertFalse(report["monto"]["ok"])
        self.assertEqual(report["monto"]["diff"], "5.00")

    def test_finalize_missing_sesiones_returns_409_with_sesiones(self):
        self.client_http.force_login(self.admin)
        # Only 3 of 5 CONFIRMADA -> sesiones.ok = False
        for _ in range(3):
            self._add_cita(CitaMedica.Estado.CONFIRMADA)
        self._add_cuota(1, Decimal("100.00"), CuotaPlanPago.Estado.PAGADO)

        response = _post(
            self.client_http,
            FINALIZAR_URL.format(op_id=self.operacion.pk),
        )

        self.assertEqual(response.status_code, 409, response.content)
        report = response.json()["preconditions"]
        self.assertFalse(report["sesiones"]["ok"])
        self.assertEqual(report["sesiones"]["missing"], 2)

    def test_finalize_programada_cita_blocks_closure(self):
        # Regression: a PROGRAMADA cita blocks closure even though the
        # admin "completed" the sesiones_totales count by reserving.
        # Only CONFIRMADA counts as a realized session.
        self.client_http.force_login(self.admin)
        # Override the default sesiones_totales=5 to keep the math
        # tight: 1 CONFIRMADA + 1 PROGRAMADA of 2 expected -> missing = 1.
        self.operacion.sesiones_totales = 2
        self.operacion.save(update_fields=["sesiones_totales", "updated_at"])
        self._add_cita(CitaMedica.Estado.CONFIRMADA)
        self._add_cita(CitaMedica.Estado.PROGRAMADA)
        self._add_cuota(1, Decimal("100.00"), CuotaPlanPago.Estado.PAGADO)

        response = _post(
            self.client_http,
            FINALIZAR_URL.format(op_id=self.operacion.pk),
        )

        self.assertEqual(response.status_code, 409, response.content)
        report = response.json()["preconditions"]
        self.assertFalse(report["sesiones"]["ok"])
        self.assertEqual(report["sesiones"]["missing"], 1)
        self.assertEqual(report["sesiones"]["reserved"], 1)

    # ---- finalize source-state rejection ----

    def test_finalize_from_wrong_source_returns_409_with_detail(self):
        self.client_http.force_login(self.admin)
        self.operacion.estado = Operacion.Estado.FINALIZADA
        self.operacion.save(update_fields=["estado", "updated_at"])

        response = _post(
            self.client_http,
            FINALIZAR_URL.format(op_id=self.operacion.pk),
        )

        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertIn("detail", body)
        self.assertEqual(body["estado"], Operacion.Estado.FINALIZADA)
        # No precondition payload on source-state rejection.
        self.assertNotIn("preconditions", body)

    # ---- suspend success + source-state ----

    def test_suspend_success_returns_200_with_audit(self):
        self.client_http.force_login(self.admin)
        # Even with broken preconditions, suspend succeeds.
        self._add_cita(CitaMedica.Estado.PROGRAMADA)
        self._add_cuota(1, Decimal("50.00"), CuotaPlanPago.Estado.VENCIDA)

        response = _post(
            self.client_http,
            SUSPENDER_URL.format(op_id=self.operacion.pk),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.Estado.SUSPENDIDA)
        self.assertEqual(
            self.operacion.finalization_kind,
            Operacion.FinalizationKind.MANUAL_SUSPENDIDA,
        )

    def test_suspend_from_wrong_source_returns_409(self):
        self.client_http.force_login(self.admin)
        self.operacion.estado = Operacion.Estado.FINALIZADA
        self.operacion.save(update_fields=["estado", "updated_at"])

        response = _post(
            self.client_http,
            SUSPENDER_URL.format(op_id=self.operacion.pk),
        )

        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertIn("detail", body)
        self.assertEqual(body["estado"], Operacion.Estado.FINALIZADA)
        self.assertNotIn("preconditions", body)

    # ---- 403 non-admin ----

    def test_finalize_non_admin_returns_403(self):
        self.client_http.force_login(self.non_admin)
        self._ready_operacion()

        response = _post(
            self.client_http,
            FINALIZAR_URL.format(op_id=self.operacion.pk),
        )

        self.assertEqual(response.status_code, 403, response.content)
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.Estado.EN_PROCESO)

    def test_suspend_non_admin_returns_403(self):
        self.client_http.force_login(self.non_admin)
        self._add_cita(CitaMedica.Estado.PROGRAMADA)

        response = _post(
            self.client_http,
            SUSPENDER_URL.format(op_id=self.operacion.pk),
        )

        self.assertEqual(response.status_code, 403, response.content)
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.Estado.EN_PROCESO)

    # ---- 404 ----

    def test_finalize_missing_operacion_returns_404(self):
        self.client_http.force_login(self.admin)
        response = _post(self.client_http, FINALIZAR_URL.format(op_id=99999))
        self.assertEqual(response.status_code, 404, response.content)

    def test_suspend_missing_operacion_returns_404(self):
        self.client_http.force_login(self.admin)
        response = _post(self.client_http, SUSPENDER_URL.format(op_id=99999))
        self.assertEqual(response.status_code, 404, response.content)
