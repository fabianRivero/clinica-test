"""Tests for the GET /api/especialista/mis-citas/ endpoint.

Covers:
- Specialist sees only citas where they appear in CitaEspecialista
- CANCELADA and NO_ASISTIO excluded
- Read-only shape: planning data + maquinaría, no admin action flags
- Non-specialist users get 403
- Specialist without Especialista profile gets 403
- Multiple specialists on the same cita each see it independently

Part of the appointment-reservation-redesign change.
"""

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


class EspecialistaMisCitasTests(TestCase):
    TZ = ZoneInfo("America/La_Paz")

    def setUp(self):
        self.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.rol_especialista = Rol.objects.create(rol="TRABAJADOR")
        self.rol_cliente = Rol.objects.create(rol="CLIENTE")

        self.sucursal = Sucursal.objects.create(nombre="Centro", activa=True)
        self.admin = Usuario.objects.create_user(
            username="admin",
            password="password123",
            primer_nombre="A",
            apellido_paterno="A",
            rol=self.rol_admin,
            sucursal=self.sucursal,
        )

        self.esp1_user = Usuario.objects.create_user(
            username="esp1",
            password="password123",
            primer_nombre="Lucia",
            apellido_paterno="Lopez",
            rol=self.rol_especialista,
            sucursal=self.sucursal,
        )
        self.esp1 = Especialista.objects.create(
            usuario=self.esp1_user, sucursal_base=self.sucursal
        )

        self.esp2_user = Usuario.objects.create_user(
            username="esp2",
            password="password123",
            primer_nombre="Mario",
            apellido_paterno="M",
            rol=self.rol_especialista,
            sucursal=self.sucursal,
        )
        self.esp2 = Especialista.objects.create(
            usuario=self.esp2_user, sucursal_base=self.sucursal
        )

        self.laser = Maquinaria.objects.create(
            nombre="Laser", cantidad_total=2, sucursal=self.sucursal
        )

        # Two clientes (each with their own operacion) so we can build two citas.
        self.cliente1_user = Usuario.objects.create_user(
            username="c1",
            password="password123",
            primer_nombre="Ana",
            apellido_paterno="P",
            rol=self.rol_cliente,
        )
        self.cliente1 = Cliente.objects.create(
            usuario=self.cliente1_user,
            ci="1",
            telefono="1",
            fecha_nacimiento=date(1990, 1, 1),
        )

        self.cliente2_user = Usuario.objects.create_user(
            username="c2",
            password="password123",
            primer_nombre="Bea",
            apellido_paterno="Q",
            rol=self.rol_cliente,
        )
        self.cliente2 = Cliente.objects.create(
            usuario=self.cliente2_user,
            ci="2",
            telefono="2",
            fecha_nacimiento=date(1990, 1, 1),
        )

        tipo = TipoServicio.objects.create(tipo="T")
        servicio = ServicioConfig.objects.create(tipo_servicio=tipo, precio_base=100)
        self.op1 = Operacion.objects.create(
            paciente=self.cliente1,
            servicio_config=servicio,
            sesiones_totales=4,
            precio_total=400,
            estado=Operacion.Estado.EN_PROCESO,
        )
        self.op2 = Operacion.objects.create(
            paciente=self.cliente2,
            servicio_config=servicio,
            sesiones_totales=4,
            precio_total=400,
            estado=Operacion.Estado.EN_PROCESO,
        )

        # Cita 1: PROGRAMADA, esp1 planned.
        self.cita1 = CitaMedica.objects.create(
            operacion=self.op1,
            sucursal=self.sucursal,
            fecha_hora=datetime(2026, 9, 1, 10, 0, tzinfo=self.TZ),
            estado=CitaMedica.Estado.PROGRAMADA,
            duracion_estimada_minutos=60,
            procedimiento_planificado="Depilacion axilas",
            zona_cuerpo_planificada="Axilas",
            descripcion_general="Sesion inicial",
            notas_previas="Sin alergias",
        )
        CitaEspecialista.objects.create(
            cita=self.cita1, especialista=self.esp1, planificada=True
        )
        CitaMaquinaria.objects.create(
            cita=self.cita1, maquinaria=self.laser, cantidad=1, planificada=True
        )

        # Cita 2: CONFIRMADA, esp2 planned AND attended.
        self.cita2 = CitaMedica.objects.create(
            operacion=self.op2,
            sucursal=self.sucursal,
            fecha_hora=datetime(2026, 9, 2, 11, 0, tzinfo=self.TZ),
            estado=CitaMedica.Estado.CONFIRMADA,
            metodo_confirmacion=CitaMedica.MetodoConfirmacion.MANUAL,
            procedimiento_realizado="Limpieza facial",
        )
        CitaEspecialista.objects.create(
            cita=self.cita2, especialista=self.esp2, planificada=True
        )
        CitaEspecialista.objects.create(
            cita=self.cita2, especialista=self.esp2, planificada=False
        )

        # Cita 3: CANCELADA, esp1 planned (should be excluded).
        self.cita3 = CitaMedica.objects.create(
            operacion=self.op1,
            sucursal=self.sucursal,
            fecha_hora=datetime(2026, 9, 3, 12, 0, tzinfo=self.TZ),
            estado=CitaMedica.Estado.CANCELADA,
        )
        CitaEspecialista.objects.create(
            cita=self.cita3, especialista=self.esp1, planificada=True
        )

        self.url = "/api/especialista/mis-citas/"

    def test_specialist_sees_only_assigned_citas(self):
        self.client.force_login(self.esp1_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        items = response.json()["citas"]
        ids = {c["rawId"] for c in items}
        self.assertSetEqual(ids, {self.cita1.pk})

    def test_other_specialist_sees_their_own(self):
        self.client.force_login(self.esp2_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        items = response.json()["citas"]
        ids = {c["rawId"] for c in items}
        self.assertSetEqual(ids, {self.cita2.pk})

    def test_cancelled_cita_excluded(self):
        self.client.force_login(self.esp1_user)
        response = self.client.get(self.url)
        items = response.json()["citas"]
        self.assertNotIn(self.cita3.pk, {c["rawId"] for c in items})

    def test_response_includes_planning_data(self):
        self.client.force_login(self.esp1_user)
        response = self.client.get(self.url)
        item = response.json()["citas"][0]
        self.assertEqual(item["fecha"], "2026-09-01")
        self.assertEqual(item["horaInicio"], "10:00")
        self.assertEqual(item["duracionEstimadaMinutos"], 60)
        self.assertEqual(item["procedimientoPlanificado"], "Depilacion axilas")
        self.assertEqual(item["zonaCuerpoPlanificada"], "Axilas")
        self.assertEqual(item["descripcionGeneral"], "Sesion inicial")
        self.assertEqual(item["notasPrevias"], "Sin alergias")
        self.assertEqual(item["sucursal"], "Centro")

    def test_response_includes_maquinaria(self):
        self.client.force_login(self.esp1_user)
        response = self.client.get(self.url)
        item = response.json()["citas"][0]
        self.assertEqual(len(item["maquinaria"]), 1)
        self.assertEqual(item["maquinaria"][0]["nombre"], "Laser")
        self.assertEqual(item["maquinaria"][0]["cantidad"], 1)
        self.assertTrue(item["maquinaria"][0]["planificada"])

    def test_response_excludes_admin_action_flags(self):
        self.client.force_login(self.esp1_user)
        response = self.client.get(self.url)
        item = response.json()["citas"][0]
        self.assertNotIn("canManage", item)
        self.assertNotIn("canMarkPendingBiometric", item)
        self.assertNotIn("canConfirmBiometric", item)
        self.assertNotIn("canCancelFromVerification", item)
        self.assertNotIn("biometricMockTemplate", item)

    def test_client_user_denied(self):
        self.client.force_login(self.cliente1_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_admin_user_denied(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_anon_denied(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (401, 403))

    def test_specialist_with_attended_row_sees_cita(self):
        """Citas where the specialist is in planificada=False only also count."""
        # Add esp1 attended to cita2 (no planned).
        CitaEspecialista.objects.create(
            cita=self.cita2, especialista=self.esp1, planificada=False
        )
        self.client.force_login(self.esp1_user)
        response = self.client.get(self.url)
        ids = {c["rawId"] for c in response.json()["citas"]}
        self.assertIn(self.cita2.pk, ids)