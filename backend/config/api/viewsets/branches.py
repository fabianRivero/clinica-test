"""
Branch viewsets for DRF migration.
Domain 5 of Phase 6 — most complex domain with wizard logic.
"""

from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from catalogs.models import Sucursal
from accounts.models import Usuario, Rol
from operations.models import BranchAdminAuditLog, TabletKiosko

from config.api.permissions import AdminRequired, AdminPrincipalRequired
from config.api.serializers.branches import (
    BranchSerializer,
    BranchCreateSerializer,
    BranchUpdateSerializer,
    BranchToggleSerializer,
    BranchDeactivationImpactSerializer,
    BranchChangeAdminSerializer,
    BranchWizardStep1Serializer,
    BranchWizardStep2Serializer,
    BranchWizardFinalizeSerializer,
    BranchAuditLogSerializer,
)
from config.api_helpers import get_user_branch

BRANCH_CREATE_WIZARD_SESSION_KEY = "branch_create_wizard_draft"


class BranchesViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for branch management.
    AdminPrincipalRequired for write operations (except session branch set).

    Endpoints:
    - GET  /sucursales/                         → list branches (filters: status, city, admin_name, branch_id)
    - POST /sucursales/crear/                   → create branch (simple form)
    - POST /sucursales/wizard/inicializar/      → initialize wizard
    - POST /sucursales/wizard/paso-1/           → wizard step 1 (branch data)
    - POST /sucursales/wizard/paso-2/           → wizard step 2 (admin assignment)
    - POST /sucursales/wizard/finalizar/        → wizard finalize + create branch+admin+tablet
    - POST /sucursales/<int:branch_id>/actualizar/     → update branch
    - POST /sucursales/<int:branch_id>/estado/        → toggle active
    - POST /sucursales/<int:branch_id>/cambiar-admin/ → change branch admin
    - GET  /sucursales/<int:branch_id>/deactivation-impact/ → deactivation impact
    - GET  /sucursales/auditoria/               → audit logs
    - POST /disponibilidad/sucursales/cambiar/  → set session branch (any admin)
    """

    permission_classes = [AdminRequired]

    # -------------------------------------------------------------------------
    # Session branch (no AdminPrincipal required — any admin)
    # -------------------------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="disponibilidad/sucursales/cambiar")
    def set_session_branch(self, request):
        """POST /disponibilidad/sucursales/cambiar/ — set active branch in session."""
        from config.api_helpers import get_user_branch
        branch = get_user_branch(request)
        if not branch:
            return Response({"detail": "No se pudo determinar la sucursal."}, status=400)
        return Response({"detail": "Sucursal seleccionada.", "branch": {"id": branch.pk, "name": branch.nombre}})

    # -------------------------------------------------------------------------
    # List branches (no AdminPrincipal — just AdminRequired for list)
    # -------------------------------------------------------------------------
    def list(self, request):
        """GET /sucursales/ — list branches with optional filters."""
        status_filter = (request.query_params.get("status") or "all").lower()
        city = (request.query_params.get("city") or "").strip()
        admin_name = (request.query_params.get("admin_name") or "").strip()
        branch_id = request.query_params.get("branch_id")

        branches = Sucursal.objects.all().order_by("nombre")
        if status_filter == "active":
            branches = branches.filter(activa=True)
        elif status_filter == "inactive":
            branches = branches.filter(activa=False)
        if city:
            branches = branches.filter(ciudad__icontains=city)
        if branch_id:
            branches = branches.filter(pk=branch_id)

        # Admin lookup for response enrichment
        admins = Usuario.objects.filter(
            rol__rol="ADMIN_SUCURSAL", is_active=True
        ).select_related("sucursal")
        if admin_name:
            admins = admins.filter(
                Q(primer_nombre__icontains=admin_name)
                | Q(apellido_paterno__icontains=admin_name)
                | Q(username__icontains=admin_name)
            )
            branches = branches.filter(pk__in=admins.values_list("sucursal_id", flat=True))
        admin_by_branch = {admin.sucursal_id: admin for admin in admins if admin.sucursal_id}

        items = []
        for branch in branches:
            admin = admin_by_branch.get(branch.id)
            items.append({
                "id": branch.id,
                "nombre": branch.nombre,
                "ciudad": branch.ciudad,
                "direccion": branch.direccion,
                "activa": branch.activa,
                "esPrincipal": branch.es_principal,
                "admin": {
                    "id": admin.pk,
                    "nombre": admin.nombre_completo,
                    "username": admin.username,
                } if admin else None,
            })
        return Response({"branches": items, "total": len(items)})

    # -------------------------------------------------------------------------
    # Create branch (simple form)
    # -------------------------------------------------------------------------
    def create(self, request):
        """POST /sucursales/crear/ — create a new branch (simple form)."""
        serializer = BranchCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": serializer.errors},
                status=400,
            )
        try:
            branch = serializer.save()
        except ValidationError as exc:
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": exc.message_dict},
                status=400,
            )
        except IntegrityError:
            return Response(
                {"detail": "Ya existe una sucursal con este nombre."},
                status=409,
            )
        return Response(
            {"detail": "Sucursal creada correctamente.", "branchId": branch.id},
            status=status.HTTP_201_CREATED,
        )

    # -------------------------------------------------------------------------
    # Update branch
    # -------------------------------------------------------------------------
    def update(self, request, branch_id=None):
        """POST /sucursales/<int:branch_id>/actualizar/ — update branch fields."""
        try:
            branch = Sucursal.objects.get(pk=branch_id)
        except Sucursal.DoesNotExist:
            return Response({"detail": "Sucursal no encontrada."}, status=404)

        serializer = BranchUpdateSerializer(data=request.data, instance=branch)
        if not serializer.is_valid():
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": serializer.errors},
                status=400,
            )
        try:
            branch = serializer.save()
        except IntegrityError:
            return Response({"detail": "Ya existe una sucursal con este nombre."}, status=409)

        return Response({"detail": "Sucursal actualizada correctamente."})

    # -------------------------------------------------------------------------
    # Toggle active
    # -------------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="estado")
    def toggle_active(self, request, branch_id=None):
        """POST /sucursales/<int:branch_id>/estado/ — toggle branch active state."""
        try:
            branch = Sucursal.objects.get(pk=branch_id)
        except Sucursal.DoesNotExist:
            return Response({"detail": "Sucursal no encontrada."}, status=404)

        data = request.data
        active = data.get("active")
        force = bool(data.get("force"))

        if not isinstance(active, bool):
            return Response(
                {"detail": "Debes indicar si la sucursal quedará activa o inactiva."},
                status=400,
            )

        impact = self._branch_deactivation_impact(branch)
        has_pending = any(impact.values())

        if active is False and has_pending and not force:
            return Response(
                {
                    "detail": "La sucursal tiene pendientes operativos.",
                    "impact": impact,
                    "requiresConfirmation": True,
                },
                status=409,
            )

        if active is True and not self._active_branch_has_any_admin(branch):
            return Response(
                {"detail": "No puedes activar una sucursal sin un administrador asignado."},
                status=409,
            )

        if active is False:
            branch_admin = Usuario.objects.filter(
                rol__rol="ADMIN_SUCURSAL",
                sucursal=branch,
                is_active=True,
            ).first()
            if branch_admin:
                branch_admin.is_active = False
                branch_admin.sucursal = None
                branch_admin.save(update_fields=["is_active", "sucursal", "updated_at"])

        branch.activa = active
        branch.save(update_fields=["activa", "updated_at"])

        self._log_branch_admin_audit(
            request, branch,
            BranchAdminAuditLog.Action.TOGGLE_BRANCH,
            f"Sucursal {'activada' if active else 'desactivada'}.",
            {"active": active, "force": force, "impact": impact, "adminDeactivated": branch_admin.id if active is False and branch_admin else None},
        )

        return Response({
            "detail": "Sucursal activada correctamente." if active else "Sucursal desactivada correctamente.",
            "impact": impact,
        })

    # -------------------------------------------------------------------------
    # Change admin
    # -------------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="cambiar-admin")
    def change_admin(self, request, branch_id=None):
        """POST /sucursales/<int:branch_id>/cambiar-admin/ — reassign branch admin."""
        try:
            branch = Sucursal.objects.get(pk=branch_id)
        except Sucursal.DoesNotExist:
            return Response({"detail": "Sucursal no encontrada."}, status=404)

        new_admin_id = request.data.get("newAdminUserId")
        if not new_admin_id:
            return Response({"detail": "newAdminUserId es obligatorio."}, status=400)

        try:
            new_admin = Usuario.objects.get(pk=new_admin_id)
        except Usuario.DoesNotExist:
            return Response({"detail": "Usuario no encontrado."}, status=404)

        if not (new_admin.rol and new_admin.rol.rol == "ADMIN_SUCURSAL"):
            return Response({"detail": "El usuario seleccionado no es admin de sucursal."}, status=400)

        current_main_admin = Usuario.objects.filter(
            rol__rol="ADMIN_PRINCIPAL",
            sucursal=branch,
            is_active=True,
        ).first()
        current_admin = (
            Usuario.objects.filter(rol__rol="ADMIN_SUCURSAL", sucursal=branch, is_active=True)
            .exclude(pk=new_admin.pk).first()
        )
        previous_branch = new_admin.sucursal
        selected_is_inactive = (not new_admin.is_active) or (new_admin.sucursal_id is None)

        if current_main_admin:
            if selected_is_inactive:
                return Response(
                    {"detail": "El administrador principal solo puede intercambiar con un admin de sucursal activo y con sucursal."},
                    status=409,
                )
            if not previous_branch:
                return Response(
                    {"detail": "El admin de sucursal seleccionado debe tener una sucursal activa para intercambiar con el admin principal."},
                    status=409,
                )
            new_admin.sucursal = branch
            new_admin.save(update_fields=["sucursal", "updated_at"])
            current_main_admin.sucursal = previous_branch
            current_main_admin.is_active = True
            current_main_admin.save(update_fields=["sucursal", "is_active", "updated_at"])
            self._log_branch_admin_audit(
                request, branch,
                BranchAdminAuditLog.Action.CHANGE_ADMIN,
                "Intercambio entre admin principal y admin de sucursal.",
                {
                    "mainAdminUserId": current_main_admin.id,
                    "newAdminUserId": new_admin.id,
                    "fromBranchId": previous_branch.id,
                    "mode": "swap_with_main_admin",
                },
            )
            return Response({"detail": "Intercambio con administrador principal realizado correctamente.", "mode": "swap_with_main_admin"})

        if selected_is_inactive:
            new_admin.is_active = True
            new_admin.sucursal = branch
            new_admin.save(update_fields=["is_active", "sucursal", "updated_at"])
            if current_admin:
                current_admin.is_active = False
                current_admin.sucursal = None
                current_admin.save(update_fields=["is_active", "sucursal", "updated_at"])
            self._log_branch_admin_audit(
                request, branch,
                BranchAdminAuditLog.Action.CHANGE_ADMIN,
                "Reemplazo por admin inactivo.",
                {"newAdminUserId": new_admin.id, "previousAdminUserId": current_admin.id if current_admin else None, "mode": "replace_with_inactive"},
            )
            return Response({"detail": "Administrador inactivo activado y asignado correctamente.", "mode": "replace_with_inactive"})

        if new_admin.sucursal_id == branch.id:
            return Response({"detail": "El administrador ya está asignado a esta sucursal.", "mode": "assign"})

        new_admin.sucursal = branch
        new_admin.save(update_fields=["sucursal", "updated_at"])
        if current_admin and previous_branch and previous_branch.id != branch.id:
            current_admin.sucursal = previous_branch
            current_admin.save(update_fields=["sucursal", "updated_at"])
            self._log_branch_admin_audit(
                request, branch,
                BranchAdminAuditLog.Action.CHANGE_ADMIN,
                "Intercambio de administradores entre sucursales.",
                {"newAdminUserId": new_admin.id, "previousAdminUserId": current_admin.id, "fromBranchId": previous_branch.id, "mode": "swap"},
            )
            return Response({"detail": "Administradores intercambiados correctamente.", "mode": "swap"})

        self._log_branch_admin_audit(
            request, branch,
            BranchAdminAuditLog.Action.CHANGE_ADMIN,
            "Asignación directa de administrador.",
            {"newAdminUserId": new_admin.id, "mode": "assign"},
        )
        return Response({"detail": "Administrador de sucursal actualizado correctamente.", "mode": "assign"})

    # -------------------------------------------------------------------------
    # Deactivation impact
    # -------------------------------------------------------------------------
    @action(detail=True, methods=["get"], url_path="deactivation-impact")
    def deactivation_impact(self, request, branch_id=None):
        """GET /sucursales/<int:branch_id>/deactivation-impact/ — check before deactivating."""
        try:
            branch = Sucursal.objects.get(pk=branch_id)
        except Sucursal.DoesNotExist:
            return Response({"detail": "Sucursal no encontrada."}, status=404)
        return Response({"branchId": branch.id, "impact": self._branch_deactivation_impact(branch)})

    # -------------------------------------------------------------------------
    # Audit logs
    # -------------------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="auditoria")
    def audit_logs(self, request):
        """GET /sucursales/auditoria/ — list branch admin audit logs."""
        branch_id = request.query_params.get("branchId")
        logs = BranchAdminAuditLog.objects.select_related("branch", "actor")
        if branch_id:
            logs = logs.filter(branch_id=branch_id)

        items = [
            {
                "id": log.id,
                "createdAt": log.created_at.isoformat(),
                "action": log.action,
                "detail": log.detail,
                "branchId": log.branch_id,
                "branchName": log.branch.nombre,
                "actor": log.actor.nombre_completo if log.actor else "Sistema",
                "metadata": log.metadata or {},
            }
            for log in logs[:200]
        ]
        return Response({"items": items, "total": len(items)})

    # -------------------------------------------------------------------------
    # Wizard endpoints (session-based multi-step)
    # -------------------------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="wizard/inicializar")
    def wizard_initialize(self, request):
        """POST /sucursales/wizard/inicializar/ — reset wizard session."""
        request.session[BRANCH_CREATE_WIZARD_SESSION_KEY] = {}
        request.session.modified = True
        return Response({"detail": "Wizard de sucursal inicializado.", "draft": {}})

    @action(detail=False, methods=["post"], url_path="wizard/paso-1")
    def wizard_step1(self, request):
        """POST /sucursales/wizard/paso-1/ — store branch data in session."""
        serializer = BranchWizardStep1Serializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": serializer.errors},
                status=400,
            )
        data = serializer.validated_data
        draft = request.session.get(BRANCH_CREATE_WIZARD_SESSION_KEY) or {}
        draft["branch"] = {
            "nombre": data["nombre"],
            "ciudad": data.get("ciudad", ""),
            "direccion": data.get("direccion", ""),
            "es_principal": data.get("esPrincipal", False),
            "especialistas_pueden_abrir_fichas": data.get("especialistasPuedenAbrirFichas", True),
        }
        request.session[BRANCH_CREATE_WIZARD_SESSION_KEY] = draft
        request.session.modified = True
        return Response({"detail": "Paso 1 guardado.", "draft": draft})

    @action(detail=False, methods=["post"], url_path="wizard/paso-2")
    def wizard_step2(self, request):
        """POST /sucursales/wizard/paso-2/ — store admin assignment in session."""
        serializer = BranchWizardStep2Serializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": serializer.errors},
                status=400,
            )

        draft = request.session.get(BRANCH_CREATE_WIZARD_SESSION_KEY) or {}
        if not draft.get("branch"):
            return Response({"detail": "Debes completar el paso 1 primero."}, status=409)

        data = serializer.validated_data
        mode = data["mode"]

        if mode == "existing_inactive":
            draft["admin"] = {"mode": "existing_inactive", "adminUserId": data["adminUserId"]}
        else:
            draft["admin"] = {
                "mode": "create_new",
                "username": data["username"],
                "email": data.get("email", ""),
                "primerNombre": data["primerNombre"],
                "segundoNombre": data.get("segundoNombre", ""),
                "apellidoPaterno": data["apellidoPaterno"],
                "apellidoMaterno": data.get("apellidoMaterno", ""),
                "ci": data["ci"],
                "telefono": data.get("telefono", ""),
                "password": data["password"],
            }

        request.session[BRANCH_CREATE_WIZARD_SESSION_KEY] = draft
        request.session.modified = True
        return Response({"detail": "Paso 2 guardado.", "draft": draft})

    @action(detail=False, methods=["post"], url_path="wizard/finalizar")
    def wizard_finalize(self, request):
        """POST /sucursales/wizard/finalizar/ — create branch + admin + tablet."""
        serializer = BranchWizardFinalizeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": serializer.errors},
                status=400,
            )

        draft = request.session.get(BRANCH_CREATE_WIZARD_SESSION_KEY) or {}
        branch_data = draft.get("branch")
        admin_data = draft.get("admin")

        if not branch_data or not admin_data:
            return Response({"detail": "Debes completar los pasos 1 y 2 antes de finalizar."}, status=409)

        nombre = serializer.validated_data["nombre"]
        clave = serializer.validated_data["clave"]

        branch = Sucursal.objects.create(**branch_data, activa=True)

        codigo = f"KIOSKO-{branch.id}"
        if TabletKiosko.objects.filter(codigo=codigo).exists():
            return Response({"detail": "No se pudo autogenerar un código único de tablet."}, status=409)

        if admin_data["mode"] == "existing_inactive":
            admin_user = Usuario.objects.get(pk=admin_data["adminUserId"])
            admin_user.is_active = True
            admin_user.sucursal = branch
            admin_user.save(update_fields=["is_active", "sucursal", "updated_at"])
        else:
            admin_user = Usuario(
                username=admin_data["username"],
                email=admin_data.get("email", ""),
                primer_nombre=admin_data["primerNombre"],
                segundo_nombre=admin_data.get("segundoNombre", ""),
                apellido_paterno=admin_data["apellidoPaterno"],
                apellido_materno=admin_data.get("apellidoMaterno", ""),
                rol=Rol.objects.get_or_create(rol="ADMIN_SUCURSAL")[0],
                sucursal=branch,
                is_active=True,
            )
            admin_user.set_password(admin_data["password"])
            admin_user.save()

        kiosko = TabletKiosko(codigo=codigo, nombre=nombre, sucursal=branch, activo=True)
        kiosko.set_clave(clave)
        kiosko.save()

        self._log_branch_admin_audit(
            request, branch,
            BranchAdminAuditLog.Action.CREATE_BRANCH_WIZARD,
            "Sucursal creada via wizard con admin y tablet.",
            {"adminUserId": admin_user.id, "tabletKioskId": kiosko.id},
        )

        request.session.pop(BRANCH_CREATE_WIZARD_SESSION_KEY, None)
        request.session.modified = True

        return Response({
            "detail": "Sucursal creada correctamente con administrador y tablet.",
            "branchId": branch.id,
            "adminUserId": admin_user.id,
            "tabletKioskId": kiosko.id,
            "tabletKioskCode": kiosko.codigo,
        }, status=status.HTTP_201_CREATED)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _branch_deactivation_impact(self, branch):
        from operations.models import CitaMedica, Operacion
        from customers.models import Prospecto
        from billing.models import PagoRealizado

        return {
            "pendingAppointments": CitaMedica.objects.filter(
                sucursal=branch, estado=CitaMedica.Estado.PROGRAMADA
            ).count(),
            "pendingOperations": Operacion.objects.filter(
                paciente__sucursal_registro=branch,
                estado__in=[Operacion.Estado.BORRADOR, Operacion.Estado.EN_PROCESO]
            ).count(),
            "pendingProspectAppointments": 0,
            "pendingPayments": PagoRealizado.objects.filter(
                cuota__operacion__paciente__sucursal_registro=branch,
                estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
            ).count(),
        }

    def _active_branch_has_any_admin(self, branch):
        return Usuario.objects.filter(
            rol__rol="ADMIN_SUCURSAL",
            is_active=True,
            sucursal=branch,
        ).exists() or Usuario.objects.filter(
            rol__rol="ADMIN_PRINCIPAL",
            is_active=True,
            sucursal=branch,
        ).exists()

    def _log_branch_admin_audit(self, request, branch, action, detail, metadata):
        BranchAdminAuditLog.objects.create(
            branch=branch,
            actor=request.user,
            action=action,
            detail=detail,
            metadata=metadata,
        )