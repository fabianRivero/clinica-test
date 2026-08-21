"""
Payment viewsets for DRF migration.
Domain 3 of Phase 6.
"""

import os

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
from config.api_helpers import (
    currency,
    date_label,
    datetime_label,
    full_name,
    get_user_branch,
    procedure_name,
)


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
            "paymentQrConfig": self._payment_qr_config_item(config, os.getenv("STORAGE_PROVIDER", "local")),
            "payments": [self._payment_item(p) for p in pagos_qs],
            "quotas": [self._admin_quota_item(c) for c in cuotas_qs],
        })

    @action(detail=False, methods=["post"], url_path="configuracion-qr")
    def update_qr_config(self, request):
        """POST /pagos/configuracion-qr/ — update QR config (multipart)."""
        import logging
        import traceback
        logger = logging.getLogger('billing')
        branch = get_user_branch(request)
        qr_file = request.FILES.get("qrImage")
        instructions = request.POST.get("instructions", "").strip()
        config = ConfiguracionPagoQR.objects.filter(sucursal=branch).first()
        if not config:
            config = ConfiguracionPagoQR(sucursal=branch)

        storage_provider = os.getenv("STORAGE_PROVIDER", "local")
        public_url = None

        try:
            if qr_file:
                if storage_provider in ("supabase", "s3"):
                    from django.utils.timezone import now
                    import requests

                    date_path = now().strftime("%Y/%m")
                    # Strip any existing path from the uploaded filename
                    # (browsers may send full paths like "pagos_qr/2026/06/file.webp")
                    safe_filename = os.path.basename(qr_file.name.replace(" ", "_"))
                    # Full path for Supabase (includes upload_to prefix)
                    supabase_path = f"pagos_qr/{date_path}/{safe_filename}"

                    if storage_provider == "supabase":
                        supabase_url = os.getenv("SUPABASE_URL")
                        supabase_key = os.getenv("SUPABASE_KEY")
                        bucket = os.getenv("SUPABASE_BUCKET")
                        upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{supabase_path}"
                        headers = {
                            "Authorization": f"Bearer {supabase_key}",
                            "Content-Type": qr_file.content_type,
                        }
                        qr_file.open()
                        response = requests.put(
                            upload_url,
                            headers=headers,
                            data=qr_file.read(),
                            timeout=30,
                        )
                        qr_file.close()
                        if response.status_code not in (200, 201):
                            logger.error(f"[QR-UPDATE] Supabase error: {response.status_code} {response.text}")
                            raise Exception(f"Supabase upload failed: {response.status_code}")
                        public_url = f"{supabase_url}/storage/v1/object/public/{bucket}/{supabase_path}"
                    else:  # s3
                        import boto3
                        from botocore.config import Config
                        client = boto3.client(
                            "s3",
                            endpoint_url=os.getenv("AWS_S3_ENDPOINT_URL"),
                            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                            region_name=os.getenv("AWS_S3_REGION_NAME", "us-east-1"),
                            config=Config(signature_version="s3v4"),
                        )
                        client.put_object(
                            Bucket=os.getenv("AWS_STORAGE_BUCKET_NAME"),
                            Key=supabase_path,
                            Body=qr_file.read(),
                            ContentType=qr_file.content_type,
                        )
                        endpoint = os.getenv("AWS_S3_ENDPOINT_URL", "")
                        bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
                        public_url = f"{endpoint.replace('/storage/v1', '')}/{bucket_name}/{supabase_path}" if endpoint else f"https://{bucket_name}.s3.amazonaws.com/{supabase_path}"

                    # For cloud storage: save only the filename to DB (Django adds upload_to prefix)
                    # This avoids double-prefix duplication
                    from django.core.files.base import ContentFile
                    config.imagen_qr.save(safe_filename, ContentFile(b""), save=False)
                else:
                    config.imagen_qr = qr_file

            if instructions:
                config.instrucciones = instructions

            config.save()

            # Determine qr_url based on storage provider
            if storage_provider in ("supabase", "s3") and public_url:
                qr_url = public_url
            elif config.imagen_qr:
                qr_url = config.imagen_qr.url
                if not qr_url.startswith("http"):
                    qr_url = request.build_absolute_uri(qr_url)
            else:
                qr_url = ""

            return Response({
                "detail": f"QR actualizado. Branch_id usado: {branch.id if branch else 'None'}",
                "paymentQrConfig": {
                    "id": config.pk,
                    "hasQr": bool(config.imagen_qr),
                    "qrImageUrl": qr_url,
                    "instructions": config.instrucciones or "",
                    "updated_at": config.updated_at.isoformat() if config.updated_at else None,
                },
            })

        except Exception as exc:
            logger.error(f"[QR-UPDATE] Error: {exc}\n{traceback.format_exc()}")
            return Response({"detail": f"Error al guardar imagen: {exc}"}, status=500)

    @action(detail=True, methods=["post"], url_path="estado")
    def update_status(self, request, pk=None):
        """POST /pagos/<int:payment_id>/estado/ — update payment verification status."""
        payment = (
            PagoRealizado.objects.select_related(
                "cuota__operacion__paciente__usuario",
                "cuota__operacion__servicio_config__proc_estetico",
                "verificado_por",
            )
            .filter(pk=pk)
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

    def _payment_qr_config_item(self, config, storage_provider=None):
        if not config:
            return {"hasQr": False, "qrImageUrl": "", "instructions": ""}
        qr_url = ""
        if config.imagen_qr:
            if storage_provider in ("supabase", "s3"):
                # For cloud storage, rebuild public URL from filename stored in DB
                # config.imagen_qr.name already includes the full path (e.g. "pagos_qr/2026/06/file.webp")
                name = config.imagen_qr.name
                if storage_provider == "supabase":
                    supabase_url = os.getenv("SUPABASE_URL")
                    bucket = os.getenv("SUPABASE_BUCKET")
                    if supabase_url and bucket:
                        qr_url = f"{supabase_url}/storage/v1/object/public/{bucket}/{name}"
                elif storage_provider == "s3":
                    endpoint = os.getenv("AWS_S3_ENDPOINT_URL", "")
                    bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
                    if bucket_name:
                        if endpoint:
                            qr_url = f"{endpoint.replace('/storage/v1', '')}/{bucket_name}/{name}"
                        else:
                            qr_url = f"https://{bucket_name}.s3.amazonaws.com/{name}"
            else:
                qr_url = config.imagen_qr.url
            if not qr_url.startswith("http"):
                qr_url = self.request.build_absolute_uri(qr_url)
        return {
            "id": config.pk,
            "hasQr": bool(config.imagen_qr),
            "qrImageUrl": qr_url,
            "instructions": config.instrucciones or "",
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    def _payment_item(self, payment):
        operacion = payment.cuota.operacion
        paciente = operacion.paciente
        status_map = {
            PagoRealizado.EstadoVerificacion.APROBADO: "aprobado",
            PagoRealizado.EstadoVerificacion.RECHAZADO: "observado",
            PagoRealizado.EstadoVerificacion.CANCELADO: "cancelado",
        }
        return {
            "id": f"PAY-{payment.pk:04d}",
            "rawId": payment.pk,
            "clientId": paciente.pk,
            "patient": full_name(paciente.usuario) if paciente.usuario else "—",
            "operation": procedure_name(operacion),
            "amount": currency(payment.monto_pagado),
            "submittedAt": datetime_label(payment.created_at),
            "bank": "Transferencia",
            "status": status_map.get(payment.estado_verificacion, "pendiente"),
            "quota": f"Cuota {payment.cuota.nro_cuota}",
            "dueDate": date_label(payment.cuota.fecha_vencimiento),
            "verifier": full_name(payment.verificado_por) if payment.verificado_por else "Sin revisar",
            "receiptUrl": payment.comprobante_url.url if payment.comprobante_url else "",
            "note": payment.observacion_verificacion or payment.detalles_pago or "",
        }

    def _admin_quota_item(self, cuota):
        operacion = cuota.operacion
        paciente = operacion.paciente
        return {
            "id": cuota.pk,
            "clientId": paciente.pk,
            "patient": (
                f"{paciente.usuario.primer_nombre} {paciente.usuario.apellido_paterno}"
                if paciente.usuario else "—"
            ),
            "operation": (
                operacion.servicio_config.proc_estetico.proceso
                if operacion.servicio_config.proc_estetico else "—"
            ),
            "quotaNumber": cuota.nro_cuota,
            "amount": str(cuota.monto_programado),
            "dueDate": cuota.fecha_vencimiento.isoformat(),
            "status": cuota.estado,
            "paymentsCount": cuota.pagos_realizados.count(),
        }