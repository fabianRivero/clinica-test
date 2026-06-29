"""Permission-scope tests for the admin_ticket_open_permission endpoint.

Validates that:
- Admin principal (general) can toggle specialists and admins of any branch.
- Admin de sucursal (branch admin) can toggle specialists of their own branch.
- Admin de sucursal CANNOT toggle other admins (returns 403), even admins
  of their own branch — because admins can also create fichas and only the
  general admin should control that.

These tests close a real bug where admin_ticket_open_permission would
silently fall through to the branch-wide toggle path when an admin de
sucursal sent an `adminUserId` payload, toggling every specialist of the
branch instead of returning 403.
"""

import json

from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import Sucursal
from staff.models import Especialista


class AdminOpenPermissionScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.rol_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        cls.sucursal_a = Sucursal.objects.create(nombre="Sucursal A scope", activa=True)
        cls.sucursal_b = Sucursal.objects.create(nombre="Sucursal B scope", activa=True)

        cls.admin_general = Usuario.objects.create_user(
            username="admin.general.scope",
            password="password123",
            primer_nombre="General",
            apellido_paterno="Scope",
            rol=cls.rol_principal,
            sucursal=None,
        )
        cls.admin_sucursal_a = Usuario.objects.create_user(
            username="admin.sucursal.a.scope",
            password="password123",
            primer_nombre="SucursalA",
            apellido_paterno="Admin",
            rol=cls.rol_sucursal,
            sucursal=cls.sucursal_a,
        )
        cls.admin_sucursal_b = Usuario.objects.create_user(
            username="admin.sucursal.b.scope",
            password="password123",
            primer_nombre="SucursalB",
            apellido_paterno="Admin",
            rol=cls.rol_sucursal,
            sucursal=cls.sucursal_b,
        )

        # Specialist in branch A.
        cls.spec_a_user = Usuario.objects.create_user(
            username="spec.a.scope",
            password="password123",
            primer_nombre="SpecialistA",
            apellido_paterno="Spec",
            rol=None,
            sucursal=cls.sucursal_a,
        )
        cls.spec_a = Especialista.objects.create(
            usuario=cls.spec_a_user,
            sucursal_base=cls.sucursal_a,
            puede_abrir_fichas=True,
        )

    def _post_permission(self, payload, branch_id_header=None):
        headers = {}
        if branch_id_header is not None:
            headers["HTTP_X_SELECTED_BRANCH_ID"] = str(branch_id_header)
        return self.client.post(
            "/api/tickets/permisos/apertura/",
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def test_admin_principal_can_toggle_admin_user(self):
        self.client.force_login(self.admin_general)
        response = self._post_permission(
            {"enabled": False, "adminUserId": self.admin_sucursal_a.id},
            branch_id_header=self.sucursal_a.id,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.admin_sucursal_a.refresh_from_db()
        self.assertFalse(self.admin_sucursal_a.is_active)

    def test_admin_principal_can_toggle_specialist(self):
        self.client.force_login(self.admin_general)
        response = self._post_permission(
            {"enabled": False, "specialistId": self.spec_a.id},
            branch_id_header=self.sucursal_a.id,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.spec_a.refresh_from_db()
        self.assertFalse(self.spec_a.puede_abrir_fichas)

    def test_branch_admin_can_toggle_own_branch_specialist(self):
        self.client.force_login(self.admin_sucursal_a)
        response = self._post_permission(
            {"enabled": False, "specialistId": self.spec_a.id},
            branch_id_header=self.sucursal_a.id,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.spec_a.refresh_from_db()
        self.assertFalse(self.spec_a.puede_abrir_fichas)

    def test_branch_admin_cannot_toggle_other_admin(self):
        """The main bug: branch admin sends adminUserId; backend must 403."""
        self.client.force_login(self.admin_sucursal_a)
        original_active = self.admin_sucursal_b.is_active
        response = self._post_permission(
            {"enabled": False, "adminUserId": self.admin_sucursal_b.id},
            branch_id_header=self.sucursal_a.id,
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.admin_sucursal_b.refresh_from_db()
        # The target admin's state must not have changed.
        self.assertEqual(self.admin_sucursal_b.is_active, original_active)
        # And the branch-wide specialist toggle must NOT have been triggered.
        self.spec_a.refresh_from_db()
        self.assertTrue(self.spec_a.puede_abrir_fichas)

    def test_branch_admin_cannot_toggle_branch_admins_mass(self):
        """The target=branch_admins mass toggle also requires admin principal."""
        self.client.force_login(self.admin_sucursal_a)
        original_active_a = self.admin_sucursal_a.is_active
        original_active_b = self.admin_sucursal_b.is_active
        response = self._post_permission(
            {"enabled": False, "target": "branch_admins"},
            branch_id_header=self.sucursal_a.id,
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.admin_sucursal_a.refresh_from_db()
        self.admin_sucursal_b.refresh_from_db()
        self.assertEqual(self.admin_sucursal_a.is_active, original_active_a)
        self.assertEqual(self.admin_sucursal_b.is_active, original_active_b)