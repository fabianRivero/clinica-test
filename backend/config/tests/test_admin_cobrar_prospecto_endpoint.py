"""Tests for the admin ``prospectos`` cobro + edit-precio endpoints.

Covers the follow-on to ``citas-pagos`` that extends the cobro surface to
``CitaProspecto`` (pre-conversion appointments). Two endpoints are exercised:

* ``POST /api/admin/prospectos/citas/<cita_id>/cobrar/``
  → ``admin_cobrar_prospect_medical_appointment``
* ``POST /api/admin/prospectos/citas/<cita_id>/precio/``
  → ``admin_update_prospect_medical_appointment_precio``

Coverage mirrors the cita-medica / cita-libre endpoint tests:

* **CobrarCitaProspectoTests** — FISICO / VIRTUAL / MIXTO happy paths;
  MIXTO mismatch → 400; ``precio == 0`` → 400; ``CANCELADA`` / ``NO_ASISTIO``
  → 400; over-payment → 400; cross-branch → 403; missing cita → 404;
  the cita FK on the resulting ``PagoCita`` is ``cita_prospecto`` (not the
  other two).
* **EditPrecioCitaProspectoTests** — admin can edit ``precio`` while no
  ``APROBADO`` row exists; once an ``APROBADO`` payment lands, the price
  is locked; negative / non-numeric values rejected.
"""

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import PagoCita
from catalogs.models import ServicioConfig, Sucursal, TipoServicio
from customers.models import Prospecto
from operations.models import CitaProspecto


CITA_PROSPECTO_COBRAR_URL = "/api/admin/prospectos/citas/{cita_id}/cobrar/"
CITA_PROSPECTO_PRECIO_URL = "/api/admin/prospectos/citas/{cita_id}/precio/"


def _build_branch(nombre):
    return Sucursal.objects.create(nombre=nombre, activa=True)


def _build_admin(username, branch, rol_name="ADMIN_SUCURSAL"):
    rol = Rol.objects.get_or_create(rol=rol_name)[0]
    return Usuario.objects.create_user(
        username=username,
        password="password123",
        rol=rol,
        sucursal=branch,
    )


def _build_cita_prospecto_graph(*, branch, precio, estado=CitaProspecto.Estado.PROGRAMADA):
    """Return a Prospecto + CitaProspecto + supporting graph in the given branch.

    Uses ``ServicioConfig`` without ``proc_estetico`` so the cita
    satisfies ``CitaProspecto.clean()`` (``proc_estetico must be null``).
    """
    rol = Rol.objects.get_or_create(rol="ADMIN_SUCURSAL")[0]
    admin = Usuario.objects.create_user(
        username=f"admin.prospecto.{branch.pk}",
        password="password123",
        rol=rol,
        sucursal=branch,
    )
    tipo = TipoServicio.objects.create(tipo=f"Consulta-Prospecto-{branch.pk}")
    service = ServicioConfig.objects.create(
        tipo_servicio=tipo,
        proc_estetico=None,
        precio_base=Decimal("180.00"),
    )
    prospecto = Prospecto.objects.create(
        primer_nombre="Prospecto",
        apellido_paterno="Test",
        telefono="70000000",
        estado=Prospecto.Estado.PASAJERO,
        sucursal_registro=branch,
    )
    cita = CitaProspecto.objects.create(
        prospecto=prospecto,
        servicio_config=service,
        sucursal=branch,
        fecha_hora=timezone.now() + timezone.timedelta(days=1),
        estado=estado,
        precio=precio,
    )
    return {
        "branch": branch,
        "admin": admin,
        "prospecto": prospecto,
        "cita": cita,
        "service": service,
    }


class CobrarCitaProspectoTests(TestCase):
    """Happy path + rejection paths on the prospect cobro endpoint."""

    def setUp(self):
        self.branch = _build_branch("Sucursal Prospecto A")
        self.g = _build_cita_prospecto_graph(
            branch=self.branch, precio=Decimal("150.00")
        )
        self.client = Client()
        self.client.force_login(self.g["admin"])

    def _receipt(self, name="receipt.pdf"):
        return SimpleUploadedFile(
            name, b"%PDF-test", content_type="application/pdf"
        )

    def _url(self):
        return CITA_PROSPECTO_COBRAR_URL.format(cita_id=self.g["cita"].pk)

    def _post(self, **extra):
        data = {"paymentMethod": "FISICO", "monto_pagado": "150.00"}
        data.update(extra)
        return self.client.post(self._url(), data)

    # -------------------------------------------------------------------------
    # Happy paths (one per method)
    # -------------------------------------------------------------------------

    def test_fisico_happy_path_creates_aprobado_pago_cita(self):
        response = self._post()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIn("payment", body)
        self.assertIn("appointment", body)
        self.assertEqual(PagoCita.objects.count(), 1)
        pago = PagoCita.objects.get()
        self.assertEqual(pago.estado_verificacion, PagoCita.EstadoVerificacion.APROBADO)
        # The XOR discriminator must be ``cita_prospecto`` (not the others).
        self.assertEqual(pago.cita_prospecto_id, self.g["cita"].pk)
        self.assertIsNone(pago.cita_medica_id)
        self.assertIsNone(pago.cita_cliente_libre_id)

    def test_virtual_with_receipt_happy_path(self):
        response = self._post(paymentMethod="VIRTUAL", receiptFile=self._receipt())
        self.assertEqual(response.status_code, 201, response.content)
        pago = PagoCita.objects.get()
        self.assertEqual(pago.metodo_pago, PagoCita.MetodoPago.VIRTUAL)
        self.assertEqual(pago.monto_virtual, Decimal("150.00"))
        self.assertEqual(pago.monto_fisico, Decimal("0"))

    def test_mixto_happy_path(self):
        response = self._post(
            paymentMethod="MIXTO",
            montoFisico="70.00",
            montoVirtual="80.00",
        )
        self.assertEqual(response.status_code, 201, response.content)
        pago = PagoCita.objects.get()
        self.assertEqual(pago.metodo_pago, PagoCita.MetodoPago.MIXTO)
        self.assertEqual(pago.monto_fisico, Decimal("70.00"))
        self.assertEqual(pago.monto_virtual, Decimal("80.00"))

    # -------------------------------------------------------------------------
    # Validation rejections
    # -------------------------------------------------------------------------

    def test_precio_zero_rejects_with_400(self):
        self.g["cita"].precio = Decimal("0")
        self.g["cita"].save(update_fields=["precio", "updated_at"])
        response = self._post()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("precio", response.json()["detail"].lower())
        self.assertEqual(PagoCita.objects.count(), 0)

    def test_mixto_breakdown_mismatch_rejects_with_400(self):
        response = self._post(
            paymentMethod="MIXTO",
            montoFisico="70.00",
            montoVirtual="70.00",  # 70+70 != 150
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), 0)

    def test_cancelada_state_rejects_with_400(self):
        self.g["cita"].estado = CitaProspecto.Estado.CANCELADA
        self.g["cita"].save(update_fields=["estado", "updated_at"])
        response = self._post()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), 0)

    def test_no_asistio_state_rejects_with_400(self):
        self.g["cita"].estado = CitaProspecto.Estado.NO_ASISTIO
        self.g["cita"].save(update_fields=["estado", "updated_at"])
        response = self._post()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), 0)

    def test_over_payment_rejects_with_400(self):
        # precio=150, try to charge 150 twice.
        first = self._post()
        self.assertEqual(first.status_code, 201, first.content)
        # Second cobro with the full precio → over-payment guard rejects.
        response = self._post()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), 1)

    def test_cross_branch_rejects_with_403(self):
        other_branch = _build_branch("Sucursal Prospecto B")
        other_admin = _build_admin("admin.prospecto.other", other_branch)
        client = Client()
        client.force_login(other_admin)
        response = client.post(
            self._url(),
            {"paymentMethod": "FISICO", "monto_pagado": "150.00"},
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(PagoCita.objects.count(), 0)

    def test_missing_cita_rejects_with_404(self):
        missing_url = CITA_PROSPECTO_COBRAR_URL.format(cita_id=99999)
        response = self.client.post(
            missing_url,
            {"paymentMethod": "FISICO", "monto_pagado": "150.00"},
        )
        self.assertEqual(response.status_code, 404, response.content)


class EditPrecioCitaProspectoTests(TestCase):
    """Edit-precio endpoint — locked once the first APROBADO row exists."""

    def setUp(self):
        self.branch = _build_branch("Sucursal Prospecto Edit")
        self.g = _build_cita_prospecto_graph(
            branch=self.branch, precio=Decimal("100.00")
        )
        self.client = Client()
        self.client.force_login(self.g["admin"])

    def _url(self):
        return CITA_PROSPECTO_PRECIO_URL.format(cita_id=self.g["cita"].pk)

    def _post(self, **extra):
        import json
        data = {"precio": "200.00"}
        data.update(extra)
        return self.client.post(
            self._url(),
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_edit_precio_succeeds_before_any_pago_aprobado(self):
        response = self._post(precio="250.00")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIn("appointment", body)
        self.g["cita"].refresh_from_db()
        self.assertEqual(self.g["cita"].precio, Decimal("250.00"))

    def test_edit_precio_rejects_negative_value(self):
        response = self._post(precio="-50.00")
        self.assertEqual(response.status_code, 400, response.content)

    def test_edit_precio_rejects_non_numeric_value(self):
        response = self._post(precio="abc")
        self.assertEqual(response.status_code, 400, response.content)

    def test_edit_precio_rejects_missing_value(self):
        import json
        response = self.client.post(
            self._url(),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_edit_precio_locked_after_first_aprobado_pago(self):
        # Register one APROBADO PagoCita first.
        self.g["cita"].precio = Decimal("150.00")
        self.g["cita"].save(update_fields=["precio", "updated_at"])
        PagoCita.objects.create(
            cita_prospecto=self.g["cita"],
            monto_pagado=Decimal("150.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("150.00"),
            monto_virtual=Decimal("0"),
            estado_verificacion=PagoCita.EstadoVerificacion.APROBADO,
            verificado_por=self.g["admin"],
            fecha_verificacion=timezone.now(),
        )
        # Attempt to edit the price now → 400.
        response = self._post(precio="200.00")
        self.assertEqual(response.status_code, 400, response.content)
        self.g["cita"].refresh_from_db()
        # Price stays at the value that was active when the APROBADO row
        # was registered (150), NOT the attempted 200.
        self.assertEqual(self.g["cita"].precio, Decimal("150.00"))

    def test_edit_precio_succeeds_after_a_rejected_pago_cita(self):
        # A RECHAZADO row must NOT lock the price — only APROBADO does.
        PagoCita.objects.create(
            cita_prospecto=self.g["cita"],
            monto_pagado=Decimal("50.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("50.00"),
            monto_virtual=Decimal("0"),
            estado_verificacion=PagoCita.EstadoVerificacion.RECHAZADO,
        )
        response = self._post(precio="300.00")
        self.assertEqual(response.status_code, 200, response.content)
        self.g["cita"].refresh_from_db()
        self.assertEqual(self.g["cita"].precio, Decimal("300.00"))