"""
Client ViewSets for DRF migration.
Domain 6 of Phase 6.

Three ViewSets:
- ClientesViewSet: search, detail, inactivate, migrar
- OperacionesViewSet: reservation availability + create (nested under operations)
- FreeMedicalAppointmentViewSet: free medical appointment availability + create
"""

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from customers.models import Cliente
from operations.models import CitaMedica, CitaClienteLibre, Operacion
from billing.models import CuotaPlanPago, PagoRealizado
from operations.scheduling import mark_expired_programmed_appointments_as_no_show

from config.api.permissions import AdminRequired
from config.api.serializers.clientes import (
    ClientSearchSerializer,
    ClientDetailSerializer,
    ClientInactivateSerializer,
    ClientMigrateSerializer,
    OperationReservationAvailabilitySerializer,
    OperationReservationCreateSerializer,
    FreeMedicalAvailabilitySerializer,
    FreeMedicalAppointmentCreateSerializer,
)
from config.api_helpers import full_name, currency, date_label, datetime_label, metric, procedure_name, get_user_branch
from config.client_api_views import (
    _operation_item as _client_operation_item,
    _appointment_item as _client_appointment_item,
    _payment_item as _client_payment_item,
    _quota_item as _client_quota_item,
    BLOCKING_RESERVATION_STATES,
)


# =============================================================================
# Helpers (mirroring api_views.py helpers)
# =============================================================================

def _client_item(cliente):
    """Build a lightweight client dict for search results."""
    return {
        "id": cliente.pk,
        "name": full_name(cliente.usuario),
        "ci": cliente.ci or "Sin CI",
        "phone": cliente.telefono or "Sin teléfono",
        "branchId": cliente.usuario.sucursal_id,
        "branchName": cliente.usuario.sucursal.nombre if cliente.usuario.sucursal else "Sin sucursal",
        "cityName": cliente.usuario.sucursal.ciudad if cliente.usuario.sucursal else "Sin ciudad",
    }


def _admin_client_queryset():
    """Return a prefetched queryset for admin client detail."""
    mark_expired_programmed_appointments_as_no_show()
    return (
        Cliente.objects.select_related("usuario")
        .prefetch_related(
            Prefetch(
                "operaciones",
                queryset=Operacion.objects.select_related(
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
                        queryset=CuotaPlanPago.objects.prefetch_related(
                            Prefetch(
                                "pagos_realizados",
                                queryset=PagoRealizado.objects.select_related("verificado_por").order_by("-created_at"),
                            )
                        ).order_by("nro_cuota"),
                    ),
                ).order_by("-created_at"),
            ),
            "analisis_esteticos",
            Prefetch(
                "citas_medicas_libres",
                queryset=CitaClienteLibre.objects.select_related().order_by("fecha_hora"),
            ),
        )
    )


def _admin_client_detail(cliente):
    """Build the full client detail response dict."""
    operations = list(cliente.operaciones.all())
    appointments = [
        cita
        for operacion in operations
        for cita in operacion.citas_medicas.all()
    ]
    free_appointments = list(cliente.citas_medicas_libres.all())
    quotas = [
        cuota
        for operacion in operations
        for cuota in operacion.cuotas_plan_pagos.all()
    ]
    payments = [
        pago
        for cuota in quotas
        for pago in cuota.pagos_realizados.all()
    ]
    pending_quotas = [
        cuota
        for cuota in quotas
        if cuota.estado != CuotaPlanPago.Estado.PAGADO
        and cuota.operacion.estado == Operacion.Estado.EN_PROCESO
    ]
    completed_sessions = [
        cita
        for cita in appointments
        if cita.estado == CitaMedica.Estado.CONFIRMADA and cita.verif_biometria
    ]
    upcoming_appointments = [
        cita
        for cita in appointments
        if cita.estado == CitaMedica.Estado.PROGRAMADA and cita.fecha_hora >= timezone.now()
    ]

    return {
        "client": _client_item(cliente),
        "metrics": [
            metric(
                "admin-client-appointments",
                "Citas reservadas",
                len(appointments),
                f"{len(upcoming_appointments)} próxima(s)",
                "primary",
            ),
            metric(
                "admin-client-sessions",
                "Sesiones realizadas",
                len(appointments),
                "Todas las sesiones",
                "success",
            ),
            metric(
                "admin-client-payments",
                "Pagos realizados",
                len(payments),
                f"{len([p for p in payments if p.estado_verificacion == PagoRealizado.EstadoVerificacion.PENDIENTE])} en revisión",
                "warning",
            ),
            metric(
                "admin-client-pending-quotas",
                "Pagos pendientes",
                len(pending_quotas),
                "Cuotas aun no pagadas",
                "danger",
            ),
        ],
        "operations": [_client_operation_item(operacion) for operacion in operations],
        "appointments": [
            *[_client_appointment_item(cita) for cita in sorted(appointments, key=lambda item: item.fecha_hora)],
            *[_free_client_appointment_item(cita) for cita in sorted(free_appointments, key=lambda item: item.fecha_hora)],
        ],
        "sessions": [
            *[_client_appointment_item(cita) for cita in sorted(appointments, key=lambda item: item.fecha_hora)],
            *[_free_client_appointment_item(cita) for cita in sorted(free_appointments, key=lambda item: item.fecha_hora)],
        ],
        "payments": [_client_payment_item(payment) for payment in sorted(payments, key=lambda item: item.created_at, reverse=True)],
        "pendingQuotas": [_client_quota_item(cuota) for cuota in sorted(pending_quotas, key=lambda item: (item.fecha_vencimiento, item.nro_cuota))],
    }


def _free_client_appointment_item(appointment):
    """Build a free client appointment dict."""
    return {
        "id": f"LIB-{appointment.pk:04d}",
        "rawId": appointment.pk,
        "dateTime": datetime_label(appointment.fecha_hora),
        "operation": appointment.servicio_config.tipo_servicio.tipo if appointment.servicio_config else "Cita libre",
        "specialist": "Por asignar",
        "status": appointment.get_estado_display(),
        "statusTone": "warning",
        "verificationStatus": "no_requerida",
        "details": "",
        "canManage": appointment.estado == CitaClienteLibre.Estado.PROGRAMADA,
        "canMarkPendingBiometric": False,
        "canConfirmBiometric": False,
        "canCancelFromVerification": False,
        "biometricMockTemplate": "",
        "isFreeMedicalAppointment": True,
        "branchId": appointment.sucursal_id,
        "branchName": appointment.sucursal.nombre if appointment.sucursal else "Sin sucursal",
    }


def _client_has_pending_reservations(cliente):
    """Check if client has any pending reservations."""
    now = timezone.now()
    return (
        CitaMedica.objects.filter(
            operacion__paciente=cliente,
            estado=CitaMedica.Estado.PROGRAMADA,
            fecha_hora__gte=now,
        ).exists()
        or CitaClienteLibre.objects.filter(
            cliente=cliente,
            estado=CitaClienteLibre.Estado.PROGRAMADA,
            fecha_hora__gte=now,
        ).exists()
    )


def _medical_appointment_service_config():
    """Get the active service config for medical appointments."""
    from catalogs.models import ServicioConfig
    return ServicioConfig.objects.filter(
        activo=True,
        tipo_servicio__tipo__icontains="medica",
    ).select_related("tipo_servicio").first()


def _notify_client_appointment_scheduled(cliente, fecha_hora, sucursal_id, appointment_id, appointment_type):
    """Send notification when a client appointment is scheduled (placeholder — mirrors api_views.py)."""
    pass  # Notifications handled by caller or external service


# =============================================================================
# ClientesViewSet
# =============================================================================

class ClientesViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for client management.
    Public endpoints: search (list)
    Admin-required: detail, inactivate, migrar

    Endpoints:
    - GET  /clientes/buscar/              → global search (PUBLIC, min 3 chars)
    - GET  /clientes/<int:client_id>/    → client detail with metrics
    - POST /clientes/<int:client_id>/inactivar/ → inactivate client
    - POST /clientes/<int:client_id>/migrar/    → migrate client to different branch
    """


    permission_classes = [AdminRequired]

    @action(detail=False, url_path="buscar-global", permission_classes=[])
    def buscar_global(self, request):
        """
        GET /clientes/buscar-global/?q=<query>
        Global client search — PUBLIC endpoint, no auth required.
        Returns max 10 clients matching CI, name, or username.
        Excludes clients with scheduled future appointments.
        """
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 3:
            return Response({"clients": []})

        clients_qs = (
            Cliente.objects.select_related("usuario", "sucursal_origen")
            .filter(
                Q(ci__icontains=query)
                | Q(usuario__primer_nombre__icontains=query)
                | Q(usuario__apellido_paterno__icontains=query)
                | Q(usuario__username__icontains=query)
            )
            .exclude(
                operaciones__citas_medicas__estado=CitaMedica.Estado.PROGRAMADA,
                operaciones__citas_medicas__fecha_hora__gte=timezone.now(),
            )
            .exclude(
                citas_medicas_libres__estado=CitaClienteLibre.Estado.PROGRAMADA,
                citas_medicas_libres__fecha_hora__gte=timezone.now(),
            )
            .distinct()[:10]
        )

        serializer = ClientSearchSerializer(clients_qs, many=True)
        return Response({"clients": serializer.data})

    def retrieve(self, request, pk=None):
        """
        GET /clientes/<int:client_id>/
        Full client detail with metrics, operations, appointments, payments.
        """
        cliente = _admin_client_queryset().filter(pk=pk).first()
        if not cliente:
            return Response({"detail": "No encontramos el cliente solicitado."}, status=404)

        data = _admin_client_detail(cliente)
        return Response(data)

    @action(detail=True, methods=["post"], url_path="inactivar")
    def inactivar(self, request, pk=None):
        """
        POST /clientes/<int:client_id>/inactivar/
        Inactivate a client: cancel pending operations/appointments, convert quotas.
        """
        cliente = (
            Cliente.objects.select_for_update(of=("self",))
            .select_related("usuario")
            .prefetch_related(
                Prefetch(
                    "operaciones",
                    queryset=Operacion.objects.select_for_update(of=("self",)).prefetch_related(
                        "citas_medicas",
                        Prefetch(
                            "cuotas_plan_pagos",
                            queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados"),
                        ),
                    ),
                )
            )
            .filter(pk=pk)
            .first()
        )
        if not cliente:
            return Response({"detail": "No encontramos el cliente solicitado."}, status=404)

        # Check for pending payments pending review
        pending_review_payment = PagoRealizado.objects.filter(
            cuota__operacion__paciente=cliente,
            estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
        ).select_related("cuota__operacion").order_by("created_at").first()
        if pending_review_payment:
            return Response(
                {
                    "detail": (
                        f"No se puede inactivar al cliente porque tiene un pago realizado pendiente de revisión. "
                        f"Primero revisa el pago #{pending_review_payment.pk} de la operacion "
                        f"#{pending_review_payment.cuota.operacion_id}."
                    )
                },
                status=400,
            )

        pendientes = cliente.pendientes_operativos()
        cancelled_operations = 0
        cancelled_appointments = 0
        converted_quotas = 0
        skipped_pending_review_quotas = 0

        for operacion in cliente.operaciones.all():
            if operacion.estado == Operacion.Estado.EN_PROCESO:
                operacion.estado = Operacion.Estado.CANCELADA
                operacion.save(update_fields=["estado", "updated_at"])
                cancelled_operations += 1
            for cuota in operacion.cuotas_plan_pagos.all():
                if cuota.estado not in {CuotaPlanPago.Estado.PENDIENTE, CuotaPlanPago.Estado.VENCIDA}:
                    continue
                has_pending_review = cuota.pagos_realizados.filter(
                    estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE
                ).exists()
                if has_pending_review:
                    skipped_pending_review_quotas += 1
                    continue
                cuota.estado = CuotaPlanPago.Estado.NO_PAGADA
                cuota.save(update_fields=["estado", "updated_at"])
                converted_quotas += 1
            for cita in operacion.citas_medicas.all():
                if cita.estado == CitaMedica.Estado.PROGRAMADA:
                    cita.estado = CitaMedica.Estado.CANCELADA
                    cita.detalles_cita = "Reserva cancelada al convertir el cliente a inactivo desde administracion."
                    cita.save(update_fields=["estado", "detalles_cita", "updated_at"])
                    cancelled_appointments += 1

        cliente.cambiar_estado(Cliente.Estado.INACTIVO, save=True, manual=True)

        return Response({
            "detail": (
                f"El cliente fue convertido a inactivo. "
                f"Antes de la inactivación tenia {pendientes['sesiones_pendientes']} sesion(es) "
                f"y {pendientes['cuotas_pendientes']} cuota(s) pendiente(s). "
                f"Se convirtieron {converted_quotas} cuota(s) a no pagadas "
                f"y se omitieron {skipped_pending_review_quotas} por tener pagos pendientes de revisión. "
                f"Se cancelaron {cancelled_operations} procedimiento(s) en proceso y "
                f"{cancelled_appointments} cita(s) programada(s)."
            ),
            "client": _client_item(cliente),
        })


    @action(detail=True, methods=["post"], url_path="migrar")
    def migrar(self, request, pk=None):
        """
        POST /clientes/<int:client_id>/migrar/
        Migrate client to a different branch.
        """
        from catalogs.models import Sucursal

        cliente = Cliente.objects.filter(pk=pk).first()
        if not cliente:
            return Response({"detail": "No encontramos el cliente solicitado."}, status=404)

        serializer = ClientMigrateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        branch_id = serializer.validated_data["branchId"]
        branch = Sucursal.objects.filter(pk=branch_id).first()
        if not branch:
            return Response({"detail": "La sucursal no existe."}, status=404)

        if _client_has_pending_reservations(cliente):
            return Response(
                {
                    "detail": (
                        "No se puede importar este cliente porque tiene reservas pendientes. "
                        "Cancela o completa sus citas programadas antes de cambiarlo de sucursal."
                    )
                },
                status=400,
            )

        # Update Usuario.sucursal_id (the operational branch). The
        # origin branch (Cliente.sucursal_origen) stays untouched: a
        # migrate only changes where the client is currently served
        # from, not where they were born.
        cliente.usuario.sucursal = branch
        cliente.usuario.save(update_fields=["sucursal", "updated_at"])

        return Response({
            "detail": f"Cliente migrado exitosamente a {branch.nombre}.",
            "branch": {"id": branch.id, "name": branch.nombre},
        })


# =============================================================================
# OperacionesViewSet
# =============================================================================

class OperacionesViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for operation-level actions (reservations).

    Endpoints:
    - GET  /operaciones/<int:operation_id>/reserva/disponibilidad/ → check availability
    - POST /operaciones/<int:operation_id>/reserva/               → create reservation
    """

    permission_classes = [AdminRequired]

    @action(detail=True, methods=["get"], url_path="reserva/disponibilidad")
    def reserva_disponibilidad(self, request, pk=None):
        """
        GET /operaciones/<int:operation_id>/reserva/disponibilidad/
        Get operation details for reservation. Requires client context via query param.
        """
        client_id = request.query_params.get("clientId")
        if not client_id:
            return Response({"detail": "Se requiere clientId."}, status=400)

        cliente = Cliente.objects.filter(pk=client_id).first()
        if not cliente:
            return Response({"detail": "No encontramos el cliente solicitado."}, status=404)

        operacion = (
            Operacion.objects.filter(paciente=cliente, pk=pk)
            .select_related("servicio_config__tipo_servicio", "servicio_config__proc_estetico")
            .prefetch_related(
                Prefetch(
                    "citas_medicas",
                    queryset=CitaMedica.objects.order_by("fecha_hora"),
                ),
                Prefetch(
                    "cuotas_plan_pagos",
                    queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
                ),
            )
            .first()
        )
        if not operacion:
            return Response({"detail": "No encontramos la operacion solicitada para este cliente."}, status=404)
        if operacion.estado != Operacion.Estado.EN_PROCESO:
            return Response({"detail": "Solo se pueden reservar citas para tratamientos en proceso."}, status=400)

        return Response({"operation": _client_operation_item(operacion)})

    @action(detail=True, methods=["post"], url_path="reserva")
    def reserva(self, request, pk=None):
        """
        POST /operaciones/<int:operation_id>/reserva/
        Create a medical appointment reservation for an operation.
        """
        client_id = request.data.get("clientId")
        if not client_id:
            return Response({"detail": "Se requiere clientId."}, status=400)

        cliente = Cliente.objects.filter(pk=client_id).first()
        if not cliente:
            return Response({"detail": "No encontramos el cliente solicitado."}, status=404)

        operacion = (
            Operacion.objects.select_for_update(of=("self",))
            .filter(paciente=cliente, pk=pk)
            .select_related("servicio_config__tipo_servicio", "servicio_config__proc_estetico")
            .prefetch_related(
                Prefetch(
                    "citas_medicas",
                    queryset=CitaMedica.objects.order_by("fecha_hora"),
                ),
                Prefetch(
                    "cuotas_plan_pagos",
                    queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
                ),
            )
            .first()
        )
        if not operacion:
            return Response({"detail": "No encontramos la operacion solicitada para este cliente."}, status=404)
        if not operacion.puede_reservar:
            return Response(
                {"detail": operacion.motivo_bloqueo_reserva or "Esta operacion no permite nuevas reservas."},
                status=400,
            )

        serializer = OperationReservationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        fecha_hora = timezone.make_aware(parse_datetime(serializer.validated_data["dateTime"]))
        sucursal_id = serializer.validated_data["branchId"]

        cita = CitaMedica.objects.create(
            operacion=operacion,
            sucursal_id=sucursal_id,
            fecha_hora=fecha_hora,
            estado=CitaMedica.Estado.PROGRAMADA,
            detalles_cita="Reserva creada desde administración.",
        )

        return Response(
            {
                "detail": "La cita fue reservada correctamente.",
                "appointment": _client_appointment_item(cita),
            },
            status=201,
        )


# =============================================================================
# FreeMedicalAppointmentViewSet
# =============================================================================

class FreeMedicalAppointmentViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for free (unscheduled) medical appointments.

    Endpoints:
    - GET  /citas-medicas-libres/<int:client_id>/disponibilidad/ → get availability info
    - POST /citas-medicas-libres/<int:client_id>/                 → create free appointment
    """

    permission_classes = [AdminRequired]

    @action(detail=True, methods=["get"], url_path="disponibilidad")
    def disponibilidad(self, request, pk=None):
        """
        GET /citas-medicas-libres/<int:client_id>/disponibilidad/
        Get free medical appointment availability for a client.
        """
        cliente = Cliente.objects.filter(pk=pk).first()
        if not cliente:
            return Response({"detail": "No encontramos el cliente solicitado."}, status=404)

        service_config = _medical_appointment_service_config()
        if not service_config:
            return Response(
                {"detail": "No existe un servicio activo de cita medica o consulta para agendar clientes."},
                status=400,
            )

        return Response({
            "client": _client_item(cliente),
            "service": {
                "rawId": service_config.pk,
                "name": service_config.tipo_servicio.tipo,
            },
        })

    def create(self, request, pk=None):
        """
        POST /citas-medicas-libres/<int:client_id>/
        Create a free (unscheduled) medical appointment for a client.
        """
        cliente = Cliente.objects.select_for_update(of=("self",)).filter(pk=pk).first()
        if not cliente:
            return Response({"detail": "No encontramos el cliente solicitado."}, status=404)

        service_config = _medical_appointment_service_config()
        if not service_config:
            return Response(
                {"detail": "No existe un servicio activo de cita medica o consulta para agendar clientes."},
                status=400,
            )

        serializer = FreeMedicalAppointmentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        fecha_hora = timezone.make_aware(parse_datetime(serializer.validated_data["dateTime"]))
        sucursal_id = serializer.validated_data["branchId"]

        appointment = CitaClienteLibre.objects.create(
            cliente=cliente,
            servicio_config=service_config,
            sucursal_id=sucursal_id,
            fecha_hora=fecha_hora,
            estado=CitaClienteLibre.Estado.PROGRAMADA,
            detalles_cita="Cita medica libre agendada por administracion.",
        )

        _notify_client_appointment_scheduled(
            cliente=cliente,
            fecha_hora=appointment.fecha_hora,
            sucursal_id=appointment.sucursal_id,
            appointment_id=appointment.pk,
            appointment_type="cita_cliente_libre",
        )

        return Response(
            {
                "detail": "La cita medica libre fue agendada correctamente para el cliente.",
                "appointment": _free_client_appointment_item(appointment),
            },
            status=201,
        )

    @action(detail=True, methods=["post"], url_path="cancelar")
    def cancelar(self, request, pk=None):
        """
        POST /citas-medicas-libres/<int:appointment_id>/cancelar/
        Cancel a free medical appointment.
        """
        appointment = CitaClienteLibre.objects.filter(pk=pk).first()
        if not appointment:
            return Response({"detail": "No encontramos la cita solicitada."}, status=404)
        if appointment.estado != CitaClienteLibre.Estado.PROGRAMADA:
            return Response({"detail": "Solo se pueden cancelar citas que esten programadas."}, status=400)

        appointment.estado = CitaClienteLibre.Estado.CANCELADA
        appointment.detalles_cita = "Cita medica libre cancelada por administracion."
        appointment.save()

        return Response({
            "detail": "La cita medica libre fue cancelada correctamente.",
            "appointment": _free_client_appointment_item(appointment),
        })

    @action(detail=True, methods=["post"], url_path="confirmar")
    def confirmar(self, request, pk=None):
        """
        POST /citas-medicas-libres/<int:appointment_id>/confirmar/
        Confirm a free medical appointment as completed (REALIZADA).
        """
        appointment = CitaClienteLibre.objects.filter(pk=pk).first()
        if not appointment:
            return Response({"detail": "No encontramos la cita solicitada."}, status=404)
        if appointment.estado != CitaClienteLibre.Estado.PROGRAMADA:
            return Response({"detail": "Solo se pueden confirmar citas que esten programadas."}, status=400)

        appointment.estado = CitaClienteLibre.Estado.REALIZADA
        appointment.save()

        return Response({
            "detail": "La cita medica libre fue confirmada correctamente.",
            "appointment": _free_client_appointment_item(appointment),
        })
