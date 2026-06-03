"""
DRF Router configuration for catalog endpoints.
Domain 1 of Phase 6.
"""

from rest_framework.routers import DefaultRouter

from config.api.viewsets.catalogs import CatalogsViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r"catálogos", CatalogsViewSet, basename="admin-catálogos")