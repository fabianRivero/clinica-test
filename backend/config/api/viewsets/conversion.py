"""
Conversion Wizard and Client Reactivation ViewSets for DRF migration.
Domain 7 of Phase 6.

Two ViewSets:
- ProspectoConversionViewSet: /prospectos/<id>/conversion/
  Actions: initialize, detail, paso-1 through paso-4, finalize, cancel

- ClientReactivationViewSet: /clientes/<id>/reactivar/
  Actions: initialize, detail, paso-1 through paso-4, finalize, cancel
  (Reuses same step handlers as conversion — same functions, different initial data)
"""

import json
import logging

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from customers.models import Cliente, Prospecto, ProspectoConversionBorrador, HuellaBiometricaCliente
from operations.models import Operacion
from config.api.permissions import AdminRequired
from config.prospect_conversion_views import (
    _get_draft_convertible,
    _admin_conversion_detail,
    _serialize_service_configs,
    _serialize_medical_config,
    _serialize_draft,
    _check_cross_city_procedures,
    _validate_user_step,
    _validate_operation_step,
    _validate_medical_step,
    _validate_biometric_step,
    _get_required_pdf_file,
    _build_initial_user_data,
    _build_initial_client_user_data,
    _build_initial_client_medical_data,
    _blank_medical_data,
    _blank_biometric_data,
    _is_effectively_empty_medical_data,
)
from config.api.serializers.conversion import (
    WizardStep1UserSerializer,
    WizardStep2OperationSerializer,
    WizardStep3MedicalSerializer,
    WizardStep4BiometricSerializer,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ProspectoConversionViewSet
# =============================================================================

class ProspectoConversionViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for prospect → client conversion wizard.

    URL prefix: /prospectos/<int:prospecto_id>/conversion/

    Actions:
    - POST initialize/   → create/get draft, return catalogs + warning
    - GET  detail/      → full conversion state
    - POST paso-1/      → user data (create account)
    - POST paso-2/      → operation data (treatment plan)
    - POST paso-3/      → medical form data (supports multipart)
    - POST paso-4/      → biometric enrollment
    - POST finalize/    → complete conversion
    - POST cancelar/    → discard draft
    """

    permission_classes = [AdminRequired]

    def _get_prospecto(self, pk):
        return Prospecto.objects.filter(pk=pk).first()

    def _serialize_service_configs(self):
        return _serialize_service_configs()

    @action(detail=True, methods=["post"], url_path="inicializar")
    def initialize(self, request, pk=None):
        """
        POST /prospectos/<int:prospecto_id>/conversion/inicializar/
        Initialize or retrieve the conversion draft for a prospect.
        """
        prospecto = self._get_prospecto(pk)
        if not prospecto:
            return Response({"detail": "No encontramos el prospecto solicitado."}, status=404)
        if prospecto.estado != Prospecto.Estado.PASAJERO:
            return Response({"detail": "Este prospecto ya fue procesado."}, status=400)

        draft, error = _get_draft_convertible(request, prospecto_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        warning = _check_cross_city_procedures(request, prospecto=draft.prospecto)

        return Response({
            "draft": _serialize_draft(draft),
            "crossCityWarning": warning,
            "catalogs": {
                "serviceConfigs": _serialize_service_configs(),
            },
        })

    @action(detail=True, methods=["get"], url_path="detalle")
    def detail(self, request, pk=None):
        """
        GET /prospectos/<int:prospecto_id>/conversion/detalle/
        Get full conversion wizard state.
        """
        prospecto = self._get_prospecto(pk)
        if not prospecto:
            return Response({"detail": "No encontramos el prospecto solicitado."}, status=404)

        draft, error = _get_draft_convertible(request, prospecto_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        payload = _admin_conversion_detail(draft)
        logger.warning(
            "[PREFILL] response(prospect) draft_id=%s",
            getattr(draft, "id", None),
        )
        return Response(payload)

    @action(detail=True, methods=["post"], url_path="paso-1")
    def paso_usuario(self, request, pk=None):
        """
        POST /prospectos/<int:prospecto_id>/conversion/paso-1/
        Step 1: User/client account data.
        """
        draft, error = _get_draft_convertible(request, prospecto_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        payload = request.data
        user_data, errors = _validate_user_step(payload, draft)
        if errors:
            return Response({"detail": "Corrige los errores del paso 1.", "errors": errors}, status=400)

        draft.datos_usuario = user_data
        draft.paso_usuario_completado = True
        draft.paso_actual = max(draft.paso_actual, ProspectoConversionBorrador.Paso.OPERACION)
        draft.save(
            update_fields=["datos_usuario", "paso_usuario_completado", "paso_actual", "updated_at"]
        )
        return Response(_admin_conversion_detail(draft))

    @action(detail=True, methods=["post"], url_path="paso-2")
    def paso_operacion(self, request, pk=None):
        """
        POST /prospectos/<int:prospecto_id>/conversion/paso-2/
        Step 2: Operation/treatment plan.
        """
        draft, error = _get_draft_convertible(request, prospecto_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        if not draft.paso_usuario_completado:
            return Response({"detail": "Debes completar primero los datos de usuario."}, status=400)

        payload = request.data
        previous_service_config_id = (draft.datos_operacion or {}).get("serviceConfigId")
        operation_data, service_config, errors = _validate_operation_step(payload)
        if errors:
            return Response({"detail": "Corrige los errores del paso 2.", "errors": errors}, status=400)

        draft.datos_operacion = operation_data
        draft.paso_operacion_completado = True
        draft.paso_actual = max(draft.paso_actual, ProspectoConversionBorrador.Paso.FICHA_MEDICA)
        if str(previous_service_config_id or "") != str(operation_data["serviceConfigId"]):
            draft.datos_ficha = _blank_medical_data()
            draft.paso_ficha_completado = False
        draft.save(
            update_fields=[
                "datos_operacion", "datos_ficha", "paso_operacion_completado",
                "paso_ficha_completado", "paso_actual", "updated_at",
            ]
        )
        return Response(_admin_conversion_detail(draft))

    @action(detail=True, methods=["post"], url_path="paso-3")
    def paso_ficha(self, request, pk=None):
        """
        POST /prospectos/<int:prospecto_id>/conversion/paso-3/
        Step 3: Medical form (ficha médica). Supports multipart/form-data with PDF.
        """
        draft, error = _get_draft_convertible(request, prospecto_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        if not draft.paso_operacion_completado:
            return Response({"detail": "Debes completar primero los datos de la operacion."}, status=400)

        # Handle multipart (PDF upload)
        if request.content_type and request.content_type.startswith("multipart/form-data"):
            payload_raw = request.POST.get("payload")
            if not payload_raw:
                return Response({"detail": "Falta el campo 'payload' en el form-data."}, status=400)
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                return Response({"detail": "El campo 'payload' no es JSON valido."}, status=400)
            pdf_file = request.FILES.get("documento_escaneado_pdf")
            if pdf_file:
                draft.documento_pdf = pdf_file
                draft.save(update_fields=["documento_pdf"])
        else:
            payload = request.data

        service_config_id = (draft.datos_operacion or {}).get("serviceConfigId")
        service_config = None
        if service_config_id:
            from catalogs.models import ServicioConfig
            service_config = (
                ServicioConfig.objects.select_related("tipo_servicio", "proc_estetico")
                .filter(pk=service_config_id).first()
            )

        medical_data, errors = _validate_medical_step(payload, service_config)
        if errors:
            return Response({"detail": "Corrige los errores del paso 3.", "errors": errors}, status=400)

        draft.datos_ficha = medical_data
        draft.paso_ficha_completado = True
        draft.paso_actual = max(draft.paso_actual, ProspectoConversionBorrador.Paso.BIOMETRIA)
        draft.save(
            update_fields=["datos_ficha", "paso_ficha_completado", "paso_actual", "updated_at"]
        )
        return Response(_admin_conversion_detail(draft))

    @action(detail=True, methods=["post"], url_path="paso-4")
    def paso_biometria(self, request, pk=None):
        """
        POST /prospectos/<int:prospecto_id>/conversion/paso-4/
        Step 4: Biometric enrollment.
        """
        draft, error = _get_draft_convertible(request, prospecto_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        if not draft.paso_ficha_completado:
            return Response({"detail": "Debes completar primero la ficha medica."}, status=400)

        payload = request.data
        biometric_data, errors = _validate_biometric_step(payload)
        if errors:
            return Response({"detail": "Corrige los errores del paso 4.", "errors": errors}, status=400)

        draft.datos_biometria = biometric_data
        draft.paso_biometria_completado = True
        draft.paso_actual = ProspectoConversionBorrador.Paso.BIOMETRIA
        draft.save(
            update_fields=["datos_biometria", "paso_biometria_completado", "paso_actual", "updated_at"]
        )
        return Response(_admin_conversion_detail(draft))

    @action(detail=True, methods=["post"], url_path="finalizar")
    def finalize(self, request, pk=None):
        """
        POST /prospectos/<int:prospecto_id>/conversion/finalizar/
        Finalize conversion: create user, client, operation, biometric record.
        """
        draft, error = _get_draft_convertible(request, prospecto_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        document_file, document_error = _get_required_pdf_file(request, draft=draft)
        if document_error:
            return document_error

        if not (
            draft.paso_usuario_completado
            and draft.paso_operacion_completado
            and draft.paso_ficha_completado
            and draft.paso_biometria_completado
        ):
            return Response({"detail": "Debes completar los cuatro pasos antes de finalizar."}, status=400)

        # Delegate to existing finalize logic — call the FBV handler
        # Reconstruct a Django-like request for the FBV
        from django.http import HttpRequest
        django_request = HttpRequest()
        django_request.user = request.user
        django_request.session = request.session
        django_request.META = dict(request.META)
        django_request.method = "POST"
        django_request._stream = request.stream
        django_request._request = request._request  # Original DRF request

        # Call the existing FBV handler
        from config.prospect_conversion_views import admin_prospect_conversion_finalize
        response = admin_prospect_conversion_finalize(django_request, prospecto_id=pk)
        return Response(response.data, status=response.status_code)

    @action(detail=True, methods=["post"], url_path="cancelar")
    def cancelar(self, request, pk=None):
        """
        POST /prospectos/<int:prospecto_id>/conversion/cancelar/
        Cancel/discard the conversion draft.
        """
        draft, error = _get_draft_convertible(request, prospecto_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        draft.delete()
        return Response({"detail": "El borrador de conversion fue descartado correctamente."})


# =============================================================================
# ClientReactivationViewSet
# =============================================================================

class ClientReactivationViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for reactivating inactive clients via conversion wizard.

    URL prefix: /clientes/<int:cliente_id>/reactivar/

    Actions mirror ProspectoConversionViewSet but use cliente_id and
    pre-populate user/biometric data from the existing client record.
    Steps 1-4 and finalize REUSE the same backend functions from
    prospect_conversion_views (called via the same URLs that FBVs use).

    Note: This ViewSet's step handlers are the SAME functions imported
    from prospect_conversion_views — they accept both prospecto_id and cliente_id.
    """

    permission_classes = [AdminRequired]

    def _get_cliente(self, pk):
        return Cliente.objects.select_related("usuario", "sucursal_registro").filter(pk=pk).first()

    @action(detail=True, methods=["post"], url_path="inicializar")
    def initialize(self, request, pk=None):
        """
        POST /clientes/<int:cliente_id>/reactivar/inicializar/
        Initialize client reactivation draft.
        """
        cliente = self._get_cliente(pk)
        if not cliente:
            return Response({"detail": "No encontramos el cliente solicitado."}, status=404)

        draft, error = _get_draft_convertible(request, cliente_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        warning = _check_cross_city_procedures(request, cliente=draft.cliente)
        detail = _admin_conversion_detail(draft)
        detail["crossCityWarning"] = warning
        return Response(detail)

    @action(detail=True, methods=["get"], url_path="detalle")
    def detail(self, request, pk=None):
        """
        GET /clientes/<int:cliente_id>/reactivar/
        Get full reactivation wizard state.
        """
        cliente = self._get_cliente(pk)
        if not cliente:
            return Response({"detail": "No encontramos el cliente solicitado."}, status=404)

        draft, error = _get_draft_convertible(request, cliente_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        return Response(_admin_conversion_detail(draft))

    @action(detail=True, methods=["post"], url_path="paso-1")
    def paso_usuario(self, request, pk=None):
        """
        POST /clientes/<int:cliente_id>/reactivar/paso-1/
        Step 1 for reactivation.
        """
        draft, error = _get_draft_convertible(request, cliente_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        payload = request.data
        user_data, errors = _validate_user_step(payload, draft)
        if errors:
            return Response({"detail": "Corrige los errores del paso 1.", "errors": errors}, status=400)

        draft.datos_usuario = user_data
        draft.paso_usuario_completado = True
        draft.paso_actual = max(draft.paso_actual, ProspectoConversionBorrador.Paso.OPERACION)
        draft.save(
            update_fields=["datos_usuario", "paso_usuario_completado", "paso_actual", "updated_at"]
        )
        return Response(_admin_conversion_detail(draft))

    @action(detail=True, methods=["post"], url_path="paso-2")
    def paso_operacion(self, request, pk=None):
        """
        POST /clientes/<int:cliente_id>/reactivar/paso-2/
        """
        draft, error = _get_draft_convertible(request, cliente_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        if not draft.paso_usuario_completado:
            return Response({"detail": "Debes completar primero los datos de usuario."}, status=400)

        payload = request.data
        previous_service_config_id = (draft.datos_operacion or {}).get("serviceConfigId")
        operation_data, service_config, errors = _validate_operation_step(payload)
        if errors:
            return Response({"detail": "Corrige los errores del paso 2.", "errors": errors}, status=400)

        draft.datos_operacion = operation_data
        draft.paso_operacion_completado = True
        draft.paso_actual = max(draft.paso_actual, ProspectoConversionBorrador.Paso.FICHA_MEDICA)
        if str(previous_service_config_id or "") != str(operation_data["serviceConfigId"]):
            draft.datos_ficha = _blank_medical_data()
            draft.paso_ficha_completado = False
        draft.save(
            update_fields=[
                "datos_operacion", "datos_ficha", "paso_operacion_completado",
                "paso_ficha_completado", "paso_actual", "updated_at",
            ]
        )
        return Response(_admin_conversion_detail(draft))

    @action(detail=True, methods=["post"], url_path="paso-3")
    def paso_ficha(self, request, pk=None):
        """
        POST /clientes/<int:cliente_id>/reactivar/paso-3/
        """
        draft, error = _get_draft_convertible(request, cliente_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        if not draft.paso_operacion_completado:
            return Response({"detail": "Debes completar primero los datos de la operacion."}, status=400)

        if request.content_type and request.content_type.startswith("multipart/form-data"):
            payload_raw = request.POST.get("payload")
            if not payload_raw:
                return Response({"detail": "Falta el campo 'payload' en el form-data."}, status=400)
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                return Response({"detail": "El campo 'payload' no es JSON valido."}, status=400)
            pdf_file = request.FILES.get("documento_escaneado_pdf")
            if pdf_file:
                draft.documento_pdf = pdf_file
                draft.save(update_fields=["documento_pdf"])
        else:
            payload = request.data

        service_config_id = (draft.datos_operacion or {}).get("serviceConfigId")
        service_config = None
        if service_config_id:
            from catalogs.models import ServicioConfig
            service_config = (
                ServicioConfig.objects.select_related("tipo_servicio", "proc_estetico")
                .filter(pk=service_config_id).first()
            )

        medical_data, errors = _validate_medical_step(payload, service_config)
        if errors:
            return Response({"detail": "Corrige los errores del paso 3.", "errors": errors}, status=400)

        draft.datos_ficha = medical_data
        draft.paso_ficha_completado = True
        draft.paso_actual = max(draft.paso_actual, ProspectoConversionBorrador.Paso.BIOMETRIA)
        draft.save(
            update_fields=["datos_ficha", "paso_ficha_completado", "paso_actual", "updated_at"]
        )
        return Response(_admin_conversion_detail(draft))

    @action(detail=True, methods=["post"], url_path="paso-4")
    def paso_biometria(self, request, pk=None):
        """
        POST /clientes/<int:cliente_id>/reactivar/paso-4/
        """
        draft, error = _get_draft_convertible(request, cliente_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        if not draft.paso_ficha_completado:
            return Response({"detail": "Debes completar primero la ficha medica."}, status=400)

        payload = request.data
        biometric_data, errors = _validate_biometric_step(payload)
        if errors:
            return Response({"detail": "Corrige los errores del paso 4.", "errors": errors}, status=400)

        draft.datos_biometria = biometric_data
        draft.paso_biometria_completado = True
        draft.paso_actual = ProspectoConversionBorrador.Paso.BIOMETRIA
        draft.save(
            update_fields=["datos_biometria", "paso_biometria_completado", "paso_actual", "updated_at"]
        )
        return Response(_admin_conversion_detail(draft))

    @action(detail=True, methods=["post"], url_path="finalizar")
    def finalize(self, request, pk=None):
        """
        POST /clientes/<int:cliente_id>/reactivar/finalizar/
        Finalize client reactivation.
        """
        draft, error = _get_draft_convertible(request, cliente_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        document_file, document_error = _get_required_pdf_file(request, draft=draft)
        if document_error:
            return document_error

        if not (
            draft.paso_usuario_completado
            and draft.paso_operacion_completado
            and draft.paso_ficha_completado
            and draft.paso_biometria_completado
        ):
            return Response({"detail": "Debes completar los cuatro pasos antes de finalizar."}, status=400)

        # Call the existing FBV handler for finalize
        from django.http import HttpRequest
        django_request = HttpRequest()
        django_request.user = request.user
        django_request.session = request.session
        django_request.META = dict(request.META)
        django_request.method = "POST"
        django_request._stream = request.stream
        django_request._request = request._request

        from config.prospect_conversion_views import admin_prospect_conversion_finalize
        response = admin_prospect_conversion_finalize(django_request, cliente_id=pk)
        return Response(response.data, status=response.status_code)

    @action(detail=True, methods=["post"], url_path="cancelar")
    def cancelar(self, request, pk=None):
        """
        POST /clientes/<int:cliente_id>/reactivar/cancelar/
        """
        draft, error = _get_draft_convertible(request, cliente_id=pk)
        if error:
            return Response({"detail": error}, status=400)

        draft.delete()
        return Response({"detail": "El borrador de conversion fue descartado correctamente."})
