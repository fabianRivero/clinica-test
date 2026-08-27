"""Tests for get_maquinaria_conflicts helper and admin_check_maquinaria endpoint.

Covers:
- Helper returns conflicts when suma+cantidad_solicitada > cantidad_total
- Helper omits items without overlap
- Helper ignores CANCELADA / NO_ASISTIO citas
- Helper skips items whose maquinaría is outside the branch scope
- Endpoint parses query params and returns the helper's output
- Endpoint validates fecha/hora/duracion formats and ranges

Part of the appointment-reservation-redesign change.
"""

import json
from datetime import date, datetime, time

from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import Maquinaria, Sucursal
from operations.models import CitaMedica, CitaMaquinaria
from operations.scheduling import get_maquinaria_conflicts


class GetMaquinariaConflictsHelperTests(TestCase):
    def setUp(self):
        self.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.sucursal = Sucursal.objects.create(nombre="Centro", activa=True)
        self.sucursal_otra = Sucursal.objects.create(nombre="Norte", activa=True)

        self.laser = Maquinaria.objects.create(
            nombre="Laser diodo",
            marca="Alma",
            cantidad_total=1,
            sucursal=self.sucursal,
        )
        self.camilla = Maquinaria.objects.create(
            nombre="Camilla",
            cantidad_total=2,
            sucursal=None,  # global
        )
        self.laser_otra = Maquinaria.objects.create(
            nombre="Laser otra sede",
            cantidad_total=1,
            sucursal=self.sucursal_otra,
        )

        self.cliente = Usuario.objects.create_user(
            username="cliente",
            password="password123",
            primer_nombre="Ana",
            apellido_paterno="Perez",
            rol=Rol.objects.create(rol="CLIENTE"),
        )

    def _make_cita(self, sucursal, hora_inicio, estado=CitaMedica.Estado.PROGRAMADA):
        from customers.models import Cliente
        from operations.models import Operacion
        from catalogs.models import ServicioConfig, TipoServicio

        tipo = TipoServicio.objects.create(tipo="Consulta")
        servicio = ServicioConfig.objects.create(
            tipo_servicio=tipo, precio_base=10,
        )
        cliente = Cliente.objects.create(
            usuario=self.cliente,
            ci="1234567",
            telefono="7000000",
            fecha_nacimiento=date(1990, 1, 1),
        )
        op = Operacion.objects.create(
            paciente=cliente,
            servicio_config=servicio,
            sesiones_totales=4,
            precio_total=10,
        )
        return CitaMedica.objects.create(
            operacion=op,
            sucursal=sucursal,
            fecha_hora=datetime.combine(date(2026, 9, 1), hora_inicio),
            estado=estado,
        )

    def test_no_conflict_when_nothing_overlaps(self):
        cita = self._make_cita(self.sucursal, time(10, 0))
        CitaMaquinaria.objects.create(cita=cita, maquinaria=self.laser, cantidad=1)

        result = get_maquinaria_conflicts(
            sucursal_id=self.sucursal.pk,
            fecha=date(2026, 9, 1),
            hora_inicio=time(15, 0),
            duracion_minutos=60,
            items=[{"maquinariaId": self.laser.pk, "cantidad": 1}],
        )
        self.assertEqual(result, [])

    def test_conflict_when_cantidad_exceeds_total(self):
        cita = self._make_cita(self.sucursal, time(10, 0))
        CitaMaquinaria.objects.create(cita=cita, maquinaria=self.laser, cantidad=1)

        result = get_maquinaria_conflicts(
            sucursal_id=self.sucursal.pk,
            fecha=date(2026, 9, 1),
            hora_inicio=time(10, 0),
            duracion_minutos=60,
            items=[{"maquinariaId": self.laser.pk, "cantidad": 1}],
        )
        self.assertEqual(len(result), 1)
        conflict = result[0]
        self.assertEqual(conflict["maquinariaId"], self.laser.pk)
        self.assertEqual(conflict["cantidadSolicitada"], 1)
        self.assertEqual(conflict["cantidadDisponible"], 0)
        self.assertEqual(len(conflict["citasQueLaUsan"]), 1)
        self.assertEqual(conflict["citasQueLaUsan"][0]["citaId"], cita.pk)

    def test_no_conflict_when_quantity_fits(self):
        """camilla has cantidad_total=2 and one prior cita uses 1; requesting 1 is fine."""
        cita = self._make_cita(self.sucursal, time(10, 0))
        CitaMaquinaria.objects.create(cita=cita, maquinaria=self.camilla, cantidad=1)

        result = get_maquinaria_conflicts(
            sucursal_id=self.sucursal.pk,
            fecha=date(2026, 9, 1),
            hora_inicio=time(10, 30),
            duracion_minutos=60,
            items=[{"maquinariaId": self.camilla.pk, "cantidad": 1}],
        )
        self.assertEqual(result, [])

    def test_cancelled_cita_excluded(self):
        cita = self._make_cita(self.sucursal, time(10, 0), estado=CitaMedica.Estado.CANCELADA)
        CitaMaquinaria.objects.create(cita=cita, maquinaria=self.laser, cantidad=1)

        result = get_maquinaria_conflicts(
            sucursal_id=self.sucursal.pk,
            fecha=date(2026, 9, 1),
            hora_inicio=time(10, 0),
            duracion_minutos=60,
            items=[{"maquinariaId": self.laser.pk, "cantidad": 1}],
        )
        self.assertEqual(result, [])

    def test_other_branch_cita_excluded(self):
        """Citas in another branch don't count toward the conflict."""
        cita = self._make_cita(self.sucursal_otra, time(10, 0))
        CitaMaquinaria.objects.create(cita=cita, maquinaria=self.laser, cantidad=1)

        result = get_maquinaria_conflicts(
            sucursal_id=self.sucursal.pk,
            fecha=date(2026, 9, 1),
            hora_inicio=time(10, 0),
            duracion_minutos=60,
            items=[{"maquinariaId": self.laser.pk, "cantidad": 1}],
        )
        self.assertEqual(result, [])

    def test_maquinaria_outside_scope_skipped(self):
        """Asking about a maquinaría in another branch is silently skipped."""
        cita = self._make_cita(self.sucursal, time(10, 0))
        CitaMaquinaria.objects.create(cita=cita, maquinaria=self.laser, cantidad=1)

        result = get_maquinaria_conflicts(
            sucursal_id=self.sucursal.pk,
            fecha=date(2026, 9, 1),
            hora_inicio=time(10, 0),
            duracion_minutos=60,
            items=[{"maquinariaId": self.laser_otra.pk, "cantidad": 1}],
        )
        self.assertEqual(result, [])

    def test_planificada_false_excluded(self):
        """CitaMaquinaria(planificada=False) is real-use, not reservation, so it doesn't block."""
        cita = self._make_cita(self.sucursal, time(10, 0))
        CitaMaquinaria.objects.create(
            cita=cita, maquinaria=self.laser, cantidad=1, planificada=False
        )

        result = get_maquinaria_conflicts(
            sucursal_id=self.sucursal.pk,
            fecha=date(2026, 9, 1),
            hora_inicio=time(10, 0),
            duracion_minutos=60,
            items=[{"maquinariaId": self.laser.pk, "cantidad": 1}],
        )
        self.assertEqual(result, [])


class AdminCheckMaquinariaEndpointTests(TestCase):
    def setUp(self):
        self.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.sucursal = Sucursal.objects.create(nombre="Centro", activa=True)
        self.admin = Usuario.objects.create_user(
            username="admin",
            password="password123",
            primer_nombre="A",
            apellido_paterno="B",
            rol=self.rol_admin,
            sucursal=self.sucursal,
        )
        self.laser = Maquinaria.objects.create(
            nombre="Laser", cantidad_total=1, sucursal=self.sucursal
        )

    def test_endpoint_returns_empty_when_no_conflicts(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            "/api/admin/disponibilidad/check-maquinaria/",
            {
                "sucursalId": self.sucursal.pk,
                "fecha": "2026-09-01",
                "hora": "15:00",
                "duracionMinutos": 60,
                "maquinariaIds": str(self.laser.pk),
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["conflictos"], [])
        self.assertEqual(len(data["disponibilidad"]), 1)
        self.assertEqual(data["disponibilidad"][0]["maquinariaId"], self.laser.pk)

    def test_endpoint_validates_required_params(self):
        self.client.force_login(self.admin)
        response = self.client.get("/api/admin/disponibilidad/check-maquinaria/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("sucursalId", response.json()["detail"])

    def test_endpoint_validates_duracion_range(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            "/api/admin/disponibilidad/check-maquinaria/",
            {
                "sucursalId": self.sucursal.pk,
                "fecha": "2026-09-01",
                "hora": "15:00",
                "duracionMinutos": 0,
                "maquinariaIds": str(self.laser.pk),
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_endpoint_requires_admin(self):
        from accounts.models import Rol as R
        anon = Usuario.objects.create_user(
            username="anon",
            password="password123",
            primer_nombre="C",
            apellido_paterno="D",
            rol=R.objects.create(rol="CLIENTE"),
        )
        self.client.force_login(anon)
        response = self.client.get(
            "/api/admin/disponibilidad/check-maquinaria/",
            {
                "sucursalId": self.sucursal.pk,
                "fecha": "2026-09-01",
                "hora": "15:00",
                "duracionMinutos": 60,
                "maquinariaIds": str(self.laser.pk),
            },
        )
        self.assertEqual(response.status_code, 403)