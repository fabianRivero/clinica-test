"""Shared fixtures for the biometric suspension regression matrix.

Tasks 2.1-2.5 of ``suspend-fingerprint-integration`` PR 2 use a single
set of roles / branch / users / cliente / cita to keep the new
behaviour deterministic. Concrete behaviour classes live next to this
helper module.
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
    ServicioConfig,
    Sucursal,
    TipoPiel,
    TipoServicio,
)
from customers.models import Cliente
from operations.models import CitaMedica, Operacion


def post_json(client, url, payload=None, **extra):
    body = json.dumps(payload or {})
    return client.post(url, data=body, content_type="application/json", **extra)


class SuspensionGateTestBase(TestCase):
    """Shared fixture: roles, branch, users, cliente and cita."""

    @classmethod
    def setUpTestData(cls):
        cls.rol_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.rol_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        cls.rol_cliente = Rol.objects.create(rol="CLIENTE")
        cls.rol_trabajador = Rol.objects.create(rol="TRABAJADOR")

        cls.sucursal = Sucursal.objects.create(nombre="Suspension-Centro", activa=True)
        cls.tipo = TipoServicio.objects.create(tipo="Consulta", activo=True)
        cls.servicio = ServicioConfig.objects.create(
            tipo_servicio=cls.tipo, precio_base=Decimal("100"), activo=True
        )

        # Catalog rows required by the reactivation finalize path.
        cls.tipo_piel = TipoPiel.objects.create(nombre="Normal", activo=True)
        cls.grado_deshidratacion = GradoDeshidratacion.objects.create(
            nombre="Bajo", activo=True
        )
        cls.grosor_piel = GrosorPiel.objects.create(nombre="Medio", activo=True)

        cls.admin_principal = Usuario.objects.create_user(
            username="susp.principal",
            password="pw12345!",
            primer_nombre="Adm",
            apellido_paterno="Pri",
            rol=cls.rol_principal,
            sucursal=None,
        )
        cls.admin_sucursal = Usuario.objects.create_user(
            username="susp.sucursal",
            password="pw12345!",
            primer_nombre="Adm",
            apellido_paterno="Suc",
            rol=cls.rol_sucursal,
            sucursal=cls.sucursal,
        )
        cls.worker = Usuario.objects.create_user(
            username="susp.worker",
            password="pw12345!",
            primer_nombre="Wor",
            apellido_paterno="Ker",
            rol=cls.rol_trabajador,
            sucursal=cls.sucursal,
        )
        cls.client_user = Usuario.objects.create_user(
            username="susp.cliente",
            password="pw12345!",
            primer_nombre="Cli",
            apellido_paterno="Ente",
            rol=cls.rol_cliente,
            sucursal=cls.sucursal,
        )
        cls.cliente = Cliente.objects.create(
            usuario=cls.client_user, fecha_nacimiento=timezone.localdate()
        )
        cls.operacion = Operacion.objects.create(
            paciente=cls.cliente,
            servicio_config=cls.servicio,
            precio_total=Decimal("100"),
            sesiones_totales=3,
            estado=Operacion.Estado.EN_PROCESO,
        )
        cls.cita = CitaMedica.objects.create(
            operacion=cls.operacion,
            sucursal=cls.sucursal,
            fecha_hora=timezone.now(),
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        )

    def setUp(self):
        self.client_http = Client()

    def login(self, user):
        self.client_http.force_login(user)
