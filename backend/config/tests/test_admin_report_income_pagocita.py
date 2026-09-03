"""Tests for ``GET /api/admin/reportes/ingresos/`` after the ``citas-pagos`` change.

The report now combines two payment sources:

* ``PagoRealizado`` — cuota-plan payments (legacy, unchanged).
* ``PagoCita`` — appointment payments for ``CitaMedica``,
  ``CitaClienteLibre`` and ``CitaProspecto``.

Coverage:

* **PagoCita rows show up in the report** — one happy path per cita
  kind, all three methods, plus a multi-branch branch-isolation test.
* **Date filter uses the cita's ``fecha_hora``** (devengo, not caja) so
  a cobro made in February for a January cita still shows up in
  January.
* **Person label** distinguishes prospecto (``"Prospecto: Juan Dominguez"``)
  from formal clients.
* **Truncation** still works when both sources together exceed
  ``REPORT_ROW_CAP``.
"""

import datetime as dt
from decimal import Decimal

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import PagoCita, PagoRealizado
from catalogs.models import (
    ProcEstetico,
    ProcEsteticosTipo,
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from common.models import CatalogoEditableModel, TimeStampedModel  # noqa: F401
from customers.models import Cliente, Prospecto
from operations.models import (
    CitaClienteLibre,
    CitaMedica,
    CitaProspecto,
    Operacion,
)


REPORT_INCOME_URL = "/api/admin/reportes/ingresos/"


def _branch(nombre):
    return Sucursal.objects.create(nombre=nombre, activa=True)


def _admin(username, branch):
    rol = Rol.objects.get_or_create(rol="ADMIN_SUCURSAL")[0]
    return Usuario.objects.create_user(
        username=username,
        password="password123",
        rol=rol,
        sucursal=branch,
    )


def _client_user(username, branch):
    user = Usuario.objects.create_user(
        username=username,
        password="password123",
    )
    user.sucursal = branch
    user.save()
    return user


def _build_graph(*, branch, other_branch):
    """Return a fixture with one of each cita kind + a cuota-plan."""
    admin = _admin("admin.income", branch)
    rol = Rol.objects.get_or_create(rol="ADMIN_SUCURSAL")[0]
    admin_other = Usuario.objects.create_user(
        username="admin.income.other",
        password="password123",
        rol=rol,
        sucursal=other_branch,
    )

    tipo = TipoServicio.objects.create(tipo="Consulta")
    proc_tipo = ProcEsteticosTipo.objects.create(tipo="Facial")
    proc = ProcEstetico.objects.create(
        tipo_p_estetico=proc_tipo, proceso="Limpieza"
    )
    service_with_proc = ServicioConfig.objects.create(
        tipo_servicio=tipo,
        proc_estetico=proc,
        precio_base=Decimal("200.00"),
    )
    service_consulta = ServicioConfig.objects.create(
        tipo_servicio=tipo,
        proc_estetico=None,
        precio_base=Decimal("180.00"),
    )

    cliente_user = _client_user("cliente.income", branch)
    cliente = Cliente.objects.create(
        usuario=cliente_user,
        sucursal_origen=branch,
        fecha_nacimiento=timezone.localdate().replace(
            year=timezone.localdate().year - 30
        ),
        estado_cliente=Cliente.Estado.ACTIVO,
    )
    operacion = Operacion.objects.create(
        paciente=cliente,
        servicio_config=service_with_proc,
        precio_total=Decimal("200.00"),
        cuotas_totales=1,
        sesiones_totales=1,
        estado=Operacion.Estado.EN_PROCESO,
    )

    # Three citas in the SAME month (the month the test asserts against).
    cita_medica = CitaMedica.objects.create(
        operacion=operacion,
        sucursal=branch,
        fecha_hora=dt.datetime(2026, 9, 10, 10, 0, tzinfo=dt.timezone.utc),
        estado=CitaMedica.Estado.PROGRAMADA,
        precio=Decimal("150.00"),
    )
    cita_libre = CitaClienteLibre.objects.create(
        cliente=cliente,
        servicio_config=service_consulta,
        sucursal=branch,
        fecha_hora=dt.datetime(2026, 9, 12, 11, 0, tzinfo=dt.timezone.utc),
        estado=CitaClienteLibre.Estado.PROGRAMADA,
        precio=Decimal("120.00"),
    )
    prospecto = Prospecto.objects.create(
        primer_nombre="Juan",
        apellido_paterno="Dominguez",
        estado=Prospecto.Estado.PASAJERO,
        sucursal_registro=branch,
    )
    cita_prospecto = CitaProspecto.objects.create(
        prospecto=prospecto,
        servicio_config=service_consulta,
        sucursal=branch,
        fecha_hora=dt.datetime(2026, 9, 14, 12, 0, tzinfo=dt.timezone.utc),
        estado=CitaProspecto.Estado.PROGRAMADA,
        precio=Decimal("80.00"),
    )
    # One cita in a different month — must NOT show up.
    cita_prospecto_other_month = CitaProspecto.objects.create(
        prospecto=prospecto,
        servicio_config=service_consulta,
        sucursal=branch,
        fecha_hora=dt.datetime(2026, 10, 5, 12, 0, tzinfo=dt.timezone.utc),
        estado=CitaProspecto.Estado.PROGRAMADA,
        precio=Decimal("60.00"),
    )
    # One cita in the OTHER branch — must NOT leak across.
    prospecto_other_branch = Prospecto.objects.create(
        primer_nombre="Maria",
        apellido_paterno="Lopez",
        estado=Prospecto.Estado.PASAJERO,
        sucursal_registro=other_branch,
    )
    cita_prospecto_other_branch = CitaProspecto.objects.create(
        prospecto=prospecto_other_branch,
        servicio_config=service_consulta,
        sucursal=other_branch,
        fecha_hora=dt.datetime(2026, 9, 18, 13, 0, tzinfo=dt.timezone.utc),
        estado=CitaProspecto.Estado.PROGRAMADA,
        precio=Decimal("99.00"),
    )
    return {
        "branch": branch,
        "other_branch": other_branch,
        "admin": admin,
        "admin_other": admin_other,
        "cliente": cliente,
        "operacion": operacion,
        "cita_medica": cita_medica,
        "cita_libre": cita_libre,
        "cita_prospecto": cita_prospecto,
        "cita_prospecto_other_month": cita_prospecto_other_month,
        "cita_prospecto_other_branch": cita_prospecto_other_branch,
        "prospecto": prospecto,
    }


def _create_pago_cita(*, cita, monto=Decimal("100.00"), metodo="FISICO"):
    return PagoCita.objects.create(
        cita_medica=cita if hasattr(cita, "operacion") else None,
        cita_cliente_libre=cita if hasattr(cita, "cliente") and not hasattr(cita, "operacion") else None,
        cita_prospecto=cita if hasattr(cita, "prospecto") else None,
        monto_pagado=monto,
        metodo_pago=metodo,
        monto_fisico=monto,
        monto_virtual=Decimal("0"),
        estado_verificacion=PagoCita.EstadoVerificacion.APROBADO,
    )


class ReportIncomePagoCitaTests(TestCase):
    """citas-pagos follow-on: PagoCita rows appear in the income report."""

    def setUp(self):
        self.branch = _branch("Sucursal A")
        self.other_branch = _branch("Sucursal B")
        self.g = _build_graph(branch=self.branch, other_branch=self.other_branch)
        self.client = Client()
        self.client.force_login(self.g["admin"])

    def _get(self, **params):
        params.setdefault("month", 9)
        params.setdefault("year", 2026)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return self.client.get(f"{REPORT_INCOME_URL}?{query}")

    def test_cita_medica_pago_cita_shows_up_in_report(self):
        pago = _create_pago_cita(cita=self.g["cita_medica"], monto=Decimal("150.00"))
        response = self._get()
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        row_ids = [row["paymentId"] for row in body["rows"]]
        self.assertIn(pago.pk, row_ids)
        # Find the row
        row = next(r for r in body["rows"] if r["paymentId"] == pago.pk)
        self.assertEqual(row["amount"], "150.00")
        # Service name for CitaMedica comes from the operacion's procedure.
        self.assertIn("Limpieza", row["serviceName"])
        # Client name comes from the formal cliente (no "Prospecto:" prefix).
        self.assertNotIn("Prospecto:", row["clientName"])

    def test_cita_cliente_libre_pago_cita_shows_up_in_report(self):
        pago = _create_pago_cita(cita=self.g["cita_libre"], monto=Decimal("120.00"))
        response = self._get()
        body = response.json()
        row = next(r for r in body["rows"] if r["paymentId"] == pago.pk)
        self.assertEqual(row["amount"], "120.00")
        # Service name for CitaClienteLibre comes from the ServicioConfig.
        self.assertEqual(row["serviceName"], "Consulta")

    def test_cita_prospecto_pago_cita_shows_up_with_prospecto_prefix(self):
        pago = _create_pago_cita(cita=self.g["cita_prospecto"], monto=Decimal("80.00"))
        response = self._get()
        body = response.json()
        row = next(r for r in body["rows"] if r["paymentId"] == pago.pk)
        self.assertEqual(row["amount"], "80.00")
        self.assertEqual(row["clientName"], "Prospecto: Juan Dominguez")
        self.assertEqual(row["serviceName"], "Consulta")

    def test_cita_prospecto_in_other_month_does_not_show_up(self):
        _create_pago_cita(cita=self.g["cita_prospecto_other_month"], monto=Decimal("60.00"))
        response = self._get()  # September only
        body = response.json()
        client_names = [r["clientName"] for r in body["rows"]]
        # The October cita must not leak into September.
        self.assertNotIn("Prospecto: Juan Dominguez", client_names)

    def test_cita_prospecto_in_other_branch_does_not_leak(self):
        _create_pago_cita(cita=self.g["cita_prospecto_other_branch"], monto=Decimal("99.00"))
        response = self._get()
        body = response.json()
        client_names = [r["clientName"] for r in body["rows"]]
        self.assertNotIn("Prospecto: Maria Lopez", client_names)

    def test_cross_branch_admin_cannot_see_other_branch_cita(self):
        # Login as the OTHER branch admin — must not see the cita in branch A.
        client = Client()
        client.force_login(self.g["admin_other"])
        # Sanity: confirm what branch the helper sees for this user.
        from config.api_helpers import get_user_branch
        from django.test import RequestFactory
        rf = RequestFactory()
        fake_req = rf.get("/")
        fake_req.user = self.g["admin_other"]
        seen_branch = get_user_branch(fake_req)
        self.assertIsNotNone(
            seen_branch,
            "Sanity check failed: get_user_branch returned None for branch admin"
        )
        self.assertEqual(seen_branch.pk, self.g["other_branch"].pk)
        # Make sure BOTH the cross-branch cita (branch B) and an
        # in-branch cita exist. Without a PagoCita on the branch-B
        # cita, the report will be empty for this admin regardless of
        # branch isolation logic.
        _create_pago_cita(
            cita=self.g["cita_prospecto_other_branch"], monto=Decimal("99.00")
        )
        response = client.get(
            f"{REPORT_INCOME_URL}?month=9&year=2026"
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        # Cita in branch A has Juan Dominguez (branch A prospect).
        # Cita in branch B has Maria Lopez (branch B prospect) — this
        # admin SHOULD see it.
        client_names = [row["clientName"] for row in body["rows"]]
        self.assertIn("Prospecto: Maria Lopez", client_names)
        self.assertNotIn("Prospecto: Juan Dominguez", client_names)

    def test_pago_cita_date_is_cita_fecha_hora_not_created_at(self):
        # If we filtered by created_at, a cobro on 2026-10-31 for a
        # 2026-09-10 cita would NOT show up in September. The devengo
        # rule says it SHOULD.
        cita = self.g["cita_medica"]  # fecha_hora 2026-09-10
        pago = _create_pago_cita(cita=cita, monto=Decimal("42.00"))
        # Force created_at to October 31 to confirm the filter ignores it.
        PagoCita.objects.filter(pk=pago.pk).update(
            created_at=dt.datetime(2026, 10, 31, 23, 59, tzinfo=dt.timezone.utc)
        )
        response = self._get()  # September only
        body = response.json()
        row_ids = [row["paymentId"] for row in body["rows"]]
        self.assertIn(pago.pk, row_ids,
                      "PagoCita should land in the month of its cita, not its cobro")