"""API integration tests for the `especialidades` admin catalog's
auto-assigned `orden` contract.

Mirrors `test_admin_catalog_sectores.py` to lock the auto-assign on
create / preserve on update behavior for `Especialidad` and to assert
the list response and form-field definitions no longer leak `orden`.
"""

import json

from django.db.models import Max
from django.test import TestCase

from accounts.models import Rol, Usuario
from staff.models import Especialidad


class EspecialidadesCatalogApiTests(TestCase):
    """Integration tests for the `/api/admin/catalogos/especialidades/`
    endpoints focused on the auto-assigned orden contract.
    """

    def setUp(self):
        self.rol_admin_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")

        self.admin_general = Usuario.objects.create_user(
            username="admin.general.especialidades",
            password="password123",
            primer_nombre="Admin",
            apellido_paterno="General",
            rol=self.rol_admin_principal,
            sucursal=None,
        )

        # Two baseline records so the next create's max+1 is well-defined.
        self._existing_ids = set(Especialidad.objects.values_list("id", flat=True))
        Especialidad.objects.create(
            nombre="Cardiologia",
            descripcion="Baseline 1",
            orden=1,
        )
        Especialidad.objects.create(
            nombre="Dermatologia",
            descripcion="Baseline 2",
            orden=2,
        )

    def tearDown(self):
        Especialidad.objects.exclude(id__in=self._existing_ids).delete()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _unique_suffix(self):
        return self._testMethodName.replace("_", "-")[:12]

    def _post(self, path, payload):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=f"especialidades-{self._testMethodName}",
        )

    # ------------------------------------------------------------------
    # GET /api/admin/catalogos/especialidades/ — list response shape
    # ------------------------------------------------------------------
    def test_list_response_has_no_order_in_metadata(self):
        self.client.force_login(self.admin_general)
        response = self.client.get("/api/admin/catalogos/especialidades/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        for item in data["items"]:
            for entry in item["metadata"]:
                self.assertNotEqual(
                    entry.get("label"),
                    "Orden",
                    f"Expected no 'Orden' metadata entry, found in item {item['id']}",
                )

    def test_list_response_has_no_order_in_values(self):
        self.client.force_login(self.admin_general)
        response = self.client.get("/api/admin/catalogos/especialidades/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        for item in data["items"]:
            self.assertNotIn(
                "order",
                item["values"],
                f"Expected no 'order' key in values, found in item {item['id']}",
            )

    def test_form_fields_has_no_order_entry(self):
        self.client.force_login(self.admin_general)
        response = self.client.get("/api/admin/catalogos/especialidades/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        for field in data["fields"]:
            self.assertNotEqual(
                field.get("name"),
                "order",
                f"Expected no 'order' field definition, found: {field}",
            )

    # ------------------------------------------------------------------
    # POST /api/admin/catalogos/especialidades/crear/ — auto-assign
    # ------------------------------------------------------------------
    def test_create_auto_assigns_max_plus_1(self):
        baseline_max = Especialidad.objects.aggregate(Max("orden"))["orden__max"] or 0

        self.client.force_login(self.admin_general)
        suffix = self._unique_suffix()
        response = self._post(
            "/api/admin/catalogos/especialidades/crear/",
            {
                "name": f"Auto Orden {suffix}",
                "description": "Sin enviar orden",
                "active": True,
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        created = Especialidad.objects.get(pk=body["item"]["id"])
        self.assertEqual(created.orden, baseline_max + 1)

    def test_create_ignores_explicit_order(self):
        baseline_max = Especialidad.objects.aggregate(Max("orden"))["orden__max"] or 0

        self.client.force_login(self.admin_general)
        suffix = self._unique_suffix()
        response = self._post(
            "/api/admin/catalogos/especialidades/crear/",
            {
                "name": f"Orden Explicito {suffix}",
                "description": "Debe ser ignorado",
                "order": 999,
                "active": True,
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        created = Especialidad.objects.get(pk=body["item"]["id"])
        # Payload `order: 999` must be ignored; server assigns max+1.
        self.assertEqual(created.orden, baseline_max + 1)
        self.assertNotEqual(created.orden, 999)

    def test_create_asigna_orden_max_mas_uno(self):
        # Spanish-named alias of `test_create_auto_assigns_max_plus_1` to match
        # the in-repo Spanish naming style referenced by the apply prompt.
        baseline_max = Especialidad.objects.aggregate(Max("orden"))["orden__max"] or 0

        self.client.force_login(self.admin_general)
        suffix = self._unique_suffix()
        response = self._post(
            "/api/admin/catalogos/especialidades/crear/",
            {
                "name": f"Alias ES {suffix}",
                "description": "Mismo comportamiento, alias en espanol",
                "active": True,
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        created = Especialidad.objects.get(pk=body["item"]["id"])
        self.assertEqual(created.orden, baseline_max + 1)

    def test_create_ignora_order_del_payload(self):
        # Spanish-named alias of `test_create_ignores_explicit_order`.
        baseline_max = Especialidad.objects.aggregate(Max("orden"))["orden__max"] or 0

        self.client.force_login(self.admin_general)
        suffix = self._unique_suffix()
        response = self._post(
            "/api/admin/catalogos/especialidades/crear/",
            {
                "name": f"Alias Ignora {suffix}",
                "description": "Payload con order debe ser ignorado",
                "order": 999,
                "active": True,
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        created = Especialidad.objects.get(pk=body["item"]["id"])
        self.assertEqual(created.orden, baseline_max + 1)

    # ------------------------------------------------------------------
    # POST /api/admin/catalogos/especialidades/<id>/actualizar/ — preserve
    # ------------------------------------------------------------------
    def test_update_preserves_orden(self):
        especialidad = Especialidad.objects.create(
            nombre="Editable",
            descripcion="Test update",
            orden=5,
        )

        self.client.force_login(self.admin_general)
        response = self._post(
            f"/api/admin/catalogos/especialidades/{especialidad.pk}/actualizar/",
            {
                "name": "Editable (renombrado)",
                "description": "Descripcion actualizada",
                "order": 999,
            },
        )

        self.assertEqual(response.status_code, 200, response.content)
        especialidad.refresh_from_db()
        # orden is not exposed in the form; updates must preserve the existing value
        self.assertEqual(especialidad.orden, 5)
        self.assertEqual(especialidad.nombre, "Editable (renombrado)")
        self.assertEqual(especialidad.descripcion, "Descripcion actualizada")
