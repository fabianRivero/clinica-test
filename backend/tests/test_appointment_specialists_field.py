"""Tests for ``appointment_specialists`` helper and the
``specialist`` field on the per-appointment payloads emitted by
``_operation_detail`` / ``_appointment_item`` / ``_admin_client_detail``.

Background: every cita serializer used to hard-code the string
``"Sin asignar"`` for the ``specialist`` field regardless of whether
the cita had any Especialista associated. The helper now joins the
names of every Especialista (planned or attended) so the appointments
list in cms/clientes/<id> and cms/operaciones/<id> shows the real
people responsible for the cita.

Covers:
- Empty cita returns ``"—"``
- Cita with no Especialista rows returns ``"—"``
- Cita with one Especialista returns the user full name
- Cita with multiple specialists returns comma-separated names
- Same Especialista appearing in both planned + attended rows is
  deduplicated
- ``_operation_detail`` and ``_appointment_item`` propagate the value
  end-to-end so the frontend receives it without further wiring
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import (
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from config.api_helpers import appointment_specialists
from customers.models import Cliente
from operations.models import (
    CitaEspecialista,
    CitaMedica,
    Operacion,
)
from staff.models import Especialista


class AppointmentSpecialistsHelperTests(TestCase):
    """Unit tests for the helper itself."""

    TZ = ZoneInfo("America/La_Paz")

    def setUp(self):
        self.rol_especialista = Rol.objects.create(rol="TRABAJADOR")
        self.rol_cliente = Rol.objects.create(rol="CLIENTE")
        self.sucursal = Sucursal.objects.create(nombre="Centro", activa=True)
        self.cliente_user = Usuario.objects.create_user(
            username="cli",
            password="password123",
            primer_nombre="M",
            apellido_paterno="G",
            rol=self.rol_cliente,
        )
        self.cliente = Cliente.objects.create(
            usuario=self.cliente_user,
            ci="1",
            telefono="1",
            fecha_nacimiento=date(1990, 1, 1),
        )
        self.tipo = TipoServicio.objects.create(tipo="T")
        self.servicio = ServicioConfig.objects.create(
            tipo_servicio=self.tipo, precio_base=100
        )
        self.operacion = Operacion.objects.create(
            paciente=self.cliente,
            servicio_config=self.servicio,
            sesiones_totales=1,
            precio_total=100,
            estado=Operacion.Estado.EN_PROCESO,
        )
        self.cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=datetime(2026, 9, 1, 10, 0, tzinfo=self.TZ),
            estado=CitaMedica.Estado.PROGRAMADA,
        )

    def _make_especialista(self, username, primer_nombre, apellido):
        user = Usuario.objects.create_user(
            username=username,
            password="password123",
            primer_nombre=primer_nombre,
            apellido_paterno=apellido,
            rol=self.rol_especialista,
            sucursal=self.sucursal,
        )
        return Especialista.objects.create(
            usuario=user, sucursal_base=self.sucursal
        )

    def test_returns_dash_when_cita_is_none(self):
        self.assertEqual(appointment_specialists(None), "—")

    def test_returns_dash_when_cita_has_no_especialistas(self):
        self.assertEqual(appointment_specialists(self.cita), "—")

    def test_returns_single_especialista_name(self):
        esp = self._make_especialista("esp_a", "Lucia", "Lopez")
        CitaEspecialista.objects.create(
            cita=self.cita, especialista=esp, planificada=True
        )
        # usuario.nombre_completo returns "Lucia Lopez" with current
        # naming; assert against the user string to avoid coupling to
        # the exact join rules of Usuario.
        self.assertEqual(
            appointment_specialists(self.cita),
            esp.usuario.nombre_completo or esp.usuario.username,
        )

    def test_returns_multiple_especialistas_joined(self):
        esp1 = self._make_especialista("esp_a", "Lucia", "Lopez")
        esp2 = self._make_especialista("esp_b", "Mario", "Perez")
        CitaEspecialista.objects.create(
            cita=self.cita, especialista=esp1, planificada=True
        )
        CitaEspecialista.objects.create(
            cita=self.cita, especialista=esp2, planificada=True
        )
        nombres = esp1.usuario.nombre_completo, esp2.usuario.nombre_completo
        self.assertEqual(
            appointment_specialists(self.cita), ", ".join(nombres)
        )

    def test_deduplicates_when_same_especialista_is_planned_and_attended(self):
        esp = self._make_especialista("esp_a", "Lucia", "Lopez")
        CitaEspecialista.objects.create(
            cita=self.cita, especialista=esp, planificada=True
        )
        CitaEspecialista.objects.create(
            cita=self.cita, especialista=esp, planificada=False
        )
        # Same person shows up only once even though two CitaEspecialista
        # rows exist (one planned, one attended).
        self.assertEqual(
            appointment_specialists(self.cita),
            esp.usuario.nombre_completo or esp.usuario.username,
        )


class OperationDetailSpecialistFieldTests(TestCase):
    """End-to-end: ``_operation_detail`` and ``_appointment_item`` now
    expose the helper output, not the old placeholder."""

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
        self.esp_user = Usuario.objects.create_user(
            username="esp",
            password="password123",
            primer_nombre="Lucia",
            apellido_paterno="Lopez",
            rol=self.rol_especialista,
            sucursal=self.sucursal,
        )
        self.esp = Especialista.objects.create(
            usuario=self.esp_user, sucursal_base=self.sucursal
        )
        self.cliente_user = Usuario.objects.create_user(
            username="cli",
            password="password123",
            primer_nombre="M",
            apellido_paterno="G",
            rol=self.rol_cliente,
        )
        self.cliente = Cliente.objects.create(
            usuario=self.cliente_user,
            ci="1",
            telefono="1",
            fecha_nacimiento=date(1990, 1, 1),
        )
        self.tipo = TipoServicio.objects.create(tipo="T")
        self.servicio = ServicioConfig.objects.create(
            tipo_servicio=self.tipo, precio_base=100
        )
        self.operacion = Operacion.objects.create(
            paciente=self.cliente,
            servicio_config=self.servicio,
            sesiones_totales=1,
            precio_total=100,
            estado=Operacion.Estado.EN_PROCESO,
        )
        self.cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=datetime(2026, 9, 1, 10, 0, tzinfo=self.TZ),
            estado=CitaMedica.Estado.PROGRAMADA,
        )
        CitaEspecialista.objects.create(
            cita=self.cita, especialista=self.esp, planificada=True
        )

    def test_operation_detail_specialist_is_not_the_placeholder(self):
        from config.api_views import _operation_detail

        payload = _operation_detail(self.operacion)
        specialist = payload["appointments"][0]["specialist"]
        self.assertNotEqual(specialist, "Sin asignar")
        self.assertEqual(
            specialist,
            self.esp.usuario.nombre_completo or self.esp.usuario.username,
        )

    def test_operation_detail_specialist_dash_when_no_especialistas(self):
        from config.api_views import _operation_detail

        self.cita.especialistas_items.all().delete()
        payload = _operation_detail(self.operacion)
        self.assertEqual(payload["appointments"][0]["specialist"], "—")

    def test_client_appointment_item_specialist_is_not_the_placeholder(self):
        from config.client_api_views import _appointment_item

        item = _appointment_item(self.cita)
        self.assertNotEqual(item["specialist"], "Sin asignar")
        self.assertEqual(
            item["specialist"],
            self.esp.usuario.nombre_completo or self.esp.usuario.username,
        )