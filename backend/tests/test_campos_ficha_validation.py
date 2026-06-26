"""API integration tests for `grupo_opciones` validation in the
`campos-ficha` admin catalog.

Covers the new rule introduced in editor-visual-ficha-medica/PR1:
creating or updating a FichaCampo with `tipo_campo` in
{SELECCION, MULTISELECCION} without an `optionGroupId` must return
HTTP 400. Other tipos (TEXTO, NUMERO, FECHA, BOOLEANO) keep working
without `grupo_opciones`.
"""

import json

from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import GrupoOpciones, ProcEstetico, ProcEsteticosTipo, Sector
from clinical.models import FichaCampo, FichaSeccion


class CamposFichaGrupoOpcionesValidationTests(TestCase):
    """End-to-end coverage of the grupo_opciones requirement for
    SELECCION/MULTISELECCION fields via the admin catalog API.
    """

    @classmethod
    def setUpTestData(cls):
        admin_role = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.admin = Usuario.objects.create_user(
            username="admin.campos.ficha.validation",
            password="password123",
            primer_nombre="Admin",
            apellido_paterno="Campos Ficha",
            rol=admin_role,
            sucursal=None,
        )

        cls.procedure_type = ProcEsteticosTipo.objects.create(
            tipo="Campos ficha validation",
        )
        cls.proc = ProcEstetico.objects.create(
            tipo_p_estetico=cls.procedure_type,
            proceso="Proc validacion campos",
        )
        cls.dep_sector = Sector.objects.get_or_create(
            codigo="DEP",
            defaults={"nombre": "Depilacion", "activo": True, "orden": 1},
        )[0]

        cls.seccion = FichaSeccion.objects.create(
            proc_estetico=cls.proc,
            sector=cls.dep_sector,
            codigo="VALID-SECC",
            nombre="Seccion validacion",
        )

        cls.grupo = GrupoOpciones.objects.create(
            codigo="VALID-GRUPO",
            nombre="Grupo validacion",
            activo=True,
        )

    def setUp(self):
        # Each test gets a unique codigo so the (seccion, codigo)
        # uniqueness constraint does not interfere across tests.
        suffix = self._testMethodName.replace("_", "-")[:14].upper()
        self._codigo = f"CMP-{suffix}"

    def _post(self, path, payload):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=f"campos-ficha-{self._testMethodName}",
        )

    # ------------------------------------------------------------------
    # SELECCION requires grupo_opciones
    # ------------------------------------------------------------------
    def test_create_seleccion_without_grupo_opciones_returns_400(self):
        self.client.force_login(self.admin)
        payload = {
            "sectionId": self.seccion.pk,
            "code": self._codigo,
            "label": "Seleccion sin grupo",
            "fieldType": FichaCampo.TipoCampo.SELECCION,
        }
        response = self._post("/api/admin/catalogos/campos-ficha/crear/", payload)

        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertEqual(body["detail"], "Hay errores en el formulario.")
        self.assertIn("optionGroupId", body["errors"])
        self.assertIn("grupo de opciones", body["errors"]["optionGroupId"][0])

    def test_create_seleccion_with_grupo_opciones_returns_201(self):
        self.client.force_login(self.admin)
        payload = {
            "sectionId": self.seccion.pk,
            "code": self._codigo,
            "label": "Seleccion con grupo",
            "fieldType": FichaCampo.TipoCampo.SELECCION,
            "optionGroupId": self.grupo.pk,
        }
        response = self._post("/api/admin/catalogos/campos-ficha/crear/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        created = FichaCampo.objects.get(codigo=self._codigo)
        self.assertEqual(created.tipo_campo, FichaCampo.TipoCampo.SELECCION)
        self.assertEqual(created.grupo_opciones_id, self.grupo.pk)

    # ------------------------------------------------------------------
    # MULTISELECCION requires grupo_opciones
    # ------------------------------------------------------------------
    def test_create_multiseleccion_without_grupo_opciones_returns_400(self):
        self.client.force_login(self.admin)
        payload = {
            "sectionId": self.seccion.pk,
            "code": self._codigo,
            "label": "Multiseleccion sin grupo",
            "fieldType": FichaCampo.TipoCampo.MULTISELECCION,
        }
        response = self._post("/api/admin/catalogos/campos-ficha/crear/", payload)

        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertIn("optionGroupId", body["errors"])

    def test_create_multiseleccion_with_grupo_opciones_returns_201(self):
        self.client.force_login(self.admin)
        payload = {
            "sectionId": self.seccion.pk,
            "code": self._codigo,
            "label": "Multiseleccion con grupo",
            "fieldType": FichaCampo.TipoCampo.MULTISELECCION,
            "optionGroupId": self.grupo.pk,
            "isMultiple": True,
        }
        response = self._post("/api/admin/catalogos/campos-ficha/crear/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        created = FichaCampo.objects.get(codigo=self._codigo)
        self.assertEqual(created.tipo_campo, FichaCampo.TipoCampo.MULTISELECCION)
        self.assertEqual(created.grupo_opciones_id, self.grupo.pk)
        self.assertTrue(created.es_multiple)

    # ------------------------------------------------------------------
    # Other tipos: TEXTO, NUMERO, FECHA, BOOLEANO must keep working
    # without grupo_opciones (existing behavior preserved).
    # ------------------------------------------------------------------
    def test_create_texto_without_grupo_opciones_returns_201(self):
        self.client.force_login(self.admin)
        payload = {
            "sectionId": self.seccion.pk,
            "code": self._codigo,
            "label": "Campo texto",
            "fieldType": FichaCampo.TipoCampo.TEXTO,
        }
        response = self._post("/api/admin/catalogos/campos-ficha/crear/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        created = FichaCampo.objects.get(codigo=self._codigo)
        self.assertEqual(created.tipo_campo, FichaCampo.TipoCampo.TEXTO)
        self.assertIsNone(created.grupo_opciones_id)

    def test_create_numero_without_grupo_opciones_returns_201(self):
        self.client.force_login(self.admin)
        payload = {
            "sectionId": self.seccion.pk,
            "code": self._codigo,
            "label": "Campo numero",
            "fieldType": FichaCampo.TipoCampo.NUMERO,
        }
        response = self._post("/api/admin/catalogos/campos-ficha/crear/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        created = FichaCampo.objects.get(codigo=self._codigo)
        self.assertEqual(created.tipo_campo, FichaCampo.TipoCampo.NUMERO)
        self.assertIsNone(created.grupo_opciones_id)

    def test_create_fecha_without_grupo_opciones_returns_201(self):
        self.client.force_login(self.admin)
        payload = {
            "sectionId": self.seccion.pk,
            "code": self._codigo,
            "label": "Campo fecha",
            "fieldType": FichaCampo.TipoCampo.FECHA,
        }
        response = self._post("/api/admin/catalogos/campos-ficha/crear/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        created = FichaCampo.objects.get(codigo=self._codigo)
        self.assertEqual(created.tipo_campo, FichaCampo.TipoCampo.FECHA)
        self.assertIsNone(created.grupo_opciones_id)

    def test_create_booleano_without_grupo_opciones_returns_201(self):
        self.client.force_login(self.admin)
        payload = {
            "sectionId": self.seccion.pk,
            "code": self._codigo,
            "label": "Campo booleano",
            "fieldType": FichaCampo.TipoCampo.BOOLEANO,
        }
        response = self._post("/api/admin/catalogos/campos-ficha/crear/", payload)

        self.assertEqual(response.status_code, 201, response.content)
        created = FichaCampo.objects.get(codigo=self._codigo)
        self.assertEqual(created.tipo_campo, FichaCampo.TipoCampo.BOOLEANO)
        self.assertIsNone(created.grupo_opciones_id)


class CamposFichaGrupoOpcionesUpdateTests(TestCase):
    """Cover the grupo_opciones requirement on the update path too."""

    @classmethod
    def setUpTestData(cls):
        admin_role = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.admin = Usuario.objects.create_user(
            username="admin.campos.ficha.update",
            password="password123",
            primer_nombre="Admin",
            apellido_paterno="Update",
            rol=admin_role,
            sucursal=None,
        )

        cls.procedure_type = ProcEsteticosTipo.objects.create(
            tipo="Campos ficha update",
        )
        cls.proc = ProcEstetico.objects.create(
            tipo_p_estetico=cls.procedure_type,
            proceso="Proc update",
        )
        cls.seccion = FichaSeccion.objects.create(
            proc_estetico=cls.proc,
            codigo="UPD-SECC",
            nombre="Seccion update",
        )
        cls.grupo = GrupoOpciones.objects.create(
            codigo="UPD-GRUPO",
            nombre="Grupo update",
        )

    def test_switching_field_type_to_seleccion_without_grupo_returns_400(self):
        # Start as TEXTO so the field can be created without grupo.
        campo = FichaCampo.objects.create(
            seccion=self.seccion,
            codigo="TEXTO-A-SEL",
            etiqueta="Original texto",
            tipo_campo=FichaCampo.TipoCampo.TEXTO,
        )

        self.client.force_login(self.admin)
        response = self.client.post(
            f"/api/admin/catalogos/campos-ficha/{campo.pk}/actualizar/",
            data=json.dumps(
                {
                    "sectionId": self.seccion.pk,
                    "code": campo.codigo,
                    "label": campo.etiqueta,
                    "fieldType": FichaCampo.TipoCampo.SELECCION,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertIn("optionGroupId", body["errors"])

    def test_switching_field_type_to_seleccion_with_grupo_succeeds(self):
        campo = FichaCampo.objects.create(
            seccion=self.seccion,
            codigo="TEXTO-A-SEL-OK",
            etiqueta="Original texto",
            tipo_campo=FichaCampo.TipoCampo.TEXTO,
        )

        self.client.force_login(self.admin)
        response = self.client.post(
            f"/api/admin/catalogos/campos-ficha/{campo.pk}/actualizar/",
            data=json.dumps(
                {
                    "sectionId": self.seccion.pk,
                    "code": campo.codigo,
                    "label": campo.etiqueta,
                    "fieldType": FichaCampo.TipoCampo.SELECCION,
                    "optionGroupId": self.grupo.pk,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        campo.refresh_from_db()
        self.assertEqual(campo.tipo_campo, FichaCampo.TipoCampo.SELECCION)
        self.assertEqual(campo.grupo_opciones_id, self.grupo.pk)