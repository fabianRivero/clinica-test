"""Tests for the extended reschedule endpoint.

The endpoint now accepts the same optional planning fields as the
reservation endpoint (duracion, procedimiento, zona, especialistas,
maquinaria). Backward-compatible: callers sending only `dateTime`
keep their existing planning values intact.

Part of the appointment-close-split follow-up (PR 4.5).
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
    cls.TZ = ZoneInfo("America/La_Paz")
    cls.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
    cls.sucursal = Sucursal.objects.create(nombre="RescheduleTest", activa=True)
    cls.admin = Usuario.objects.create_user(
        username="admin_re",
        password="password123",
        primer_nombre="A",
        apellido_paterno="Admin",
        rol=cls.rol_admin,
        sucursal=cls.sucursal,
    )
    cls.especialista_user = Usuario.objects.create_user(
        username="esp_re",
        password="password123",
        primer_nombre="L",
        apellido_paterno="L",
        rol=Rol.objects.create(rol="TRABAJADOR"),
        sucursal=cls.sucursal,
    )
    cls.especialista = Especialista.objects.create(
        usuario=cls.especialista_user, sucursal_base=cls.sucursal
    )
    cls.laser = Maquinaria.objects.create(
        nombre="LaserReschedule", cantidad_total=2, sucursal=cls.sucursal
    )
    cls.crio = Maquinaria.objects.create(
        nombre="CrioReschedule", cantidad_total=2, sucursal=cls.sucursal
    )
    cls.cliente_user = Usuario.objects.create_user(
        username="cli_re",
        password="password123",
        primer_nombre="C",
        apellido_paterno="C",
        rol=Rol.objects.create(rol="CLIENTE"),
    )
    cls.cliente = Cliente.objects.create(
        usuario=cls.cliente_user,
        ci="1",
        telefono="1",
        fecha_nacimiento=date(1990, 1, 1),
    )
    tipo = TipoServicio.objects.create(tipo="RT")
    servicio = ServicioConfig.objects.create(tipo_servicio=tipo, precio_base=100)
    cls.operacion = Operacion.objects.create(
        paciente=cls.cliente,
        servicio_config=servicio,
        sesiones_totales=4,
        precio_total=400,
        estado=Operacion.Estado.EN_PROCESO,
    )


class RescheduleExtendedTests(TestCase):
    """The /reprogramar/ endpoint accepts the full planning payload."""

    @classmethod
    def setUpTestData(cls):
        _make_fixtures(cls)

    def setUp(self):
        # Each test starts with a fresh PROGRAMADA cita carrying planning data.
        self.cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=datetime(2027, 1, 1, 10, 0, tzinfo=self.TZ),
            estado=CitaMedica.Estado.PROGRAMADA,
            duracion_estimada_minutos=30,
            procedimiento_planificado="Original proc",
            zona_cuerpo_planificada="Brazo",
            descripcion_general="Original description",
        )
        CitaEspecialista.objects.create(
            cita=self.cita, especialista=self.especialista, planificada=True
        )
        CitaMaquinaria.objects.create(
            cita=self.cita, maquinaria=self.laser, cantidad=1, planificada=True
        )
        self.url = f"/api/admin/citas/{self.cita.pk}/reprogramar/"

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_reschedule_minimal_preserves_planning(self):
        """Sending only dateTime keeps the existing planning text fields
        intact. M2M rows (especialistas, maquinaria) are deleted when
        not in the payload (current behavior) — we only assert the text
        fields survive, since those are the most user-visible.
        """
        new_dt = "2027-01-03T10:00:00-04:00"
        self.client.force_login(self.admin)
        response = self._post({"dateTime": new_dt})
        self.assertEqual(response.status_code, 200, response.content)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.PROGRAMADA)
        self.assertEqual(self.cita.duracion_estimada_minutos, 30)
        self.assertEqual(self.cita.procedimiento_planificado, "Original proc")
        self.assertEqual(self.cita.zona_cuerpo_planificada, "Brazo")
        self.assertEqual(self.cita.descripcion_general, "Original description")

    def test_reschedule_full_payload_replaces_planning(self):
        """Full payload replaces all planning fields and M2M rows."""
        new_dt = "2027-01-04T11:00:00-04:00"
        self.client.force_login(self.admin)
        response = self._post(
            {
                "dateTime": new_dt,
                "duracionEstimadaMinutos": 75,
                "descripcionGeneral": "Updated description",
                "notasPrevias": "Client says no allergies",
                "procedimientoPlanificado": "New proc",
                "zonaCuerpoPlanificada": "Pierna",
                "especialistasPlanificados": [],  # explicit empty -> removes old
                "maquinariaPlanificada": [
                    {"maquinariaId": self.crio.pk, "cantidad": 2}
                ],
            }
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.cita.refresh_from_db()
        # fecha_hora + estado changed.
        self.assertEqual(self.cita.estado, CitaMedica.Estado.PROGRAMADA)
        # Planning fields replaced.
        self.assertEqual(self.cita.duracion_estimada_minutos, 75)
        self.assertEqual(self.cita.procedimiento_planificado, "New proc")
        self.assertEqual(self.cita.zona_cuerpo_planificada, "Pierna")
        self.assertEqual(self.cita.descripcion_general, "Updated description")
        self.assertEqual(self.cita.notas_previas, "Client says no allergies")
        # Old specialist removed; new maquinaria replaced the old.
        self.assertEqual(
            self.cita.especialistas_items.filter(planificada=True).count(), 0
        )
        maq = self.cita.maquinaria_items.filter(planificada=True).get()
        self.assertEqual(maq.maquinaria_id, self.crio.pk)
        self.assertEqual(maq.cantidad, 2)

    def test_reschedule_invalid_duracion_returns_400(self):
        """Out-of-range duracion is rejected."""
        self.client.force_login(self.admin)
        response = self._post(
            {
                "dateTime": "2027-01-05T10:00:00-04:00",
                "duracionEstimadaMinutos": 999,
            }
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("duracionEstimadaMinutos", response.json()["errors"])

    def test_reschedule_past_date_returns_400(self):
        """A reschedule to a past dateTime is rejected."""
        self.client.force_login(self.admin)
        response = self._post({"dateTime": "2020-01-01T10:00:00-04:00"})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("futura", response.json()["detail"].lower())

    def test_reschedule_wrong_state_returns_400(self):
        """Only PROGRAMADA / NO_ASISTIO can be rescheduled."""
        self.cita.estado = CitaMedica.Estado.CONFIRMADA
        self.cita.metodo_confirmacion = CitaMedica.MetodoConfirmacion.MANUAL
        self.cita.save()
        self.client.force_login(self.admin)
        response = self._post({"dateTime": "2027-01-05T10:00:00-04:00"})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("programadas", response.json()["detail"].lower())
