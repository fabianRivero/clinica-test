import json

from django.test import Client, TestCase

from accounts.models import Rol, Usuario
from catalogs.models import Sucursal
from customers.models import Cliente
from staff.models import Especialista


class ProfileUpdateSerializetionTests(TestCase):
    """Task 4.1: Django unit test — _serialize_user includes telefono in response."""

    def setUp(self):
        self.rol_cliente = Rol.objects.create(rol="CLIENTE")
        self.rol_trabajador = Rol.objects.create(rol="TRABAJADOR")
        self.sucursal = Sucursal.objects.create(nombre="Centro", activa=True)

    def test_serialize_user_includes_telefono(self):
        """GET /api/auth/me/ returns telefono in the serialized user."""
        user = Usuario.objects.create_user(
            username="test.user",
            password="password123",
            rol=self.rol_cliente,
            telefono="70000000",
            sucursal=self.sucursal,
        )
        Cliente.objects.create(usuario=user, telefono="70000000")

        client = Client()
        client.login(username="test.user", password="password123")

        response = client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("user", data)
        self.assertEqual(data["user"]["telefono"], "70000000")


class ProfileUpdateIntegrationTests(TestCase):
    """Task 4.2: Django integration test — PATCH /api/auth/me/ with session auth."""

    def setUp(self):
        self.rol_cliente = Rol.objects.create(rol="CLIENTE")
        self.rol_trabajador = Rol.objects.create(rol="TRABAJADOR")
        self.rol_admin_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        self.sucursal = Sucursal.objects.create(nombre="Centro", activa=True)

        self.client_user = Usuario.objects.create_user(
            username="cliente.profile",
            password="password123",
            rol=self.rol_cliente,
            telefono="70000000",
            sucursal=self.sucursal,
            primer_nombre="Juan",
            apellido_paterno="Perez",
        )
        self.cliente = Cliente.objects.create(
            usuario=self.client_user,
            telefono="70000000",
            fecha_nacimiento="2000-01-01",
        )

        self.worker_user = Usuario.objects.create_user(
            username="trabajador.profile",
            password="password123",
            rol=self.rol_trabajador,
            telefono="71000000",
            sucursal=self.sucursal,
            primer_nombre="Maria",
            apellido_paterno="Garcia",
        )
        self.especialista = Especialista.objects.create(
            usuario=self.worker_user,
            telefono="71000000",
        )

        self.client_http = Client()
        self.client_http.login(username="cliente.profile", password="password123")

        self.worker_http = Client()
        self.worker_http.login(username="trabajador.profile", password="password123")

        # ADMIN_SUCURSAL user (no separate profile model — telefono stored on Usuario directly)
        self.admin_user = Usuario.objects.create_user(
            username="admin.profile",
            password="password123",
            rol=self.rol_admin_sucursal,
            telefono="72000000",
            sucursal=self.sucursal,
            primer_nombre="Pedro",
            apellido_paterno="Admin",
        )

        self.admin_http = Client()
        self.admin_http.login(username="admin.profile", password="password123")

    def test_patch_partial_update_telefono(self):
        """PATCH updates only telefono without affecting other fields."""
        response = self.client_http.patch(
            "/api/auth/me/",
            data=json.dumps({"telefono": "79999999"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["user"]["telefono"], "79999999")
        self.assertEqual(data["user"]["username"], "cliente.profile")

    def test_patch_telefono_cascades_to_cliente(self):
        """PATCH telefono syncs to Cliente.telefono."""
        response = self.client_http.patch(
            "/api/auth/me/",
            data=json.dumps({"telefono": "78888888"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        self.client_user.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertEqual(self.client_user.telefono, "78888888")
        self.assertEqual(self.cliente.telefono, "78888888")

    def test_patch_telefono_cascades_to_especialista(self):
        """PATCH telefono syncs to Especialista.telefono."""
        response = self.worker_http.patch(
            "/api/auth/me/",
            data=json.dumps({"telefono": "77777777"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        self.worker_user.refresh_from_db()
        self.especialista.refresh_from_db()
        self.assertEqual(self.worker_user.telefono, "77777777")
        self.assertEqual(self.especialista.telefono, "77777777")

    def test_patch_password_change(self):
        """PATCH with password updates the password and cycles session."""
        response = self.client_http.patch(
            "/api/auth/me/",
            data=json.dumps({"password": "newpassword123"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        # User can still use session (session was cycled but still valid)
        response = self.client_http.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "cliente.profile")

    def test_patch_username_collision_returns_409(self):
        """PATCH with existing username returns 409 Conflict."""
        Usuario.objects.create_user(
            username="existing.user",
            password="password123",
            rol=self.rol_cliente,
            telefono="70000001",
            sucursal=self.sucursal,
        )

        response = self.client_http.patch(
            "/api/auth/me/",
            data=json.dumps({"username": "existing.user"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertIn("detail", data)
        self.assertIn("ya esta en uso", data["detail"])

    def test_patch_invalid_field_returns_400(self):
        """PATCH with unknown fields returns 400."""
        response = self.client_http.patch(
            "/api/auth/me/",
            data=json.dumps({"invalid_field": "value"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("detail", data)
        self.assertIn("invalid_field", data["detail"])

    def test_patch_email_update(self):
        """PATCH updates email correctly."""
        response = self.client_http.patch(
            "/api/auth/me/",
            data=json.dumps({"email": "new@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        self.client_user.refresh_from_db()
        self.assertEqual(self.client_user.email, "new@example.com")
        self.assertEqual(response.json()["user"]["email"], "new@example.com")

    def test_patch_telefono_updates_admin_sucursal(self):
        """PATCH telefono updates ADMIN_SUCURSAL user directly (no separate profile model)."""
        response = self.admin_http.patch(
            "/api/auth/me/",
            data=json.dumps({"telefono": "72999999"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        self.admin_user.refresh_from_db()
        self.assertEqual(self.admin_user.telefono, "72999999")
        self.assertEqual(response.json()["user"]["telefono"], "72999999")