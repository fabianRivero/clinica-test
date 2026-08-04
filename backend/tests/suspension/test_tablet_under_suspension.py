"""Cliente-portal TABLET confirmation stays operational under biometric suspension.

The TABLET path does NOT touch the agent or any fingerprint material.
The actual ``client_confirm_pending_appointment_tablet`` endpoint at
``/api/client/citas/<id>/confirmar-tablet/`` is gated by the standard
``@_client_required`` decorator (cliente session) — the kiosk-session
flow lives behind the separate ``/api/client/tablet/auth/login/`` and
``/api/client/tablet/client/login/`` URLs. This module proves the
cliente-portal TABLET path still writes
``CONFIRMADA / TABLET / verif_biometria=false`` while suspended, paired
with the MANUAL fallback covered in
``test_canonical_gates.test_manual_confirmation_still_works_under_suspension``.
The kiosk round-trip is exercised by
``tests.test_appointment_confirmation_flows`` and is out of scope for
the suspension matrix.
"""

from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import Rol, Usuario
from catalogs.models import ServicioConfig, Sucursal, TipoServicio
from customers.models import Cliente
from operations.models import CitaMedica, EventoConfirmacionCita, Operacion


SUSPENDED = override_settings(BIOMETRIC_SUSPENDED=True)


@SUSPENDED
class ClientePortalTabletUnderSuspensionTests(TestCase):
    def setUp(self):
        self.rol_cliente = Rol.objects.create(rol="CLIENTE")
        self.sucursal = Sucursal.objects.create(nombre="Tablet-Centro", activa=True)
        self.tipo = TipoServicio.objects.create(tipo="Consulta", activo=True)
        self.servicio = ServicioConfig.objects.create(
            tipo_servicio=self.tipo, precio_base=100, activo=True
        )

        self.client_user = Usuario.objects.create_user(
            username="tablet.cliente",
            password="password123",
            rol=self.rol_cliente,
            sucursal=self.sucursal,
        )
        self.cliente = Cliente.objects.create(
            usuario=self.client_user,
            fecha_nacimiento=timezone.localdate(),
            sucursal_registro=self.sucursal,
        )
        self.operacion = Operacion.objects.create(
            paciente=self.cliente,
            servicio_config=self.servicio,
            precio_total=100,
            sesiones_totales=3,
            estado=Operacion.Estado.EN_PROCESO,
        )
        self.cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=timezone.now(),
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        )

    def test_cliente_portal_tablet_confirm_still_writes_TABLET(self):
        # The actual endpoint is gated by @_client_required, not the
        # kiosk session, so we authenticate as the cliente and POST to
        # the cliente-portal URL.
        client = Client()
        client.force_login(self.client_user)
        response = client.post(
            f"/api/client/citas/{self.cita.id}/confirmar-tablet/",
            content_type="application/json",
            REMOTE_ADDR="10.20.30.40",
        )
        self.assertEqual(response.status_code, 200)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.CONFIRMADA)
        self.assertEqual(self.cita.metodo_confirmacion, CitaMedica.MetodoConfirmacion.TABLET)
        self.assertFalse(self.cita.verif_biometria)

        event = EventoConfirmacionCita.objects.get(cita=self.cita)
        self.assertEqual(event.metodo, EventoConfirmacionCita.Metodo.TABLET)
        self.assertEqual(event.ip_origen, "10.20.30.40")
