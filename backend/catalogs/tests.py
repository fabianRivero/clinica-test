from django.test import Client, TestCase

from accounts.models import Rol, Usuario
from billing.models import CategoriaGasto
from catalogs.models import ProcEstetico, ProcEsteticosTipo, ServicioConfig, TipoServicio
from staff.models import Especialidad


URL_TEMPLATES = {
    "todos-los-servicios": "/api/admin/catalogos/todos-los-servicios/",
    "procedimientos-esteticos": "/api/admin/catalogos/procedimientos-esteticos/",
    "tipos-servicio": "/api/admin/catalogos/tipos-servicio/",
    "tipos-procedimiento": "/api/admin/catalogos/tipos-procedimiento/",
    "especialidades": "/api/admin/catalogos/especialidades/",
    "categorias-gasto": "/api/admin/catalogos/categorias-gasto/",
}


class CatalogDetailFilterTests(TestCase):
    """Backend tests for `?q=` title search and `?active=` filter on the
    admin catalog detail endpoint. Covers the five in-scope catalogs.
    """

    @classmethod
    def setUpTestData(cls):
        admin_role = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.admin = Usuario.objects.create_superuser(
            username="catalog_admin",
            password="test",
            primer_nombre="Catalog",
            apellido_paterno="Admin",
            rol=admin_role,
        )

        cls.ts_consulta = TipoServicio.objects.create(tipo="Consulta general", activo=True)
        cls.ts_estetica = TipoServicio.objects.create(tipo="Estética facial", activo=False)

        cls.ptipo = ProcEsteticosTipo.objects.create(tipo="Laser")
        cls.tipo_proc_laser = ProcEsteticosTipo.objects.create(tipo="Laser diodo", activo=True)
        cls.tipo_proc_inactivo = ProcEsteticosTipo.objects.create(tipo="Peeling inactivo", activo=False)
        cls.tipo_proc_unique = ProcEsteticosTipo.objects.create(tipo="TestLaser", activo=True)
        cls.pe_botox = ProcEstetico.objects.create(
            tipo_p_estetico=cls.ptipo, proceso="Aplicación de botox", activo=True
        )
        cls.pe_laser = ProcEstetico.objects.create(
            tipo_p_estetico=cls.ptipo, proceso="Sesión de láser", activo=True
        )

        cls.servicio = ServicioConfig.objects.create(
            tipo_servicio=cls.ts_consulta,
            proc_estetico=cls.pe_laser,
            precio_base=100,
            activo=True,
        )

        cls.esp_cardiologia = Especialidad.objects.create(
            nombre="Cardiología", activo=True, orden=1
        )
        cls.esp_dermatologia = Especialidad.objects.create(
            nombre="Dermatología cosmética", activo=False, orden=2
        )

        cls.cat_insumos = CategoriaGasto.objects.create(
            nombre="Insumos médicos", activo=True
        )
        cls.cat_otros = CategoriaGasto.objects.create(
            nombre="Otros gastos", activo=False
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)

    def _ids(self, response):
        return [item["id"] for item in response.json()["items"]]

    def _titles(self, response):
        return [item["title"] for item in response.json()["items"]]

    # --- happy path: no params returns 200 for every catalog ---

    def test_get_without_params_returns_200_for_every_catalog(self):
        for key, url in URL_TEMPLATES.items():
            with self.subTest(catalog=key):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    # --- q search: one per in-scope catalog ---

    def test_search_tipos_servicio_filters_by_title(self):
        response = self.client.get(URL_TEMPLATES["tipos-servicio"], {"q": "estét"})
        self.assertEqual(self._titles(response), ["Estética facial"])

    def test_search_procedimientos_esteticos_filters_by_proceso(self):
        response = self.client.get(URL_TEMPLATES["procedimientos-esteticos"], {"q": "botox"})
        self.assertEqual(self._titles(response), ["Aplicación de botox"])

    def test_search_especialidades_filters_by_nombre(self):
        response = self.client.get(URL_TEMPLATES["especialidades"], {"q": "derma"})
        self.assertEqual(self._titles(response), ["Dermatología cosmética"])

    def test_search_categorias_gasto_filters_by_nombre(self):
        response = self.client.get(URL_TEMPLATES["categorias-gasto"], {"q": "insumos"})
        self.assertEqual(self._titles(response), ["Insumos médicos"])

    def test_search_todos_los_servicios_uses_or_across_fks(self):
        # "láser" only appears in proc_estetico.proceso for the active service.
        response = self.client.get(URL_TEMPLATES["todos-los-servicios"], {"q": "láser"})
        self.assertEqual(self._ids(response), [self.servicio.pk])

    # --- active filter: true / false / all on tipos-servicio ---

    def test_active_true_and_false_and_all(self):
        url = URL_TEMPLATES["tipos-servicio"]
        self.assertEqual(
            self._ids(self.client.get(url, {"active": "true"})),
            [self.ts_consulta.pk],
        )
        self.assertEqual(
            self._ids(self.client.get(url, {"active": "false"})),
            [self.ts_estetica.pk],
        )
        expected = sorted([self.ts_consulta.pk, self.ts_estetica.pk])
        self.assertEqual(
            sorted(self._ids(self.client.get(url, {"active": "all"}))),
            expected,
        )

    # --- combined q + active ---

    def test_combined_q_and_active_narrows_results(self):
        url = URL_TEMPLATES["tipos-servicio"]
        # 'estét' only matches "Estética facial" (inactive), so active=true drops it.
        response = self.client.get(url, {"q": "estét", "active": "true"})
        self.assertEqual(self._titles(response), [])

    # --- validation: invalid active value ---

    def test_invalid_active_param_returns_400(self):
        response = self.client.get(URL_TEMPLATES["tipos-servicio"], {"active": "maybe"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("active", response.json()["detail"].lower())

    # --- unauthenticated request proves params are parsed even when blocked ---

    def test_unauthenticated_request_returns_401(self):
        response = Client().get(URL_TEMPLATES["tipos-servicio"], {"q": "consulta"})
        self.assertEqual(response.status_code, 401)

    # --- metrics MUST reflect the unfiltered catalog (regression for
    #     todos-los-servicios bug where the metrics block was re-assigned
    #     from the filtered queryset, contradicting the spec).

    def test_metrics_reflect_unfiltered_catalog(self):
        # 'estét' only matches the inactive "Estética facial"; combined with
        # active=true, items is empty — but metrics MUST still report 2 total.
        response = self.client.get(
            URL_TEMPLATES["tipos-servicio"],
            {"q": "estét", "active": "true"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 0)
        metrics = {m["id"]: m for m in payload["metrics"]}
        self.assertEqual(metrics["catalog-active"]["value"], "1")
        self.assertEqual(metrics["catalog-inactive"]["value"], "1")
        self.assertEqual(metrics["catalog-total"]["value"], "2")

    def test_active_filter_on_todos_los_servicios(self):
        # Build a second ServicioConfig using a different tipo_servicio and
        # no proc_estetico, marked inactive, to exercise the active filter
        # on the most complex catalog branch.
        ts_otro = TipoServicio.objects.create(tipo="Consulta de control", activo=True)
        servicio_inactivo = ServicioConfig.objects.create(
            tipo_servicio=ts_otro,
            proc_estetico=None,
            precio_base=50,
            activo=False,
        )

        url = URL_TEMPLATES["todos-los-servicios"]

        # active=false returns only the inactive service.
        response_false = self.client.get(url, {"active": "false"})
        self.assertEqual(response_false.status_code, 200)
        ids_false = self._ids(response_false)
        self.assertIn(servicio_inactivo.pk, ids_false)
        self.assertNotIn(self.servicio.pk, ids_false)

        # active=true returns only the active service.
        response_true = self.client.get(url, {"active": "true"})
        self.assertEqual(response_true.status_code, 200)
        ids_true = self._ids(response_true)
        self.assertIn(self.servicio.pk, ids_true)
        self.assertNotIn(servicio_inactivo.pk, ids_true)

        # Metrics on the active=true call must still report the unfiltered
        # totals (2 total, 1 active, 1 inactive) — locking in the spec
        # contract for this branch.
        metrics = {m["id"]: m for m in response_true.json()["metrics"]}
        self.assertEqual(metrics["catalog-active"]["value"], "1")
        self.assertEqual(metrics["catalog-inactive"]["value"], "1")
        self.assertEqual(metrics["catalog-total"]["value"], "2")

    # --- tipos-procedimiento catalog (added in manage-procedure-types-catalog) ---

    def test_search_tipos_procedimiento_filters_by_tipo(self):
        response = self.client.get(URL_TEMPLATES["tipos-procedimiento"], {"q": "TestLaser"})
        self.assertEqual(self._ids(response), [self.tipo_proc_unique.pk])

    def test_active_true_and_false_and_all_on_tipos_procedimiento(self):
        url = URL_TEMPLATES["tipos-procedimiento"]
        # ptipo defaults to activo=True via the model, so active=true includes it
        # along with the two explicitly active fixtures.
        self.assertEqual(
            sorted(self._ids(self.client.get(url, {"active": "true"}))),
            sorted([self.ptipo.pk, self.tipo_proc_laser.pk, self.tipo_proc_unique.pk]),
        )
        self.assertEqual(
            self._ids(self.client.get(url, {"active": "false"})),
            [self.tipo_proc_inactivo.pk],
        )
        expected = sorted(
            [
                self.ptipo.pk,
                self.tipo_proc_laser.pk,
                self.tipo_proc_unique.pk,
                self.tipo_proc_inactivo.pk,
            ]
        )
        self.assertEqual(
            sorted(self._ids(self.client.get(url, {"active": "all"}))),
            expected,
        )

    def test_combined_q_and_active_on_tipos_procedimiento(self):
        url = URL_TEMPLATES["tipos-procedimiento"]
        # 'TestLaser' matches only the active fixture, so active=false drops it.
        response = self.client.get(url, {"q": "TestLaser", "active": "false"})
        self.assertEqual(self._ids(response), [])

    def test_invalid_active_param_returns_400_for_tipos_procedimiento(self):
        response = self.client.get(
            URL_TEMPLATES["tipos-procedimiento"], {"active": "invalid"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("active", response.json()["detail"].lower())

    def test_metrics_reflect_unfiltered_catalog_for_tipos_procedimiento(self):
        # Search that returns 0 items but metrics MUST still report full totals.
        response = self.client.get(
            URL_TEMPLATES["tipos-procedimiento"],
            {"q": "zzz_no_match"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 0)
        metrics = {m["id"]: m for m in payload["metrics"]}
        # Four fixtures: ptipo + Laser diodo + TestLaser are active; Peeling inactivo is not.
        self.assertEqual(metrics["catalog-active"]["value"], "3")
        self.assertEqual(metrics["catalog-inactive"]["value"], "1")
        self.assertEqual(metrics["catalog-total"]["value"], "4")
