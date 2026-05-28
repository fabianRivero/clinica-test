"""
DRF Router configuration for Domain 9 — Disponibilidad (Availability Management).
"""

from rest_framework.routers import DefaultRouter

from config.api.viewsets.disponibilidad import DisponibilidadViewSet

disponibilidad_router = DefaultRouter(trailing_slash=False)
disponibilidad_router.register(r"disponibilidad", DisponibilidadViewSet, basename="admin-disponibilidad")
