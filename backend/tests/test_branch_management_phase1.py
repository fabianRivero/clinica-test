import json

from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import Sucursal


class BranchManagementPhase1Test(TestCase):
    def setUp(self):
        self.rol_admin_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.rol_admin_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        self.rol_trabajador = Rol.objects.create(rol="TRABAJADOR")

        self.sucursal_activa = Sucursal.objects.create(nombre="Centro", ciudad="La Paz", direccion="Av. 1", activa=True)
        self.sucursal_inactiva = Sucursal.objects.create(nombre="Norte", ciudad="Cochabamba", direccion="Av. 2", activa=False)

        self.admin_general = Usuario.objects.create_user(
            username="admin.general", password="password123", primer_nombre="Admin", apellido_paterno="General",
            rol=self.rol_admin_principal, sucursal=self.sucursal_activa
        )
        self.admin_sucursal = Usuario.objects.create_user(
            username="admin.sucursal", password="password123", primer_nombre="Admin", apellido_paterno="Sucursal",
            rol=self.rol_admin_sucursal, sucursal=self.sucursal_activa
        )
        self.admin_sucursal_nuevo = Usuario.objects.create_user(
            username="admin.sucursal.2", password="password123", primer_nombre="Nuevo", apellido_paterno="Admin",
            rol=self.rol_admin_sucursal, sucursal=self.sucursal_inactiva
        )
        self.trabajador = Usuario.objects.create_user(
            username="trabajador", password="password123", primer_nombre="Trab", apellido_paterno="Uno",
            rol=self.rol_trabajador, sucursal=self.sucursal_activa
        )

    def test_only_main_admin_can_create_branch(self):
        self.client.force_login(self.admin_sucursal)
        response = self.client.post(
            "/api/admin/sucursales/crear/",
            data=json.dumps({"nombre": "Sur", "ciudad": "Santa Cruz", "direccion": "Av. 3"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase1-create-non-main",
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.admin_general)
        ok = self.client.post(
            "/api/admin/sucursales/crear/",
            data=json.dumps({"nombre": "Sur", "ciudad": "Santa Cruz", "direccion": "Av. 3"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase1-create-main",
        )
        self.assertEqual(ok.status_code, 201)

    def test_soft_disable_toggle(self):
        self.client.force_login(self.admin_general)
        response = self.client.post(
            f"/api/admin/sucursales/{self.sucursal_activa.id}/estado/",
            data=json.dumps({"active": False}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase1-toggle",
        )
        self.assertEqual(response.status_code, 200)
        self.sucursal_activa.refresh_from_db()
        self.assertFalse(self.sucursal_activa.activa)

    def test_cannot_leave_branch_without_admin(self):
        self.client.force_login(self.admin_general)
        response = self.client.post(
            f"/api/admin/sucursales/{self.sucursal_activa.id}/cambiar-admin/",
            data=json.dumps({"newAdminUserId": self.admin_sucursal_nuevo.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Usuario.objects.filter(sucursal=self.sucursal_activa, rol__rol="ADMIN_SUCURSAL", is_active=True).exists()
        )

    def test_replace_with_inactive_admin_activates_new_and_inactivates_current(self):
        self.admin_sucursal_nuevo.is_active = False
        self.admin_sucursal_nuevo.sucursal = None
        self.admin_sucursal_nuevo.save(update_fields=["is_active", "sucursal", "updated_at"])

        self.client.force_login(self.admin_general)
        response = self.client.post(
            f"/api/admin/sucursales/{self.sucursal_activa.id}/cambiar-admin/",
            data=json.dumps({"newAdminUserId": self.admin_sucursal_nuevo.id}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase1-change-inactive",
        )
        self.assertEqual(response.status_code, 200)

        self.admin_sucursal.refresh_from_db()
        self.admin_sucursal_nuevo.refresh_from_db()
        self.assertFalse(self.admin_sucursal.is_active)
        self.assertIsNone(self.admin_sucursal.sucursal_id)
        self.assertTrue(self.admin_sucursal_nuevo.is_active)
        self.assertEqual(self.admin_sucursal_nuevo.sucursal_id, self.sucursal_activa.id)

    def test_swap_admins_between_branches(self):
        self.client.force_login(self.admin_general)
        response = self.client.post(
            f"/api/admin/sucursales/{self.sucursal_activa.id}/cambiar-admin/",
            data=json.dumps({"newAdminUserId": self.admin_sucursal_nuevo.id}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase1-change-swap",
        )
        self.assertEqual(response.status_code, 200)

        self.admin_sucursal.refresh_from_db()
        self.admin_sucursal_nuevo.refresh_from_db()
        self.assertEqual(self.admin_sucursal_nuevo.sucursal_id, self.sucursal_activa.id)
        self.assertEqual(self.admin_sucursal.sucursal_id, self.sucursal_inactiva.id)

    def test_cannot_assign_branch_admin_when_main_admin_is_assigned_to_branch(self):
        self.admin_general.sucursal = self.sucursal_activa
        self.admin_general.is_active = True
        self.admin_general.save(update_fields=["sucursal", "is_active", "updated_at"])
        self.admin_sucursal_nuevo.is_active = True
        self.admin_sucursal_nuevo.sucursal = None
        self.admin_sucursal_nuevo.save(update_fields=["is_active", "sucursal", "updated_at"])

        self.client.force_login(self.admin_general)
        response = self.client.post(
            f"/api/admin/sucursales/{self.sucursal_activa.id}/cambiar-admin/",
            data=json.dumps({"newAdminUserId": self.admin_sucursal_nuevo.id}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase1-change-main-admin-conflict",
        )
        self.assertEqual(response.status_code, 409)

    def test_inactive_branch_admin_is_blocked(self):
        self.admin_sucursal.sucursal = self.sucursal_inactiva
        self.admin_sucursal.save(update_fields=["sucursal", "updated_at"])

        self.client.force_login(self.admin_sucursal)
        response = self.client.get("/api/admin/disponibilidad/sucursales/")
        self.assertEqual(response.status_code, 403)
