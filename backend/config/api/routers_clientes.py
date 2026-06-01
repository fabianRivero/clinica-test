"""
DRF Router configuration for client-related endpoints.
Domain 6 of Phase 6.

Three routers:
- clientes_router:    /clientes/ (search, detail, inactivate, migrar)
- operaciones_router: /operaciones/<id>/reserva/ (reservation availability + create)
- free_medical_router: /citas-medicas-libres/<client_id>/ (free medical appointment)
"""

from rest_framework.routers import DefaultRouter

from config.api.viewsets.clientes import (
    ClientesViewSet,
    OperacionesViewSet,
    FreeMedicalAppointmentViewSet,
)

# ClientesViewSet router
clientes_router = DefaultRouter(trailing_slash=False)
clientes_router.register(r"clientes", ClientesViewSet, basename="admin-cliente")

# OperacionesViewSet router (operation reservations)
operaciones_router = DefaultRouter(trailing_slash=False)
operaciones_router.register(r"operaciones", OperacionesViewSet, basename="admin-operacion")

# FreeMedicalAppointmentViewSet router
free_medical_router = DefaultRouter(trailing_slash=True)
free_medical_router.register(r"citas-medicas-libres", FreeMedicalAppointmentViewSet, basename="admin-citas-medicas-libres")
