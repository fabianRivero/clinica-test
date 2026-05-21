from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago
from catalogs.models import ServicioConfig, TipoServicio
from customers.models import Cliente
from operations.models import CitaMedica, Operacion
from operations.scheduling import mark_expired_programmed_appointments_as_no_show
from notifications.models import Notification
from staff.models import Especialista


class AppointmentNoShowSyncTests(TestCase):
    def setUp(self):
        client_role = Rol.objects.create(rol="CLIENTE")
        specialist_role = Rol.objects.create(rol="TRABAJADOR")
        client_user = Usuario.objects.create_user(
            username="cliente",
            password="test",
            primer_nombre="Cliente",
            apellido_paterno="Prueba",
            rol=client_role,
        )
        specialist_user = Usuario.objects.create_user(
            username="especialista",
            password="test",
            primer_nombre="Especialista",
            apellido_paterno="Prueba",
            rol=specialist_role,
        )
        self.cliente = Cliente.objects.create(usuario=client_user)
        self.especialista = Especialista.objects.create(usuario=specialist_user)
        tipo_servicio = TipoServicio.objects.create(tipo="Consulta")
        servicio = ServicioConfig.objects.create(tipo_servicio=tipo_servicio, precio_base=100)
        self.operacion = Operacion.objects.create(
            paciente=self.cliente,
            servicio_config=servicio,
            precio_total=100,
            sesiones_totales=3,
            estado=Operacion.Estado.EN_PROCESO,
        )

    def test_marks_programmed_appointments_as_no_show_after_one_day(self):
        reference_time = timezone.now()
        stale_appointment = CitaMedica.objects.create(
            operacion=self.operacion,
            medico=self.especialista,
            fecha_hora=reference_time - timedelta(days=1, minutes=1),
            estado=CitaMedica.Estado.PROGRAMADA,
        )
        fresh_appointment = CitaMedica.objects.create(
            operacion=self.operacion,
            medico=self.especialista,
            fecha_hora=reference_time - timedelta(hours=23),
            estado=CitaMedica.Estado.PROGRAMADA,
        )

        summary = mark_expired_programmed_appointments_as_no_show(reference_time)

        stale_appointment.refresh_from_db()
        fresh_appointment.refresh_from_db()
        self.assertEqual(summary["no_show"], 1)
        self.assertEqual(stale_appointment.estado, CitaMedica.Estado.NO_ASISTIO)
        self.assertEqual(fresh_appointment.estado, CitaMedica.Estado.PROGRAMADA)

    def test_keeps_pending_biometric_appointments(self):
        reference_time = timezone.now()
        appointment = CitaMedica.objects.create(
            operacion=self.operacion,
            medico=self.especialista,
            fecha_hora=reference_time - timedelta(days=2),
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA,
        )

        summary = mark_expired_programmed_appointments_as_no_show(reference_time)

        appointment.refresh_from_db()
        self.assertEqual(summary["no_show"], 0)
        self.assertEqual(appointment.estado, CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA)

    def test_creates_client_notification_when_appointment_becomes_no_show(self):
        reference_time = timezone.now()
        stale_appointment = CitaMedica.objects.create(
            operacion=self.operacion,
            medico=self.especialista,
            fecha_hora=reference_time - timedelta(days=2),
            estado=CitaMedica.Estado.PROGRAMADA,
        )

        mark_expired_programmed_appointments_as_no_show(reference_time)

        notification = Notification.objects.filter(
            recipient=self.cliente.usuario,
            source_event="appointment_marked_no_show",
            source_entity_id=stale_appointment.pk,
        ).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.type, "CLIENT_APPOINTMENT_CANCELLED")

    def test_client_becomes_inactive_when_sessions_and_payments_are_complete(self):
        self.operacion.sesiones_totales = 1
        self.operacion.save(update_fields=["sesiones_totales", "updated_at"])
        CuotaPlanPago.objects.create(
            operacion=self.operacion,
            nro_cuota=1,
            fecha_vencimiento=timezone.localdate(),
            estado=CuotaPlanPago.Estado.PAGADO,
        )

        CitaMedica.objects.create(
            operacion=self.operacion,
            medico=self.especialista,
            fecha_hora=timezone.now(),
            estado=CitaMedica.Estado.CONFIRMADA,
            verif_biometria=True,
        )

        self.operacion.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertEqual(self.operacion.estado, Operacion.Estado.FINALIZADA)
        self.assertEqual(self.cliente.estado_cliente, Cliente.Estado.INACTIVO)
