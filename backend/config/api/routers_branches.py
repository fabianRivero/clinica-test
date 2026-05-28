"""
DRF Router configuration for branch endpoints.
Domain 5 of Phase 6.
"""

from rest_framework.routers import DefaultRouter

from config.api.viewsets.branches import BranchesViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r"sucursales", BranchesViewSet, basename="admin-branch")