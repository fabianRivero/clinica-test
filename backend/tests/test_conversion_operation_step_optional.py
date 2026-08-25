"""Tests for the prospect conversion "paso 2" (operation data) endpoint.

Focused coverage for the new optional behaviour: ``cuotasTotales`` is no
longer required, and ``fechasVencimientoCuotas`` are only required when
the admin explicitly opts in by sending at least one non-empty date.
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from catalogs.models import (
    GradoDeshidratacion,
    GrosorPiel,
    ProcEstetico,
    ProcEsteticosTipo,
    ServicioConfig,
    Sucursal,
    TipoPiel,
    TipoServicio,
)
from customers.models import (
    Cliente,
    Prospecto,
    ProspectoConversionBorrador,
)
from billing.models import CuotaPlanPago
from operations.models import Operacion


def post_json(client, url, payload):
    return client.post(
        url, data=json.dumps(payload), content_type="application/json"
    )


class ConversionOperationStepOptionalCuotasTests(TestCase):
    """Validates the optional ``cuotasTotales`` behaviour in paso 2."""

    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.rol_cliente = Rol.objects.create(rol="CLIENTE")
        cls.sucursal = Sucursal.objects.create(nombre="Centro", activa=True)
        cls.tipo_serv = TipoServicio.objects.create(tipo="Tratamiento", activo=True)
        cls.tipo_proc = ProcEsteticosTipo.objects.create(tipo="Corporal", activo=True)
        cls.proc = ProcEstetico.objects.create(
            tipo_p_estetico=cls.tipo_proc,
            proceso="Depilacion",
            activo=True,
        )
        cls.servicio = ServicioConfig.objects.create(
            tipo_servicio=cls.tipo_serv,
            proc_estetico=cls.proc,
            precio_base=Decimal("100.00"),
            activo=True,
        )
        cls.admin = Usuario.objects.create_user(
            username="admin.op",
            password="pw12345!",
            primer_nombre="Adm",
            apellido_paterno="Op",
            rol=cls.rol_admin,
            sucursal=None,
        )

    def setUp(self):
        self.client_http = Client()
        self.client_http.force_login(self.admin)
        self.prospecto = Prospecto.objects.create(
            primer_nombre="Pro",
            apellido_paterno="Spect",
            telefono="7000-0000",
            sucursal_registro=self.sucursal,
            registrado_por=self.admin,
        )
        self.url = f"/api/admin/prospectos/{self.prospecto.id}/conversion/paso-2/"

        # Pre-complete paso 1 so paso 2 is reachable.
        self.draft = ProspectoConversionBorrador.objects.create(
            prospecto=self.prospecto,
            iniciado_por=self.admin,
            paso_usuario_completado=True,
            datos_usuario={
                "primerNombre": "Pro",
                "apellidoPaterno": "Spect",
                "username": "pro.spect",
                "passwordHash": "x",
                "fechaNacimiento": "1990-01-01",
                "ci": "12345",
            },
        )

    def _base_payload(self, **overrides):
        payload = {
            "serviceConfigId": self.servicio.id,
            "precioTotal": "100.00",
            "cuotasTotales": 0,
            "sesionesTotales": 0,
            "fechaInicio": str(timezone.localdate()),
            "zonaGeneral": "Zona",
            "zonaEspecifica": "Detalle",
            "fechasVencimientoCuotas": [],
        }
        payload.update(overrides)
        return payload

    def test_cuotas_totales_null_acepta_paso_2(self):
        """Sin numero de cuotas y sin fechas, el paso 2 debe aceptar la carga."""
        response = post_json(self.client_http, self.url, self._base_payload())
        self.assertEqual(response.status_code, 200, response.content)

        self.draft.refresh_from_db()
        self.assertIsNone(self.draft.datos_operacion["cuotasTotales"])
        self.assertEqual(self.draft.datos_operacion["fechasVencimientoCuotas"], [])
        self.assertTrue(self.draft.paso_operacion_completado)

    def test_cuotas_totales_cero_acepta_paso_2(self):
        """El frontend envia 0 cuando el campo esta vacio; el backend lo
        trata como 'aun sin definir' y no exige fechas."""
        response = post_json(self.client_http, self.url, self._base_payload(cuotasTotales=0))
        self.assertEqual(response.status_code, 200, response.content)

        self.draft.refresh_from_db()
        self.assertIsNone(self.draft.datos_operacion["cuotasTotales"])

    def test_sesiones_totales_null_acepta_paso_2(self):
        """Sin numero de sesiones el paso 2 debe aceptar la carga."""
        response = post_json(
            self.client_http,
            self.url,
            self._base_payload(sesionesTotales=None),
        )
        self.assertEqual(response.status_code, 200, response.content)

        self.draft.refresh_from_db()
        self.assertIsNone(self.draft.datos_operacion["sesionesTotales"])

    def test_sesiones_totales_cero_acepta_paso_2(self):
        """El frontend envia 0 cuando el campo esta vacio; el backend lo
        trata como 'aun sin definir'."""
        response = post_json(
            self.client_http,
            self.url,
            self._base_payload(sesionesTotales=0),
        )
        self.assertEqual(response.status_code, 200, response.content)

        self.draft.refresh_from_db()
        self.assertIsNone(self.draft.datos_operacion["sesionesTotales"])

    def test_sesiones_totales_invalidas_rechazadas(self):
        """Si el admin manda un valor invalido, sigue siendo rechazado."""
        response = post_json(
            self.client_http,
            self.url,
            self._base_payload(sesionesTotales=-2),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("sesionesTotales", response.json().get("errors", {}))

    def test_cuotas_totales_definidas_acepta_sin_fechas(self):
        """Si el admin define el numero de cuotas puede dejar las fechas
        vacias para completarlas despues."""
        payload = self._base_payload(
            cuotasTotales=3,
            fechasVencimientoCuotas=[],
        )
        response = post_json(self.client_http, self.url, payload)
        self.assertEqual(response.status_code, 200, response.content)

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.datos_operacion["cuotasTotales"], 3)
        self.assertEqual(self.draft.datos_operacion["fechasVencimientoCuotas"], [])

    def test_cuotas_totales_definidas_con_algunas_fechas(self):
        """Si el admin define el numero de cuotas y manda algunas fechas,
        el backend las acepta aunque no complete todas."""
        today = timezone.localdate()
        payload = self._base_payload(
            cuotasTotales=3,
            fechasVencimientoCuotas=[str(today), "", ""],
        )
        response = post_json(self.client_http, self.url, payload)
        self.assertEqual(response.status_code, 200, response.content)

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.datos_operacion["cuotasTotales"], 3)
        self.assertEqual(
            self.draft.datos_operacion["fechasVencimientoCuotas"],
            [today.isoformat()],
        )

    def test_cuotas_totales_sin_fechas_obligatorias(self):
        """No debe existir el error historico 'una fecha por cada cuota'."""
        payload = self._base_payload(
            cuotasTotales=5,
            fechasVencimientoCuotas=[],
        )
        response = post_json(self.client_http, self.url, payload)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertNotIn("fechasVencimientoCuotas", body.get("errors", {}))

    def test_fechas_rechazadas_sin_cuotas(self):
        """No se aceptan fechas de vencimiento si no hay numero de cuotas."""
        today = timezone.localdate()
        payload = self._base_payload(
            cuotasTotales=0,
            fechasVencimientoCuotas=[str(today)],
        )
        response = post_json(self.client_http, self.url, payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("fechasVencimientoCuotas", response.json().get("errors", {}))

    def test_fechas_duplicadas_siguen_rechazadas(self):
        """Aunque las fechas sean opcionales, si se envian deben ser
        validas (no repetidas, no en el pasado)."""
        today = timezone.localdate()
        payload = self._base_payload(
            cuotasTotales=3,
            fechasVencimientoCuotas=[str(today), str(today), ""],
        )
        response = post_json(self.client_http, self.url, payload)
        self.assertEqual(response.status_code, 400)
        errors = response.json().get("errors", {})
        self.assertIn("fechasVencimientoCuotas.1", errors)


class ConversionFinalizeOptionalCuotasTests(TestCase):
    """Validates that finalize works when ``cuotasTotales`` is ``None``."""

    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.rol_cliente = Rol.objects.create(rol="CLIENTE")
        cls.sucursal = Sucursal.objects.create(nombre="Centro", activa=True)
        cls.tipo_serv = TipoServicio.objects.create(tipo="Tratamiento", activo=True)
        cls.tipo_proc = ProcEsteticosTipo.objects.create(tipo="Corporal", activo=True)
        cls.proc = ProcEstetico.objects.create(
            tipo_p_estetico=cls.tipo_proc,
            proceso="Depilacion",
            activo=True,
        )
        cls.servicio = ServicioConfig.objects.create(
            tipo_servicio=cls.tipo_serv,
            proc_estetico=cls.proc,
            precio_base=Decimal("100.00"),
            activo=True,
        )
        # Catalogos requeridos por la ficha medica del finalize.
        cls.tipo_piel = TipoPiel.objects.create(nombre="Normal", activo=True)
        cls.grado_desh = GradoDeshidratacion.objects.create(nombre="Bajo", activo=True)
        cls.grosor = GrosorPiel.objects.create(nombre="Medio", activo=True)
        cls.admin = Usuario.objects.create_user(
            username="admin.finalize",
            password="pw12345!",
            primer_nombre="Adm",
            apellido_paterno="Fin",
            rol=cls.rol_admin,
            sucursal=None,
        )
        cls.prospecto = Prospecto.objects.create(
            primer_nombre="Pro",
            apellido_paterno="Spect",
            telefono="7000-0000",
            sucursal_registro=cls.sucursal,
            registrado_por=cls.admin,
        )

    def setUp(self):
        self.client_http = Client()
        self.client_http.force_login(self.admin)
        self.draft = ProspectoConversionBorrador.objects.create(
            prospecto=self.prospecto,
            iniciado_por=self.admin,
            paso_usuario_completado=True,
            paso_operacion_completado=True,
            paso_ficha_completado=True,
            paso_biometria_completado=True,
            datos_usuario={
                "primerNombre": "Pro",
                "apellidoPaterno": "Spect",
                "username": "pro.spect",
                "passwordHash": "pbkdf2_sha256$test$test",
                "fechaNacimiento": "1990-01-01",
                "ci": "12345",
                "email": "pro@example.com",
            },
            datos_operacion={
                "serviceConfigId": self.servicio.id,
                "zonaGeneral": "Zona",
                "zonaEspecifica": "Detalle",
                "precioTotal": "100.00",
                "cuotasTotales": None,
                "sesionesTotales": None,
                "fechaInicio": str(timezone.localdate()),
                "estado": Operacion.Estado.EN_PROCESO,
                "fechasVencimientoCuotas": [],
            },
            datos_ficha={
                "fechaFicha": str(timezone.localdate()),
                "motivoConsulta": "consulta",
                "observaciones": "",
                "consentimientoAceptado": True,
                "firmaPacienteCi": "12345",
                "analisisEstetico": {
                    "tipoPielId": str(self.tipo_piel.id),
                    "gradoDeshidratacionId": str(self.grado_desh.id),
                    "grosorPielId": str(self.grosor.id),
                    "patologiaIds": [],
                },
                "antecedentes": [],
                "implantes": [],
                "cirugias": [],
                "fieldResponses": {},
            },
            datos_biometria={"template": "", "quality": 0, "provider": "MOCK_LEGACY"},
            paso_actual=ProspectoConversionBorrador.Paso.BIOMETRIA,
        )

    def test_finalize_sin_cuotas_no_crea_cuotas_plan_pago(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        url = f"/api/admin/prospectos/{self.prospecto.id}/conversion/finalizar/"
        pdf = SimpleUploadedFile("ficha.pdf", b"%PDF-test", content_type="application/pdf")
        response = self.client_http.post(
            url,
            data={"documento_escaneado_pdf": pdf},
        )
        self.assertEqual(response.status_code, 201, response.content)

        operacion = Operacion.objects.get(paciente__ci="12345")
        # `cuotas_totales` y `sesiones_totales` caen al default del modelo
        # (1) cuando llegan como `None` desde el paso 2; el admin los
        # ajustara despues en otro flujo.
        self.assertEqual(operacion.cuotas_totales, 1)
        self.assertEqual(operacion.sesiones_totales, 1)
        # Sin fechas enviadas no creamos ninguna CuotaPlanPago.
        self.assertEqual(CuotaPlanPago.objects.filter(operacion=operacion).count(), 0)
