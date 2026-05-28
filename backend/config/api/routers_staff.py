"""
DRF Router configuration for staff endpoints.
Domain 4 of Phase 6 — Staff + Branch Admins.
"""

from rest_framework.routers import DefaultRouter

from config.api.viewsets.staff import StaffViewSet, BranchAdminsViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r"equipo", StaffViewSet, basename="admin-equipo")
router.register(r"equipo/admins-sucursal", BranchAdminsViewSet, basename="admin-branch-admins")