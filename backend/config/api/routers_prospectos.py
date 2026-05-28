"""
DRF Router configuration for Domain 7 — Prospects + Conversion.
"""

from rest_framework.routers import DefaultRouter

from config.api.viewsets.prospectos import ProspectosViewSet
from config.api.viewsets.conversion import ProspectoConversionViewSet, ClientReactivationViewSet

# ProspectosViewSet router — handles prospect CRUD + medical appointments
prospectos_router = DefaultRouter(trailing_slash=False)
prospectos_router.register(r"prospectos", ProspectosViewSet, basename="admin-prospecto")

# ProspectoConversionViewSet — handles prospect conversion wizard
conversion_router = DefaultRouter(trailing_slash=False)
conversion_router.register(r"prospectos", ProspectoConversionViewSet, basename="admin-prospecto-conversion")

# ClientReactivationViewSet — handles client reactivation wizard
reactivation_router = DefaultRouter(trailing_slash=False)
reactivation_router.register(r"clientes", ClientReactivationViewSet, basename="admin-cliente-reactivation")
