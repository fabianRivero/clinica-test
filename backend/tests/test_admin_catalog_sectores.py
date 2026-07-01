"""API integration tests for the `sectores` admin catalog.

These tests exercise the sixth catalog registered on the admin catalog API
(sectores) end-to-end: list, search, active filter, create, duplicate
validation, update, and toggle.

The data migration `0006_seed_sectores_and_reassign_fichaseccion` seeds three
baseline sectors (DEP/MAN/TAT). Tests use suffixed codigos/nombres so they
stay independent of the seed and can run in any order.
"""

import json

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import Sector


class SectoresCatalogApiTests(TestCase):
    """Integration tests for the `/api/admin/catalogos/sectores/` endpoints."""

    SEED_RESERVED_CODIGOS = ("DEP", "MAN", "TAT")

    def setUp(self):
        self.rol_admin_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.sucursal = None  # admin principal no requiere sucursal activa

        self.admin_general = Usuario.objects.create_user(
            username="admin.general.sectores",
            password="password123",
            primer_nombre="Admin",
            apellido_paterno="General",
            rol=self.rol_admin_principal,
            sucursal=self.sucursal,
        )

        # Capture any pre-existing sectors so we can clean up after the
        # test finishes and leave the global seed intact for the rest
        # of the suite.
        self._existing_ids = set(Sector.objects.values_list("id", flat=True))

        # DEP/MAN/TAT are seeded by the data migration. Create them here
        # too in case the test database is built without running the
        # migration (e.g. when running with --keepdb from a prior seed).
        for codigo, nombre in (
            ("DEP", "Depilacion"),
            ("MAN", "Manchas"),
            ("TAT", "Tatuajes"),
        ):
            if not Sector.objects.filter(codigo__iexact=codigo).exists():
                Sector.objects.create(
                    codigo=codigo,
                    nombre=nombre,
                    descripcion=f"Sector {nombre} seeded for test.",
                    activo=True,
                    orden={"DEP": 1, "MAN": 2, "TAT": 3}[codigo],
                )

    def tearDown(self):
        Sector.objects.exclude(id__in=self._existing_ids).delete()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _unique_suffix(self):
        # Codigo-safe suffix for tests that need to avoid the seed.
        return self._testMethodName.replace("_", "-")[:12]

    def _create_unique_sector(self, *, activo=True, codigo_prefix="OTR"):
        suffix = self._unique_suffix()
        return Sector.objects.create(
            codigo=f"{codigo_prefix}-{suffix}".upper(),
            nombre=f"Sector {suffix}",
            activo=activo,
        )

    def _post(self, path, payload):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=f"sectores-{self._testMethodName}",
        )

    # ------------------------------------------------------------------
    # GET /api/admin/catalogos/sectores/
    # ------------------------------------------------------------------
    def test_list_returns_baseline_seed_sectores(self):
        self.client.force_login(self.admin_general)
        response = self.client.get("/api/admin/catalogos/sectores/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["catalog"]["key"], "sectores")
        self.assertEqual(data["catalog"]["title"], "Sectores")
        self.assertEqual(data["catalog"]["createLabel"], "Crear sector")

        codigos = {item["values"]["code"] for item in data["items"]}
        self.assertEqual(codigos, {"DEP", "MAN", "TAT"})

        # Items expose the expected fields used by the frontend tab.
        sample = data["items"][0]
        for key in ("id", "title", "subtitle", "active", "metadata", "values"):
            self.assertIn(key, sample)
        for key in ("code", "name", "description"):
            self.assertIn(key, sample["values"])
        # `order` is server-managed and no longer exposed in the list payload
        self.assertNotIn("order", sample["values"])
        self.assertNotIn(
            "Orden",
            [entry.get("label") for entry in sample["metadata"]],
        )

    def test_list_active_true_returns_only_active_sectors(self):
        inactive = self._create_unique_sector(activo=False)

        self.client.force_login(self.admin_general)
        response = self.client.get("/api/admin/catalogos/sectores/?active=true")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        active_ids = {item["id"] for item in data["items"]}
        self.assertNotIn(inactive.pk, active_ids)

        # DEP/MAN/TAT are seeded as active.
        seed_ids = set(
            Sector.objects.filter(
                codigo__in=self.SEED_RESERVED_CODIGOS, activo=True
            ).values_list("id", flat=True)
        )
        self.assertTrue(seed_ids.issubset(active_ids))
        self.assertTrue(all(item["active"] for item in data["items"]))

    def test_list_active_false_returns_only_inactive_sectors(self):
        self._create_unique_sector(activo=False)

        self.client.force_login(self.admin_general)
        response = self.client.get("/api/admin/catalogos/sectores/?active=false")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["items"])
        self.assertTrue(all(not item["active"] for item in data["items"]))

    def test_list_q_matches_codigo(self):
        self.client.force_login(self.admin_general)
        response = self.client.get("/api/admin/catalogos/sectores/?q=dep")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        codigos = [item["values"]["code"] for item in data["items"]]
        self.assertIn("DEP", codigos)
        self.assertNotIn("TAT", codigos)

    def test_list_q_matches_nombre_substring(self):
        # Create a sector whose name contains "dep" but whose codigo does
        # NOT, so the search has to look at the `nombre` field.
        suffix = self._unique_suffix()
        Sector.objects.create(
            codigo=f"NOM-{suffix}".upper(),
            nombre=f"Depilacion {suffix}",
        )

        self.client.force_login(self.admin_general)
        response = self.client.get("/api/admin/catalogos/sectores/?q=dep")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        nombres = [item["values"]["name"] for item in data["items"]]
        self.assertTrue(
            any("Depilacion" in n for n in nombres),
            f"Expected at least one match on nombre for q=dep; got {nombres}",
        )

    def test_list_invalid_active_param_returns_400(self):
        self.client.force_login(self.admin_general)
        response = self.client.get("/api/admin/catalogos/sectores/?active=bogus")

        self.assertEqual(response.status_code, 400)
        self.assertIn("active", response.json()["detail"].lower())

    # ------------------------------------------------------------------
    # POST /api/admin/catalogos/sectores/crear/
    # ------------------------------------------------------------------
    def test_create_sector_persists_and_returns_201(self):
        self.client.force_login(self.admin_general)
        suffix = self._unique_suffix()
        payload = {
            "code": f"NEW-{suffix}".upper(),
            "name": f"Nuevo sector {suffix}",
            "description": "Creado desde test",
            "order": 5,
            "active": True,
        }
        baseline_max = Sector.objects.aggregate(Max("orden"))["orden__max"] or 0

        response = self._post("/api/admin/catalogos/sectores/crear/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["detail"], "Registro creado correctamente.")
        self.assertEqual(body["item"]["values"]["code"], payload["code"])

        created = Sector.objects.get(pk=body["item"]["id"])
        self.assertEqual(created.codigo, payload["code"])
        self.assertEqual(created.nombre, payload["name"])
        self.assertEqual(created.descripcion, payload["description"])
        # orden is auto-assigned on create; payload's `order` is ignored
        self.assertEqual(created.orden, baseline_max + 1)
        self.assertTrue(created.activo)

    def test_create_sector_without_codigo_returns_400(self):
        self.client.force_login(self.admin_general)
        response = self._post(
            "/api/admin/catalogos/sectores/crear/",
            {"name": "Sin codigo"},
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["detail"], "Hay errores en el formulario.")
        self.assertIn("code", body["errors"])

    def test_create_sector_without_nombre_returns_400(self):
        self.client.force_login(self.admin_general)
        response = self._post(
            "/api/admin/catalogos/sectores/crear/",
            {"code": "NOCODIGO"},
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["detail"], "Hay errores en el formulario.")
        self.assertIn("name", body["errors"])

    def test_create_sector_with_duplicate_codigo_returns_400(self):
        self.client.force_login(self.admin_general)

        first = self._post(
            "/api/admin/catalogos/sectores/crear/",
            {"code": "DUP-SECTORESAPI", "name": "Original"},
        )
        self.assertEqual(first.status_code, 201, first.content)

        # Try with the same codigo (case insensitive) and a different nombre.
        second = self._post(
            "/api/admin/catalogos/sectores/crear/",
            {"code": "dup-sectoresapi", "name": "Duplicado"},
        )

        # The unique constraint (case-insensitive) is enforced through
        # full_clean(), so the response is a ValidationError envelope with
        # a 400 status, not the IntegrityError "Ya existe..." fallback.
        self.assertEqual(second.status_code, 400, second.content)
        body = second.json()
        self.assertEqual(body["detail"], "Hay errores en el formulario.")
        self.assertIn("__all__", body["errors"])
        self.assertTrue(
            any("uniq_sector_codigo_ci" in msg for msg in body["errors"]["__all__"]),
            f"Expected uniq_sector_codigo_ci in errors, got {body['errors']}",
        )

    def test_create_sector_with_duplicate_nombre_returns_400(self):
        self.client.force_login(self.admin_general)

        first = self._post(
            "/api/admin/catalogos/sectores/crear/",
            {"code": "DUP-NAME-A", "name": "Nombre Duplicado"},
        )
        self.assertEqual(first.status_code, 201, first.content)

        second = self._post(
            "/api/admin/catalogos/sectores/crear/",
            {"code": "DUP-NAME-B", "name": "NOMBRE DUPLICADO"},
        )

        self.assertEqual(second.status_code, 400, second.content)
        body = second.json()
        self.assertEqual(body["detail"], "Hay errores en el formulario.")
        self.assertIn("__all__", body["errors"])
        self.assertTrue(
            any("uniq_sector_nombre_ci" in msg for msg in body["errors"]["__all__"]),
            f"Expected uniq_sector_nombre_ci in errors, got {body['errors']}",
        )

    # ------------------------------------------------------------------
    # POST /api/admin/catalogos/sectores/<id>/actualizar/
    # ------------------------------------------------------------------
    def test_update_sector_persists_changes(self):
        sector = self._create_unique_sector()
        original_orden = sector.orden

        self.client.force_login(self.admin_general)
        response = self._post(
            f"/api/admin/catalogos/sectores/{sector.pk}/actualizar/",
            {
                "code": sector.codigo,
                "name": f"{sector.nombre} (editado)",
                "description": "Descripcion actualizada",
                "order": 9,
            },
        )

        self.assertEqual(response.status_code, 200, response.content)
        sector.refresh_from_db()
        self.assertEqual(sector.descripcion, "Descripcion actualizada")
        # orden is not exposed in the form; updates must preserve the existing value
        self.assertEqual(sector.orden, original_orden)
        self.assertTrue(sector.nombre.endswith("(editado)"))

    # ------------------------------------------------------------------
    # POST /api/admin/catalogos/sectores/<id>/estado/
    # ------------------------------------------------------------------
    def test_toggle_activo_endpoint_flips_flag(self):
        sector = self._create_unique_sector(activo=True)

        self.client.force_login(self.admin_general)
        response = self._post(
            f"/api/admin/catalogos/sectores/{sector.pk}/estado/",
            {"active": False},
        )

        self.assertEqual(response.status_code, 200, response.content)
        sector.refresh_from_db()
        self.assertFalse(sector.activo)

        # Toggle back to active.
        response = self._post(
            f"/api/admin/catalogos/sectores/{sector.pk}/estado/",
            {"active": True},
        )
        self.assertEqual(response.status_code, 200)
        sector.refresh_from_db()
        self.assertTrue(sector.activo)

    def test_toggle_activo_without_bool_returns_400(self):
        sector = self._create_unique_sector()

        self.client.force_login(self.admin_general)
        response = self._post(
            f"/api/admin/catalogos/sectores/{sector.pk}/estado/",
            {"active": "no"},
        )

        self.assertEqual(response.status_code, 400)

    def test_create_sector_auto_assigns_orden_plus_one(self):
        baseline_max = Sector.objects.aggregate(Max("orden"))["orden__max"] or 0

        self.client.force_login(self.admin_general)
        suffix = self._unique_suffix()
        response = self._post(
            "/api/admin/catalogos/sectores/crear/",
            {
                "code": f"auto-{suffix}".lower(),
                "name": f"Auto Orden {suffix}",
                "description": "Sector creado sin enviar orden",
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        new_sector = Sector.objects.get(codigo=f"auto-{suffix}".lower())
        self.assertEqual(new_sector.orden, baseline_max + 1)

    def test_update_sector_does_not_change_orden(self):
        sector = self._create_unique_sector()
        sector.orden = 7
        sector.save(update_fields=["orden"])
        original_orden = sector.orden

        self.client.force_login(self.admin_general)
        response = self._post(
            f"/api/admin/catalogos/sectores/{sector.pk}/actualizar/",
            {
                "code": sector.codigo,
                "name": f"{sector.nombre} (renombrado)",
                "description": sector.descripcion or "",
            },
        )

        self.assertEqual(response.status_code, 200, response.content)
        sector.refresh_from_db()
        self.assertEqual(sector.orden, original_orden)


class SectoresModelConstraintsTests(TestCase):
    """Cover the model-level unique constraints independently of the API."""

    def setUp(self):
        self._existing_ids = set(Sector.objects.values_list("id", flat=True))

    def tearDown(self):
        Sector.objects.exclude(id__in=self._existing_ids).delete()

    def test_model_unique_codigo_rejects_duplicate_at_db_level(self):
        suffix = "dbuniqcod"
        Sector.objects.create(
            codigo=f"UCOD-{suffix}".upper(),
            nombre="Unico codigo",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Sector.objects.create(
                    codigo=f"ucod-{suffix}".lower(),
                    nombre="Distinto nombre",
                )

    def test_model_unique_nombre_rejects_duplicate_at_db_level(self):
        suffix = "dbuniqnom"
        Sector.objects.create(
            codigo=f"UNOM-A-{suffix}",
            nombre=f"Repetido {suffix}",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Sector.objects.create(
                    codigo=f"UNOM-B-{suffix}",
                    nombre=f"REPETIDO {suffix}",
                )