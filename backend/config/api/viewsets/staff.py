"""
Staff viewsets for DRF migration.
Domain 4 of Phase 6 — Staff management and Branch Admins.
"""

from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import Usuario
from staff.models import Especialista, Especialidad, EspecialistaEspecialidad
from operations.models import CitaMedica

from config.api.permissions import AdminRequired, AdminPrincipalRequired
from config.api.serializers.staff import (
    BranchAdminSerializer,
    BranchAdminCreateSerializer,
    BranchAdminUpdateSerializer,
    BranchAdminToggleSerializer,
    EspecialistaSerializer,
    SpecialistCreateSerializer,
    SpecialistUpdateSerializer,
    SpecialistToggleSerializer,
)
from config.api_helpers import get_user_branch


class BranchAdminsViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for branch admin user management.
    Only main admins (AdminPrincipalRequired) can manage branch admins.

    Endpoints:
    - GET  /equipo/admins-sucursal/                    → list branch admins
    - POST /equipo/admins-sucursal/crear/              → create branch admin
    - GET  /equipo/admins-sucursal/<int:user_id>/      → branch admin detail
    - POST /equipo/admins-sucursal/<int:user_id>/actualizar/ → update
    - POST /equipo/admins-sucursal/<int:user_id>/estado/     → toggle active
    """

    permission_classes = [AdminPrincipalRequired]

    def list(self, request):
        """GET /equipo/admins-sucursal/ — list all branch admins."""
        admins = (
            Usuario.objects.select_related("sucursal", "rol")
            .filter(rol__rol="ADMIN_SUCURSAL")
            .order_by("-is_active", "username")
        )
        return Response({
            "admins": [self._branch_admin_item(admin) for admin in admins]
        })

    def create(self, request):
        """POST /equipo/admins-sucursal/crear/ — create a new branch admin."""
        serializer = BranchAdminCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": serializer.errors},
                status=400,
            )

        try:
            user = serializer.save()
        except ValidationError as exc:
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": exc.message_dict},
                status=400,
            )
        except IntegrityError:
            return Response(
                {"detail": "Este nombre de usuario ya existe."},
                status=409,
            )

        return Response(
            {
                "detail": "Administrador de sucursal creado como inactivo.",
                "admin": self._branch_admin_item(user),
            },
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, pk=None):
        """GET /equipo/admins-sucursal/<int:user_id>/ — get branch admin detail."""
        user = Usuario.objects.select_related("sucursal", "rol").filter(
            pk=pk, rol__rol="ADMIN_SUCURSAL"
        ).first()
        if not user:
            return Response(
                {"detail": "No encontramos el administrador solicitado."},
                status=404,
            )
        return Response({"admin": self._branch_admin_item(user)})

    def update(self, request, pk=None):
        """POST /equipo/admins-sucursal/<int:user_id>/actualizar/ — update branch admin."""
        user = Usuario.objects.select_related("sucursal", "rol").filter(
            pk=pk, rol__rol="ADMIN_SUCURSAL"
        ).first()
        if not user:
            return Response(
                {"detail": "No encontramos el administrador solicitado."},
                status=404,
            )

        serializer = BranchAdminUpdateSerializer(data=request.data, instance=user)
        if not serializer.is_valid():
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": serializer.errors},
                status=400,
            )

        try:
            user = serializer.save()
        except IntegrityError:
            return Response({"detail": "Este nombre de usuario ya existe."}, status=409)

        return Response({
            "detail": "Administrador de sucursal actualizado.",
            "admin": self._branch_admin_item(user),
        })

    @action(detail=True, methods=["post"], url_path="estado")
    def toggle_active(self, request, pk=None):
        """POST /equipo/admins-sucursal/<int:user_id>/estado/ — toggle active state."""
        user = Usuario.objects.select_related("sucursal", "rol").filter(
            pk=pk, rol__rol="ADMIN_SUCURSAL"
        ).first()
        if not user:
            return Response(
                {"detail": "No encontramos el administrador solicitado."},
                status=404,
            )

        data = request.data
        active = data.get("active")
        if not isinstance(active, bool):
            return Response(
                {"detail": "Debes indicar active true/false."},
                status=400,
            )

        old_branch = user.sucursal
        user.is_active = active
        if not active:
            if old_branch and old_branch.activa:
                has_other_admin = (
                    Usuario.objects.filter(
                        rol__rol="ADMIN_SUCURSAL",
                        is_active=True,
                        sucursal=old_branch,
                    ).exclude(pk=user.pk).exists()
                    or Usuario.objects.filter(
                        rol__rol="ADMIN_PRINCIPAL",
                        is_active=True,
                        sucursal=old_branch,
                    ).exists()
                )
                if not has_other_admin:
                    return Response(
                        {"detail": "No puedes inactivar este administrador porque la sucursal activa quedaria sin admin."},
                        status=409,
                    )
            user.sucursal = None

        user.save()
        return Response({
            "detail": "Estado actualizado.",
            "admin": self._branch_admin_item(user),
        })

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _branch_admin_item(self, user):
        return {
            "id": user.pk,
            "username": user.username,
            "email": user.email or "",
            "primerNombre": user.primer_nombre,
            "segundoNombre": user.segundo_nombre or "",
            "apellidoPaterno": user.apellido_paterno,
            "apellidoMaterno": user.apellido_materno or "",
            "telefono": user.telefono or "",
            "fechaNacimiento": (
                user.fecha_nacimiento.isoformat() if user.fecha_nacimiento else None
            ),
            "isActive": user.is_active,
            "sucursal": {
                "id": user.sucursal.pk if user.sucursal else None,
                "nombre": user.sucursal.nombre if user.sucursal else None,
            },
        }


class StaffViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for specialist/team management.

    Endpoints:
    - GET  /equipo/                                    → list staff with metrics
    - POST /equipo/crear/                            → create specialist
    - POST /equipo/<int:specialist_id>/actualizar/   → update specialist
    - POST /equipo/<int:specialist_id>/estado/       → toggle specialist active
    - POST /equipo/<int:user_id>/cambiar-sucursal/   → change specialist branch
    """

    permission_classes = [AdminRequired]

    def list(self, request):
        """GET /equipo/ — list specialists with metrics."""
        branch = get_user_branch(request)
        staff_qs = (
            Especialista.objects.select_related("usuario", "sucursal_base")
            .prefetch_related("especialidades_rel__especialidad")
            .order_by("-usuario__is_active", "usuario__primer_nombre", "usuario__apellido_paterno")
        )
        if branch:
            staff_qs = staff_qs.filter(sucursal_base=branch)

        upcoming_appointments_qs = CitaMedica.objects.filter(fecha_hora__gte=timezone.now())
        pending_biometric_qs = CitaMedica.objects.filter(
            estado=CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA
        )
        if branch:
            upcoming_appointments_qs = upcoming_appointments_qs.filter(sucursal=branch)
            pending_biometric_qs = pending_biometric_qs.filter(sucursal=branch)

        active_staff = staff_qs.filter(usuario__is_active=True).count()
        inactive_staff = staff_qs.filter(usuario__is_active=False).count()

        return Response({
            "metrics": [
                {
                    "id": "team-specialists",
                    "label": "Especialistas activos",
                    "value": str(active_staff),
                    "delta": "Usuarios con perfil operativo asignado",
                    "tone": "primary",
                },
                {
                    "id": "team-specialties",
                    "label": "Especialidades",
                    "value": str(Especialidad.objects.filter(activo=True).count()),
                    "delta": "Catalogo editable desde administracion",
                    "tone": "success",
                },
                {
                    "id": "team-agenda",
                    "label": "Citas futuras",
                    "value": str(upcoming_appointments_qs.count()),
                    "delta": "Carga agendada a partir de hoy",
                    "tone": "warning",
                },
                {
                    "id": "team-biometric",
                    "label": "Pendientes de biometria",
                    "value": str(pending_biometric_qs.count()),
                    "delta": "Citas realizadas sin cierre final",
                    "tone": "danger",
                },
                {
                    "id": "team-inactive",
                    "label": "Especialistas inactivos",
                    "value": str(inactive_staff),
                    "delta": "Sin disponibilidad publicada",
                    "tone": "warning",
                },
            ],
            "staff": [self._staff_item(es) for es in staff_qs],
            "specialtyOptions": [
                {"id": e.pk, "nombre": e.nombre}
                for e in Especialidad.objects.filter(activo=True).order_by("orden", "nombre")
            ],
        })

    def create(self, request):
        """POST /equipo/crear/ — create a new specialist."""
        serializer = SpecialistCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": serializer.errors},
                status=400,
            )

        try:
            especialista = serializer.save()
        except ValidationError as exc:
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": exc.message_dict},
                status=400,
            )
        except IntegrityError:
            return Response(
                {"detail": "Ya existe un especialista o usuario con esos datos."},
                status=400,
            )

        especialista = (
            Especialista.objects.select_related("usuario", "sucursal_base")
            .prefetch_related("especialidades_rel__especialidad")
            .get(pk=especialista.pk)
        )
        return Response(
            {
                "detail": "Especialista creado correctamente.",
                "staffMember": self._staff_item(especialista),
            },
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, specialist_id=None):
        """POST /equipo/<int:specialist_id>/actualizar/ — update specialist."""
        especialista = (
            Especialista.objects.select_related("usuario")
            .prefetch_related("especialidades_rel")
            .filter(pk=specialist_id)
            .first()
        )
        if not especialista:
            return Response(
                {"detail": "No encontramos el especialista solicitado."},
                status=404,
            )

        serializer = SpecialistUpdateSerializer(data=request.data, instance=especialista)
        if not serializer.is_valid():
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": serializer.errors},
                status=400,
            )

        old_branch_id = especialista.sucursal_base_id
        try:
            especialista = serializer.save()
        except IntegrityError:
            return Response(
                {"detail": "Ya existe un especialista o usuario con esos datos."},
                status=400,
            )

        if old_branch_id and especialista.sucursal_base_id != old_branch_id:
            self._clear_specialist_availability(especialista)

        especialista = (
            Especialista.objects.select_related("usuario", "sucursal_base")
            .prefetch_related("especialidades_rel__especialidad")
            .get(pk=especialista.pk)
        )
        return Response({
            "detail": "Especialista actualizado correctamente.",
            "staffMember": self._staff_item(especialista),
        })

    @action(detail=True, methods=["post"], url_path="estado")
    def toggle_status(self, request, specialist_id=None):
        """POST /equipo/<int:specialist_id>/estado/ — toggle specialist active."""
        especialista = (
            Especialista.objects.select_related("usuario")
            .filter(pk=specialist_id)
            .first()
        )
        if not especialista:
            return Response(
                {"detail": "No encontramos el especialista solicitado."},
                status=404,
            )

        active = request.data.get("active")
        if not isinstance(active, bool):
            return Response(
                {"detail": "Debes indicar si el especialista quedara activo o inactivo."},
                status=400,
            )

        especialista.usuario.is_active = active
        especialista.usuario.save(update_fields=["is_active"])

        if not active:
            self._clear_specialist_availability(especialista)

        especialista = (
            Especialista.objects.select_related("usuario", "sucursal_base")
            .prefetch_related("especialidades_rel__especialidad")
            .get(pk=especialista.pk)
        )
        return Response({
            "detail": (
                "Especialista activado correctamente."
                if active
                else "Especialista desactivado y disponibilidad eliminada correctamente."
            ),
            "staffMember": self._staff_item(especialista),
        })

    @action(detail=False, methods=["post"], url_path="(?P<user_id>[^/]+)/cambiar-sucursal")
    def change_branch(self, request, user_id=None):
        """POST /equipo/<int:user_id>/cambiar-sucursal/ — reassign specialist branch."""
        from operations.models import AgendaHabitualEspecialista, AgendaExcepcionEspecialista

        especialista = (
            Especialista.objects.select_related("usuario", "sucursal_base")
            .filter(pk=user_id)
            .first()
        )
        if not especialista:
            return Response(
                {"detail": "No encontramos el especialista solicitado."},
                status=404,
            )

        new_branch_id = request.data.get("branchId")
        if not new_branch_id:
            return Response(
                {"detail": "Debes indicar la nueva sucursal (branchId)."},
                status=400,
            )

        new_branch = None
        try:
            new_branch = Especialidad.objects.get(pk=new_branch_id).pk  # placeholder
            from catalogs.models import Sucursal
            new_branch = Sucursal.objects.get(pk=new_branch_id)
        except Exception:
            pass

        if not new_branch:
            return Response(
                {"detail": "Sucursal no encontrada."},
                status=404,
            )

        old_branch_id = especialista.sucursal_base_id
        especialista.sucursal_base = new_branch
        especialista.save()

        if old_branch_id != new_branch.pk:
            self._clear_specialist_availability(especialista)

        especialista = (
            Especialista.objects.select_related("usuario", "sucursal_base")
            .prefetch_related("especialidades_rel__especialidad")
            .get(pk=especialista.pk)
        )
        return Response({
            "detail": "Especialista reasignado a la nueva sucursal.",
            "staffMember": self._staff_item(especialista),
        })

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _staff_item(self, especialista):
        return {
            "id": especialista.pk,
            "usuario": {
                "id": especialista.usuario.pk,
                "nombre": especialista.usuario.nombre_completo,
                "isActive": especialista.usuario.is_active,
                "telefono": especialista.usuario.telefono or "",
            },
            "especialidades": [
                {"id": rel.especialidad.pk, "nombre": rel.especialidad.nombre}
                for rel in especialista.especialidades_rel.all()
            ],
            "sucursalBase": (
                {"id": especialista.sucursal_base.pk, "nombre": especialista.sucursal_base.nombre}
                if especialista.sucursal_base else None
            ),
            "puedeAbrirFichas": especialista.puede_abrir_fichas,
        }

    def _clear_specialist_availability(self, especialista):
        from operations.models import AgendaHabitualEspecialista, AgendaExcepcionEspecialista
        AgendaHabitualEspecialista.objects.filter(especialista=especialista).delete()
        AgendaExcepcionEspecialista.objects.filter(especialista=especialista).delete()