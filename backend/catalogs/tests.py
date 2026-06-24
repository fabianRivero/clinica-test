from django.test import Client, TestCase

from accounts.models import Rol, Usuario
from billing.models import CategoriaGasto
from catalogs.models import ProcEstetico, ProcEsteticosTipo, ServicioConfig, TipoServicio
from staff.models import Especialidad


URL_TEMPLATES = {
    "todos-los-servicios": "/api/admin/catalogos/todos-los-servicios/",
    "procedimientos-esteticos": "/api/admin/catalogos/procedimientos-esteticos/",
    "tipos-servicio": "/api/admin/catalogos/tipos-servicio/",
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
