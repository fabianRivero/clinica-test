"""Tests for the split appointment close flow.

The close flow is split into two admin steps:

1. PROGRAMADA -> REALIZADA_PENDIENTE_VERIFICACION via
   POST /api/admin/citas/<id>/pendiente-biometria/ (no body).
2. CONFIRMADA + real-time fields via POST /api/admin/citas/<id>/cerrar/.

Part of the appointment-close-split change. Notes patch tests live in
backend/tests/test_appointment_notes.py.
"""

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import (
    Maquinaria,
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from customers.models import Cliente
from operations.models import (
    CitaEspecialista,
    CitaMaquinaria,
    CitaMedica,
    Operacion,
)
from staff.models import Especialista


def _make_fixtures(cls):
    """Create a CONFIRMADA cita with operacion, sucursal, admin,
    specialist, and one maquinaría. Called from setUp()."""
    cls.TZ = ZoneInfo("America/La_Paz")

    cls.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
    cls.rol_especialista = Rol.objects.create(rol="TRABAJADOR")

    cls.sucursal = Sucursal.objects.create(nombre="Centro", activa=True)
    cls.admin = Usuario.objects.create_user(
        username="admin",
        password="password123",
        primer_nombre="A",
        apellido_paterno="Admin",
        rol=cls.rol_admin,
        sucursal=cls.sucursal,
    )
    cls.especialista_user = Usuario.objects.create_user(
        username="esp",
        password="password123",
        primer_nombre="L",
        apellido_paterno="L",
        rol=cls.rol_especialista,
        sucursal=cls.sucursal,
    )
    cls.especialista = Especialista.objects.create(
        usuario=cls.especialista_user, sucursal_base=cls.sucursal
    )
    cls.laser = Maquinaria.objects.create(
        nombre="Laser", cantidad_total=2, sucursal=cls.sucursal
    )
    cls.cliente_user = Usuario.objects.create_user(
        username="cli",
        password="password123",
        primer_nombre="M",
        apellido_paterno="G",
        rol=Rol.objects.create(rol="CLIENTE"),
    )
    cls.cliente = Cliente.objects.create(
        usuario=cls.cliente_user,
        ci="1",
        telefono="1",
        fecha_nacimiento=date(1990, 1, 1),
    )
    tipo = TipoServicio.objects.create(tipo="T")
    servicio = ServicioConfig.objects.create(
        tipo_servicio=tipo, precio_base=100
    )
    cls.operacion = Operacion.objects.create(
        paciente=cls.cliente,
        servicio_config=servicio,
        sesiones_totales=4,
        precio_total=400,
        estado=Operacion.Estado.EN_PROCESO,
    )


class PendienteBiometriaSplitTests(TestCase):
    """Step 1: PROGRAMADA -> REALIZADA_PENDIENTE_VERIFICACION.

    The endpoint now accepts no body. Real-time field capture moved
    to the new cerrar/ endpoint.
    """

    @classmethod
    def setUpTestData(cls):
        _make_fixtures(cls)

    def setUp(self):
        # Each test starts with a fresh PROGRAMADA cita.
        self.cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=datetime(2026, 9, 1, 10, 0, tzinfo=self.TZ),
            estado=CitaMedica.Estado.PROGRAMADA,
        )
        self.url = f"/api/admin/citas/{self.cita.pk}/pendiente-biometria/"

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_empty_body_transitions_to_pendiente(self):
        """Empty body transitions PROGRAMADA -> REALIZADA_PENDIENTE_VERIFICACION."""
        self.client.force_login(self.admin)
        response = self._post({})
        self.assertEqual(response.status_code, 200, response.content)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION)
        self.assertIsNone(self.cita.hora_real_inicio)
        self.assertIsNone(self.cita.hora_real_fin)
        self.assertEqual(self.cita.procedimiento_realizado, "")
        self.assertEqual(self.cita.zona_cuerpo_realizada, "")
        self.assertEqual(self.cita.especialistas_items.filter(planificada=False).count(), 0)
        self.assertEqual(self.cita.maquinaria_items.filter(planificada=False).count(), 0)

    def test_body_with_real_time_data_is_ignored(self):
        """Real-time fields in the body are silently ignored."""
        self.client.force_login(self.admin)
        response = self._post(
            {
                "horaRealInicio": "2026-09-01T10:05:00-04:00",
                "horaRealFin": "2026-09-01T11:00:00-04:00",
                "procedimientoRealizado": "No debe persistirse",
                "zonaCuerpoRealizada": "Tampoco",
                "especialistasAtendieron": [self.especialista.pk],
                "maquinariaUtilizada": [
                    {"maquinariaId": self.laser.pk, "cantidad": 1}
                ],
            }
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION)
        # Real-time fields stay empty; M2M rows are NOT created.
        self.assertIsNone(self.cita.hora_real_inicio)
        self.assertEqual(self.cita.procedimiento_realizado, "")
        self.assertEqual(self.cita.especialistas_items.count(), 0)
        self.assertEqual(self.cita.maquinaria_items.count(), 0)

    def test_wrong_state_returns_400(self):
        """A non-PROGRAMADA cita returns 400 on this endpoint."""
        self.cita.estado = CitaMedica.Estado.CONFIRMADA
        self.cita.metodo_confirmacion = CitaMedica.MetodoConfirmacion.MANUAL
        self.cita.save()
        self.client.force_login(self.admin)
        response = self._post({})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("programad", response.json()["detail"].lower())

    def test_missing_cita_returns_404(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            "/api/admin/citas/999999/pendiente-biometria/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404, response.content)

    def test_preserves_existing_real_time_data_when_called_again(self):
        """Calling pendiente-biometria does NOT erase previously-persisted
        real-time data set via cerrar/ on a CONFIRMADA cita. We confirm
        by transitioning to CONFIRMADA, backfilling via cerrar, then
        stepping back to PROGRAMADA via update_status and re-calling
        pendiente-biometria — the real-time fields must survive.
        """
        # Backfill real-time data via cerrar/ on CONFIRMADA.
        self.cita.estado = CitaMedica.Estado.CONFIRMADA
        self.cita.metodo_confirmacion = CitaMedica.MetodoConfirmacion.MANUAL
        self.cita.save()
        cerrar_url = f"/api/admin/citas/{self.cita.pk}/cerrar/"
        self.client.force_login(self.admin)
        response = self.client.post(
            cerrar_url,
            data=json.dumps({"procedimientoRealizado": "Backfilled"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        # Move back to PROGRAMADA via the generic update endpoint.
        status_url = f"/api/admin/citas/{self.cita.pk}/actualizar/"
        response = self.client.post(
            status_url,
            data=json.dumps({"status": "PROGRAMADA"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        # Re-call pendiente-biometria; the previously-persisted
        # procedimiento_realizado must NOT be erased.
        response = self.client.post(
            self.url,
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION)
        self.assertEqual(self.cita.procedimiento_realizado, "Backfilled")


class CerrarCitaTests(TestCase):
    """Step 2: CONFIRMADA + real-time fields via /cerrar/."""

    @classmethod
    def setUpTestData(cls):
        _make_fixtures(cls)

    def setUp(self):
        # Each test starts with a CONFIRMADA cita ready to be closed.
        self.cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=datetime(2026, 9, 1, 10, 0, tzinfo=self.TZ),
            estado=CitaMedica.Estado.CONFIRMADA,
            metodo_confirmacion=CitaMedica.MetodoConfirmacion.MANUAL,
        )
        self.url = f"/api/admin/citas/{self.cita.pk}/cerrar/"

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_close_confirmada_persists_all_fields(self):
        """Full payload on CONFIRMADA persists real-time fields + M2M rows."""
        self.client.force_login(self.admin)
        response = self._post(
            {
                "horaRealInicio": "2026-09-01T10:05:00-04:00",
                "horaRealFin": "2026-09-01T11:00:00-04:00",
                "procedimientoRealizado": "Limpieza facial",
                "zonaCuerpoRealizada": "Rostro",
                "especialistasAtendieron": [self.especialista.pk],
                "maquinariaUtilizada": [
                    {"maquinariaId": self.laser.pk, "cantidad": 1}
                ],
            }
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.cita.refresh_from_db()
        # State unchanged.
        self.assertEqual(self.cita.estado, CitaMedica.Estado.CONFIRMADA)
        # Real-time fields persisted.
        self.assertIsNotNone(self.cita.hora_real_inicio)
        self.assertIsNotNone(self.cita.hora_real_fin)
        self.assertEqual(self.cita.procedimiento_realizado, "Limpieza facial")
        self.assertEqual(self.cita.zona_cuerpo_realizada, "Rostro")
        # M2M rows persisted with planificada=False.
        items_esp = list(self.cita.especialistas_items.filter(planificada=False).values_list(
            "especialista_id", flat=True
        ))
        self.assertEqual(items_esp, [self.especialista.pk])
        items_maq = list(self.cita.maquinaria_items.filter(planificada=False).values(
            "maquinaria_id", "cantidad"
        ))
        self.assertEqual(len(items_maq), 1)
        self.assertEqual(items_maq[0]["maquinaria_id"], self.laser.pk)
        self.assertEqual(items_maq[0]["cantidad"], 1)

    def test_close_empty_body_accepted(self):
        """Empty body on CONFIRMADA does not erase previously-persisted data."""
        # First close: persist some data.
        self.client.force_login(self.admin)
        self._post({"procedimientoRealizado": "Initial close"}).json()
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.procedimiento_realizado, "Initial close")

        # Second close with empty body must keep the field intact.
        response = self._post({})
        self.assertEqual(response.status_code, 200, response.content)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.CONFIRMADA)
        self.assertEqual(self.cita.procedimiento_realizado, "Initial close")

    def test_close_wrong_state_returns_400(self):
        """PROGRAMADA and CANCELADA both reject with 400."""
        self.cita.estado = CitaMedica.Estado.PROGRAMADA
        self.cita.metodo_confirmacion = ""
        self.cita.save()
        self.client.force_login(self.admin)
        response = self._post({})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("confirmad", response.json()["detail"].lower())

        self.cita.estado = CitaMedica.Estado.CANCELADA
        self.cita.save()
        response = self._post({})
        self.assertEqual(response.status_code, 400, response.content)

    def test_close_missing_cita_returns_404(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            "/api/admin/citas/999999/cerrar/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404, response.content)

    def test_close_is_idempotent(self):
        """Re-close replaces planificada=False M2M rows instead of duplicating."""
        self.client.force_login(self.admin)

        # First close: 1 specialist + 1 machinery.
        self._post(
            {
                "especialistasAtendieron": [self.especialista.pk],
                "maquinariaUtilizada": [{"maquinariaId": self.laser.pk, "cantidad": 1}],
            }
        )
        self.assertEqual(self.cita.especialistas_items.filter(planificada=False).count(), 1)
        self.assertEqual(self.cita.maquinaria_items.filter(planificada=False).count(), 1)

        # Second close with different staff + machinery: the old rows
        # for specialist 1 / laser must be deleted and replaced.
        self._post(
            {
                "especialistasAtendieron": [],  # explicit empty: removes the row
                "maquinariaUtilizada": [],  # explicit empty: removes the row
            }
        )
        self.assertEqual(self.cita.especialistas_items.filter(planificada=False).count(), 0)
        self.assertEqual(self.cita.maquinaria_items.filter(planificada=False).count(), 0)

    def test_invalid_hour_range_returns_400(self):
        self.client.force_login(self.admin)
        response = self._post(
            {
                "horaRealInicio": "2026-09-01T11:00:00-04:00",
                "horaRealFin": "2026-09-01T10:00:00-04:00",
            }
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("horaRealFin", response.json()["errors"])

    def test_inicio_before_scheduled_minus_one_hour_returns_400(self):
        self.client.force_login(self.admin)
        response = self._post(
            {
                "horaRealInicio": "2026-09-01T05:00:00-04:00",  # 5h before scheduled 10:00
                "horaRealFin": "2026-09-01T11:00:00-04:00",
            }
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("horaRealInicio", response.json()["errors"])
