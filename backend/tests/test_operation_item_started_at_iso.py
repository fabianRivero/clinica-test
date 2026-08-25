"""Unit tests for ``_operation_item`` helper used by the client detail
endpoint and other client/operation views.

Covers:

* ``startedAtIso`` is the new ISO-formatted mirror of ``startedAt`` so the
  frontend can filter the procedure list by month/year without parsing
  localised labels.
* ``branch`` (from ``_operation_branch``) falls back to the client's
  origin branch when the operation has no appointments yet (the normal
  case right after the conversion wizard finalises the procedure). It
  only returns ``"Por asignar"`` when the client also lacks a branch.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import (
    ProcEsteticosTipo,
    ProcEstetico,
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from config.client_api_views import _operation_item, _operation_branch
from config.api.helpers_operations import (
    operation_branch as helpers_operation_branch,
    operation_branch_id as helpers_operation_branch_id,
)
from config.api_views import _operation_detail as detail_helper
from customers.models import Cliente
from operations.models import CitaMedica, Operacion


class OperationItemStartedAtIsoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.sucursal = Sucursal.objects.create(nombre="Central", activa=True)
        cls.tipo = TipoServicio.objects.create(tipo="Tratamiento", activo=True)
        cls.tipo_proc = ProcEsteticosTipo.objects.create(tipo="Corporal", activo=True)
        cls.proc = ProcEstetico.objects.create(
            tipo_p_estetico=cls.tipo_proc, proceso="Limpieza", activo=True
        )
        cls.service = ServicioConfig.objects.create(
            tipo_servicio=cls.tipo,
            proc_estetico=cls.proc,
            precio_base=Decimal("120.00"),
            activo=True,
        )
        cls.user = Usuario.objects.create_user(username="op.item.user", password="pw12345!")
        cls.customer = Cliente.objects.create(
            usuario=cls.user,
            sucursal_origen=cls.sucursal,
            fecha_nacimiento=date(1990, 1, 1),
        )

    def _make_operation(self, fecha_inicio):
        return Operacion.objects.create(
            paciente=self.customer,
            servicio_config=self.service,
            precio_total=Decimal("100.00"),
            cuotas_totales=1,
            sesiones_totales=1,
            fecha_inicio=fecha_inicio,
            estado=Operacion.Estado.EN_PROCESO,
        )

    def test_started_at_iso_with_fecha_inicio(self):
        operation = self._make_operation(date(2026, 3, 15))
        item = _operation_item(operation)
        self.assertEqual(item["startedAtIso"], "2026-03-15")
        # El label localizado sigue presente para no romper consumidores previos.
        self.assertEqual(item["startedAt"], "15/03/2026")

    def test_started_at_iso_is_none_without_fecha_inicio(self):
        operation = self._make_operation(None)
        item = _operation_item(operation)
        self.assertIsNone(item["startedAtIso"])
        self.assertEqual(item["startedAt"], "Sin fecha")


class OperationBranchFallbackTests(TestCase):
    """``_operation_branch`` debe caer a la sede de origen del cliente
    cuando la operacion aun no tiene citas reservadas (caso normal
    inmediatamente despues del wizard de conversion)."""

    @classmethod
    def setUpTestData(cls):
        cls.sucursal_origen = Sucursal.objects.create(
            nombre="Central", activa=True
        )
        cls.tipo = TipoServicio.objects.create(tipo="Tratamiento", activo=True)
        cls.tipo_proc = ProcEsteticosTipo.objects.create(tipo="Corporal", activo=True)
        cls.proc = ProcEstetico.objects.create(
            tipo_p_estetico=cls.tipo_proc, proceso="Limpieza", activo=True
        )
        cls.service = ServicioConfig.objects.create(
            tipo_servicio=cls.tipo,
            proc_estetico=cls.proc,
            precio_base=Decimal("120.00"),
            activo=True,
        )
        cls.user = Usuario.objects.create_user(
            username="op.branch.user", password="pw12345!"
        )
        cls.customer = Cliente.objects.create(
            usuario=cls.user,
            sucursal_origen=cls.sucursal_origen,
            fecha_nacimiento=date(1990, 1, 1),
        )

    def test_branch_falls_back_to_cliente_sucursal_origen_sin_citas(self):
        """Operacion recien creada por el wizard: sin citas, pero con
        cliente que ya tiene sucursal_origen persistida por el finalize."""
        operation = Operacion.objects.create(
            paciente=self.customer,
            servicio_config=self.service,
            precio_total=Decimal("100.00"),
            cuotas_totales=1,
            sesiones_totales=1,
            fecha_inicio=date(2026, 1, 15),
            estado=Operacion.Estado.EN_PROCESO,
        )
        branch = _operation_branch(operation)
        self.assertEqual(branch, f"Sede: {self.sucursal_origen.nombre}")

    def test_branch_devuelve_por_asignar_si_cliente_tampoco_tiene_sede(self):
        """Si el cliente tampoco tiene sucursal_origen (p.ej. registros
        muy antiguos migrados o caso borde del SET_NULL), el helper debe
        seguir devolviendo el literal 'Por asignar'."""
        user_sin_sucursal = Usuario.objects.create_user(
            username="op.branch.no.branch", password="pw12345!"
        )
        cliente_sin_sucursal = Cliente.objects.create(
            usuario=user_sin_sucursal,
            sucursal_origen=None,
            fecha_nacimiento=date(1990, 1, 1),
        )
        operation = Operacion.objects.create(
            paciente=cliente_sin_sucursal,
            servicio_config=self.service,
            precio_total=Decimal("100.00"),
            cuotas_totales=1,
            sesiones_totales=1,
            fecha_inicio=date(2026, 1, 15),
            estado=Operacion.Estado.EN_PROCESO,
        )
        branch = _operation_branch(operation)
        self.assertEqual(branch, "Por asignar")

    def test_branch_no_falla_si_paciente_es_none(self):
        """Defensivo: si la operacion no tiene paciente, no debe explotar.
        Devuelve 'Por asignar' en lugar de tirar AttributeError."""
        operation = Operacion.objects.create(
            paciente=self.customer,
            servicio_config=self.service,
            precio_total=Decimal("100.00"),
            cuotas_totales=1,
            sesiones_totales=1,
            fecha_inicio=date(2026, 1, 15),
            estado=Operacion.Estado.EN_PROCESO,
        )
        operation.paciente = None
        branch = _operation_branch(operation)
        self.assertEqual(branch, "Por asignar")


class HelpersOperationBranchFallbackTests(TestCase):
    """Cubre el segundo helper `operation_branch` usado por la lista de
    operaciones y por el detail viejo (``admin_operation_detail``). Hasta
    este cambio no tenia fallback al `Cliente.sucursal_origen`, asi que
    operaciones sin citas siempre mostraban "Por asignar" aunque el
    cliente ya tuviera una sede de origen persistida por el wizard."""

    @classmethod
    def setUpTestData(cls):
        cls.sucursal_origen = Sucursal.objects.create(
            nombre="Capacity-Central", activa=True
        )
        cls.tipo = TipoServicio.objects.create(tipo="Tratamiento", activo=True)
        cls.tipo_proc = ProcEsteticosTipo.objects.create(tipo="Corporal", activo=True)
        cls.proc = ProcEstetico.objects.create(
            tipo_p_estetico=cls.tipo_proc, proceso="Limpieza", activo=True
        )
        cls.service = ServicioConfig.objects.create(
            tipo_servicio=cls.tipo,
            proc_estetico=cls.proc,
            precio_base=Decimal("120.00"),
            activo=True,
        )
        cls.user = Usuario.objects.create_user(username="op.helpers.user", password="pw12345!")
        cls.customer = Cliente.objects.create(
            usuario=cls.user,
            sucursal_origen=cls.sucursal_origen,
            fecha_nacimiento=date(1990, 1, 1),
        )

    def test_branch_falls_back_to_cliente_sucursal_origen_sin_citas(self):
        operation = Operacion.objects.create(
            paciente=self.customer,
            servicio_config=self.service,
            precio_total=Decimal("100.00"),
            cuotas_totales=1,
            sesiones_totales=1,
            fecha_inicio=date(2026, 1, 15),
            estado=Operacion.Estado.EN_PROCESO,
        )
        self.assertEqual(
            helpers_operation_branch(operation),
            f"Sede: {self.sucursal_origen.nombre}",
        )
        self.assertEqual(
            helpers_operation_branch_id(operation),
            self.sucursal_origen.pk,
        )

    def test_branch_devuelve_por_asignar_si_cliente_tampoco_tiene_sede(self):
        user_sin_sucursal = Usuario.objects.create_user(
            username="op.helpers.no.branch", password="pw12345!"
        )
        cliente_sin_sucursal = Cliente.objects.create(
            usuario=user_sin_sucursal,
            sucursal_origen=None,
            fecha_nacimiento=date(1990, 1, 1),
        )
        operation = Operacion.objects.create(
            paciente=cliente_sin_sucursal,
            servicio_config=self.service,
            precio_total=Decimal("100.00"),
            cuotas_totales=1,
            sesiones_totales=1,
            fecha_inicio=date(2026, 1, 15),
            estado=Operacion.Estado.EN_PROCESO,
        )
        self.assertEqual(helpers_operation_branch(operation), "Por asignar")
        self.assertIsNone(helpers_operation_branch_id(operation))


class AvailableAppointmentsFieldTests(TestCase):
    """``availableAppointments`` se expone en ambos helpers del detail
    de operacion para que el frontend pueda bloquear el formulario
    "Reservar nueva cita" sin parsear el string ``sessions``.
    """

    @classmethod
    def setUpTestData(cls):
        cls.sucursal = Sucursal.objects.create(
            nombre="Capacity-Central", activa=True
        )
        cls.tipo = TipoServicio.objects.create(tipo="Tratamiento", activo=True)
        cls.tipo_proc = ProcEsteticosTipo.objects.create(tipo="Corporal", activo=True)
        cls.proc = ProcEstetico.objects.create(
            tipo_p_estetico=cls.tipo_proc, proceso="Limpieza", activo=True
        )
        cls.service = ServicioConfig.objects.create(
            tipo_servicio=cls.tipo,
            proc_estetico=cls.proc,
            precio_base=Decimal("120.00"),
            activo=True,
        )
        cls.user = Usuario.objects.create_user(username="op.cap.user", password="pw12345!")
        cls.customer = Cliente.objects.create(
            usuario=cls.user,
            sucursal_origen=cls.sucursal,
            fecha_nacimiento=date(1990, 1, 1),
        )

    def _make_operation(self, sesiones_totales=1):
        return Operacion.objects.create(
            paciente=self.customer,
            servicio_config=self.service,
            precio_total=Decimal("100.00"),
            cuotas_totales=1,
            sesiones_totales=sesiones_totales,
            fecha_inicio=date(2026, 1, 15),
            estado=Operacion.Estado.EN_PROCESO,
        )

    def test_client_operation_item_incluye_available_appointments(self):
        operation = self._make_operation(sesiones_totales=3)
        item = _operation_item(operation)
        self.assertEqual(item["availableAppointments"], 3)

    def test_detail_helper_incluye_available_appointments(self):
        operation = self._make_operation(sesiones_totales=3)
        item = detail_helper(operation)
        self.assertEqual(item["availableAppointments"], 3)

    def test_available_appointments_refleja_reserva_activa(self):
        """Si hay una cita programada, los cupos bajan en uno y
        ``availableAppointments`` refleja la cuenta real (lo mismo que
        usa ``operacion.puede_reservar`` para bloquear el POST)."""
        from django.utils import timezone as tz

        operation = self._make_operation(sesiones_totales=1)
        CitaMedica.objects.create(
            operacion=operation,
            sucursal=self.sucursal,
            fecha_hora=tz.now() + tz.timedelta(days=1),
            estado=CitaMedica.Estado.PROGRAMADA,
        )
        item = _operation_item(operation)
        self.assertEqual(item["availableAppointments"], 0)

    def test_endpoint_admin_operaciones_expone_available_appointments(self):
        """El endpoint real de detail (``admin_operation_detail``) debe
        incluir el campo. Protege contra una regresion donde solo se
        actualice uno de los dos helpers."""
        from django.test import Client
        from accounts.models import Rol

        admin = Usuario.objects.create_user(
            username="admin.cap", password="pw12345!",
            primer_nombre="Adm", apellido_paterno="Cap",
            rol=Rol.objects.create(rol="ADMIN_PRINCIPAL"),
        )
        operation = self._make_operation(sesiones_totales=2)
        client = Client()
        client.force_login(admin)
        response = client.get(f"/api/admin/operaciones/{operation.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("availableAppointments", response.json()["operation"])
