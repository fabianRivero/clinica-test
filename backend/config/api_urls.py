from django.urls import path

from config.admin_availability_views import admin_availability, admin_create_availability
from config.api_views import (
    admin_catalogos,
    admin_crear_prospecto,
    admin_dashboard,
    admin_equipo,
    admin_operacion_detalle,
    admin_operaciones,
    admin_pagos,
    admin_prospectos,
    admin_update_payment_qr_config,
)
from config.prospect_conversion_views import (
    admin_prospect_conversion_cancel,
    admin_prospect_conversion_detail,
    admin_prospect_conversion_finalize,
    admin_prospect_conversion_medical_step,
    admin_prospect_conversion_operation_step,
    admin_prospect_conversion_user_step,
)


urlpatterns = [
    path("dashboard/", admin_dashboard, name="admin-dashboard-api"),
    path("prospectos/", admin_prospectos, name="admin-prospectos-api"),
    path("prospectos/crear/", admin_crear_prospecto, name="admin-prospectos-create-api"),
    path(
        "prospectos/<int:prospecto_id>/conversion/",
        admin_prospect_conversion_detail,
        name="admin-prospect-conversion-detail-api",
    ),
    path(
        "prospectos/<int:prospecto_id>/conversion/cancelar/",
        admin_prospect_conversion_cancel,
        name="admin-prospect-conversion-cancel-api",
    ),
    path(
        "prospectos/<int:prospecto_id>/conversion/paso-1/",
        admin_prospect_conversion_user_step,
        name="admin-prospect-conversion-user-step-api",
    ),
    path(
        "prospectos/<int:prospecto_id>/conversion/paso-2/",
        admin_prospect_conversion_operation_step,
        name="admin-prospect-conversion-operation-step-api",
    ),
    path(
        "prospectos/<int:prospecto_id>/conversion/paso-3/",
        admin_prospect_conversion_medical_step,
        name="admin-prospect-conversion-medical-step-api",
    ),
    path(
        "prospectos/<int:prospecto_id>/conversion/finalizar/",
        admin_prospect_conversion_finalize,
        name="admin-prospect-conversion-finalize-api",
    ),
    path("operaciones/", admin_operaciones, name="admin-operaciones-api"),
    path("operaciones/<int:operacion_id>/", admin_operacion_detalle, name="admin-operacion-detail-api"),
    path("disponibilidad/", admin_availability, name="admin-availability-api"),
    path("disponibilidad/crear/", admin_create_availability, name="admin-availability-create-api"),
    path("pagos/", admin_pagos, name="admin-pagos-api"),
    path("pagos/configuracion-qr/", admin_update_payment_qr_config, name="admin-pagos-qr-config-api"),
    path("catalogos/", admin_catalogos, name="admin-catalogos-api"),
    path("equipo/", admin_equipo, name="admin-equipo-api"),
]
