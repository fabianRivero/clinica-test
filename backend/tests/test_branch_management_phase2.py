import json
from unittest.mock import patch

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
        with patch("config.api_views._branch_deactivation_impact") as mock_impact:
            mock_impact.return_value = {
                "appointments_pending": 2,
                "payments_pending": 1,
                "processes_pending": 3,
            }
            response = self.client.post(
                f"/api/admin/sucursales/{self.sucursal.id}/estado/",
                data=json.dumps({"active": False}),
                content_type="application/json",
                **headers,
            )

            self.assertEqual(response.status_code, 409)
            data = response.json()
            self.assertTrue(data["requiresConfirmation"])
            self.assertEqual(data["impact"]["appointments_pending"], 2)

    def test_deactivation_with_force_allows_soft_disable(self):
        self.client.force_login(self.admin_general)
        headers = {"HTTP_IDEMPOTENCY_KEY": "toggle-2"}
        with patch("config.api_views._branch_deactivation_impact") as mock_impact:
            mock_impact.return_value = {
                "appointments_pending": 2,
                "payments_pending": 1,
                "processes_pending": 3,
            }
            response = self.client.post(
                f"/api/admin/sucursales/{self.sucursal.id}/estado/",
                data=json.dumps({"active": False, "force": True}),
                content_type="application/json",
                **headers,
            )
            self.assertEqual(response.status_code, 200)
            self.sucursal.refresh_from_db()
            self.assertFalse(self.sucursal.activa)

    def test_deactivation_impact_endpoint(self):
        self.client.force_login(self.admin_general)
        response = self.client.get(f"/api/admin/sucursales/{self.sucursal.id}/deactivation-impact/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("impact", data)
        self.assertIn("appointments_pending", data["impact"])

    def test_filters_list_by_status_city_admin_and_branch(self):
        self.client.force_login(self.admin_general)
        sur = Sucursal.objects.create(nombre="Sur", ciudad="Santa Cruz", direccion="Av 2", activa=False)
        rol_admin_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        Usuario.objects.create_user(
            username="admin.sur",
            password="password123",
            primer_nombre="Ana",
            apellido_paterno="Suarez",
            rol=rol_admin_sucursal,
            sucursal=sur,
        )
        response = self.client.get(
            f"/api/admin/sucursales/?status=inactive&city=Santa&admin_name=Ana&branch_id={sur.id}"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["branches"][0]["id"], sur.id)
