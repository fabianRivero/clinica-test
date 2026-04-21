from django.urls import path

from config.api_views import (
    admin_catalogos,
    admin_dashboard,
    admin_equipo,
    admin_operaciones,
    admin_pagos,
    admin_prospectos,
)


urlpatterns = [
    path("dashboard/", admin_dashboard, name="admin-dashboard-api"),
    path("prospectos/", admin_prospectos, name="admin-prospectos-api"),
    path("operaciones/", admin_operaciones, name="admin-operaciones-api"),
    path("pagos/", admin_pagos, name="admin-pagos-api"),
    path("catalogos/", admin_catalogos, name="admin-catalogos-api"),
    path("equipo/", admin_equipo, name="admin-equipo-api"),
]
