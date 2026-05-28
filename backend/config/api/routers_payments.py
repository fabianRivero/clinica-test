"""
DRF Router configuration for payment endpoints.
Domain 3 of Phase 6.
"""

from rest_framework.routers import DefaultRouter

from config.api.viewsets.payments import PagosViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r"pagos", PagosViewSet, basename="admin-pagos")