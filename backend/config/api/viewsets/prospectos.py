"""
Prospect ViewSet for DRF migration.
Domain 7 of Phase 6 — Prospects + Medical Appointments.
"""

from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from customers.models import Prospecto, Cliente
from operations.models import CitaProspecto
from operations.scheduling import mark_expired_programmed_appointments_as_no_show
from config.api.permissions import AdminRequired
from config.api.serializers.prospectos import (
    ProspectListSerializer,
    ProspectCreateSerializer,
    ProspectUpdateSerializer,
    ProspectMigrateSerializer,
    ProspectDuplicateCheckSerializer,
    ProspectMedicalAvailabilitySerializer,
    ProspectMedicalAppointmentCreateSerializer,
    ProspectAppointmentUpdateSerializer,
)
from config.api_helpers import capitalize_first_letter, get_user_branch, full_name
from config.api_views import _prospect_item, _prospect_appointment_item


def _build_prospect_medical_slot_map(service_config, branch_id=1):
    """Return empty slot map (placeholder — mirrors api_views.py)."""
    return {
        "windowStart": None,
        "windowEnd": None,
        "monthLabel": "",
        "availableDates": [],
        "slotsByDate": {},
        "slotCount": 0,
    }


def _medical_appointment_service_config():
    """Get active service config for prospect medical appointments."""
    from catalogs.models import ServicioConfig
    return ServicioConfig.objects.filter(
        activo=True,
        tipo_servicio__tipo__icontains="medica",
    ).select_related("tipo_servicio").first()


class ProspectosViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for prospect management.

    Endpoints:
    - GET  /prospectos/                        → list with metrics
    - POST /prospectos/crear/                  → create prospect
    - GET  /prospectos/verificar-duplicados/   → check duplicates (query params)
    - GET  /prospectos/<int:prospecto_id>/   → retrieve prospect detail
    - POST /prospectos/<int:prospecto_id>/   → update prospect
    - POST /prospectos/<int:prospecto_id>/migrar/ → migrate to another branch
    - GET  /prospectos/<int:prospecto_id>/cita-medica/disponibilidad/ → medical availability
    - POST /prospectos/<int:prospecto_id>/cita-medica/reservar/ → create medical appointment
    - POST /prospectos/citas/<int:appointment_id>/actualizar/ → update appointment status
    - POST /prospectos/citas-medicas/<int:appointment_id>/cancelar/ → cancel appointment
    """

    permission_classes = [AdminRequired]

    def list(self, request):
        """
        GET /prospectos/
        List prospects with metrics (same data as admin_prospectos).
        """
        mark_expired_programmed_appointments_as_no_show()
        branch = get_user_branch(request)
        prospectos_qs = (
            Prospecto.objects.select_related("registrado_por")
            .prefetch_related(
                Prefetch(
                    "citas_medicas",
                    queryset=CitaProspecto.objects.select_related(
                        "servicio_config__tipo_servicio",
                    ).order_by("fecha_hora"),
                )
            )
        )
        if branch:
            prospectos_qs = prospectos_qs.filter(sucursal_registro=branch)
        prospectos_qs = prospectos_qs.order_by("-created_at")

        # Client metrics
        clientes_qs = (
            Cliente.objects.select_related("usuario")
            .prefetch_related(
                Prefetch(
                    "operaciones",
                    queryset=Cliente.objects.none(),  # Don't prefetch operations for metrics
                ),
            ).order_by("usuario__primer_nombre", "usuario__apellido_paterno")
        )
        if branch:
            clientes_qs = clientes_qs.filter(
                Q(sucursal_registro=branch)
                | Q(operaciones__citas_medicas__sucursal=branch)
            ).distinct()

        data = {
            "metrics": [
                {
                    "key": "prospects-open",
                    "label": "Prospectos abiertos",
                    "value": prospectos_qs.filter(estado=Prospecto.Estado.PASAJERO).count(),
                    "description": "Registrados internamente por el equipo",
                    "tone": "primary",
                },
                {
                    "key": "prospects-converted",
                    "label": "Prospectos convertidos",
                    "value": prospectos_qs.filter(estado=Prospecto.Estado.CONVERTIDO).count(),
                    "description": "Ya cuentan con tratamiento activo o historico",
                    "tone": "success",
                },
                {
                    "key": "clients-active",
                    "label": "Clientes activos",
                    "value": clientes_qs.filter(estado_cliente=Cliente.Estado.ACTIVO).count(),
                    "description": "Con al menos una operacion vigente",
                    "tone": "warning",
                },
                {
                    "key": "clients-inactive",
                    "label": "Clientes inactivos",
                    "value": clientes_qs.filter(estado_cliente=Cliente.Estado.INACTIVO).count(),
                    "description": "Con historial disponible en portal",
                    "tone": "danger",
                },
            ],
            "prospects": [_prospect_item(p) for p in prospectos_qs],
        }
        return Response(data)

    @action(detail=False, methods=["post"], url_path="crear")
    def crear(self, request):
        """
        POST /prospectos/crear/
        Create a new prospect.
        """
        serializer = ProspectCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Hay errores en el formulario.", "errors": serializer.errors}, status=400)

        data = serializer.validated_data
        branch = get_user_branch(request)
        if not branch:
            return Response({"detail": "No encontramos una sucursal activa para registrar el prospecto."}, status=400)

        prospecto = Prospecto.objects.create(
            primer_nombre=_capitalize_first_letter(data["primerNombre"]),
            segundo_nombre=_capitalize_first_letter(data.get("segundoNombre") or ""),
            apellido_paterno=capitalize_first_letter(data["apellidoPaterno"]),
            apellido_materno=capitalize_first_letter(data.get("apellidoMaterno") or ""),
            telefono=(data.get("telefono") or "").strip(),
            estado=data.get("estado", Prospecto.Estado.PASAJERO),
            observaciones=(data.get("observaciones") or "").strip(),
            registrado_por=request.user,
            sucursal_registro=branch,
        )

        return Response(
            {"detail": "Prospecto registrado correctamente.", "prospect": _prospect_item(prospecto)},
            status=201,
        )

    @action(detail=False, methods=["get"], url_path="verificar-duplicados")
    def verificar_duplicados(self, request):
        """
        GET /prospectos/verificar-duplicados/?primerNombre=X&apellidoPaterno=Y&...
        Check for duplicate prospects.
        """
        primer_nombre = (request.query_params.get("primerNombre") or request.query_params.get("nombres") or "").strip()
        segundo_nombre = (request.query_params.get("segundoNombre") or "").strip()
        apellido_paterno = (request.query_params.get("apellidoPaterno") or request.query_params.get("apellidos") or "").strip()
        apellido_materno = (request.query_params.get("apellidoMaterno") or "").strip()
        telefono = (request.query_params.get("telefono") or "").strip()

        if not primer_nombre or not apellido_paterno:
            return Response({"detail": "Primer nombre y apellido paterno son requeridos."}, status=400)

        # Build duplicate filter
        duplicate_filter = Q(primer_nombre__iexact=primer_nombre, apellido_paterno__iexact=apellido_paterno)
        if segundo_nombre:
            duplicate_filter |= Q(
                primer_nombre__iexact=primer_nombre,
                segundo_nombre__iexact=segundo_nombre,
                apellido_paterno__iexact=apellido_paterno,
            )
        if apellido_materno:
            duplicate_filter |= Q(
                primer_nombre__iexact=primer_nombre,
                apellido_paterno__iexact=apellido_paterno,
                apellido_materno__iexact=apellido_materno,
            )
        if telefono:
            duplicate_filter |= Q(telefono=telefono)

        duplicates = Prospecto.objects.filter(duplicate_filter).exclude(estado=Prospecto.Estado.CONVERTIDO)

        if duplicates.exists():
            match = duplicates.first()
            branch = match.sucursal_registro
            branch_info = f"{branch.nombre} ({branch.ciudad})" if branch else "otra sucursal"
            return Response({
                "exists": True,
                "message": f"Atencion: Ya existe un prospecto con datos similares ({match}) registrado en {branch_info}.",
                "match": {
                    "id": match.pk,
                    "name": str(match),
                    "branch": branch_info,
                },
            })

        return Response({"exists": False})

    def retrieve(self, request, pk=None):
        """
        GET /prospectos/<int:prospecto_id>/
        Get prospect detail (returns full prospect item).
        """
        prospecto = Prospecto.objects.filter(pk=pk).first()
        if not prospecto:
            return Response({"detail": "No encontramos el prospecto solicitado."}, status=404)
        return Response({"prospect": _prospect_item(prospecto)})

    def update(self, request, pk=None):
        """
        POST /prospectos/<int:prospecto_id>/
        Update a prospect (name, phone, observations, state).
        """
        prospecto = Prospecto.objects.filter(pk=pk).first()
        if not prospecto:
            return Response({"detail": "No encontramos el prospecto solicitado."}, status=404)

        payload = request.data

        if "firstName" in payload or "primerNombre" in payload:
            prospecto.primer_nombre = capitalize_first_letter(payload.get("primerNombre") or payload.get("firstName"))
        if "segundoNombre" in payload:
            prospecto.segundo_nombre = capitalize_first_letter(payload.get("segundoNombre"))
        if "lastName" in payload or "apellidoPaterno" in payload:
            prospecto.apellido_paterno = capitalize_first_letter(payload.get("apellidoPaterno") or payload.get("lastName"))
        if "apellidoMaterno" in payload:
            prospecto.apellido_materno = capitalize_first_letter(payload.get("apellidoMaterno"))
        if "phone" in payload:
            prospecto.telefono = payload["phone"]
        if "observations" in payload:
            prospecto.observaciones = payload["observations"]
        if "stateValue" in payload:
            requested_state = (payload.get("stateValue") or "").strip().upper()
            if requested_state in {Prospecto.Estado.PASAJERO, Prospecto.Estado.DESCARTADO}:
                prospecto.estado = requested_state
            elif requested_state:
                return Response(
                    {"detail": "El estado seleccionado no es valido para este prospecto."},
                    status=400,
                )

        errors = {}
        if not prospecto.primer_nombre:
            errors["primerNombre"] = "El primer nombre es obligatorio."
        if not prospecto.apellido_paterno:
            errors["apellidoPaterno"] = "El apellido paterno es obligatorio."
        if errors:
            return Response({"detail": "Hay errores en el formulario.", "errors": errors}, status=400)

        prospecto.save()

        # Handle appointment status updates
        appointment_statuses = payload.get("appointmentStatuses", {})
        if appointment_statuses:
            for app_id_str, new_status in appointment_statuses.items():
                try:
                    app_id = int(app_id_str)
                    appointment = CitaProspecto.objects.filter(pk=app_id, prospecto=prospecto).first()
                    if appointment and new_status in CitaProspecto.Estado.values:
                        appointment.estado = new_status
                        appointment.save()
                except (ValueError, TypeError):
                    continue

        return Response({
            "detail": "Datos del prospecto y estados de citas actualizados correctamente.",
            "prospect": _prospect_item(prospecto),
        })

    @action(detail=True, methods=["post"], url_path="migrar")
    def migrar(self, request, pk=None):
        """
        POST /prospectos/<int:prospecto_id>/migrar/
        Migrate prospect to a different branch.
        """
        prospecto = Prospecto.objects.filter(pk=pk).first()
        if not prospecto:
            return Response({"detail": "No encontramos el prospecto solicitado."}, status=404)

        serializer = ProspectMigrateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        from catalogs.models import Sucursal
        branch_id = serializer.validated_data["branchId"]
        branch = Sucursal.objects.filter(pk=branch_id).first()
        if not branch:
            return Response({"detail": "La sucursal no existe."}, status=404)

        prospecto.sucursal_registro = branch
        prospecto.save(update_fields=["sucursal_registro", "updated_at"])

        return Response({
            "detail": f"Prospecto migrado exitosamente a {branch.nombre}.",
            "branch": {"id": branch.id, "name": branch.nombre},
        })

    @action(detail=True, methods=["get"], url_path="cita-medica/disponibilidad")
    def medical_availability(self, request, pk=None):
        """
        GET /prospectos/<int:prospecto_id>/cita-medica/disponibilidad/?branchId=X
        Get medical appointment availability for a prospect.
        """
        prospecto = Prospecto.objects.filter(pk=pk).first()
        if not prospecto:
            return Response({"detail": "No encontramos el prospecto solicitado."}, status=404)
        if prospecto.estado != Prospecto.Estado.PASAJERO:
            return Response({"detail": "Solo se pueden agendar citas para prospectos no convertidos."}, status=400)

        service_config = _medical_appointment_service_config()
        if not service_config:
            return Response(
                {"detail": "No existe un servicio activo de cita medica o consulta para agendar prospectos."},
                status=400,
            )

        branch_id = request.query_params.get("branchId")
        if branch_id:
            try:
                branch_id = int(branch_id)
            except ValueError:
                branch_id = 1
        else:
            branch_id = 1

        return Response({
            "prospect": _prospect_item(prospecto),
            "service": {
                "rawId": service_config.pk,
                "name": service_config.tipo_servicio.tipo,
            },
            "calendar": _build_prospect_medical_slot_map(service_config, branch_id=branch_id),
        })

    @action(detail=True, methods=["post"], url_path="cita-medica/reservar")
    def create_medical_appointment(self, request, pk=None):
        """
        POST /prospectos/<int:prospecto_id>/cita-medica/reservar/
        Create a medical appointment for a prospect.
        """
        prospecto = (
            Prospecto.objects.prefetch_related("citas_medicas")
            .filter(pk=pk)
            .first()
        )
        if not prospecto:
            return Response({"detail": "No encontramos el prospecto solicitado."}, status=404)
        if prospecto.estado != Prospecto.Estado.PASAJERO:
            return Response({"detail": "Solo se pueden agendar citas para prospectos no convertidos."}, status=400)
        if prospecto.citas_medicas.filter(estado=CitaProspecto.Estado.PROGRAMADA).exists():
            return Response({"detail": "Este prospecto ya tiene una cita medica programada."}, status=400)

        service_config = _medical_appointment_service_config()
        if not service_config:
            return Response(
                {"detail": "No existe un servicio activo de cita medica o consulta para agendar prospectos."},
                status=400,
            )

        serializer = ProspectMedicalAppointmentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        fecha_hora = serializer.validated_data["dateTime"]
        if timezone.is_naive(fecha_hora):
            fecha_hora = timezone.make_aware(fecha_hora)

        sucursal_id = serializer.validated_data["branchId"]

        appointment = CitaProspecto.objects.create(
            prospecto=prospecto,
            servicio_config=service_config,
            sucursal_id=sucursal_id,
            fecha_hora=fecha_hora,
            estado=CitaProspecto.Estado.PROGRAMADA,
            detalles_cita="Cita medica agendada libremente por administracion.",
        )

        return Response(
            {
                "detail": "La cita medica fue agendada correctamente para el prospecto.",
                "appointment": _prospect_appointment_item(appointment),
            },
            status=201,
        )

    @action(detail=False, methods=["post"], url_path="citas/(?P<appointment_id>[0-9]+)/actualizar")
    def update_prospect_appointment(self, request, appointment_id=None):
        """
        POST /prospectos/citas/<int:appointment_id>/actualizar/
        Update a prospect appointment status.
        """
        appointment = (
            CitaProspecto.objects.select_related("prospecto")
            .filter(pk=appointment_id)
            .first()
        )
        if not appointment:
            return Response({"detail": "No encontramos la cita solicitada."}, status=404)

        serializer = ProspectAppointmentUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos insuficientes."}, status=400)

        new_status = serializer.validated_data["status"]
        appointment.estado = new_status
        appointment.save()

        return Response({
            "detail": "Cita medica actualizada correctamente.",
            "prospect": _prospect_item(appointment.prospecto),
        })

    @action(detail=False, methods=["post"], url_path="citas-medicas/(?P<appointment_id>[0-9]+)/cancelar")
    def cancel_prospect_appointment(self, request, appointment_id=None):
        """
        POST /prospectos/citas-medicas/<int:appointment_id>/cancelar/
        Cancel a prospect medical appointment.
        """
        appointment = (
            CitaProspecto.objects.select_related("prospecto", "servicio_config__tipo_servicio")
            .filter(pk=appointment_id)
            .first()
        )
        if not appointment:
            return Response({"detail": "No encontramos la cita solicitada."}, status=404)
        if appointment.estado != CitaProspecto.Estado.PROGRAMADA:
            return Response({"detail": "Solo se pueden cancelar citas programadas."}, status=400)

        appointment.estado = CitaProspecto.Estado.CANCELADA
        appointment.detalles_cita = "Cita medica de prospecto cancelada desde administracion."
        appointment.save(update_fields=["estado", "detalles_cita", "updated_at"])

        return Response({
            "detail": "La cita medica del prospecto fue cancelada correctamente.",
            "appointment": _prospect_appointment_item(appointment),
        })
