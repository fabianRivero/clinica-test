from django.urls import path

from config.admin_availability_views import (
    admin_availability,
    admin_create_habitual_schedule,
    admin_create_specialist_exception,
    admin_create_time_slot,
    admin_delete_habitual_schedule,
    admin_delete_specialist_exception,
    admin_delete_time_slot,
    admin_manage_global_day,
    admin_remove_visible_slot,
    admin_update_habitual_schedule,
    admin_update_time_slot,
)
from config.api_views import (
    admin_actualizar_especialista,
    admin_catalogo_actualizar,
    admin_catalogo_crear,
    admin_catalogo_detalle,
    admin_catalogo_estado,
    admin_cancel_appointment,
    admin_catalogos,
    admin_crear_especialista,
    admin_crear_prospecto,
    admin_dashboard,
    admin_equipo,
    admin_estado_especialista,
    admin_operacion_detalle,
    admin_operaciones,
    admin_pagos,
    admin_prospectos,
    admin_update_payment_status,
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
    path("citas/<int:appointment_id>/cancelar/", admin_cancel_appointment, name="admin-appointment-cancel-api"),
    path("disponibilidad/", admin_availability, name="admin-availability-api"),
    path(
        "disponibilidad/cupos/<int:slot_id>/retirar/",
        admin_remove_visible_slot,
        name="admin-availability-visible-slot-remove-api",
    ),
    path("disponibilidad/horarios/crear/", admin_create_time_slot, name="admin-availability-time-slot-create-api"),
    path(
        "disponibilidad/horarios/<int:slot_id>/actualizar/",
        admin_update_time_slot,
        name="admin-availability-time-slot-update-api",
    ),
    path(
        "disponibilidad/horarios/<int:slot_id>/eliminar/",
        admin_delete_time_slot,
        name="admin-availability-time-slot-delete-api",
    ),
    path(
        "disponibilidad/habitual/crear/",
        admin_create_habitual_schedule,
        name="admin-availability-habitual-create-api",
    ),
    path(
        "disponibilidad/habitual/<int:rule_id>/actualizar/",
        admin_update_habitual_schedule,
        name="admin-availability-habitual-update-api",
    ),
    path(
        "disponibilidad/habitual/<int:rule_id>/eliminar/",
        admin_delete_habitual_schedule,
        name="admin-availability-habitual-delete-api",
    ),
    path(
        "disponibilidad/excepciones/crear/",
        admin_create_specialist_exception,
        name="admin-availability-exception-create-api",
    ),
    path(
        "disponibilidad/excepciones/<int:exception_id>/eliminar/",
        admin_delete_specialist_exception,
        name="admin-availability-exception-delete-api",
    ),
    path(
        "disponibilidad/global/gestionar/",
        admin_manage_global_day,
        name="admin-availability-global-manage-api",
    ),
    path("pagos/", admin_pagos, name="admin-pagos-api"),
    path("pagos/configuracion-qr/", admin_update_payment_qr_config, name="admin-pagos-qr-config-api"),
    path("pagos/<int:payment_id>/estado/", admin_update_payment_status, name="admin-pagos-status-api"),
    path("catalogos/", admin_catalogos, name="admin-catalogos-api"),
    path("catalogos/<slug:catalog_key>/", admin_catalogo_detalle, name="admin-catalogo-detail-api"),
    path("catalogos/<slug:catalog_key>/crear/", admin_catalogo_crear, name="admin-catalogo-create-api"),
    path(
        "catalogos/<slug:catalog_key>/<int:item_id>/actualizar/",
        admin_catalogo_actualizar,
        name="admin-catalogo-update-api",
    ),
    path(
        "catalogos/<slug:catalog_key>/<int:item_id>/estado/",
        admin_catalogo_estado,
        name="admin-catalogo-state-api",
    ),
    path("equipo/", admin_equipo, name="admin-equipo-api"),
    path("equipo/crear/", admin_crear_especialista, name="admin-equipo-create-api"),
    path(
        "equipo/<int:specialist_id>/actualizar/",
        admin_actualizar_especialista,
        name="admin-equipo-update-api",
    ),
    path(
        "equipo/<int:specialist_id>/estado/",
        admin_estado_especialista,
        name="admin-equipo-status-api",
    ),
]
