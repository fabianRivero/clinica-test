"""API integration tests for the nested `OpcionCatalogo` endpoints under
`/api/admin/catalogos/grupos-opciones/<grupo_id>/opciones/`.

These tests cover list with filters, single create (with validation and
uniqueness), bulk create with all-or-nothing rollback semantics, partial
update, activo toggle, and the integration invariant that inactive options
do not surface in `_serialize_medical_config`.

The endpoints are read-only for any admin (@admin_required) but require
@_admin_principal_required for mutations, mirroring the existing catalog
machinery in `admin_catalogo_crear` / `admin_catalogo_actualizar`.
"""

import json

from django.db import transaction
from django.test import Client, TestCase

from accounts.models import Rol, Usuario
from catalogs.models import (
    GrupoOpciones,
    OpcionCatalogo,
    ProcEstetico,
    ProcEsteticosTipo,
    Sector,
    ServicioConfig,
    TipoServicio,
)
from clinical.models import FichaCampo, FichaSeccion
from config.prospect_conversion_views import _serialize_medical_config


BASE_URL = "/api/admin/catalogos/grupos-opciones/{grupo_id}/opciones/"
CREAR_URL = "/api/admin/catalogos/grupos-opciones/{grupo_id}/opciones/crear/"
CREAR_MULT_URL = (
    "/api/admin/catalogos/grupos-opciones/{grupo_id}/opciones/crear-multiples/"
)
ACTUALIZAR_URL = (
    "/api/admin/catalogos/grupos-opciones/{grupo_id}/opciones/"
    "{opcion_id}/actualizar/"
)
ESTADO_URL = (
    "/api/admin/catalogos/grupos-opciones/{grupo_id}/opciones/"
    "{opcion_id}/estado/"
)


class OpcionCatalogoApiTests(TestCase):
    """Integration tests for the nested `OpcionCatalogo` endpoints."""

    def setUp(self):
        self.rol_admin_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.admin_principal = Usuario.objects.create_superuser(
            username="opciones.admin.principal",
            password="password123",
            primer_nombre="Admin",
            apellido_paterno="Principal",
            rol=self.rol_admin_principal,
            sucursal=None,
        )

        # A non-principal admin to confirm mutations are blocked for them.
        self.rol_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        self.sucursal = None  # admin principal no requiere sucursal activa
        self.admin_sucursal = Usuario.objects.create_user(
            username="opciones.admin.sucursal",
            password="password123",
            primer_nombre="Admin",
            apellido_paterno="Sucursal",
            rol=self.rol_sucursal,
            sucursal=self.sucursal,
        )

        self.grupo = GrupoOpciones.objects.create(
            codigo="OPC_TEST",
            nombre="Opciones de prueba",
            activo=True,
        )
        # Suffix used to keep codigos unique across tests in this class.
        self._suffix = self._testMethodName[:8].replace("_", "-").upper()

    def tearDown(self):
        OpcionCatalogo.objects.filter(grupo=self.grupo).delete()
        GrupoOpciones.objects.filter(pk=self.grupo.pk).delete()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _client(self, user):
        client = Client()
        client.force_login(user)
        return client

    def _post(self, client, path, payload):
        return client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _unique_codigo(self, prefix="OP"):
        return f"{prefix}-{self._suffix}"

    def _create_opcion(self, *, codigo=None, nombre=None, valor=None, activo=True, orden=0):
        return OpcionCatalogo.objects.create(
            grupo=self.grupo,
            codigo=codigo or self._unique_codigo("SEED"),
            nombre=nombre or f"Opcion {self._suffix}",
            valor=valor or "valor",
            orden=orden,
            activo=activo,
        )

    # ------------------------------------------------------------------
    # GET /opciones/  (list)
    # ------------------------------------------------------------------
    def test_list_empty_group_returns_empty_items(self):
        client = self._client(self.admin_principal)
        response = client.get(BASE_URL.format(grupo_id=self.grupo.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": []})

    def test_list_returns_all_options_with_expected_shape(self):
        opcion_a = self._create_opcion(codigo="LIST-A", nombre="A", valor="a", orden=2)
        opcion_b = self._create_opcion(codigo="LIST-B", nombre="B", valor="b", orden=1)

        client = self._client(self.admin_principal)
        response = client.get(BASE_URL.format(grupo_id=self.grupo.pk))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["items"]), 2)
        # Ordered by (orden, nombre): opcion_b (orden=1) before opcion_a (orden=2).
        self.assertEqual([item["codigo"] for item in data["items"]], ["LIST-B", "LIST-A"])

        sample = data["items"][0]
        for key in ("id", "codigo", "nombre", "valor", "orden", "activo", "grupoId"):
            self.assertIn(key, sample)
        self.assertEqual(sample["grupoId"], self.grupo.pk)
        self.assertEqual(sample["activo"], True)

    def test_list_filter_active_true_returns_only_active(self):
        self._create_opcion(codigo="ACT-1", activo=True)
        self._create_opcion(codigo="INA-1", activo=False)

        client = self._client(self.admin_principal)
        response = client.get(BASE_URL.format(grupo_id=self.grupo.pk), {"active": "true"})

        self.assertEqual(response.status_code, 200)
        codigos = [item["codigo"] for item in response.json()["items"]]
        self.assertEqual(codigos, ["ACT-1"])

    def test_list_filter_active_false_returns_only_inactive(self):
        self._create_opcion(codigo="ACT-2", activo=True)
        self._create_opcion(codigo="INA-2", activo=False)

        client = self._client(self.admin_principal)
        response = client.get(BASE_URL.format(grupo_id=self.grupo.pk), {"active": "false"})

        self.assertEqual(response.status_code, 200)
        codigos = [item["codigo"] for item in response.json()["items"]]
        self.assertEqual(codigos, ["INA-2"])

    def test_list_search_q_matches_codigo_nombre_and_valor(self):
        self._create_opcion(codigo="BUSQ-A", nombre="Buscar opcion", valor="uno")
        self._create_opcion(codigo="OTRO-X", nombre="Otro", valor="no importa")
        # The codigo itself contains the search term (case-insensitive).
        self._create_opcion(codigo="BUSCAR-COD", nombre="Sin match en nombre", valor="x")
        # Only the valor contains the term.
        self._create_opcion(codigo="OTRO-Y", nombre="Sin match", valor="buscar-en-valor")

        client = self._client(self.admin_principal)
        response = client.get(BASE_URL.format(grupo_id=self.grupo.pk), {"q": "buscar"})

        self.assertEqual(response.status_code, 200)
        codigos = sorted(item["codigo"] for item in response.json()["items"])
        self.assertEqual(codigos, ["BUSCAR-COD", "BUSQ-A", "OTRO-Y"])

    def test_list_unknown_group_returns_404(self):
        client = self._client(self.admin_principal)
        response = client.get(BASE_URL.format(grupo_id=9999))
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # POST /opciones/crear/  (single create)
    # ------------------------------------------------------------------
    def test_crear_valid_returns_201_and_item(self):
        client = self._client(self.admin_principal)
        payload = {
            "codigo": "CREAR-A",
            "nombre": "Opcion nueva",
            "valor": "n",
        }
        response = self._post(client, CREAR_URL.format(grupo_id=self.grupo.pk), payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("detail", data)
        self.assertEqual(data["item"]["codigo"], "CREAR-A")
        self.assertEqual(data["item"]["grupoId"], self.grupo.pk)
        # Default activo is True and orden is auto-assigned to 1.
        self.assertTrue(data["item"]["activo"])
        self.assertEqual(data["item"]["orden"], 1)
        self.assertTrue(OpcionCatalogo.objects.filter(codigo="CREAR-A").exists())

    def test_crear_without_codigo_returns_400(self):
        client = self._client(self.admin_principal)
        response = self._post(
            client,
            CREAR_URL.format(grupo_id=self.grupo.pk),
            {"nombre": "Sin codigo", "valor": "x"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("codigo", response.json()["errors"])
        self.assertEqual(OpcionCatalogo.objects.count(), 0)

    def test_crear_without_nombre_returns_400(self):
        client = self._client(self.admin_principal)
        response = self._post(
            client,
            CREAR_URL.format(grupo_id=self.grupo.pk),
            {"codigo": "SIN-NOMBRE", "valor": "x"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("nombre", response.json()["errors"])
        self.assertEqual(OpcionCatalogo.objects.count(), 0)

    def test_crear_without_valor_returns_400(self):
        client = self._client(self.admin_principal)
        response = self._post(
            client,
            CREAR_URL.format(grupo_id=self.grupo.pk),
            {"codigo": "SIN-VALOR", "nombre": "Sin valor"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("valor", response.json()["errors"])
        self.assertEqual(OpcionCatalogo.objects.count(), 0)

    def test_crear_duplicate_codigo_in_same_group_returns_400(self):
        self._create_opcion(codigo="DUP-1")

        client = self._client(self.admin_principal)
        response = self._post(
            client,
            CREAR_URL.format(grupo_id=self.grupo.pk),
            {"codigo": "DUP-1", "nombre": "Duplicado", "valor": "d"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("codigo", response.json()["errors"])
        # No duplicate was created.
        self.assertEqual(OpcionCatalogo.objects.filter(codigo="DUP-1").count(), 1)

    def test_crear_auto_assigns_orden_when_omitted(self):
        self._create_opcion(codigo="EXISTE", orden=3)
        client = self._client(self.admin_principal)
        response = self._post(
            client,
            CREAR_URL.format(grupo_id=self.grupo.pk),
            {"codigo": "AUTO-ORDEN", "nombre": "Auto", "valor": "a"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["item"]["orden"], 4)

    def test_crear_unknown_group_returns_404(self):
        client = self._client(self.admin_principal)
        response = self._post(
            client,
            CREAR_URL.format(grupo_id=9999),
            {"codigo": "GR-NO-EXISTE", "nombre": "Ghost", "valor": "g"},
        )

        self.assertEqual(response.status_code, 404)

    def test_crear_rejects_non_principal_admin(self):
        client = self._client(self.admin_sucursal)
        response = self._post(
            client,
            CREAR_URL.format(grupo_id=self.grupo.pk),
            {"codigo": "BLOQ", "nombre": "Bloqueado", "valor": "b"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(OpcionCatalogo.objects.count(), 0)

    # ------------------------------------------------------------------
    # POST /opciones/crear-multiples/  (bulk)
    # ------------------------------------------------------------------
    def test_crear_multiples_valid_batch_returns_201_with_all_items(self):
        client = self._client(self.admin_principal)
        payload = {
            "options": [
                {"codigo": "BULK-1", "nombre": "Uno", "valor": "1"},
                {"codigo": "BULK-2", "nombre": "Dos", "valor": "2"},
                {"codigo": "BULK-3", "nombre": "Tres", "valor": "3"},
            ]
        }
        response = self._post(
            client, CREAR_MULT_URL.format(grupo_id=self.grupo.pk), payload
        )

        self.assertEqual(response.status_code, 201)
        items = response.json()["items"]
        self.assertEqual(len(items), 3)
        self.assertEqual(OpcionCatalogo.objects.filter(grupo=self.grupo).count(), 3)
        # All three codigos exist in the group.
        self.assertEqual(
            set(OpcionCatalogo.objects.values_list("codigo", flat=True)),
            {"BULK-1", "BULK-2", "BULK-3"},
        )

    def test_crear_multiples_with_duplicate_in_batch_rolls_back_all(self):
        client = self._client(self.admin_principal)
        payload = {
            "options": [
                {"codigo": "BULK-A", "nombre": "A", "valor": "a"},
                {"codigo": "BULK-B", "nombre": "B", "valor": "b"},
                {"codigo": "BULK-A", "nombre": "Duplicado", "valor": "d"},
            ]
        }
        response = self._post(
            client, CREAR_MULT_URL.format(grupo_id=self.grupo.pk), payload
        )

        self.assertEqual(response.status_code, 400)
        # The duplicate entry at index 2 is reported with a per-field key.
        errors = response.json()["errors"]
        self.assertIn("options.2.codigo", errors)
        # Nothing was created.
        self.assertEqual(OpcionCatalogo.objects.filter(grupo=self.grupo).count(), 0)

    def test_crear_multiples_with_missing_field_rolls_back_all(self):
        client = self._client(self.admin_principal)
        payload = {
            "options": [
                {"codigo": "BULK-X", "nombre": "X", "valor": "x"},
                {"codigo": "BULK-Y", "valor": "y"},  # missing nombre
            ]
        }
        response = self._post(
            client, CREAR_MULT_URL.format(grupo_id=self.grupo.pk), payload
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("nombre", response.json()["errors"]["options.1.nombre"])
        self.assertEqual(OpcionCatalogo.objects.filter(grupo=self.grupo).count(), 0)

    def test_crear_multiples_with_codigo_already_in_db_rolls_back_all(self):
        self._create_opcion(codigo="EXISTE-DB")

        client = self._client(self.admin_principal)
        payload = {
            "options": [
                {"codigo": "FRESH-1", "nombre": "Uno", "valor": "1"},
                {"codigo": "EXISTE-DB", "nombre": "Dos", "valor": "2"},
            ]
        }
        response = self._post(
            client, CREAR_MULT_URL.format(grupo_id=self.grupo.pk), payload
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("codigo", response.json()["errors"]["options.1.codigo"])
        # Fresh entry was not created — atomic block rolled everything back.
        self.assertFalse(OpcionCatalogo.objects.filter(codigo="FRESH-1").exists())

    def test_crear_multiples_unknown_group_returns_404(self):
        client = self._client(self.admin_principal)
        payload = {
            "options": [{"codigo": "GHOST-1", "nombre": "G", "valor": "g"}]
        }
        response = self._post(
            client, CREAR_MULT_URL.format(grupo_id=9999), payload
        )
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # POST /opciones/<opcion_id>/actualizar/  (update)
    # ------------------------------------------------------------------
    def test_actualizar_partial_update_returns_200(self):
        opcion = self._create_opcion(codigo="UPD-1", nombre="Original", valor="orig", orden=1)

        client = self._client(self.admin_principal)
        response = self._post(
            client,
            ACTUALIZAR_URL.format(grupo_id=self.grupo.pk, opcion_id=opcion.pk),
            {"nombre": "Nuevo nombre"},
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()["item"]
        self.assertEqual(item["nombre"], "Nuevo nombre")
        # Untouched fields remain the same.
        self.assertEqual(item["valor"], "orig")
        self.assertEqual(item["orden"], 1)

        opcion.refresh_from_db()
        self.assertEqual(opcion.nombre, "Nuevo nombre")

    def test_actualizar_unknown_opcion_returns_404(self):
        client = self._client(self.admin_principal)
        response = self._post(
            client,
            ACTUALIZAR_URL.format(grupo_id=self.grupo.pk, opcion_id=9999),
            {"nombre": "Nada"},
        )
        self.assertEqual(response.status_code, 404)

    def test_actualizar_empty_valor_returns_400(self):
        opcion = self._create_opcion(codigo="UPD-2", valor="valor-original")

        client = self._client(self.admin_principal)
        response = self._post(
            client,
            ACTUALIZAR_URL.format(grupo_id=self.grupo.pk, opcion_id=opcion.pk),
            {"valor": ""},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("valor", response.json()["errors"])
        opcion.refresh_from_db()
        self.assertEqual(opcion.valor, "valor-original")

    # ------------------------------------------------------------------
    # POST /opciones/<opcion_id>/estado/  (toggle)
    # ------------------------------------------------------------------
    def test_estado_toggle_true_to_false(self):
        opcion = self._create_opcion(codigo="TOG-1", activo=True)

        client = self._client(self.admin_principal)
        response = self._post(
            client,
            ESTADO_URL.format(grupo_id=self.grupo.pk, opcion_id=opcion.pk),
            {"active": False},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"]["activo"], False)
        opcion.refresh_from_db()
        self.assertFalse(opcion.activo)

    def test_estado_toggle_false_to_true(self):
        opcion = self._create_opcion(codigo="TOG-2", activo=False)

        client = self._client(self.admin_principal)
        response = self._post(
            client,
            ESTADO_URL.format(grupo_id=self.grupo.pk, opcion_id=opcion.pk),
            {"active": True},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"]["activo"], True)
        opcion.refresh_from_db()
        self.assertTrue(opcion.activo)

    def test_estado_unknown_opcion_returns_404(self):
        client = self._client(self.admin_principal)
        response = self._post(
            client,
            ESTADO_URL.format(grupo_id=self.grupo.pk, opcion_id=9999),
            {"active": True},
        )
        self.assertEqual(response.status_code, 404)

    def test_estado_missing_active_returns_400(self):
        opcion = self._create_opcion(codigo="TOG-3")

        client = self._client(self.admin_principal)
        response = self._post(
            client,
            ESTADO_URL.format(grupo_id=self.grupo.pk, opcion_id=opcion.pk),
            {},
        )
        self.assertEqual(response.status_code, 400)


class OpcionCatalogoSerializationIntegrationTests(TestCase):
    """Integration invariant: an inactive `OpcionCatalogo` MUST NOT appear
    in the downstream `_serialize_medical_config` payload for fields that
    use its parent `GrupoOpciones`. The serializer filters by
    `activo=True` (see `prospect_conversion_views._serialize_medical_config`).
    """

    def setUp(self):
        self.procedure_type = ProcEsteticosTipo.objects.create(tipo="Opciones test")
        self.proc = ProcEstetico.objects.create(
            tipo_p_estetico=self.procedure_type, proceso="Proc opciones test"
        )
        self.servicio_tipo = TipoServicio.objects.create(tipo="Servicio opciones test")
        # Reuse DEP seed if available, otherwise create a local sector.
        self.sector = Sector.objects.filter(codigo="DEP").first() or Sector.objects.create(
            codigo="OPTEST",
            nombre="Sector opciones test",
            orden=99,
        )
        self.service_config = ServicioConfig.objects.create(
            tipo_servicio=self.servicio_tipo,
            proc_estetico=self.proc,
            sector=self.sector,
            precio_base=10,
            activo=True,
        )

        self.grupo = GrupoOpciones.objects.create(
            codigo="MED-OPC",
            nombre="Opciones medicas",
            activo=True,
        )
        self.seccion = FichaSeccion.objects.create(
            sector=self.sector,
            proc_estetico=self.proc,
            codigo="SEC-MEDOPC",
            nombre="Seccion medica",
        )
        self.campo = FichaCampo.objects.create(
            seccion=self.seccion,
            codigo="CMP-MEDOPC",
            etiqueta="Campo opciones",
            tipo_campo=FichaCampo.TipoCampo.SELECCION,
            grupo_opciones=self.grupo,
        )
        self.opcion_activa = OpcionCatalogo.objects.create(
            grupo=self.grupo,
            codigo="ACTIVA",
            nombre="Activa",
            valor="a",
            orden=1,
            activo=True,
        )
        self.opcion_inactiva = OpcionCatalogo.objects.create(
            grupo=self.grupo,
            codigo="INACTIVA",
            nombre="Inactiva",
            valor="i",
            orden=2,
            activo=False,
        )

    def tearDown(self):
        OpcionCatalogo.objects.filter(grupo=self.grupo).delete()
        self.campo.delete()
        self.seccion.delete()
        self.service_config.delete()
        self.grupo.delete()
        # Only delete the sector we created locally; keep the seed intact.
        if self.sector.codigo != "DEP":
            self.sector.delete()
        self.proc.delete()
        self.procedure_type.delete()
        self.servicio_tipo.delete()

    def test_inactive_option_is_excluded_from_medical_config(self):
        config = _serialize_medical_config(self.service_config)

        # Find our section by code so the test is independent of ordering.
        seccion = next(
            (s for s in config["sections"] if s["code"] == "SEC-MEDOPC"), None
        )
        self.assertIsNotNone(seccion, "Section must be present in medical config")

        campo = next((f for f in seccion["fields"] if f["code"] == "CMP-MEDOPC"), None)
        self.assertIsNotNone(campo, "Field must be present in medical config")

        option_ids = {opt["id"] for opt in campo["options"]}
        self.assertIn(self.opcion_activa.id, option_ids)
        self.assertNotIn(self.opcion_inactiva.id, option_ids)
