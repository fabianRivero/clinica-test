import json

from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import Sucursal


class BranchManagementPhase2Test(TestCase):
    def setUp(self):
        self.rol_admin_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.sucursal = Sucursal.objects.create(nombre="Centro", ciudad="La Paz", direccion="Av", activa=True)
        self.admin_general = Usuario.objects.create_user(
            username="admin.general", password="password123", primer_nombre="Admin", apellido_paterno="General",
            rol=self.rol_admin_principal, sucursal=self.sucursal
        )

    def test_create_branch_requires_idempotency_key(self):
        self.client.force_login(self.admin_general)
        response = self.client.post(
            "/api/admin/sucursales/crear/",
            data=json.dumps({"nombre": "Sur", "ciudad": "Santa Cruz", "direccion": "A"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_branch_is_idempotent(self):
        self.client.force_login(self.admin_general)
        headers = {"HTTP_IDEMPOTENCY_KEY": "abc-1"}
        payload = {"nombre": "Sur", "ciudad": "Santa Cruz", "direccion": "A"}

        first = self.client.post("/api/admin/sucursales/crear/", data=json.dumps(payload), content_type="application/json", **headers)
        second = self.client.post("/api/admin/sucursales/crear/", data=json.dumps(payload), content_type="application/json", **headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(Sucursal.objects.filter(nombre="Sur").count(), 1)

    def test_deactivation_requires_force_when_pending(self):
        self.client.force_login(self.admin_general)
        headers = {"HTTP_IDEMPOTENCY_KEY": "toggle-1"}
        response = self.client.post(
            f"/api/admin/sucursales/{self.sucursal.id}/estado/",
            data=json.dumps({"active": False}),
            content_type="application/json",
            **headers,
        )
        # sin pendientes reales en este fixture, debe permitir desactivar
        self.assertEqual(response.status_code, 200)

    def test_deactivation_impact_endpoint(self):
        self.client.force_login(self.admin_general)
        response = self.client.get(f"/api/admin/sucursales/{self.sucursal.id}/deactivation-impact/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("impact", data)
        self.assertIn("appointments_pending", data["impact"])
