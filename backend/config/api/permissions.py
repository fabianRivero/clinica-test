"""
Custom DRF permission classes replicating the @admin_required decorator logic.
"""

from rest_framework import permissions


class AdminRequired(permissions.BasePermission):
    """
    Replicates the @admin_required decorator:

    - 401 if not authenticated.
    - 403 if not an admin (superuser or ``es_administrador``).
    - 403 if the admin's branch is inactive (branch admins only).
    """

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if not (user.is_superuser or user.es_administrador):
            return False
        # Branch admins: check their branch is active
        if not (user.is_superuser or user.es_admin_principal):
            if not user.sucursal or not user.sucursal.activa:
                return False
        return True


class AdminPrincipalRequired(permissions.BasePermission):
    """
    Replicates @_admin_principal_required — only main/principal admins.
    Used for write operations (create/update/delete).
    """

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if not (user.is_superuser or user.es_admin_principal):
            return False
        return True