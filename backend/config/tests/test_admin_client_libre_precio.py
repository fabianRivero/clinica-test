"""Tests for the admin client free-medical-appointment endpoints after
the citas-pagos follow-on: optional ``precio`` at booking + edit-precio
endpoint.

These tests cover the two new pieces of the surface that the
``/cms/clientes/<id>`` "Reservar cita médica" section needs:

* The reserva endpoint now accepts an optional ``precio`` field so
  the admin can quote the cita price at booking time.
* A new ``POST /api/admin/citas-medicas-libres/<cita_id>/precio/``
  endpoint lets the admin edit the price after booking — locked once
  the first APROBADO PagoCita exists.

The cobro endpoint (``POST .../cobrar/``) was already covered by
``test_admin_cobrar_cita_endpoint.py`` and is not duplicated here.
"""

import json
from decimal import Decimal

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import PagoCita
from catalogs.models import ServicioConfig, Sucursal, TipoServicio
from customers.models import Cliente
from operations.models import CitaClienteLibre


CLIENT_LIBRE_RESERVAR_URL_TMPL = "/api/admin/clientes/{client_id}/cita-medica/reservar/"
CLIENT_LIBRE_PRECIO_URL_TMPL = "/api/admin/citas-medicas-libres/{cita_id}/precio/"


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


def _build_graph(*, branch, precio=Decimal("0")):
    """Return a Cliente + ServicioConfig + admin in the given branch."""
    admin = _admin("admin.libre", branch)
    tipo = TipoServicio.objects.create(tipo="Consulta-Libre")
    service = ServicioConfig.objects.create(
        tipo_servicio=tipo,
        proc_estetico=None,
        precio_base=Decimal("180.00"),
    )
    cliente_user = Usuario.objects.create_user(
        username="cliente.libre",
        password="password123",
    )
    cliente_user.sucursal = branch
    cliente_user.save()
    cliente = Cliente.objects.create(
        usuario=cliente_user,
        sucursal_origen=branch,
        fecha_nacimiento=timezone.localdate().replace(
            year=timezone.localdate().year - 25
        ),
        estado_cliente=Cliente.Estado.ACTIVO,
    )
    cita = CitaClienteLibre.objects.create(
        cliente=cliente,
        servicio_config=service,
        sucursal=branch,
        fecha_hora=timezone.now() + timezone.timedelta(days=2),
        estado=CitaClienteLibre.Estado.PROGRAMADA,
        precio=precio,
    )
    return {
        "branch": branch,
        "admin": admin,
        "cliente": cliente,
        "service": service,
        "cita": cita,
    }


class ReservarCitaLibrePrecioTests(TestCase):
    """POST /clientes/<id>/cita-medica/reservar/ accepts optional precio."""

    def setUp(self):
        self.branch = _branch("Sucursal Libre Reservar")
        self.g = _build_graph(branch=self.branch, precio=Decimal("0"))
        self.client = Client()
        self.client.force_login(self.g["admin"])

    def _reservar(self, **extra):
        payload = {
            "branchId": self.g["branch"].pk,
            "dateTime": (timezone.now() + timezone.timedelta(days=5)).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
        }
        payload.update(extra)
        return self.client.post(
            CLIENT_LIBRE_RESERVAR_URL_TMPL.format(client_id=self.g["cliente"].pk),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_reservar_without_precio_creates_with_zero(self):
        response = self._reservar()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        # The cita in the response carries the price the backend set.
        self.assertEqual(body["appointment"]["precio"], "Bs 0.00")

    def test_reservar_with_precio_creates_with_that_price(self):
        response = self._reservar(precio="80.00")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["appointment"]["precio"], "Bs 80.00")
        # Also verify it landed in the DB.
        cita_id = body["appointment"]["rawId"]
        cita = CitaClienteLibre.objects.get(pk=cita_id)
        self.assertEqual(cita.precio, Decimal("80.00"))

    def test_reservar_with_negative_precio_rejects(self):
        response = self._reservar(precio="-50.00")
        self.assertEqual(response.status_code, 400, response.content)

    def test_reservar_with_invalid_precio_rejects(self):
        response = self._reservar(precio="not-a-number")
        self.assertEqual(response.status_code, 400, response.content)


class EditPrecioCitaLibreTests(TestCase):
    """POST /citas-medicas-libres/<id>/precio/ mirrors prospecto behavior."""

    def setUp(self):
        self.branch = _branch("Sucursal Libre Edit")
        self.g = _build_graph(branch=self.branch, precio=Decimal("100.00"))
        self.client = Client()
        self.client.force_login(self.g["admin"])

    def _url(self):
        return CLIENT_LIBRE_PRECIO_URL_TMPL.format(cita_id=self.g["cita"].pk)

    def _post(self, **extra):
        data = {"precio": "200.00"}
        data.update(extra)
        return self.client.post(
            self._url(),
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_edit_precio_succeeds_before_any_aprobado(self):
        response = self._post(precio="250.00")
        self.assertEqual(response.status_code, 200, response.content)
        self.g["cita"].refresh_from_db()
        self.assertEqual(self.g["cita"].precio, Decimal("250.00"))

    def test_edit_precio_rejects_negative(self):
        response = self._post(precio="-30.00")
        self.assertEqual(response.status_code, 400, response.content)

    def test_edit_precio_locked_after_first_aprobado(self):
        PagoCita.objects.create(
            cita_cliente_libre=self.g["cita"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("100.00"),
            monto_virtual=Decimal("0"),
            estado_verificacion=PagoCita.EstadoVerificacion.APROBADO,
            verificado_por=self.g["admin"],
            fecha_verificacion=timezone.now(),
        )
        response = self._post(precio="300.00")
        self.assertEqual(response.status_code, 400, response.content)
        self.g["cita"].refresh_from_db()
        self.assertEqual(self.g["cita"].precio, Decimal("100.00"))

    def test_edit_precio_succeeds_after_a_rejected_pago_cita(self):
        PagoCita.objects.create(
            cita_cliente_libre=self.g["cita"],
            monto_pagado=Decimal("50.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("50.00"),
            monto_virtual=Decimal("0"),
            estado_verificacion=PagoCita.EstadoVerificacion.RECHAZADO,
        )
        response = self._post(precio="180.00")
        self.assertEqual(response.status_code, 200, response.content)
        self.g["cita"].refresh_from_db()
        self.assertEqual(self.g["cita"].precio, Decimal("180.00"))


class AdminClientDetailFreeAppointmentsTestTest(TestCase):
    """The admin client detail payload surfaces free appointments
    with their pago breakdown (precio / saldoPendiente / pagos[]).

    Locks the contract that the frontend 'Reservar cita medica' section
    depends on: free citas appear with the same shape as operation
    citas so the unified 'Sesiones' section can render both without a
    type switch.
    """

    def setUp(self):
        self.branch = _branch("Sucursal Libre Detail")
        self.g = _build_graph(branch=self.branch, precio=Decimal("120.00"))
        self.client = Client()
        self.client.force_login(self.g["admin"])

    def _detail(self):
        return self.client.get(f"/api/admin/clientes/{self.g['cliente'].pk}/")

    def test_free_cita_appears_in_admin_client_detail_with_precio(self):
        response = self._detail()
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        appts = body["appointments"]
        free = [a for a in appts if a.get("isFreeMedicalAppointment")]
        self.assertEqual(len(free), 1)
        self.assertEqual(free[0]["precio"], "Bs 120.00")
        self.assertEqual(free[0]["saldoPendiente"], "Bs 120.00")
        self.assertEqual(free[0]["pagos_count"], 0)
        self.assertEqual(free[0]["pagos"], [])

    def test_free_cita_with_aprobado_pago_surfaces_saldo_cero(self):
        PagoCita.objects.create(
            cita_cliente_libre=self.g["cita"],
            monto_pagado=Decimal("120.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("120.00"),
            monto_virtual=Decimal("0"),
            estado_verificacion=PagoCita.EstadoVerificacion.APROBADO,
            verificado_por=self.g["admin"],
            fecha_verificacion=timezone.now(),
        )
        response = self._detail()
        body = response.json()
        free = [a for a in body["appointments"] if a.get("isFreeMedicalAppointment")][0]
        self.assertEqual(free["precio"], "Bs 120.00")
        self.assertEqual(free["saldoPendiente"], "Bs 0.00")
        self.assertEqual(free["pagos_count"], 1)
        self.assertEqual(len(free["pagos"]), 1)
        self.assertEqual(free["pagos"][0]["estado_verificacion"], "APROBADO")