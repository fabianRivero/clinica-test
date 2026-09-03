"""Tests for ``/api/admin/pagos/configuracion-qr/``.

The cobro modal for citas and cuotas needs to read the QR image so it
can surface it under the ``Método de pago`` selector when the admin
picks VIRTUAL or MIXTO. This test covers BOTH the read (GET) and the
update (POST) paths of the same URL — DRF only registers one
``@action`` per ``url_path`` so both verbs share one method that
dispatches internally.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from accounts.models import Rol, Usuario
from billing.models import ConfiguracionPagoQR
from catalogs.models import Sucursal


QR_CONFIG_URL = "/api/admin/pagos/configuracion-qr/"


class GetPaymentQrConfigTests(TestCase):
    def setUp(self):
        self.branch = Sucursal.objects.create(nombre="Sucursal QR", activa=True)
        self.other_branch = Sucursal.objects.create(
            nombre="Otra Sucursal", activa=True
        )

        rol = Rol.objects.get_or_create(rol="ADMIN_SUCURSAL")[0]
        self.admin = Usuario.objects.create_user(
            username="admin.qr",
            password="password123",
            rol=rol,
            sucursal=self.branch,
        )
        # Pre-existing config in the OTHER branch — must NOT leak across.
        ConfiguracionPagoQR.objects.create(
            sucursal=self.other_branch,
            instrucciones="No me muestres.",
        )

    def _get(self):
        client = Client()
        client.force_login(self.admin)
        return client.get(QR_CONFIG_URL)

    def test_returns_has_qr_false_when_no_config_for_branch(self):
        response = self._get()
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["paymentQrConfig"]["hasQr"], False)
        self.assertEqual(body["paymentQrConfig"]["qrImageUrl"], "")

    def test_does_not_leak_qr_from_other_branches(self):
        # Even if another branch has a ConfiguracionPagoQR, the admin
        # must only see their own branch's QR (or none).
        response = self._get()
        body = response.json()
        self.assertNotIn("No me muestres.", body["paymentQrConfig"]["instructions"])

    def _post(self, *, instructions="", file=None):
        client = Client()
        client.force_login(self.admin)
        data = {"instructions": instructions}
        files = {}
        if file is not None:
            files["qrImage"] = file
        return client.post(QR_CONFIG_URL, data, **files)


class PostPaymentQrConfigTests(TestCase):
    """The POST half of ``/api/admin/pagos/configuracion-qr/``.

    Locks the instructions field without uploading a file so we don't
    depend on the storage backend choice (Supabase vs local).
    """

    def setUp(self):
        self.branch = Sucursal.objects.create(nombre="Sucursal POST", activa=True)
        rol = Rol.objects.get_or_create(rol="ADMIN_SUCURSAL")[0]
        self.admin = Usuario.objects.create_user(
            username="admin.qr.post",
            password="password123",
            rol=rol,
            sucursal=self.branch,
        )

    def _post(self, **extra):
        client = Client()
        client.force_login(self.admin)
        data = {"instructions": "Pagos al 70000000"}
        data.update(extra)
        return client.post(QR_CONFIG_URL, data)

    def test_post_creates_config_with_instructions(self):
        response = self._post(instructions="Nuevo texto")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["paymentQrConfig"]["instructions"], "Nuevo texto")
        self.assertEqual(ConfiguracionPagoQR.objects.filter(sucursal=self.branch).count(), 1)

    def test_post_with_qr_image_marks_has_qr_true(self):
        qr = SimpleUploadedFile("qr.png", b"%PNG-fake", content_type="image/png")
        response = self._post(qrImage=qr)
        self.assertEqual(response.status_code, 200, response.content)
        self.config = ConfiguracionPagoQR.objects.get(sucursal=self.branch)
        self.assertTrue(self.config.imagen_qr)