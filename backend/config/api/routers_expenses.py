"""
DRF Router configuration for expense endpoints.
Domain 2 of Phase 6.
"""

from rest_framework.routers import DefaultRouter

from config.api.viewsets.expenses import GastosViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r"gastos", GastosViewSet, basename="admin-gastos")