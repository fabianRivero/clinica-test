"""API integration tests for the `secciones-ficha` admin catalog.

These tests exercise the new FichaSeccion catalog end-to-end: list
with search/active/sector/proc filters, create with the three binding
modes (sector only, proc only, both), at-least-one validation,
uniqueness per (proc_estetico, codigo), update, and toggle.

The data migration `0006_seed_sectores_and_reassign_fichaseccion`
pre-populates the test DB with DEP/MAN/TAT sectors. Tests use suffixed
codigos/nombres so they stay independent of the seed and can run in
any order.
"""

import json

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import ProcEstetico, ProcEsteticosTipo, Sector
from clinical.models import FichaSeccion


class SeccionesFichaCatalogApiTests(TestCase):
    """Integration tests for the `/api/admin/catalogos/secciones-ficha/`
    endpoints.
    """

    SEED_RESERVED_CODIGOS = ("DEP", "MAN", "TAT")

    def setUp(self):
        self.rol_admin_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")

        self.admin_general = Usuario.objects.create_user(
            username="admin.general.secciones-ficha",
            password="password123",
            primer_nombre="Admin",
            apellido_paterno="General",
            rol=self.rol_admin_principal,
            sucursal=None,
        )

        # Capture any pre-existing sections so we can clean up after the
        # test finishes and leave the global seed intact for the rest
        # of the suite.
        self._existing_section_ids = set(
            FichaSeccion.objects.values_list("id", flat=True)
        )

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

        # Procedure type used as FK target for ProcEstetico records.
        self.procedure_type = ProcEsteticosTipo.objects.create(
            tipo="Secciones ficha test",
        )

        # Two reusable procedures so we can verify uniqueness is scoped
        # per procedure, not global.
        suffix = self._testMethodName[:8].replace("_", "-")
        self.proc_a = ProcEstetico.objects.create(
            tipo_p_estetico=self.procedure_type,
            proceso=f"Proc A secciones ficha {suffix}",
        )
        self.proc_b = ProcEstetico.objects.create(
            tipo_p_estetico=self.procedure_type,
            proceso=f"Proc B secciones ficha {suffix}",
        )

        self.dep_sector = Sector.objects.get(codigo="DEP")
        self.tat_sector = Sector.objects.get(codigo="TAT")

    def tearDown(self):
        FichaSeccion.objects.exclude(id__in=self._existing_section_ids).delete()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _unique_codigo(self, prefix="SEC"):
        # Codigo-safe suffix to keep tests independent.
        suffix = self._testMethodName.replace("_", "-")[:10]
        return f"{prefix}-{suffix}".upper()

    def _post(self, path, payload):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=f"secciones-ficha-{self._testMethodName}",
        )

    # ------------------------------------------------------------------
    # GET /api/admin/catalogos/secciones-ficha/
    # ------------------------------------------------------------------
    def test_list_returns_empty_when_no_sections_exist(self):
        self.client.force_login(self.admin_general)
        response = self.client.get("/api/admin/catalogos/secciones-ficha/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["catalog"]["key"], "secciones-ficha")
        self.assertEqual(data["catalog"]["title"], "Secciones de ficha")
        self.assertEqual(data["catalog"]["createLabel"], "Crear sección de ficha")
        self.assertEqual(data["items"], [])

    def test_list_active_true_returns_only_active_sections(self):
        active_section = FichaSeccion.objects.create(
            nombre="Activa",
            codigo=self._unique_codigo(),
            sector=self.dep_sector,
            activo=True,
        )
        inactive_section = FichaSeccion.objects.create(
            nombre="Inactiva",
            codigo=self._unique_codigo("INA"),
            sector=self.dep_sector,
            activo=False,
        )

        self.client.force_login(self.admin_general)
        response = self.client.get("/api/admin/catalogos/secciones-ficha/?active=true")

        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["items"]}
        self.assertIn(active_section.pk, ids)
        self.assertNotIn(inactive_section.pk, ids)

    def test_list_q_matches_codigo(self):
        suffix = self._testMethodName.replace("_", "-")[:10].upper()
        target = FichaSeccion.objects.create(
            nombre="Antecedentes",
            codigo=f"ANT-{suffix}",
            sector=self.dep_sector,
        )
        FichaSeccion.objects.create(
            nombre="Otra",
            codigo=f"OTR-{suffix}",
            sector=self.dep_sector,
        )

        self.client.force_login(self.admin_general)
        response = self.client.get(
            f"/api/admin/catalogos/secciones-ficha/?q=ant-{suffix.lower()}"
        )

        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["items"]}
        self.assertIn(target.pk, ids)

    def test_list_q_matches_nombre(self):
        suffix = self._testMethodName.replace("_", "-")[:10].upper()
        target = FichaSeccion.objects.create(
            nombre=f"Antecedentes {suffix}",
            codigo=f"COD-{suffix}",
            sector=self.dep_sector,
        )

        self.client.force_login(self.admin_general)
        response = self.client.get(
            f"/api/admin/catalogos/secciones-ficha/?q=antecedentes"
        )

        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["items"]}
        self.assertIn(target.pk, ids)

    def test_list_filters_by_sector(self):
        suffix = self._testMethodName.replace("_", "-")[:10].upper()
        dep_section = FichaSeccion.objects.create(
            nombre="DEP",
            codigo=f"DEP-{suffix}",
            sector=self.dep_sector,
        )
        tat_section = FichaSeccion.objects.create(
            nombre="TAT",
            codigo=f"TAT-{suffix}",
            sector=self.tat_sector,
        )

        self.client.force_login(self.admin_general)
        response = self.client.get(
            f"/api/admin/catalogos/secciones-ficha/?sector={self.dep_sector.pk}"
        )

        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["items"]}
        self.assertIn(dep_section.pk, ids)
        self.assertNotIn(tat_section.pk, ids)

    def test_list_filters_by_proc_estetico(self):
        suffix = self._testMethodName.replace("_", "-")[:10].upper()
        proc_a_section = FichaSeccion.objects.create(
            nombre="Proc A",
            codigo=f"PA-{suffix}",
            proc_estetico=self.proc_a,
        )
        proc_b_section = FichaSeccion.objects.create(
            nombre="Proc B",
            codigo=f"PB-{suffix}",
            proc_estetico=self.proc_b,
        )

        self.client.force_login(self.admin_general)
        response = self.client.get(
            f"/api/admin/catalogos/secciones-ficha/?proc_estetico={self.proc_a.pk}"
        )

        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["items"]}
        self.assertIn(proc_a_section.pk, ids)
        self.assertNotIn(proc_b_section.pk, ids)

    # ------------------------------------------------------------------
    # POST /api/admin/catalogos/secciones-ficha/crear/
    # ------------------------------------------------------------------
    def test_create_section_with_sector_only_returns_201(self):
        self.client.force_login(self.admin_general)
        codigo = self._unique_codigo()
        payload = {
            "name": "Solo sector",
            "code": codigo,
            "sectorId": self.dep_sector.pk,
            "active": True,
        }
        baseline_max = FichaSeccion.objects.aggregate(Max("orden"))["orden__max"] or 0

        response = self._post("/api/admin/catalogos/secciones-ficha/crear/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["detail"], "Registro creado correctamente.")
        self.assertEqual(body["item"]["values"]["sectorId"], self.dep_sector.pk)
        self.assertIsNone(body["item"]["values"]["procEsteticoId"])

        created = FichaSeccion.objects.get(pk=body["item"]["id"])
        self.assertEqual(created.sector_id, self.dep_sector.pk)
        self.assertIsNone(created.proc_estetico_id)
        self.assertEqual(created.codigo, codigo)
        self.assertEqual(created.nombre, "Solo sector")
        # orden is auto-assigned on create; payload no longer carries `order`
        self.assertEqual(created.orden, baseline_max + 1)
        self.assertTrue(created.activo)

    def test_create_section_with_proc_only_returns_201(self):
        self.client.force_login(self.admin_general)
        codigo = self._unique_codigo()
        payload = {
            "name": "Solo procedimiento",
            "code": codigo,
            "procEsteticoId": self.proc_a.pk,
            "active": True,
        }
        baseline_max = FichaSeccion.objects.aggregate(Max("orden"))["orden__max"] or 0

        response = self._post("/api/admin/catalogos/secciones-ficha/crear/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["item"]["values"]["procEsteticoId"], self.proc_a.pk)
        self.assertIsNone(body["item"]["values"]["sectorId"])

        created = FichaSeccion.objects.get(pk=body["item"]["id"])
        self.assertIsNone(created.sector_id)
        self.assertEqual(created.proc_estetico_id, self.proc_a.pk)
        # orden is auto-assigned on create; payload no longer carries `order`
        self.assertEqual(created.orden, baseline_max + 1)

    def test_create_section_with_both_bindings_returns_201(self):
        self.client.force_login(self.admin_general)
        codigo = self._unique_codigo()
        payload = {
            "name": "Ambos bindings",
            "code": codigo,
            "sectorId": self.dep_sector.pk,
            "procEsteticoId": self.proc_a.pk,
            "active": True,
        }
        baseline_max = FichaSeccion.objects.aggregate(Max("orden"))["orden__max"] or 0

        response = self._post("/api/admin/catalogos/secciones-ficha/crear/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["item"]["values"]["sectorId"], self.dep_sector.pk)
        self.assertEqual(body["item"]["values"]["procEsteticoId"], self.proc_a.pk)

        created = FichaSeccion.objects.get(pk=body["item"]["id"])
        self.assertEqual(created.sector_id, self.dep_sector.pk)
        self.assertEqual(created.proc_estetico_id, self.proc_a.pk)
        # orden is auto-assigned on create; payload no longer carries `order`
        self.assertEqual(created.orden, baseline_max + 1)

    def test_create_section_without_bindings_returns_400(self):
        self.client.force_login(self.admin_general)
        payload = {
            "name": "Huerfano",
            "code": self._unique_codigo(),
            "active": True,
        }

        response = self._post("/api/admin/catalogos/secciones-ficha/crear/", payload)

        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertEqual(body["detail"], "Hay errores en el formulario.")
        self.assertIn("_general", body["errors"])
        self.assertIn("al menos un sector", body["errors"]["_general"][0])

    def test_create_section_with_duplicate_codigo_in_same_proc_returns_400(self):
        self.client.force_login(self.admin_general)
        codigo = self._unique_codigo()

        first = self._post(
            "/api/admin/catalogos/secciones-ficha/crear/",
            {
                "name": "Original",
                "code": codigo,
                "procEsteticoId": self.proc_a.pk,
                "active": True,
            },
        )
        self.assertEqual(first.status_code, 201, first.content)

        second = self._post(
            "/api/admin/catalogos/secciones-ficha/crear/",
            {
                "name": "Duplicado",
                "code": codigo,
                "procEsteticoId": self.proc_a.pk,
                "active": True,
            },
        )

        self.assertEqual(second.status_code, 400, second.content)
        body = second.json()
        self.assertEqual(body["detail"], "Hay errores en el formulario.")
        self.assertIn("code", body["errors"])
        self.assertIn("Ya existe", body["errors"]["code"][0])

    def test_create_section_with_same_codigo_in_different_proc_returns_201(self):
        self.client.force_login(self.admin_general)
        codigo = self._unique_codigo()

        first = self._post(
            "/api/admin/catalogos/secciones-ficha/crear/",
            {
                "name": "En proc A",
                "code": codigo,
                "procEsteticoId": self.proc_a.pk,
                "active": True,
            },
        )
        self.assertEqual(first.status_code, 201, first.content)

        # Same codigo, different proc_estetico — must succeed because the
        # uniqueness constraint is scoped per procedure.
        second = self._post(
            "/api/admin/catalogos/secciones-ficha/crear/",
            {
                "name": "En proc B",
                "code": codigo,
                "procEsteticoId": self.proc_b.pk,
                "active": True,
            },
        )

        self.assertEqual(second.status_code, 201, second.content)
        body = second.json()
        self.assertEqual(body["item"]["values"]["code"], codigo)
        self.assertEqual(body["item"]["values"]["procEsteticoId"], self.proc_b.pk)

    def test_create_section_without_codigo_returns_400(self):
        self.client.force_login(self.admin_general)
        response = self._post(
            "/api/admin/catalogos/secciones-ficha/crear/",
            {
                "name": "Sin codigo",
                "sectorId": self.dep_sector.pk,
                "active": True,
            },
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("code", body["errors"])

    def test_create_section_without_nombre_returns_400(self):
        self.client.force_login(self.admin_general)
        response = self._post(
            "/api/admin/catalogos/secciones-ficha/crear/",
            {
                "code": self._unique_codigo(),
                "sectorId": self.dep_sector.pk,
                "active": True,
            },
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("name", body["errors"])

    # ------------------------------------------------------------------
    # POST /api/admin/catalogos/secciones-ficha/<id>/actualizar/
    # ------------------------------------------------------------------
    def test_update_section_persists_changes(self):
        section = FichaSeccion.objects.create(
            nombre="Original",
            codigo=self._unique_codigo(),
            sector=self.dep_sector,
            orden=1,
        )

        self.client.force_login(self.admin_general)
        response = self._post(
            f"/api/admin/catalogos/secciones-ficha/{section.pk}/actualizar/",
            {
                "name": "Editado",
                "code": section.codigo,
                "sectorId": self.tat_sector.pk,
                "order": 9,
                "active": True,
            },
        )

        self.assertEqual(response.status_code, 200, response.content)
        section.refresh_from_db()
        self.assertEqual(section.nombre, "Editado")
        self.assertEqual(section.sector_id, self.tat_sector.pk)
        # orden is not exposed in the form; updates must preserve the existing value
        self.assertEqual(section.orden, 1)

    def test_update_with_order_9_preserves_orden(self):
        section = FichaSeccion.objects.create(
            nombre="Original",
            codigo=self._unique_codigo(),
            sector=self.dep_sector,
            orden=3,
        )

        self.client.force_login(self.admin_general)
        response = self._post(
            f"/api/admin/catalogos/secciones-ficha/{section.pk}/actualizar/",
            {
                "name": "Renombrado",
                "code": section.codigo,
                "sectorId": self.tat_sector.pk,
                "order": 9,
                "active": True,
            },
        )

        self.assertEqual(response.status_code, 200, response.content)
        section.refresh_from_db()
        # The payload's `order: 9` must be ignored; existing orden=3 preserved.
        self.assertEqual(section.orden, 3)
        self.assertEqual(section.nombre, "Renombrado")
        self.assertEqual(section.sector_id, self.tat_sector.pk)

    def test_update_section_can_swap_proc_estetico(self):
        section = FichaSeccion.objects.create(
            nombre="Original",
            codigo=self._unique_codigo(),
            proc_estetico=self.proc_a,
        )

        self.client.force_login(self.admin_general)
        response = self._post(
            f"/api/admin/catalogos/secciones-ficha/{section.pk}/actualizar/",
            {
                "name": "Editado",
                "code": section.codigo,
                "procEsteticoId": self.proc_b.pk,
                "active": True,
            },
        )

        self.assertEqual(response.status_code, 200, response.content)
        section.refresh_from_db()
        self.assertEqual(section.proc_estetico_id, self.proc_b.pk)

    # ------------------------------------------------------------------
    # POST /api/admin/catalogos/secciones-ficha/<id>/estado/
    # ------------------------------------------------------------------
    def test_toggle_activo_endpoint_flips_flag(self):
        section = FichaSeccion.objects.create(
            nombre="Toggle",
            codigo=self._unique_codigo(),
            sector=self.dep_sector,
            activo=True,
        )

        self.client.force_login(self.admin_general)
        response = self._post(
            f"/api/admin/catalogos/secciones-ficha/{section.pk}/estado/",
            {"active": False},
        )

        self.assertEqual(response.status_code, 200, response.content)
        section.refresh_from_db()
        self.assertFalse(section.activo)

        response = self._post(
            f"/api/admin/catalogos/secciones-ficha/{section.pk}/estado/",
            {"active": True},
        )

        self.assertEqual(response.status_code, 200)
        section.refresh_from_db()
        self.assertTrue(section.activo)


class SeccionesFichaModelConstraintsTests(TestCase):
    """Cover the model-level unique constraints independently of the API."""

    def setUp(self):
        self.procedure_type = ProcEsteticosTipo.objects.create(
            tipo="Secciones ficha model constraints",
        )
        self.proc_a = ProcEstetico.objects.create(
            tipo_p_estetico=self.procedure_type,
            proceso="Modelo A",
        )
        self.proc_b = ProcEstetico.objects.create(
            tipo_p_estetico=self.procedure_type,
            proceso="Modelo B",
        )

    def test_model_unique_codigo_per_proc_rejects_duplicate_at_db_level(self):
        FichaSeccion.objects.create(
            nombre="Original",
            codigo="DUPMOD-001",
            proc_estetico=self.proc_a,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FichaSeccion.objects.create(
                    nombre="Duplicado",
                    codigo="DUPMOD-001",
                    proc_estetico=self.proc_a,
                )

    def test_model_same_codigo_across_different_procs_allowed_at_db_level(self):
        FichaSeccion.objects.create(
            nombre="En proc A",
            codigo="CROSS-001",
            proc_estetico=self.proc_a,
        )
        # Same codigo, different proc — must NOT raise.
        FichaSeccion.objects.create(
            nombre="En proc B",
            codigo="CROSS-001",
            proc_estetico=self.proc_b,
        )
        self.assertEqual(
            FichaSeccion.objects.filter(codigo="CROSS-001").count(),
            2,
        )