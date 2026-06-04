"""
Payment viewsets for DRF migration.
Domain 3 of Phase 6.
"""

from django.db.models import Q
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from billing.models import CuotaPlanPago, PagoRealizado, ConfiguracionPagoQR
from notifications.models import Notification
from notifications.services import create_notification

from config.api.permissions import AdminRequired
from config.api.serializers.payments import (
    PagoRealizadoSerializer,
    CuotaPlanPagoSerializer,
    ConfiguracionPagoQRSerializer,
    PaymentStatusUpdateSerializer,
)
from config.api_helpers import get_user_branch


class PagosViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for payment management.

    Endpoints:
    - GET  /pagos/                              → list payments with metrics
    - POST /pagos/configuracion-qr/             → update QR config (multipart)
    - POST /pagos/<int:payment_id>/estado/       → update payment status
    """

    permission_classes = [AdminRequired]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def list(self, request):
        """GET /pagos/ — list payments with filters and metrics."""
        branch = get_user_branch(request)
        status_filter = (request.query_params.get("status") or "").strip().upper()
        date_from = (request.query_params.get("dateFrom") or "").strip()
        date_to = (request.query_params.get("dateTo") or "").strip()
        search = (request.query_params.get("search") or "").strip()

        pagos_qs = (
            PagoRealizado.objects.select_related(
                "cuota__operacion__paciente__usuario",
                "cuota__operacion__servicio_config__proc_estetico",
                "verificado_por",
            ).order_by("-created_at")
        )
        if branch:
            pagos_qs = pagos_qs.filter(
                cuota__operacion__paciente__sucursal_registro=branch
            ).distinct()

        valid_statuses = {choice[0] for choice in PagoRealizado.EstadoVerificacion.choices}
        if status_filter and status_filter in valid_statuses:
            pagos_qs = pagos_qs.filter(estado_verificacion=status_filter)
        if date_from:
            pagos_qs = pagos_qs.filter(created_at__date__gte=date_from)
        if date_to:
            pagos_qs = pagos_qs.filter(created_at__date__lte=date_to)
        if search:
            pagos_qs = pagos_qs.filter(
                Q(cuota__operacion__paciente__usuario__primer_nombre__icontains=search)
                | Q(cuota__operacion__paciente__usuario__segundo_nombre__icontains=search)
                | Q(cuota__operacion__paciente__usuario__apellido_paterno__icontains=search)
                | Q(cuota__operacion__paciente__usuario__apellido_materno__icontains=search)
                | Q(cuota__operacion__servicio_config__proc_estetico__proceso__icontains=search)
                | Q(cuota__operacion__servicio_config__tipo_servicio__tipo__icontains=search)
            )

        pending_amount = sum(
            p.monto_pagado
            for p in pagos_qs
            if p.estado_verificacion == PagoRealizado.EstadoVerificacion.PENDIENTE
        )

        cuotas_qs = (
            CuotaPlanPago.objects.select_related(
                "operacion__paciente__usuario",
                "operacion__servicio_config__proc_estetico",
            )
            .prefetch_related("pagos_realizados")
            .order_by("fecha_vencimiento", "nro_cuota")
        )
        if branch:
            cuotas_qs = cuotas_qs.filter(operacion__paciente__sucursal_registro=branch).distinct()

        import logging
        logger = logging.getLogger('billing')
        logger.warning(f"[QR-GET] branch={branch.id if branch else None}, headers={dict(request.headers)}")
        config = ConfiguracionPagoQR.objects.filter(sucursal=branch).first()

        config = ConfiguracionPagoQR.objects.filter(sucursal=branch).first()

        return Response({
            "metrics": [
                {
                    "id": "payments-pending",
                    "label": "Pendientes de revisión",
                    "value": str(pagos_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE).count()),
                    "delta": f"Bs {pending_amount:.2f}",
                    "tone": "warning",
                },
                {
                    "id": "payments-approved",
                    "label": "Pagos aprobados",
                    "value": str(pagos_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO).count()),
                    "delta": "Impactan el estado de cuotas",
                    "tone": "success",
                },
                {
                    "id": "payments-observed",
                    "label": "Pagos observados",
                    "value": str(pagos_qs.filter(estado_verificacion=PagoRealizado.EstadoVerificacion.RECHAZADO).count()),
                    "delta": "Requieren seguimiento administrativo",
                    "tone": "danger",
                },
                {
                    "id": "payments-total",
                    "label": "Pagos registrados",
                    "value": str(pagos_qs.count()),
                    "delta": "Incluye historico completo del sistema",
                    "tone": "primary",
                },
            ],
            "paymentQrConfig": self._payment_qr_config_item(config),
            "payments": [self._payment_item(p) for p in pagos_qs],
            "quotas": [self._admin_quota_item(c) for c in cuotas_qs],
        })

    @action(detail=False, methods=["post"], url_path="configuracion-qr")
    def update_qr_config(self, request):
        """POST /pagos/configuracion-qr/ — update QR config (multipart)."""
        import logging
        logger = logging.getLogger('billing')
        branch = get_user_branch(request)
        qr_file = request.FILES.get("qrImage")
        instructions = request.POST.get("instructions", "").strip()
        logger.warning(f"[QR-UPDATE] user={request.user.username}, is_superuser={request.user.is_superuser}, es_admin_principal={getattr(request.user, 'es_admin_principal', False)}, branch={branch.id if branch else None}, headers={dict(request.headers)}")
        
        config = ConfiguracionPagoQR.objects.filter(sucursal=branch).first()
        if not config:
            config = ConfiguracionPagoQR(sucursal=branch)

        if qr_file:
            config.imagen_qr = qr_file
        if instructions:
            config.instrucciones = instructions

        config.save()
        return Response({
            "detail": f"QR actualizado. Branch_id usado: {branch.id if branch else 'None'}",
            "paymentQrConfig": self._payment_qr_config_item(config),
        })

    @action(detail=True, methods=["post"], url_path="estado")
    def update_status(self, request, payment_id=None):
        """POST /pagos/<int:payment_id>/estado/ — update payment verification status."""
        payment = (
            PagoRealizado.objects.select_related(
                "cuota__operacion__paciente__usuario",
                "cuota__operacion__servicio_config__proc_estetico",
                "verificado_por",
            )
            .filter(pk=payment_id)
            .first()
        )
        if not payment:
            return Response({"detail": "No encontramos el pago solicitado."}, status=404)

        status_value = (request.data.get("status") or "").strip().upper()
        note = (request.data.get("note") or "").strip()
        valid_statuses = {choice[0] for choice in PagoRealizado.EstadoVerificacion.choices}
        if status_value not in valid_statuses:
            return Response({"detail": "El estado solicitado no es valido."}, status=400)

        payment.estado_verificacion = status_value
        if status_value == PagoRealizado.EstadoVerificacion.PENDIENTE:
            payment.observacion_verificacion = ""
        else:
            payment.verificado_por = request.user
            payment.fecha_verificacion = timezone.now()
            payment.observacion_verificacion = note

        payment.save()

        payment = (
            PagoRealizado.objects.select_related(
                "cuota__operacion__paciente__usuario",
                "cuota__operacion__servicio_config__proc_estetico",
                "verificado_por",
            )
            .get(pk=payment.pk)
        )

        old_state = payment.estado_verificacion if payment.pk else None

        paciente_user = payment.cuota.operacion.paciente.usuario
        nro_cuota = payment.cuota.nro_cuota
        monto_pago = payment.monto_pagado
        procedimiento = payment.cuota.operacion.servicio_config.proc_estetico.proceso

        if status_value == PagoRealizado.EstadoVerificacion.APROBADO:
            create_notification(
                recipient=paciente_user,
                branch=payment.cuota.operacion.paciente.sucursal_registro,
                type=Notification.Type.CLIENT_PAYMENT_CONFIRMED,
                title="Pago confirmado",
                message=(
                    f"El pago de la cuota Nro {nro_cuota} de monto Bs {monto_pago} "
                    f"del procedimiento {procedimiento} fue aprobado."
                ),
                action_url="/cliente/pagos",
                source_event="payment.approved",
                source_entity_type="payment",
                source_entity_id=payment.id,
                created_by_type="admin",
                created_by_id=request.user.id,
            )
        elif status_value == PagoRealizado.EstadoVerificacion.RECHAZADO:
            create_notification(
                recipient=paciente_user,
                branch=payment.cuota.operacion.paciente.sucursal_registro,
                type=Notification.Type.CLIENT_PAYMENT_REJECTED,
                title="Pago rechazado",
                message=(
                    f"El pago de la cuota Nro {nro_cuota} de monto Bs {monto_pago} "
                    f"del procedimiento {procedimiento} fue rechazado."
                ),
                action_url="/cliente/pagos",
                source_event="payment.rejected",
                source_entity_type="payment",
                source_entity_id=payment.id,
                created_by_type="admin",
                created_by_id=request.user.id,
            )
        elif status_value == PagoRealizado.EstadoVerificacion.CANCELADO:
            create_notification(
                recipient=paciente_user,
                branch=payment.cuota.operacion.paciente.sucursal_registro,
                type=Notification.Type.CLIENT_PAYMENT_CANCELLED,
                title="Pago cancelado",
                message=(
                    f"El pago de la cuota Nro {nro_cuota} de monto Bs {monto_pago} "
                    f"del procedimiento {procedimiento} fue cancelado."
                ),
                action_url="/cliente/pagos",
                source_event="payment.cancelled",
                source_entity_type="payment",
                source_entity_id=payment.id,
                created_by_type="admin",
                created_by_id=request.user.id,
            )
        elif status_value == PagoRealizado.EstadoVerificacion.PENDIENTE:
            if old_state != PagoRealizado.EstadoVerificacion.PENDIENTE and old_state is not None:
                create_notification(
                    recipient=paciente_user,
                    branch=payment.cuota.operacion.paciente.sucursal_registro,
                    type=Notification.Type.CLIENT_PAYMENT_PENDING_REVERSION,
                    title="Pago vuelto a pendiente",
                    message=(
                        f"El pago de la cuota Nro {nro_cuota} de monto Bs {monto_pago} "
                        f"del procedimiento {procedimiento} fue vuelto a estado pendiente."
                    ),
                    action_url="/cliente/pagos",
                    source_event="payment.reverted_to_pending",
                    source_entity_type="payment",
                    source_entity_id=payment.id,
                    created_by_type="admin",
                    created_by_id=request.user.id,
                )

        detail_map = {
            PagoRealizado.EstadoVerificacion.PENDIENTE: "El pago volvio a estado pendiente.",
            PagoRealizado.EstadoVerificacion.APROBADO: "El pago fue aprobado correctamente.",
            PagoRealizado.EstadoVerificacion.RECHAZADO: "El pago fue observado correctamente.",
            PagoRealizado.EstadoVerificacion.CANCELADO: "El pago fue cancelado correctamente.",
        }

        return Response({
            "detail": detail_map[status_value],
            "payment": self._payment_item(payment),
        })

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _payment_qr_config_item(self, config):
        if not config:
            return {"hasQr": False, "qrImageUrl": "", "instructions": ""}
        return {
            "id": config.pk,
            "hasQr": bool(config.imagen_qr),
            "qrImageUrl": config.imagen_qr.url if config.imagen_qr else "",
            "instructions": config.instrucciones or "",
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    def _payment_item(self, payment):
        operacion = payment.cuota.operacion
        paciente = operacion.paciente
        return {
            "id": payment.pk,
            "monto_pagado": str(payment.monto_pagado),
            "comprobante_url": payment.comprobante_url.url if payment.comprobante_url else None,
            "estado_verificacion": payment.estado_verificacion,
            "verificado": payment.verificado,
            "verificado_por": (
                f"{payment.verificado_por.primer_nombre} {payment.verificado_por.apellido_paterno}"
                if payment.verificado_por else None
            ),
            "fecha_verificacion": (
                payment.fecha_verificacion.isoformat() if payment.fecha_verificacion else None
            ),
            "detalles_pago": payment.detalles_pago or "",
            "observacion_verificacion": payment.observacion_verificacion or "",
            "cuota": {
                "id": payment.cuota.pk,
                "nro_cuota": payment.cuota.nro_cuota,
                "fecha_vencimiento": payment.cuota.fecha_vencimiento.isoformat(),
                "monto_programado": str(payment.cuota.monto_programado),
                "estado": payment.cuota.estado,
            },
            "operacion": {
                "id": operacion.pk,
                "precio_total": str(operacion.precio_total),
                "paciente": {
                    "id": paciente.pk,
                    "nombre": (
                        f"{paciente.usuario.primer_nombre} {paciente.usuario.apellido_paterno}"
                        if paciente.usuario else "—"
                    ),
                },
            },
            "procedimiento": (
                operacion.servicio_config.proc_estetico.proceso
                if operacion.servicio_config.proc_estetico else "—"
            ),
        }

    def _admin_quota_item(self, cuota):
        operacion = cuota.operacion
        paciente = operacion.paciente
        return {
            "id": cuota.pk,
            "nro_cuota": cuota.nro_cuota,
            "fecha_vencimiento": cuota.fecha_vencimiento.isoformat(),
            "monto_programado": str(cuota.monto_programado),
            "estado": cuota.estado,
            "operacion": {
                "id": operacion.pk,
                "precio_total": str(operacion.precio_total),
                "paciente": {
                    "id": paciente.pk,
                    "nombre": (
                        f"{paciente.usuario.primer_nombre} {paciente.usuario.apellido_paterno}"
                        if paciente.usuario else "—"
                    ),
                },
            },
            "procedimiento": (
                operacion.servicio_config.proc_estetico.proceso
                if operacion.servicio_config.proc_estetico else "—"
            ),
            "pagos": [
                {"id": p.pk, "monto": str(p.monto_pagado), "estado": p.estado_verificacion}
                for p in cuota.pagos_realizados.all()
            ],
        }