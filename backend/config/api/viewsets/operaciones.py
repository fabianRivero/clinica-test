"""
Operations, Appointments, and Offline Confirmation ViewSets for DRF migration.
Domain 8 of Phase 6 — 12 endpoints total.

Three ViewSets:
- OperacionesViewSet: operations list + detail + updates
- CitasViewSet: appointment actions (cancel, biometric, status, reschedule)
- OfflineConfirmationViewSet: offline confirmation conflicts + resolve + metrics
"""


from datetime import timedelta as datetime_timedelta
from decimal import Decimal
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from django.conf import settings
from biometric.serializers import verification_suspended_payload

from billing.models import CuotaPlanPago, PagoRealizado
from operations.models import CitaMedica, EventoConfirmacionCita, Operacion
from operations.scheduling import mark_expired_programmed_appointments_as_no_show
from config.api.permissions import AdminRequired
from config.api_helpers import (
    currency,
    date_label,
    datetime_label,
    full_name,
    get_user_branch,
    metric,
    procedure_name,
    split_amount,
)
from config.api.helpers_operations import (
    operation_branch,
    operation_branch_id,
    operation_card,
    operation_next_appointment,
    prospect_appointment_operation_card,
    quota_status,
)
from config.api.serializers.operaciones import (
    OperationUpdateDetailsSerializer,
    OperationUpdatePricePlanSerializer,
    AppointmentStatusUpdateSerializer,
    AppointmentRescheduleSerializer,
    AppointmentBiometricConfirmSerializer,
    OfflineConflictResolveSerializer,
)
from config.client_api_views import _operation_item as _client_operation_item
from notifications.models import Notification
from notifications.services import create_notification


# =============================================================================
# Backward-compatible aliases — helpers moved to config/api/helpers_operations.py
# =============================================================================
_operation_branch = operation_branch
_operation_branch_id = operation_branch_id
_operation_next_appointment = operation_next_appointment
_operation_card = operation_card
_quota_status = quota_status
_prospect_appointment_operation_card = prospect_appointment_operation_card


def _client_appointment_item(cita):
    from config.client_api_views import _appointment_item as _appointment_item_client
    return _appointment_item_client(cita)


# =============================================================================
# OperacionesViewSet
# =============================================================================

class OperacionesViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for operation management.

    Endpoints:
    - GET  /operaciones/                              → list operations with metrics
    - GET  /operaciones/<int:operacion_id>/          → operation detail
    - POST /operaciones/<int:operacion_id>/actualizar-detalles/  → update details
    - POST /operaciones/<int:operacion_id>/actualizar-precio/    → update price/plan
    """

    permission_classes = [AdminRequired]

    def list(self, request):
        """
        GET /operaciones/
        List operations with metrics (branch-aware).
        """
        mark_expired_programmed_appointments_as_no_show()
        branch = get_user_branch(request)
        operaciones_qs = (
            Operacion.objects.select_related(
                "paciente__usuario",
                "servicio_config__tipo_servicio",
                "servicio_config__proc_estetico",
            )
            .prefetch_related(
                Prefetch(
                    "citas_medicas",
                    queryset=CitaMedica.objects.select_related().order_by("fecha_hora"),
                ),
                Prefetch(
                    "cuotas_plan_pagos",
                    queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
                ),
            ).order_by("-created_at")
        )
        if branch:
            operaciones_qs = operaciones_qs.filter(paciente__usuario__sucursal_id=branch)

        from customers.models import Prospecto
        prospect_appointments_qs = (
            Prospecto.objects.filter(
                citas_medicas__sucursal=branch,
            ).exclude(
                estado=Prospecto.Estado.CONVERTIDO
            ).distinct()
        )
        # Actually, let's just use CitaProspecto directly
        from operations.models import CitaProspecto
        prospect_appointments_qs = CitaProspecto.objects.select_related("prospecto", "sucursal").order_by("-fecha_hora")
        if branch:
            prospect_appointments_qs = prospect_appointments_qs.filter(sucursal=branch)

        blocked_reservations = sum(
            1
            for operacion in operaciones_qs
            if operacion.estado == Operacion.Estado.EN_PROCESO and not operacion.puede_reservar
        )

        data = {
            "metrics": [
                metric(
                    "operations-active",
                    "Operaciones en proceso",
                    operaciones_qs.filter(estado=Operacion.Estado.EN_PROCESO).count(),
                    "Tratamientos actualmente vigentes",
                    "primary",
                ),
                metric(
                    "operations-finished",
                    "Operaciones finalizadas",
                    operaciones_qs.filter(estado=Operacion.Estado.FINALIZADA).count(),
                    "Historial clinico",
                    "success",
                ),
                metric(
                    "operations-blocked",
                    "Reservas bloqueadas",
                    blocked_reservations,
                    "Sin sesiones libres",
                    "danger",
                ),
            ],
            "operations": [
                *[_operation_card(operacion) for operacion in operaciones_qs],
                *[_prospect_appointment_operation_card(cita) for cita in prospect_appointments_qs[:50]],
            ],
        }
        return Response(data)

    def retrieve(self, request, pk=None):
        """
        GET /operaciones/<int:operacion_id>/
        Get operation detail.
        """
        mark_expired_programmed_appointments_as_no_show()
        operacion = (
            Operacion.objects.select_related(
                "paciente__usuario",
                "servicio_config__tipo_servicio",
                "servicio_config__proc_estetico__tipo_p_estetico",
                "ficha_clinica",
            )
            .prefetch_related(
                Prefetch(
                    "citas_medicas",
                    queryset=CitaMedica.objects.select_related().order_by("fecha_hora"),
                ),
                Prefetch(
                    "cuotas_plan_pagos",
                    queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
                ),
            )
            .filter(pk=pk)
            .first()
        )
        if not operacion:
            return Response({"detail": "No encontramos la operacion solicitada."}, status=404)

        return Response({"operation": _client_operation_item(operacion)})

    @action(detail=True, methods=["post"], url_path="actualizar-detalles")
    def actualizar_detalles(self, request, pk=None):
        """
        POST /operaciones/<int:operacion_id>/actualizar-detalles/
        Update operation details (sessions, notes, recommendations).
        """
        serializer = OperationUpdateDetailsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Corrige los datos de la operacion.", "errors": serializer.errors}, status=400)

        operacion = Operacion.objects.select_for_update(of=("self",)).filter(pk=pk).first()
        if not operacion:
            return Response({"detail": "No encontramos la operacion solicitada."}, status=404)

        data = serializer.validated_data
        sesiones_totales = data.get("sessionsTotal")
        if sesiones_totales is not None:
            consumed = (
                operacion.sesiones_confirmadas
                + operacion.sesiones_pendientes_confirmacion
                + operacion.reservas_activas
            )
            if sesiones_totales < consumed:
                return Response(
                    {
                        "detail": f"No puedes bajar de {consumed} sesion(es), porque ya estan confirmadas, reservadas o pendientes de biometria."
                    },
                    status=400,
                )
            operacion.sesiones_totales = sesiones_totales

        if "details" in data:
            operacion.detalles_op = data["details"] or ""
        if "recommendations" in data:
            operacion.recomendaciones = data["recommendations"] or ""

        operacion.save(update_fields=["detalles_op", "recomendaciones", "sesiones_totales", "updated_at"])
        operacion.paciente.actualizar_estado_automaticamente()

        # Refetch with relations
        operacion = (
            Operacion.objects.select_related(
                "paciente__usuario",
                "servicio_config__tipo_servicio",
                "servicio_config__proc_estetico__tipo_p_estetico",
                "ficha_clinica",
            )
            .prefetch_related(
                Prefetch(
                    "citas_medicas",
                    queryset=CitaMedica.objects.select_related().order_by("fecha_hora"),
                ),
                Prefetch(
                    "cuotas_plan_pagos",
                    queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
                ),
            )
            .get(pk=pk)
        )
        return Response({
            "detail": "La operacion fue actualizada correctamente.",
            "operation": _client_operation_item(operacion),
        })

    @action(detail=True, methods=["post"], url_path="actualizar-precio")
    def actualizar_precio(self, request, pk=None):
        """
        POST /operaciones/<int:operacion_id>/actualizar-precio/
        Update operation price and payment plan (redistribute quotas).
        """
        serializer = OperationUpdatePricePlanSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Corrige los datos del plan de pagos.", "errors": serializer.errors}, status=400)

        operacion = (
            Operacion.objects.select_for_update(of=("self",))
            .prefetch_related("cuotas_plan_pagos__pagos_realizados")
            .filter(pk=pk)
            .first()
        )
        if not operacion:
            return Response({"detail": "No encontramos la operacion solicitada."}, status=404)

        data = serializer.validated_data
        new_price = data["priceTotal"]
        new_quota_count = data["quotaCount"]

        cuotas = list(operacion.cuotas_plan_pagos.all())
        paid_total = sum(
            pago.monto_pagado
            for cuota in cuotas
            for pago in cuota.pagos_realizados.all()
            if pago.estado_verificacion == PagoRealizado.EstadoVerificacion.APROBADO
        )
        paid_quotas = [cuota for cuota in cuotas if cuota.estado == CuotaPlanPago.Estado.PAGADO]
        unpaid_quotas = [cuota for cuota in cuotas if cuota.estado != CuotaPlanPago.Estado.PAGADO]
        locked_unpaid = [
            cuota for cuota in unpaid_quotas if cuota.pagos_realizados.exists()
        ]

        errors = {}
        if new_price < paid_total:
            errors["priceTotal"] = f"El nuevo precio no puede ser menor a lo ya pagado: {currency(paid_total)}."
        if new_quota_count < len(paid_quotas):
            errors["quotaCount"] = f"El numero de cuotas no puede ser menor a las {len(paid_quotas)} cuota(s) ya pagadas."
        if locked_unpaid:
            errors["quotaCount"] = "Hay cuotas no pagadas con comprobantes registrados. Resuelve o retira esos comprobantes antes."
        if errors:
            return Response({"detail": "No se pudo redistribuir el plan de pagos.", "errors": errors}, status=400)

        remaining_amount = (new_price - paid_total).quantize(Decimal("0.01"))
        remaining_quota_count = new_quota_count - len(paid_quotas)
        if remaining_quota_count == 0 and remaining_amount > 0:
            return Response(
                {
                    "detail": "No se pudo redistribuir el plan de pagos.",
                    "errors": {"quotaCount": "Necesitas al menos una cuota pendiente para el saldo restante."},
                },
                status=400,
            )

        existing_due_dates = [cuota.fecha_vencimiento for cuota in sorted(unpaid_quotas, key=lambda item: item.nro_cuota)]
        latest_due_date = max([cuota.fecha_vencimiento for cuota in cuotas], default=timezone.localdate())
        while len(existing_due_dates) < remaining_quota_count:
            latest_due_date = latest_due_date + datetime_timedelta(days=30)
            existing_due_dates.append(latest_due_date)

        for cuota in unpaid_quotas:
            cuota.delete()

        next_quota_number = max([cuota.nro_cuota for cuota in paid_quotas], default=0) + 1
        for index, amount in enumerate(split_amount(remaining_amount, remaining_quota_count)):
            CuotaPlanPago.objects.create(
                operacion=operacion,
                nro_cuota=next_quota_number + index,
                fecha_vencimiento=existing_due_dates[index],
                monto_programado=amount,
            )

        operacion.precio_total = new_price
        operacion.cuotas_totales = new_quota_count
        operacion.save(update_fields=["precio_total", "cuotas_totales", "updated_at"])
        operacion.paciente.actualizar_estado_automaticamente()

        # Refetch
        operacion = (
            Operacion.objects.select_related(
                "paciente__usuario",
                "servicio_config__tipo_servicio",
                "servicio_config__proc_estetico__tipo_p_estetico",
                "ficha_clinica",
            )
            .prefetch_related(
                Prefetch(
                    "citas_medicas",
                    queryset=CitaMedica.objects.select_related().order_by("fecha_hora"),
                ),
                Prefetch(
                    "cuotas_plan_pagos",
                    queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
                ),
            )
            .get(pk=pk)
        )
        return Response({
            "detail": "El precio y las cuotas fueron redistribuidos correctamente.",
            "operation": _client_operation_item(operacion),
        })


# =============================================================================
# CitasViewSet
# =============================================================================

class CitasViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for appointment management actions.

    Endpoints:
    - POST /citas/<int:appointment_id>/cancelar/                  → cancel appointment
    - POST /citas/<int:appointment_id>/pendiente-biometria/     → mark pending biometric
    - POST /citas/<int:appointment_id>/actualizar/            → update status
    - POST /citas/<int:appointment_id>/confirmar-biometria/    → confirm with biometric
    - POST /citas/<int:appointment_id>/reprogramar/           → reschedule
    """

    permission_classes = [AdminRequired]

    def _get_appointment(self, appointment_id):
        return (
            CitaMedica.objects.select_related(
                "operacion__paciente__usuario",
                "operacion__servicio_config__tipo_servicio",
                "operacion__servicio_config__proc_estetico",
            )
            .filter(pk=appointment_id)
            .first()
        )

    @action(detail=True, methods=["post"], url_path="cancelar")
    def cancelar(self, request, pk=None):
        """
        POST /citas/<int:appointment_id>/cancelar/
        Cancel a scheduled appointment.
        """
        appointment = self._get_appointment(pk)
        if not appointment:
            return Response({"detail": "No encontramos la cita solicitada."}, status=404)
        if appointment.estado != CitaMedica.Estado.PROGRAMADA:
            return Response({"detail": "Solo se pueden cancelar citas que todavia esten programadas."}, status=400)

        appointment.estado = CitaMedica.Estado.CANCELADA
        appointment.verif_biometria = False
        appointment.save()

        client_user = appointment.operacion.paciente.usuario
        procedimiento = procedure_name(appointment.operacion)
        fecha_cita = appointment.fecha_hora.strftime('%d/%m/%Y')
        hora_cita = appointment.fecha_hora.strftime('%H:%M')
        create_notification(
            recipient=client_user,
            branch=appointment.sucursal,
            type=Notification.Type.CLIENT_APPOINTMENT_CANCELLED,
            title="Cita cancelada",
            message=f"Tu cita de la fecha {fecha_cita}, a la hora {hora_cita}, para el procedimiento {procedimiento} fue cancelada. Puedes verlo en tu registro de citas.",
            action_url="/cliente/reservas",
            source_event="appointment.cancelled",
            source_entity_type="appointment",
            source_entity_id=appointment.id,
            created_by_type="admin",
            created_by_id=request.user.id,
        )

        return Response({
            "detail": "La cita programada fue cancelada correctamente.",
            "appointment": {
                "id": f"CIT-{appointment.pk:04d}",
                "rawId": appointment.pk,
                "dateTime": datetime_label(appointment.fecha_hora),
                "operation": procedure_name(appointment.operacion),
                "specialist": "Sin asignar",
                "status": appointment.get_estado_display(),
            },
        })

    @action(detail=True, methods=["post"], url_path="pendiente-biometria")
    def pendiente_biometria(self, request, pk=None):
        """
        POST /citas/<int:appointment_id>/pendiente-biometria/
        Mark appointment as performed, pending biometric confirmation.
        """
        appointment = self._get_appointment(pk)
        if not appointment:
            return Response({"detail": "No encontramos la cita solicitada."}, status=404)
        if appointment.estado != CitaMedica.Estado.PROGRAMADA:
            return Response({"detail": "Solo se pueden cerrar citas que aun esten programadas."}, status=400)

        appointment.estado = CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION
        appointment.verif_biometria = False
        appointment.detalles_cita = appointment.detalles_cita or "Cita marcada como realizada desde administracion."
        appointment.save()

        return Response({
            "detail": "La cita quedo realizada y pendiente de confirmación.",
            "appointment": _client_appointment_item(appointment),
            "operation": _client_operation_item(appointment.operacion),
        })

    @action(detail=True, methods=["post"], url_path="actualizar")
    def actualizar_estado(self, request, pk=None):
        """
        POST /citas/<int:appointment_id>/actualizar/
        Update appointment status.
        """
        appointment = CitaMedica.objects.filter(pk=pk).first()
        if not appointment:
            return Response({"detail": "No encontramos la cita solicitada."}, status=404)

        serializer = AppointmentStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        new_status = serializer.validated_data["status"]
        previous_status = appointment.estado
        appointment.estado = new_status

        if appointment.estado == CitaMedica.Estado.PROGRAMADA:
            appointment.verif_biometria = False
            appointment.metodo_confirmacion = ""
        elif appointment.estado == CitaMedica.Estado.CONFIRMADA:
            appointment.verif_biometria = False
            appointment.metodo_confirmacion = CitaMedica.MetodoConfirmacion.MANUAL

        appointment.save(update_fields=["estado", "verif_biometria", "metodo_confirmacion", "updated_at"])

        if (
            previous_status != CitaMedica.Estado.CONFIRMADA
            and appointment.estado == CitaMedica.Estado.CONFIRMADA
            and appointment.metodo_confirmacion == CitaMedica.MetodoConfirmacion.MANUAL
        ):
            EventoConfirmacionCita.objects.create(
                cita=appointment,
                paciente=appointment.operacion.paciente,
                sucursal=appointment.sucursal,
                metodo=EventoConfirmacionCita.Metodo.MANUAL,
                confirmado_en=timezone.now(),
                ip_origen=_request_ip(request),
            )

        return Response({
            "detail": f"El estado de la cita fue actualizado a {appointment.get_estado_display()}.",
            "appointment_id": appointment.id,
            "new_status": appointment.estado,
        })

    @action(detail=True, methods=["post"], url_path="confirmar-biometria")
    def confirmar_biometria(self, request, pk=None):
        """
        POST /citas/<int:appointment_id>/confirmar-biometria/
        Confirm appointment using biometric verification.
        """
        if settings.BIOMETRIC_SUSPENDED:
            return Response(verification_suspended_payload(), status=503)

        appointment = self._get_appointment(pk)
        if not appointment:
            return Response({"detail": "No encontramos la cita solicitada."}, status=404)
        if appointment.estado != CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
            return Response({"detail": "Solo se pueden confirmar citas pendientes de verificacion."}, status=400)

        serializer = AppointmentBiometricConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        data = serializer.validated_data
        template = data.get("template") or ""
        quality = int(data.get("quality") or 0)
        device_serial = data.get("deviceSerial") or ""

        if quality < 60:
            return Response({"detail": "La calidad debe ser al menos 60."}, status=400)

        appointment.estado = CitaMedica.Estado.CONFIRMADA
        appointment.verif_biometria = True
        appointment.metodo_confirmacion = CitaMedica.MetodoConfirmacion.BIOMETRICO
        appointment.calidad_captura = quality
        appointment.save(update_fields=[
            "estado", "verif_biometria", "metodo_confirmacion",
            "calidad_captura", "updated_at",
        ])

        EventoConfirmacionCita.objects.create(
            cita=appointment,
            paciente=appointment.operacion.paciente,
            sucursal=appointment.sucursal,
            metodo=EventoConfirmacionCita.Metodo.BIOMETRICO,
            device_id=device_serial,
            confirmed_en=timezone.now(),
            ip_origen=_request_ip(request),
        )

        appointment.operacion.paciente.actualizar_estado_automaticamente()

        return Response({
            "detail": "La cita fue confirmada correctamente.",
            "appointment": _client_appointment_item(appointment),
            "operation": _client_operation_item(appointment.operacion),
        })

    @action(detail=True, methods=["post"], url_path="cancelar-verificacion")
    def cancelar_verificacion(self, request, pk=None):
        """
        POST /citas/<int:appointment_id>/cancelar-verificacion/
        Revert REALIZADA_PENDIENTE_VERIFICACION -> PROGRAMADA.
        """
        appointment = self._get_appointment(pk)
        if not appointment:
            return Response({"detail": "No encontramos la cita solicitada."}, status=404)
        if appointment.estado != CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
            return Response({"detail": "Solo se puede cancelar la verificacion de citas pendientes."}, status=400)

        appointment.estado = CitaMedica.Estado.PROGRAMADA
        appointment.verif_biometria = False
        appointment.save(update_fields=["estado", "verif_biometria", "updated_at"])

        return Response({
            "detail": "La verificacion fue cancelada. La cita volvio a estado Programada.",
            "appointment": _client_appointment_item(appointment),
        })

    @action(detail=True, methods=["post"], url_path="reprogramar")
    def reprogramar(self, request, pk=None):
        """
        POST /citas/<int:appointment_id>/reprogramar/
        Reschedule an appointment to a new date/time.
        """
        appointment = (
            CitaMedica.objects.select_related("operacion__paciente", "sucursal")
            .filter(pk=pk)
            .first()
        )
        if not appointment:
            return Response({"detail": "No encontramos la cita solicitada."}, status=404)

        if appointment.estado not in {CitaMedica.Estado.PROGRAMADA, CitaMedica.Estado.NO_ASISTIO}:
            return Response({"detail": "Solo se pueden reprogramar citas programadas o no asistidas."}, status=400)

        serializer = AppointmentRescheduleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        date_time_str = serializer.validated_data["dateTime"]
        new_date_time = parse_datetime(date_time_str)
        if timezone.is_naive(new_date_time):
            new_date_time = timezone.make_aware(new_date_time)
        if not new_date_time:
            return Response({"detail": "Formato de fecha u hora inválido."}, status=400)
        if new_date_time <= timezone.now():
            return Response({"detail": "La nueva fecha y hora debe ser futura."}, status=400)

        appointment.fecha_hora = new_date_time
        appointment.estado = CitaMedica.Estado.PROGRAMADA
        appointment.verif_biometria = False
        appointment.metodo_confirmacion = ""
        appointment.detalles_cita = "Reserva reprogramada desde administracion."
        appointment.save(update_fields=[
            "fecha_hora", "estado", "verif_biometria",
            "metodo_confirmacion", "detalles_cita", "updated_at",
        ])

        client_user = appointment.operacion.paciente.usuario
        create_notification(
            recipient=client_user,
            branch=appointment.sucursal,
            type=Notification.Type.CLIENT_APPOINTMENT_RESCHEDULED,
            title="Cita reprogramada",
            message=f"Tu cita fue reprogramada para {datetime_label(appointment.fecha_hora)}.",
            action_url="/cliente/reservas",
            source_event="appointment.rescheduled",
            source_entity_type="appointment",
            source_entity_id=appointment.id,
            created_by_type="admin",
            created_by_id=request.user.id,
        )

        return Response({
            "detail": "La reserva fue reprogramada correctamente.",
            "appointment": _client_appointment_item(appointment),
        })


# =============================================================================
# OfflineConfirmationViewSet
# =============================================================================

class OfflineConfirmationViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for offline confirmation conflict resolution.

    Endpoints:
    - GET  /citas/offline/conflictos/                              → list conflicts
    - POST /citas/offline/conflictos/<slug:event_id>/resolver/  → resolve conflict
    - GET  /citas/offline/metricas/                              → offline metrics
    """

    permission_classes = [AdminRequired]

    @action(detail=False, methods=["get"], url_path="conflictos")
    def conflictos(self, request):
        """
        GET /citas/offline/conflictos/?branchId=X
        List offline confirmation conflicts.
        """
        branch_id = request.query_params.get("branchId")
        qs = EventoConfirmacionCita.objects.select_related("cita", "paciente", "sucursal").filter(
            origin_mode=EventoConfirmacionCita.ModoOrigen.OFFLINE,
            sync_status=EventoConfirmacionCita.EstadoSync.CONFLICT,
        )
        if branch_id:
            try:
                qs = qs.filter(sucursal_id=int(branch_id))
            except ValueError:
                return Response({"detail": "branchId inválido."}, status=400)

        items = []
        for event in qs.order_by("-confirmado_en")[:200]:
            items.append({
                "eventId": event.event_id,
                "appointmentId": event.cita_id,
                "branchId": event.sucursal_id,
                "branch": event.sucursal.nombre if event.sucursal_id else "",
                "clientId": event.paciente_id,
                "clientName": event.paciente.nombre_completo,
                "deviceId": event.device_id,
                "recordedAtDevice": event.recorded_at_device.isoformat() if event.recorded_at_device else None,
                "confirmedAtServer": event.confirmed_at_server.isoformat() if event.confirmed_at_server else None,
                "conflictReason": event.conflict_reason,
                "syncStatus": event.sync_status,
            })
        return Response({"items": items})

    @action(detail=False, methods=["post"], url_path="conflictos/(?P<event_id>[^/]+)/resolver")
    def resolver_conflicto(self, request, event_id=None):
        """
        POST /citas/offline/conflictos/<slug:event_id>/resolver/
        Resolve an offline confirmation conflict.
        """
        serializer = OfflineConflictResolveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        data = serializer.validated_data
        resolution = data["resolution"]
        reason = data["reason"]

        event = (
            EventoConfirmacionCita.objects.select_for_update(of=("self",))
            .select_related("cita")
            .filter(event_id=event_id)
            .first()
        )
        if not event:
            return Response({"detail": "No encontramos el evento solicitado."}, status=404)
        if event.sync_status != EventoConfirmacionCita.EstadoSync.CONFLICT:
            return Response({"detail": "El evento no está en estado de conflicto."}, status=400)

        if resolution == "ACCEPT":
            event.sync_status = EventoConfirmacionCita.EstadoSync.ACCEPTED
            cita = event.cita
            if cita.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
                cita.estado = CitaMedica.Estado.CONFIRMADA
                cita.metodo_confirmacion = CitaMedica.MetodoConfirmacion.MANUAL
                cita.verif_biometria = False
                cita.save(update_fields=["estado", "metodo_confirmacion", "verif_biometria", "updated_at"])
        else:
            event.sync_status = EventoConfirmacionCita.EstadoSync.REJECTED

        event.conflict_reason = f"RESOLVED:{resolution}:{reason}"
        event.confirmed_at_server = timezone.now()
        event.save(update_fields=["sync_status", "conflict_reason", "confirmed_at_server", "updated_at"])

        return Response({"detail": "Conflicto resuelto.", "eventId": event.event_id, "syncStatus": event.sync_status})

    @action(detail=False, methods=["get"], url_path="metricas")
    def metricas(self, request):
        """
        GET /citas/offline/metricas/?branchId=X&days=7
        Get offline confirmation metrics.
        """
        branch_id = request.query_params.get("branchId")
        days_str = request.query_params.get("days")
        try:
            days_int = int(days_str) if days_str else 7
        except ValueError:
            return Response({"detail": "days inválido."}, status=400)

        since = timezone.now() - datetime_timedelta(days=days_int)
        qs = EventoConfirmacionCita.objects.filter(confirmado_en__gte=since)
        if branch_id:
            try:
                qs = qs.filter(sucursal_id=int(branch_id))
            except ValueError:
                return Response({"detail": "branchId inválido."}, status=400)

        total = qs.count()
        conflicts = qs.filter(sync_status=EventoConfirmacionCita.EstadoSync.CONFLICT).count()
        accepted = qs.filter(sync_status=EventoConfirmacionCita.EstadoSync.ACCEPTED).count()
        rejected = qs.filter(sync_status=EventoConfirmacionCita.EstadoSync.REJECTED).count()

        return Response({
            "days": days_int,
            "metrics": {
                "total": total,
                "conflicts": conflicts,
                "accepted": accepted,
                "rejected": rejected,
            },
        })
