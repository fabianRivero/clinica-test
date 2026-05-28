"""
Dashboard ViewSet for DRF migration.
Domain 10 of Phase 6 — Dashboard endpoints (final domain).

3 endpoints:
- GET /dashboard/ → main metrics + alerts
- GET /dashboard/payments/ → upcoming payment quotas
- GET /dashboard/agenda/ → monthly agenda/appointments
"""

from datetime import date, timedelta

from django.db.models import Count
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from billing.models import CuotaPlanPago, PagoRealizado
from customers.models import Cliente, Prospecto
from operations.models import CitaMedica, Operacion
from operations.scheduling import mark_expired_programmed_appointments_as_no_show
from staff.models import Especialista

from config.api.permissions import AdminRequired
from config.api_helpers import currency, date_label, full_name, get_user_branch, metric, procedure_name
from config.api.helpers_operations import agenda_status, agenda_appointment_status, agenda_verification_status, agenda_verification_method, quota_programmed_amount


# Backward-compatible aliases — agenda_* have intentionally different output in dashboard context
_agenda_status = agenda_status
_agenda_appointment_status = agenda_appointment_status
_agenda_verification_status = agenda_verification_status
_agenda_verification_method = agenda_verification_method
_quota_programmed_amount = quota_programmed_amount


# ---------------------------------------------------------------------------
# Local dashboard-specific helpers (different output strings than helpers_operations)
# ---------------------------------------------------------------------------

def _agenda_status(cita):
    """Dashboard-specific: returns descriptive status strings."""
    if cita.verif_biometria:
        return "Confirmada biometricamente"
    if cita.estado == CitaMedica.Estado.CONFIRMADA:
        return "Confirmada manualmente"
    if cita.estado == CitaMedica.Estado.PROGRAMADA:
        return "Programada"
    if cita.estado == CitaMedica.Estado.CANCELADA:
        return "Cancelada"
    if cita.estado == CitaMedica.Estado.NO_ASISTIO:
        return "No asistio"
    return "Desconocido"


def _agenda_appointment_status(cita):
    return cita.get_estado_display()


def _agenda_verification_status(cita):
    if cita.verif_biometria:
        return "verified"
    if cita.estado == CitaMedica.Estado.CONFIRMADA:
        return "manual"
    return "pending"


def _agenda_verification_method(cita):
    if cita.metodo_confirmacion == CitaMedica.MetodoConfirmacion.BIOMETRICO:
        return "biometric"
    if cita.metodo_confirmacion == CitaMedica.MetodoConfirmacion.MANUAL:
        return "manual"
    return "pending"


def _dashboard_alerts():
    """Generate dashboard alerts (mirrors api_views.py logic)."""
    alerts = []
    today = timezone.localdate()

    # Alert: appointments today without confirmed biometric
    pending_biometric = CitaMedica.objects.filter(
        estado=CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA,
        fecha_hora__date=today,
    ).count()
    if pending_biometric > 0:
        alerts.append({
            "type": "warning",
            "message": f"{pending_biometric} cita(s) pendiente(s) de confirmacion biometrica hoy.",
        })

    # Alert: expired programmed appointments marked no-show
    expired_no_show = CitaMedica.objects.filter(
        estado=CitaMedica.Estado.NO_ASISTIO,
        fecha_hora__date=today,
    ).count()
    if expired_no_show > 0:
        alerts.append({
            "type": "info",
            "message": f"{expired_no_show} cita(s) marcada(s) como no asistida(s) hoy.",
        })

    # Alert: pending payment verifications
    pending_payments = PagoRealizado.objects.filter(
        estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
    ).count()
    if pending_payments > 5:
        alerts.append({
            "type": "danger",
            "message": f"{pending_payments} pagos pendientes de revision — hayqueue acumulado.",
        })

    return alerts


class DashboardViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for dashboard data.

    Endpoints:
    - GET /dashboard/                  → main metrics + alerts
    - GET /dashboard/payments/        → upcoming payment quotas
    - GET /dashboard/agenda/         → monthly appointments agenda
    """

    permission_classes = [AdminRequired]

    @action(detail=False, methods=["get"], url_path="")
    def main(self, request):
        """
        GET /dashboard/
        Returns basic metrics and alerts for the admin dashboard.
        """
        mark_expired_programmed_appointments_as_no_show()
        today = timezone.localdate()
        branch = get_user_branch(request)

        operations_qs = Operacion.objects.filter(estado=Operacion.Estado.EN_PROCESO)
        prospectos_qs = Prospecto.objects.all()
        payments_qs = PagoRealizado.objects.all()
        operations_started_qs = Operacion.objects.filter(
            created_at__year=today.year, created_at__month=today.month
        )

        if branch:
            operations_qs = operations_qs.filter(paciente__sucursal_registro=branch).distinct()
            prospectos_qs = prospectos_qs.filter(sucursal_registro=branch)
            payments_qs = payments_qs.filter(
                cuota__operacion__paciente__sucursal_registro=branch
            ).distinct()
            operations_started_qs = operations_started_qs.filter(
                paciente__sucursal_registro=branch
            ).distinct()

        pending_payments_count = payments_qs.filter(
            estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE
        ).count()
        payments_today = payments_qs.filter(created_at__date=today).count()
        operations_started_this_month = operations_started_qs.count()

        converted_prospects = prospectos_qs.filter(estado=Prospecto.Estado.CONVERTIDO).count()
        total_prospects = prospectos_qs.count()
        prospect_delta = (
            f"{round((converted_prospects / total_prospects) * 100)}% convertidos"
            if total_prospects
            else "Sin conversiones aun"
        )

        appointments_today_qs = CitaMedica.objects.filter(fecha_hora__date=today)
        pending_biometric_qs = CitaMedica.objects.filter(
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA
        )
        if branch:
            appointments_today_qs = appointments_today_qs.filter(sucursal=branch)
            pending_biometric_qs = pending_biometric_qs.filter(sucursal=branch)

        appointments_today = appointments_today_qs.count()
        pending_biometric = pending_biometric_qs.count()

        return Response({
            "metrics": [
                metric(
                    "payments",
                    "Pagos por verificar",
                    pending_payments_count,
                    f"{payments_today} subidos hoy",
                    "warning",
                ),
                metric(
                    "operations",
                    "Tratamientos activos",
                    operations_qs.count(),
                    f"{operations_started_this_month} iniciadas este mes",
                    "primary",
                ),
                metric(
                    "prospects",
                    "Prospectos en seguimiento",
                    prospectos_qs.filter(estado=Prospecto.Estado.PASAJERO).count(),
                    prospect_delta,
                    "success",
                ),
                metric(
                    "appointments",
                    "Citas del dia",
                    appointments_today,
                    f"{pending_biometric} pendientes de biometria",
                    "danger" if pending_biometric else "success",
                ),
            ],
            "alerts": _dashboard_alerts(),
        })

    @action(detail=False, methods=["get"], url_path="payments")
    def payments(self, request):
        """
        GET /dashboard/payments/?month=X&year=Y
        Returns upcoming payment quotas for a given month/year.
        """
        today = timezone.localdate()
        try:
            month = int(request.query_params.get("month", today.month))
            year = int(request.query_params.get("year", today.year))
        except (TypeError, ValueError):
            month, year = today.month, today.year

        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)

        range_start = start
        if month == today.month and year == today.year:
            range_start = today

        branch = get_user_branch(request)

        upcoming_quotas = (
            CuotaPlanPago.objects.select_related(
                "operacion__paciente__usuario",
                "operacion__servicio_config__proc_estetico",
            )
            .filter(
                fecha_vencimiento__range=(range_start, end),
                estado__in=[CuotaPlanPago.Estado.PENDIENTE, CuotaPlanPago.Estado.VENCIDA],
            )
            .order_by("fecha_vencimiento")
        )
        if branch:
            upcoming_quotas = upcoming_quotas.filter(
                operacion__citas_medicas__sucursal=branch
            ).distinct()

        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        upcoming_payments = []
        for q in upcoming_quotas:
            upcoming_payments.append({
                "id": q.pk,
                "dueDate": q.fecha_vencimiento.isoformat(),
                "dueDateLabel": date_label(q.fecha_vencimiento),
                "amount": currency(_quota_programmed_amount(q)),
                "client": full_name(q.operacion.paciente.usuario),
                "clientId": q.operacion.paciente_id,
                "operation": procedure_name(q.operacion),
                "operationId": q.operacion_id,
                "quotaNumber": q.nro_cuota,
                "isToday": q.fecha_vencimiento == today,
                "isThisWeek": start_of_week <= q.fecha_vencimiento <= end_of_week,
            })

        return Response({
            "month": month,
            "year": year,
            "payments": upcoming_payments,
        })

    @action(detail=False, methods=["get"], url_path="agenda")
    def agenda(self, request):
        """
        GET /dashboard/agenda/?month=X&year=Y
        Returns monthly appointment agenda.
        """
        today = timezone.localdate()
        try:
            month = int(request.query_params.get("month", today.month))
            year = int(request.query_params.get("year", today.year))
        except (TypeError, ValueError):
            month, year = today.month, today.year

        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)

        range_start = start
        if month == today.month and year == today.year:
            range_start = today

        branch = get_user_branch(request)

        agenda_qs = (
            CitaMedica.objects.select_related(
                "operacion__paciente__usuario",
                "operacion__servicio_config__proc_estetico",
            )
            .filter(
                fecha_hora__date__range=(range_start, end),
                estado=CitaMedica.Estado.PROGRAMADA,
            )
            .order_by("fecha_hora")
        )
        if branch:
            agenda_qs = agenda_qs.filter(sucursal=branch)

        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        agenda_data = []
        for cita in agenda_qs:
            cita_local = timezone.localtime(cita.fecha_hora)
            agenda_data.append({
                "id": cita.pk,
                "time": cita_local.strftime("%H:%M"),
                "dateLabel": cita_local.strftime("%d/%m/%Y"),
                "patient": full_name(cita.operacion.paciente.usuario),
                "clientId": cita.operacion.paciente_id,
                "procedure": procedure_name(cita.operacion),
                "operationId": cita.operacion_id,
                "specialist": "Asignado",
                "status": _agenda_status(cita),
                "appointmentStatus": _agenda_appointment_status(cita),
                "verificationStatus": _agenda_verification_status(cita),
                "verificationMethod": _agenda_verification_method(cita),
                "isToday": cita.fecha_hora.date() == today,
                "isThisWeek": start_of_week <= cita.fecha_hora.date() <= end_of_week,
            })

        return Response({
            "month": month,
            "year": year,
            "agenda": agenda_data,
        })
