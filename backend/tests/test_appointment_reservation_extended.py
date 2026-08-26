"""Tests for the extended reservation endpoint.

Covers:
- Backward-compatible: existing payload {branchId, dateTime} still works.
- Optional fields persist on CitaMedica.
- CitaMaquinaria and CitaEspecialista rows are bulk-created with planificada=True.
- duracionEstimadaMinutos > 480 rejected with 400.
- Empty especialistasPlanificados / maquinariaPlanificada is accepted.

Part of the appointment-reservation-redesign change.
"""

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from catalogs.models import Maquinaria, ServicioConfig, Sucursal, TipoServicio
from customers.models import Cliente
from operations.models import (
    CitaEspecialista,
    CitaMaquinaria,
    CitaMedica,
    Operacion,
)
from staff.models import Especialista


class ReservationExtendedTests(TestCase):
    TZ = ZoneInfo("America/La_Paz")

    def setUp(self):
        # Each test gets its own Operacion to bypass the "only one active
        # reservation per operation" business rule. We share admin/client/
        # sucursal/maquinaria across tests because they don't conflict.
        self.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.rol_especialista = Rol.objects.create(rol="TRABAJADOR")

        self.sucursal = Sucursal.objects.create(nombre="Centro", activa=True)
        self.admin = Usuario.objects.create_user(
            username="admin",
            password="password123",
            primer_nombre="A",
            apellido_paterno="Admin",
            rol=self.rol_admin,
            sucursal=self.sucursal,
        )

        self.especialista_user = Usuario.objects.create_user(
            username="esp1",
            password="password123",
            primer_nombre="Lucia",
            apellido_paterno="Lopez",
            rol=self.rol_especialista,
            sucursal=self.sucursal,
        )
        self.especialista = Especialista.objects.create(
            usuario=self.especialista_user, sucursal_base=self.sucursal
        )

        self.laser = Maquinaria.objects.create(
            nombre="Laser", cantidad_total=2, sucursal=self.sucursal
        )
        self.camilla = Maquinaria.objects.create(
            nombre="Camilla", cantidad_total=3, sucursal=self.sucursal
        )

        self.cliente_user = Usuario.objects.create_user(
            username="cliente",
            password="password123",
            primer_nombre="Maria",
            apellido_paterno="Gomez",
            rol=Rol.objects.create(rol="CLIENTE"),
        )
        self.cliente = Cliente.objects.create(
            usuario=self.cliente_user,
            ci="1234567",
            telefono="7000000",
            fecha_nacimiento=date(1990, 1, 1),
        )

        tipo = TipoServicio.objects.create(tipo="Depilacion")
        servicio = ServicioConfig.objects.create(
            tipo_servicio=tipo, precio_base=100
        )
        self.operacion = Operacion.objects.create(
            paciente=self.cliente,
            servicio_config=servicio,
            sesiones_totales=4,
            precio_total=400,
            estado=Operacion.Estado.EN_PROCESO,
        )

        self.url = (
            f"/api/admin/clientes/{self.cliente.pk}/operaciones/"
            f"{self.operacion.pk}/reservar/"
        )

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _iso(self, hour, minute=0):
        dt = datetime(2026, 9, 1, hour, minute, tzinfo=self.TZ)
        return dt.isoformat()

    def test_minimal_payload_still_works(self):
        """Backward-compat: branchId + dateTime alone creates a PROGRAMADA cita."""
        self.client.force_login(self.admin)
        response = self._post(
            {
                "branchId": self.sucursal.pk,
                "dateTime": self._iso(10),
            }
        )
        self.assertEqual(response.status_code, 201, response.content)
        cita = CitaMedica.objects.get()
        self.assertEqual(cita.estado, CitaMedica.Estado.PROGRAMADA)
        self.assertIsNone(cita.duracion_estimada_minutos)
        self.assertEqual(cita.descripcion_general, "")
        self.assertEqual(cita.maquinaria_items.count(), 0)
        self.assertEqual(cita.especialistas_items.count(), 0)

    def test_full_payload_persists_all_fields(self):
        self.client.force_login(self.admin)
        response = self._post(
            {
                "branchId": self.sucursal.pk,
                "dateTime": self._iso(10),
                "duracionEstimadaMinutos": 60,
                "descripcionGeneral": "Sesion de prueba",
                "notasPrevias": "Sin alergias",
                "procedimientoPlanificado": "Depilacion laser",
                "zonaCuerpoPlanificada": "Axilas",
                "especialistasPlanificados": [self.especialista.pk],
                "maquinariaPlanificada": [
                    {"maquinariaId": self.laser.pk, "cantidad": 1},
                    {"maquinariaId": self.camilla.pk, "cantidad": 2},
                ],
            }
        )
        self.assertEqual(response.status_code, 201, response.content)
        cita = CitaMedica.objects.get()

        self.assertEqual(cita.duracion_estimada_minutos, 60)
        self.assertEqual(cita.descripcion_general, "Sesion de prueba")
        self.assertEqual(cita.notas_previas, "Sin alergias")
        self.assertEqual(cita.procedimiento_planificado, "Depilacion laser")
        self.assertEqual(cita.zona_cuerpo_planificada, "Axilas")

        # M2M items
        items_maq = list(cita.maquinaria_items.order_by("maquinaria_id").values(
            "maquinaria_id", "cantidad", "planificada"
        ))
        self.assertEqual(len(items_maq), 2)
        self.assertTrue(all(item["planificada"] for item in items_maq))
        cantidad_por_maq = {item["maquinaria_id"]: item["cantidad"] for item in items_maq}
        self.assertEqual(cantidad_por_maq[self.laser.pk], 1)
        self.assertEqual(cantidad_por_maq[self.camilla.pk], 2)

        items_esp = list(cita.especialistas_items.values(
            "especialista_id", "planificada"
        ))
        self.assertEqual(len(items_esp), 1)
        self.assertTrue(items_esp[0]["planificada"])
        self.assertEqual(items_esp[0]["especialista_id"], self.especialista.pk)

    def test_duracion_over_limit_rejected(self):
        self.client.force_login(self.admin)
        response = self._post(
            {
                "branchId": self.sucursal.pk,
                "dateTime": self._iso(10),
                "duracionEstimadaMinutos": 999,
            }
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("duracionEstimadaMinutos", response.json()["errors"])

    def test_empty_lists_accepted(self):
        self.client.force_login(self.admin)
        response = self._post(
            {
                "branchId": self.sucursal.pk,
                "dateTime": self._iso(10),
                "especialistasPlanificados": [],
                "maquinariaPlanificada": [],
            }
        )
        self.assertEqual(response.status_code, 201, response.content)
        cita = CitaMedica.objects.get()
        self.assertEqual(cita.maquinaria_items.count(), 0)
        self.assertEqual(cita.especialistas_items.count(), 0)

    def test_maquinaria_invalid_cantidad_rejected(self):
        self.client.force_login(self.admin)
        response = self._post(
            {
                "branchId": self.sucursal.pk,
                "dateTime": self._iso(10),
                "maquinariaPlanificada": [
                    {"maquinariaId": self.laser.pk, "cantidad": 0},
                ],
            }
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("maquinariaPlanificada", response.json()["errors"])

    def test_invalid_iso_datetime_rejected(self):
        self.client.force_login(self.admin)
        response = self._post(
            {
                "branchId": self.sucursal.pk,
                "dateTime": "not-a-date",
            }
        )
        self.assertEqual(response.status_code, 400, response.content)