"""
DRF Router configuration for Domain 8 — Operations + Appointments + Offline Confirmation.
"""

from rest_framework.routers import DefaultRouter

from config.api.viewsets.operaciones import (
    OperacionesViewSet,
    CitasViewSet,
    OfflineConfirmationViewSet,
)

# OperacionesViewSet router — /operaciones/
operaciones_d8_router = DefaultRouter(trailing_slash=False)
operaciones_d8_router.register(r"operaciones", OperacionesViewSet, basename="admin-operacion")

# CitasViewSet router — /citas/
citas_d8_router = DefaultRouter(trailing_slash=False)
citas_d8_router.register(r"citas", CitasViewSet, basename="admin-citas")

# OfflineConfirmationViewSet router — /citas/offline/
offline_d8_router = DefaultRouter(trailing_slash=False)
offline_d8_router.register(r"citas/offline", OfflineConfirmationViewSet, basename="admin-offline-confirmation")
