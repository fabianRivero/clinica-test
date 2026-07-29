import json
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from catalogs.models import ServicioConfig, Sucursal, TipoServicio
from customers.models import Cliente, HuellaBiometricaCliente
from operations.models import CitaMedica, EventoConfirmacionCita, Operacion
from operations.models import TabletKiosko


class AppointmentConfirmationFlowTests(TestCase):
    def setUp(self):
        self.rol_cliente = Rol.objects.create(rol="CLIENTE")
        self.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.sucursal = Sucursal.objects.create(nombre="Centro", activa=True)
        tipo_servicio = TipoServicio.objects.create(tipo="Consulta", activa=True)
        servicio = ServicioConfig.objects.create(
            tipo_servicio=tipo_servicio,
            precio_base=100,
            activa=True,
        )

        self.client_user = Usuario.objects.create_user(
            username="cliente.test",
            password="password123",
            rol=self.rol_cliente,
            sucursal=self.sucursal,
        )
        self.cliente = Cliente.objects.create(usuario=self.client_user)
        self.operacion = Operacion.objects.create(
            paciente=self.cliente,
            servicio_config=servicio,
            precio_total=100,
            sesiones_totales=3,
            estado=Operacion.Estado.EN_PROCESO,
        )

        self.admin_user = Usuario.objects.create_user(
            username="admin.test",
            password="password123",
            rol=self.rol_admin,
            sucursal=self.sucursal,
        )

        self.client_http = Client()
        self.client_http.login(username="cliente.test", password="password123")
        self.admin_http = Client()
        self.admin_http.login(username="admin.test", password="password123")
        self.kiosko = TabletKiosko.objects.create(
            codigo="KIOSKO-CENTRO-01",
            nombre="Tablet Centro",
            sucursal=self.sucursal,
            clave="kiosk-pass",
            activo=True,
        )

    def test_client_can_confirm_pending_biometric_appointment_by_tablet(self):
        cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=timezone.now(),
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        )

        response = self.client_http.post(
            f"/api/client/citas/{cita.id}/confirmar-tablet/",
            content_type="application/json",
            **{"REMOTE_ADDR": "10.20.30.40"},
        )

        self.assertEqual(response.status_code, 200)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, CitaMedica.Estado.CONFIRMADA)
        self.assertEqual(cita.metodo_confirmacion, CitaMedica.MetodoConfirmacion.TABLET)
        self.assertFalse(cita.verif_biometria)

        event = EventoConfirmacionCita.objects.get(cita=cita)
        self.assertEqual(event.paciente, self.cliente)
        self.assertEqual(event.metodo, EventoConfirmacionCita.Metodo.TABLET)
        self.assertEqual(event.ip_origen, "10.20.30.40")

    def test_client_tablet_confirmation_requires_same_day(self):
        cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=timezone.now() - timedelta(days=1),
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        )

        response = self.client_http.post(
            f"/api/client/citas/{cita.id}/confirmar-tablet/",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION)
        self.assertFalse(EventoConfirmacionCita.objects.filter(cita=cita).exists())

    def test_admin_biometric_confirmation_creates_audit_event(self):
        HuellaBiometricaCliente.objects.create(
            cliente=self.cliente,
            proveedor=HuellaBiometricaCliente.Proveedor.MOCK_LEGACY,
            template_biometrico="TEMPLATE_OK",
            activo=True,
        )
        cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=timezone.now(),
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        )

        response = self.admin_http.post(
            f"/api/admin/citas/{cita.id}/confirmar-biometria/",
            data=json.dumps({"template": "TEMPLATE_OK", "quality": 80}),
            content_type="application/json",
            **{"REMOTE_ADDR": "192.168.1.9"},
        )

        self.assertEqual(response.status_code, 200)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, CitaMedica.Estado.CONFIRMADA)
        self.assertEqual(cita.metodo_confirmacion, CitaMedica.MetodoConfirmacion.BIOMETRICO)
        self.assertTrue(cita.verif_biometria)

        event = EventoConfirmacionCita.objects.get(cita=cita)
        self.assertEqual(event.metodo, EventoConfirmacionCita.Metodo.BIOMETRICO)
        self.assertEqual(event.ip_origen, "192.168.1.9")

    def test_admin_manual_status_confirmed_creates_manual_event(self):
        cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=timezone.now(),
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        )

        response = self.admin_http.post(
            f"/api/admin/citas/{cita.id}/actualizar/",
            data=json.dumps({"status": CitaMedica.Estado.CONFIRMADA}),
            content_type="application/json",
            **{"REMOTE_ADDR": "172.16.0.10"},
        )

        self.assertEqual(response.status_code, 200)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, CitaMedica.Estado.CONFIRMADA)
        self.assertEqual(cita.metodo_confirmacion, CitaMedica.MetodoConfirmacion.MANUAL)
        self.assertFalse(cita.verif_biometria)

        event = EventoConfirmacionCita.objects.filter(cita=cita).latest("id")
        self.assertEqual(event.metodo, EventoConfirmacionCita.Metodo.MANUAL)
        self.assertEqual(event.ip_origen, "172.16.0.10")

    def test_client_tablet_current_appointment_summary(self):
        cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=timezone.now(),
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        )

        response = self.client_http.get("/api/client/tablet/cita-actual/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNotNone(payload["currentAppointment"])
        self.assertEqual(payload["currentAppointment"]["rawId"], cita.id)
        self.assertGreaterEqual(payload["pendingAppointmentsCount"], 1)
        self.assertGreaterEqual(len(payload["procedureOptions"]), 1)
        self.assertEqual(payload["procedureOptions"][0]["operation"]["rawId"], self.operacion.id)

    def test_client_tablet_can_confirm_current_appointment_without_id(self):
        cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=timezone.now(),
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        )

        response = self.client_http.post(
            "/api/client/tablet/confirmar-cita-actual/",
            content_type="application/json",
            **{"REMOTE_ADDR": "10.10.0.8"},
        )
        self.assertEqual(response.status_code, 200)

        cita.refresh_from_db()
        self.assertEqual(cita.estado, CitaMedica.Estado.CONFIRMADA)
        self.assertEqual(cita.metodo_confirmacion, CitaMedica.MetodoConfirmacion.TABLET)
        self.assertFalse(cita.verif_biometria)

        event = EventoConfirmacionCita.objects.filter(cita=cita).latest("id")
        self.assertEqual(event.metodo, EventoConfirmacionCita.Metodo.TABLET)
        self.assertEqual(event.ip_origen, "10.10.0.8")

    def test_client_tablet_can_confirm_selected_procedure(self):
        tipo_servicio = self.operacion.servicio_config.tipo_servicio
        second_service = ServicioConfig.objects.create(
            tipo_servicio=tipo_servicio,
            precio_base=200,
            activa=True,
        )
        second_operation = Operacion.objects.create(
            paciente=self.cliente,
            servicio_config=second_service,
            precio_total=200,
            sesiones_totales=2,
            estado=Operacion.Estado.EN_PROCESO,
        )
        first_cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=timezone.now(),
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        )
        second_cita = CitaMedica.objects.create(
            operacion=second_operation,
            sucursal=self.sucursal,
            fecha_hora=timezone.now(),
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
        )

        response = self.client_http.post(
            "/api/client/tablet/confirmar-procedimiento/",
            data=json.dumps({"operationId": second_operation.id}),
            content_type="application/json",
            **{"REMOTE_ADDR": "10.10.0.9"},
        )
        self.assertEqual(response.status_code, 200)

        first_cita.refresh_from_db()
        second_cita.refresh_from_db()
        self.assertEqual(first_cita.estado, CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION)
        self.assertEqual(second_cita.estado, CitaMedica.Estado.CONFIRMADA)
        self.assertEqual(second_cita.metodo_confirmacion, CitaMedica.MetodoConfirmacion.TABLET)

        event = EventoConfirmacionCita.objects.filter(cita=second_cita).latest("id")
        self.assertEqual(event.metodo, EventoConfirmacionCita.Metodo.TABLET)
        self.assertEqual(event.ip_origen, "10.10.0.9")

    def test_admin_dashboard_agenda_includes_explicit_verification_fields(self):
        cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=timezone.now(),
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
            metodo_confirmacion=CitaMedica.MetodoConfirmacion.BIOMETRICO,
        )

        response = self.admin_http.get("/api/admin/dashboard/agenda/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        agenda_item = next(item for item in payload["agenda"] if item["id"] == cita.id)
        self.assertEqual(agenda_item["status"], "biometria")
        self.assertEqual(agenda_item["appointmentStatus"], "pendiente_verificacion")
        self.assertEqual(agenda_item["verificationStatus"], "pendiente")
        self.assertEqual(agenda_item["verificationMethod"], "biometria")

    def test_client_reservations_include_explicit_verification_fields(self):
        cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=timezone.now(),
            estado=CitaMedica.Estado.CONFIRMADA,
            metodo_confirmacion=CitaMedica.MetodoConfirmacion.TABLET,
            verif_biometria=False,
        )

        response = self.client_http.get("/api/client/reservas/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        appointment_item = next(item for item in payload["appointments"] if item["rawId"] == cita.id)
        self.assertEqual(appointment_item["verificationStatus"], "verificada")
        self.assertEqual(appointment_item["verificationMethod"], "qr")
        self.assertNotIn("confirmationStatus", appointment_item)
        self.assertNotIn("confirmationLabel", appointment_item)
        self.assertNotIn("biometric", appointment_item)

    def test_client_dashboard_appointment_payload_excludes_legacy_confirmation_fields(self):
        cita = CitaMedica.objects.create(
            operacion=self.operacion,
            sucursal=self.sucursal,
            fecha_hora=timezone.now(),
            estado=CitaMedica.Estado.CONFIRMADA,
            metodo_confirmacion=CitaMedica.MetodoConfirmacion.BIOMETRICO,
            verif_biometria=True,
        )

        response = self.client_http.get("/api/client/dashboard/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        appointment_item = next(item for item in payload["upcomingAppointments"] if item["rawId"] == cita.id)
        self.assertEqual(appointment_item["verificationStatus"], "verificada")
        self.assertEqual(appointment_item["verificationMethod"], "biometria")
        self.assertNotIn("confirmationStatus", appointment_item)
        self.assertNotIn("confirmationLabel", appointment_item)
        self.assertNotIn("biometric", appointment_item)

    def test_tablet_kiosk_login_and_client_reset_flow(self):
        response = self.client_http.post(
            "/api/client/tablet/auth/login/",
            data=json.dumps({"codigo": "KIOSKO-CENTRO-01", "clave": "kiosk-pass"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        response = self.client_http.post(
            "/api/client/tablet/client/login/",
            data=json.dumps({"username": "cliente.test", "password": "password123"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        response = self.client_http.post("/api/client/tablet/client/reset/", content_type="application/json")
        self.assertEqual(response.status_code, 200)
