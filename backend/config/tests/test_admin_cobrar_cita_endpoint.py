"""Tests for the admin ``cobrar`` endpoints landing in PR 2 of ``citas-pagos``.

Two endpoints share the same ``PagoCita`` model + serializers, so they are
exercised together:

* ``POST /api/admin/operaciones/<operacion_id>/citas/<cita_id>/cobrar/``
  → ``OperacionesViewSet.cobrar_cita`` (charges a ``CitaMedica``).
* ``POST /api/admin/citas-medicas-libres/<cita_id>/cobrar/``
  → ``FreeMedicalAppointmentViewSet.cobrar`` (charges a ``CitaClienteLibre``).

Coverage:

* **EndpointTests** — FISICO / VIRTUAL / MIXTO happy paths on both
  endpoints; MIXTO mismatch → 400; ``precio == 0`` → 400;
  ``CANCELADA`` / ``NO_ASISTIO`` → 400; over-payment → 400; cross-branch
  → 403; missing cita → 404.
* **ReadPayloadTests** — APROBADO row surfaces the right
  ``saldoPendiente`` and ``pagos_count`` in the cita payload returned by
  the cobrar endpoint; cancellation preserves rows and rejects new
  cobrars.
* **ReceiptPathTests** — uploaded file lands under
  ``comprobantes_citas/YYYY/MM/``, never ``comprobantes_pagos/``.

The factory helpers reuse the existing graph patterns from
``backend/billing/tests/`` (a branch + admin + cliente + operacion +
cita, with a second branch for the cross-branch test) and use Django's
``Client`` + ``force_login`` (project convention — ``APIClient`` is not
used in the existing suite).
"""

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import PagoCita
from catalogs.models import (
    ProcEstetico,
    ProcEsteticosTipo,
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from customers.models import Cliente
from operations.models import CitaClienteLibre, CitaMedica, Operacion


CITA_MEDICA_COBRAR_URL = (
    "/api/admin/operaciones/{op_id}/citas/{cita_id}/cobrar/"
)
CITA_LIBRE_COBRAR_URL = (
    "/api/admin/citas-medicas-libres/{cita_id}/cobrar/"
)


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


def _build_cita_medica_graph(*, branch, precio):
    """Return a CitaMedica + supporting graph in the given branch."""
    rol = Rol.objects.get_or_create(rol="ADMIN_SUCURSAL")[0]
    admin = Usuario.objects.create_user(
        username=f"admin.{branch.pk}",
        password="password123",
        rol=rol,
        sucursal=branch,
    )
    tipo = TipoServicio.objects.create(tipo=f"Tratamiento-{branch.pk}")
    proc_tipo = ProcEsteticosTipo.objects.create(tipo=f"Facial-{branch.pk}")
    proc = ProcEstetico.objects.create(
        tipo_p_estetico=proc_tipo, proceso=f"Limpieza-{branch.pk}"
    )
    service = ServicioConfig.objects.create(
        tipo_servicio=tipo,
        proc_estetico=proc,
        precio_base=Decimal("240.00"),
    )
    cliente_user = Usuario.objects.create_user(
        username=f"paciente.{branch.pk}",
        password="password123",
    )
    cliente_user.sucursal = branch
    cliente_user.save()
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
        servicio_config=service,
        precio_total=Decimal("240.00"),
        cuotas_totales=2,
        sesiones_totales=2,
        estado=Operacion.Estado.EN_PROCESO,
    )
    cita = CitaMedica.objects.create(
        operacion=operacion,
        sucursal=branch,
        fecha_hora=timezone.now() + timezone.timedelta(days=1),
        estado=CitaMedica.Estado.PROGRAMADA,
        precio=precio,
    )
    return {
        "branch": branch,
        "admin": admin,
        "operacion": operacion,
        "cita": cita,
    }


def _build_cita_libre_graph(*, branch, precio):
    """Return a CitaClienteLibre + supporting graph in the given branch."""
    rol = Rol.objects.get_or_create(rol="ADMIN_SUCURSAL")[0]
    admin = Usuario.objects.create_user(
        username=f"admin.libre.{branch.pk}",
        password="password123",
        rol=rol,
        sucursal=branch,
    )
    tipo = TipoServicio.objects.create(tipo=f"Consulta-{branch.pk}")
    service = ServicioConfig.objects.create(
        tipo_servicio=tipo,
        proc_estetico=None,
        precio_base=Decimal("180.00"),
    )
    cliente_user = Usuario.objects.create_user(
        username=f"paciente.libre.{branch.pk}",
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
        "cita": cita,
    }


class CobrarCitaMedicaEndpointTests(TestCase):
    """Happy path + rejection paths on ``OperacionesViewSet.cobrar_cita``."""

    def setUp(self):
        self.branch = _build_branch("Sucursal A")
        self.g = _build_cita_medica_graph(
            branch=self.branch, precio=Decimal("200.00")
        )
        self.client = Client()
        self.client.force_login(self.g["admin"])

    def _receipt(self, name="receipt.pdf"):
        return SimpleUploadedFile(
            name, b"%PDF-test", content_type="application/pdf"
        )

    def _url(self):
        return CITA_MEDICA_COBRAR_URL.format(
            op_id=self.g["operacion"].pk, cita_id=self.g["cita"].pk
        )

    def _post(self, **extra):
        data = {"paymentMethod": "FISICO", "monto_pagado": "200.00"}
        data.update(extra)
        return self.client.post(self._url(), data)

    # -------------------------------------------------------------------------
    # Happy paths (one per method)
    # -------------------------------------------------------------------------

    def test_fisico_happy_path_returns_201_and_aprobado_row(self):
        response = self._post()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIn("payment", body)
        self.assertIn("appointment", body)
        self.assertEqual(PagoCita.objects.count(), 1)
        pago = PagoCita.objects.get()
        self.assertEqual(pago.estado_verificacion, PagoCita.EstadoVerificacion.APROBADO)
        self.assertEqual(pago.metodo_pago, PagoCita.MetodoPago.FISICO)
        self.assertEqual(pago.monto_pagado, Decimal("200.00"))
        self.assertEqual(pago.monto_fisico, Decimal("200.00"))
        self.assertEqual(pago.monto_virtual, Decimal("0"))
        self.assertEqual(pago.cita_medica_id, self.g["cita"].pk)

    def test_virtual_happy_path_no_receipt_admins_collected_in_person(self):
        response = self._post(paymentMethod="VIRTUAL")
        self.assertEqual(response.status_code, 201, response.content)
        pago = PagoCita.objects.get()
        self.assertEqual(pago.metodo_pago, PagoCita.MetodoPago.VIRTUAL)
        self.assertEqual(pago.monto_virtual, Decimal("200.00"))
        self.assertEqual(pago.monto_fisico, Decimal("0"))

    def test_virtual_happy_path_with_receipt(self):
        response = self._post(
            paymentMethod="VIRTUAL", receiptFile=self._receipt()
        )
        self.assertEqual(response.status_code, 201, response.content)
        pago = PagoCita.objects.get()
        self.assertTrue(bool(pago.comprobante_url))

    def test_mixto_happy_path_persists_breakdown(self):
        response = self._post(
            paymentMethod="MIXTO",
            montoFisico="80.00",
            montoVirtual="120.00",
        )
        self.assertEqual(response.status_code, 201, response.content)
        pago = PagoCita.objects.get()
        self.assertEqual(pago.metodo_pago, PagoCita.MetodoPago.MIXTO)
        self.assertEqual(pago.monto_fisico, Decimal("80.00"))
        self.assertEqual(pago.monto_virtual, Decimal("120.00"))
        self.assertEqual(pago.monto_pagado, Decimal("200.00"))

    # -------------------------------------------------------------------------
    # Rejections
    # -------------------------------------------------------------------------

    def test_mixto_breakdown_mismatch_returns_400(self):
        before = PagoCita.objects.count()
        response = self._post(
            paymentMethod="MIXTO",
            montoFisico="40.00",
            montoVirtual="50.00",  # 40+50=90, not 200
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), before)

    def test_precio_zero_returns_400(self):
        cita = self.g["cita"]
        cita.precio = Decimal("0")
        cita.save()
        before = PagoCita.objects.count()
        response = self._post()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), before)

    def test_cancelada_returns_400(self):
        cita = self.g["cita"]
        cita.estado = CitaMedica.Estado.CANCELADA
        cita.save()
        before = PagoCita.objects.count()
        response = self._post()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), before)

    def test_no_asistio_returns_400(self):
        cita = self.g["cita"]
        cita.estado = CitaMedica.Estado.NO_ASISTIO
        cita.save()
        before = PagoCita.objects.count()
        response = self._post()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), before)

    def test_over_payment_returns_400(self):
        # precio=200; one APROBADO row of 150; new cobro of 100 → overpay.
        PagoCita.objects.create(
            cita_medica=self.g["cita"],
            monto_pagado=Decimal("150.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("150.00"),
            monto_virtual=Decimal("0"),
            estado_verificacion=PagoCita.EstadoVerificacion.APROBADO,
            verificado_por=self.g["admin"],
            fecha_verificacion=timezone.now(),
        )
        before = PagoCita.objects.count()
        response = self._post(monto_pagado="100.00")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), before)

    def test_cross_branch_returns_403(self):
        # Build a separate branch + admin and try to charge this cita.
        other = _build_branch("Sucursal B")
        other_admin = _build_admin("admin.b", other)
        client_b = Client()
        client_b.force_login(other_admin)
        before = PagoCita.objects.count()
        response = client_b.post(
            self._url(),
            {"paymentMethod": "FISICO", "monto_pagado": "200.00"},
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(PagoCita.objects.count(), before)

    def test_missing_cita_returns_404(self):
        before = PagoCita.objects.count()
        url = CITA_MEDICA_COBRAR_URL.format(
            op_id=self.g["operacion"].pk, cita_id=999999
        )
        response = self.client.post(
            url, {"paymentMethod": "FISICO", "monto_pagado": "200.00"}
        )
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(PagoCita.objects.count(), before)


class CobrarCitaLibreEndpointTests(TestCase):
    """Mirror the CitaMedica suite for ``FreeMedicalAppointmentViewSet.cobrar``."""

    def setUp(self):
        self.branch = _build_branch("Sucursal Libre")
        self.g = _build_cita_libre_graph(
            branch=self.branch, precio=Decimal("180.00")
        )
        self.client = Client()
        self.client.force_login(self.g["admin"])

    def _url(self):
        return CITA_LIBRE_COBRAR_URL.format(cita_id=self.g["cita"].pk)

    def _post(self, **extra):
        data = {"paymentMethod": "FISICO", "monto_pagado": "180.00"}
        data.update(extra)
        return self.client.post(self._url(), data)

    def test_fisico_happy_path_returns_201_and_aprobado_row(self):
        response = self._post()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIn("payment", body)
        self.assertIn("appointment", body)
        pago = PagoCita.objects.get()
        self.assertEqual(pago.estado_verificacion, PagoCita.EstadoVerificacion.APROBADO)
        self.assertEqual(pago.metodo_pago, PagoCita.MetodoPago.FISICO)
        self.assertEqual(pago.cita_cliente_libre_id, self.g["cita"].pk)

    def test_virtual_happy_path_no_receipt(self):
        response = self._post(paymentMethod="VIRTUAL")
        self.assertEqual(response.status_code, 201, response.content)
        pago = PagoCita.objects.get()
        self.assertEqual(pago.monto_virtual, Decimal("180.00"))

    def test_mixto_happy_path_persists_breakdown(self):
        response = self._post(
            paymentMethod="MIXTO",
            montoFisico="60.00",
            montoVirtual="120.00",
        )
        self.assertEqual(response.status_code, 201, response.content)
        pago = PagoCita.objects.get()
        self.assertEqual(pago.monto_fisico, Decimal("60.00"))
        self.assertEqual(pago.monto_virtual, Decimal("120.00"))

    def test_mixto_breakdown_mismatch_returns_400(self):
        before = PagoCita.objects.count()
        response = self._post(
            paymentMethod="MIXTO",
            montoFisico="40.00",
            montoVirtual="50.00",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), before)

    def test_precio_zero_returns_400(self):
        cita = self.g["cita"]
        cita.precio = Decimal("0")
        cita.save()
        before = PagoCita.objects.count()
        response = self._post()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), before)

    def test_cancelada_returns_400(self):
        cita = self.g["cita"]
        cita.estado = CitaClienteLibre.Estado.CANCELADA
        cita.save()
        before = PagoCita.objects.count()
        response = self._post()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), before)

    def test_no_asistio_returns_400(self):
        cita = self.g["cita"]
        cita.estado = CitaClienteLibre.Estado.NO_ASISTIO
        cita.save()
        before = PagoCita.objects.count()
        response = self._post()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), before)

    def test_over_payment_returns_400(self):
        PagoCita.objects.create(
            cita_cliente_libre=self.g["cita"],
            monto_pagado=Decimal("150.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("150.00"),
            monto_virtual=Decimal("0"),
            estado_verificacion=PagoCita.EstadoVerificacion.APROBADO,
            verificado_por=self.g["admin"],
            fecha_verificacion=timezone.now(),
        )
        before = PagoCita.objects.count()
        response = self._post(monto_pagado="50.00")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), before)

    def test_cross_branch_returns_403(self):
        other = _build_branch("Sucursal C")
        other_admin = _build_admin("admin.c", other)
        client_b = Client()
        client_b.force_login(other_admin)
        before = PagoCita.objects.count()
        response = client_b.post(
            self._url(),
            {"paymentMethod": "FISICO", "monto_pagado": "180.00"},
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(PagoCita.objects.count(), before)

    def test_missing_cita_returns_404(self):
        before = PagoCita.objects.count()
        url = CITA_LIBRE_COBRAR_URL.format(cita_id=999999)
        response = self.client.post(
            url, {"paymentMethod": "FISICO", "monto_pagado": "180.00"}
        )
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(PagoCita.objects.count(), before)


class ReadPayloadTests(TestCase):
    """After a successful cobrar, the response payload carries the new
    ``precio`` / ``saldoPendiente`` / ``pagos_count`` / ``pagos`` fields
    on the cita item, and cancellation preserves rows + blocks cobrars.
    """

    def setUp(self):
        self.branch = _build_branch("Sucursal Read")
        self.g = _build_cita_medica_graph(
            branch=self.branch, precio=Decimal("300.00")
        )
        self.client = Client()
        self.client.force_login(self.g["admin"])

    def _url(self):
        return CITA_MEDICA_COBRAR_URL.format(
            op_id=self.g["operacion"].pk, cita_id=self.g["cita"].pk
        )

    def _post(self, **extra):
        data = {"paymentMethod": "FISICO", "monto_pagado": "150.00"}
        data.update(extra)
        return self.client.post(self._url(), data)

    def test_aprobado_row_drives_saldo_pendiente(self):
        response = self._post()
        self.assertEqual(response.status_code, 201, response.content)
        cita_payload = response.json()["appointment"]
        # precio=300, approved sum=150 → saldoPendiente="Bs 150.00"
        # (``currency()`` prefixes the local-currency symbol — see
        # ``config/api_helpers.py``).
        self.assertEqual(cita_payload["precio"], "Bs 300.00")
        self.assertEqual(cita_payload["saldoPendiente"], "Bs 150.00")
        self.assertEqual(cita_payload["pagos_count"], 1)
        self.assertEqual(len(cita_payload["pagos"]), 1)
        pago = cita_payload["pagos"][0]
        self.assertEqual(pago["monto_pagado"], "150.00")
        self.assertEqual(pago["estado_verificacion"], PagoCita.EstadoVerificacion.APROBADO)

    def test_two_aprobado_rows_accumulate_saldo(self):
        # First APROBADO of 100, second APROBADO of 100 → saldo=100.
        self._post(monto_pagado="100.00")
        response = self._post(monto_pagado="100.00")
        self.assertEqual(response.status_code, 201, response.content)
        cita_payload = response.json()["appointment"]
        self.assertEqual(cita_payload["precio"], "Bs 300.00")
        self.assertEqual(cita_payload["saldoPendiente"], "Bs 100.00")
        self.assertEqual(cita_payload["pagos_count"], 2)

    def test_pendiente_row_does_not_reduce_saldo(self):
        # A PENDIENTE row must NOT affect saldo (only APROBADO counts).
        PagoCita.objects.create(
            cita_medica=self.g["cita"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("100.00"),
            monto_virtual=Decimal("0"),
            estado_verificacion=PagoCita.EstadoVerificacion.PENDIENTE,
        )
        response = self._post(monto_pagado="50.00")
        self.assertEqual(response.status_code, 201, response.content)
        cita_payload = response.json()["appointment"]
        # Only the APROBADO cobro (50) reduces saldo. Pendiente of 100 is
        # ignored → saldoPendiente=300-50=250.
        self.assertEqual(cita_payload["saldoPendiente"], "Bs 250.00")
        self.assertEqual(cita_payload["pagos_count"], 2)

    def test_cancellation_preserves_rows_and_rejects_new_cobrar(self):
        # One APROBADO cobro lands.
        response = self._post()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(PagoCita.objects.count(), 1)

        # Cancel the cita. Existing PagoCita rows must remain visible
        # (audit trail).
        cita = self.g["cita"]
        cita.estado = CitaMedica.Estado.CANCELADA
        cita.save()
        self.assertEqual(PagoCita.objects.count(), 1)

        # New cobrar on the cancelled cita is rejected with 400.
        before = PagoCita.objects.count()
        response = self._post()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PagoCita.objects.count(), before)


class ReceiptPathTests(TestCase):
    """``PagoCita.comprobante_url`` lands under ``comprobantes_citas/YYYY/MM/``,
    never under the cuota path. Exercises both endpoints.
    """

    def setUp(self):
        self.branch_medica = _build_branch("Sucursal M")
        self.branch_libre = _build_branch("Sucursal L")
        self.g_m = _build_cita_medica_graph(
            branch=self.branch_medica, precio=Decimal("150.00")
        )
        self.g_l = _build_cita_libre_graph(
            branch=self.branch_libre, precio=Decimal("150.00")
        )
        self.client = Client()
        self.client.force_login(self.g_m["admin"])

    def _receipt(self, name="receipt.pdf"):
        return SimpleUploadedFile(
            name, b"%PDF-test", content_type="application/pdf"
        )

    def test_medica_receipt_lands_under_comprobantes_citas(self):
        url = CITA_MEDICA_COBRAR_URL.format(
            op_id=self.g_m["operacion"].pk, cita_id=self.g_m["cita"].pk
        )
        self.client.force_login(self.g_m["admin"])
        response = self.client.post(
            url,
            {
                "paymentMethod": "FISICO",
                "monto_pagado": "150.00",
                "receiptFile": self._receipt(),
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        pago = PagoCita.objects.get()
        try:
            self.assertTrue(bool(pago.comprobante_url))
            stored_name = pago.comprobante_url.name
            self.assertTrue(
                stored_name.startswith("comprobantes_citas/"),
                f"expected comprobantes_citas/ prefix, got {stored_name!r}",
            )
            self.assertNotIn("comprobantes_pagos/", stored_name)
            parts = stored_name.split("/")
            self.assertEqual(parts[0], "comprobantes_citas")
            self.assertEqual(len(parts[1]), 4)
            self.assertEqual(len(parts[2]), 2)
        finally:
            # Clean up the stored file so the test is hermetic.
            if pago.comprobante_url:
                pago.comprobante_url.delete(save=False)

    def test_libre_receipt_lands_under_comprobantes_citas(self):
        url = CITA_LIBRE_COBRAR_URL.format(cita_id=self.g_l["cita"].pk)
        self.client.force_login(self.g_l["admin"])
        response = self.client.post(
            url,
            {
                "paymentMethod": "FISICO",
                "monto_pagado": "150.00",
                "receiptFile": self._receipt("libre-receipt.pdf"),
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        pago = PagoCita.objects.get()
        try:
            self.assertTrue(bool(pago.comprobante_url))
            stored_name = pago.comprobante_url.name
            self.assertTrue(
                stored_name.startswith("comprobantes_citas/"),
                f"expected comprobantes_citas/ prefix, got {stored_name!r}",
            )
            self.assertNotIn("comprobantes_pagos/", stored_name)
        finally:
            if pago.comprobante_url:
                pago.comprobante_url.delete(save=False)