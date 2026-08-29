"""API integration tests for the `maquinaria` admin catalog.

Covers:
- List endpoint (admin principal sees all; admin_sucursal sees globales + own)
- Dedicated create endpoint (admin_principal global OK; admin_sucursal global 403)
- Dedicated update endpoint (admin_sucursal cannot edit globales or other branch)
- Permission predicates for both endpoints.

Part of the appointment-reservation-redesign change.
"""

import json

from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import Maquinaria, Sucursal


class MaquinariaCatalogApiTests(TestCase):
    def setUp(self):
        self.rol_admin_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.rol_admin_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")

        self.sucursal_centro = Sucursal.objects.create(
            nombre="Centro", ciudad="La Paz", direccion="Av. 1", activa=True
        )
        self.sucursal_norte = Sucursal.objects.create(
            nombre="Norte", ciudad="Cochabamba", direccion="Av. 2", activa=True
        )

        self.admin_general = Usuario.objects.create_user(
            username="admin.general.maq",
            password="password123",
            primer_nombre="Admin",
            apellido_paterno="General",
            rol=self.rol_admin_principal,
            sucursal=self.sucursal_centro,
        )
        self.admin_centro = Usuario.objects.create_user(
            username="admin.centro.maq",
            password="password123",
            primer_nombre="Admin",
            apellido_paterno="Centro",
            rol=self.rol_admin_sucursal,
            sucursal=self.sucursal_centro,
        )
        self.admin_norte = Usuario.objects.create_user(
            username="admin.norte.maq",
            password="password123",
            primer_nombre="Admin",
            apellido_paterno="Norte",
            rol=self.rol_admin_sucursal,
            sucursal=self.sucursal_norte,
        )

    def _create(self, **overrides):
        payload = {
            "nombre": "Laser diodo",
            "marca": "Alma",
            "descripcion": "Laser para depilacion.",
            "cantidadTotal": 2,
            "sucursalId": None,
            "activo": True,
        }
        payload.update(overrides)
        return json.dumps(payload).encode("utf-8")

    def test_admin_general_sees_globales_plus_own(self):
        """admin_principal sees globales + own branch only (active-branch scope)."""
        Maquinaria.objects.create(nombre="Global", cantidad_total=1, sucursal=None)
        Maquinaria.objects.create(
            nombre="Centro Laser", cantidad_total=1, sucursal=self.sucursal_centro
        )
        Maquinaria.objects.create(
            nombre="Norte Laser", cantidad_total=1, sucursal=self.sucursal_norte
        )

        self.client.force_login(self.admin_general)
        response = self.client.get("/api/admin/catalogos/maquinaria/")
        self.assertEqual(response.status_code, 200)
        nombres = {item["title"] for item in response.json()["items"]}
        # admin_general is assigned to sucursal_centro, so they see
        # Global + Centro Laser, but NOT Norte Laser.
        self.assertSetEqual(nombres, {"Global", "Centro Laser"})

    def test_admin_sucursal_sees_globales_plus_own(self):
        """admin_sucursal sees globales + own; not other branches."""
        Maquinaria.objects.create(nombre="Global", cantidad_total=1, sucursal=None)
        Maquinaria.objects.create(
            nombre="Centro Laser", cantidad_total=1, sucursal=self.sucursal_centro
        )
        Maquinaria.objects.create(
            nombre="Norte Laser", cantidad_total=1, sucursal=self.sucursal_norte
        )

        self.client.force_login(self.admin_centro)
        response = self.client.get("/api/admin/catalogos/maquinaria/")
        self.assertEqual(response.status_code, 200)
        nombres = {item["title"] for item in response.json()["items"]}
        self.assertSetEqual(nombres, {"Global", "Centro Laser"})

    def test_admin_principal_creates_global_maquinaria(self):
        """admin_principal can create a global (sucursal=null) row."""
        self.client.force_login(self.admin_general)
        response = self.client.post(
            "/api/admin/catalogos/maquinaria/crear/",
            data=self._create(nombre="Camilla global", sucursalId=None),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        row = Maquinaria.objects.get(nombre="Camilla global")
        self.assertIsNone(row.sucursal_id)
        self.assertEqual(row.cantidad_total, 2)

    def test_admin_sucursal_cannot_create_global_maquinaria(self):
        """admin_sucursal attempting sucursalId=null is rejected."""
        self.client.force_login(self.admin_centro)
        response = self.client.post(
            "/api/admin/catalogos/maquinaria/crear/",
            data=self._create(nombre="Hacked global", sucursalId=None),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("sucursalId", response.json()["errors"])
        self.assertFalse(Maquinaria.objects.filter(nombre="Hacked global").exists())

    def test_admin_sucursal_cannot_assign_other_branch(self):
        """admin_sucursal attempting to assign to a different branch is rejected."""
        self.client.force_login(self.admin_centro)
        response = self.client.post(
            "/api/admin/catalogos/maquinaria/crear/",
            data=self._create(nombre="Hacked cross", sucursalId=self.sucursal_norte.pk),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("sucursalId", response.json()["errors"])
        self.assertFalse(Maquinaria.objects.filter(nombre="Hacked cross").exists())

    def test_admin_sucursal_creates_own_branch_maquinaria(self):
        """admin_sucursal creating for own branch succeeds."""
        self.client.force_login(self.admin_centro)
        response = self.client.post(
            "/api/admin/catalogos/maquinaria/crear/",
            data=self._create(nombre="Mio", sucursalId=self.sucursal_centro.pk),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        row = Maquinaria.objects.get(nombre="Mio")
        self.assertEqual(row.sucursal_id, self.sucursal_centro.pk)

    def test_admin_sucursal_cannot_edit_global(self):
        """admin_sucursal attempting to PATCH a global row is 403."""
        global_row = Maquinaria.objects.create(
            nombre="Global", cantidad_total=1, sucursal=None
        )
        self.client.force_login(self.admin_centro)
        response = self.client.post(
            f"/api/admin/catalogos/maquinaria/{global_row.pk}/actualizar/",
            data=self._create(nombre="Global edited", sucursalId=None),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_admin_sucursal_cannot_edit_other_branch(self):
        """admin_sucursal attempting to PATCH a row in another branch is 403."""
        other = Maquinaria.objects.create(
            nombre="Norte Laser", cantidad_total=1, sucursal=self.sucursal_norte
        )
        self.client.force_login(self.admin_centro)
        response = self.client.post(
            f"/api/admin/catalogos/maquinaria/{other.pk}/actualizar/",
            data=self._create(nombre="Norte hacked", sucursalId=self.sucursal_norte.pk),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_admin_sucursal_edits_own_branch(self):
        """admin_sucursal can PATCH a row in their own branch."""
        own = Maquinaria.objects.create(
            nombre="Mio", cantidad_total=1, sucursal=self.sucursal_centro
        )
        self.client.force_login(self.admin_centro)
        response = self.client.post(
            f"/api/admin/catalogos/maquinaria/{own.pk}/actualizar/",
            data=self._create(
                nombre="Mio actualizado", cantidadTotal=5, sucursalId=self.sucursal_centro.pk
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        own.refresh_from_db()
        self.assertEqual(own.nombre, "Mio actualizado")
        self.assertEqual(own.cantidad_total, 5)

    def test_creation_validates_cantidad_min(self):
        """cantidadTotal=0 is rejected."""
        self.client.force_login(self.admin_general)
        response = self.client.post(
            "/api/admin/catalogos/maquinaria/crear/",
            data=self._create(nombre="Sin cantidad", cantidadTotal=0, sucursalId=self.sucursal_centro.pk),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("cantidadTotal", response.json()["errors"])