filepath = "config/api_urls.py"
with open(filepath, "r") as f:
    content = f.read()

# Replace the old admin_availability_views import block
old_import = """from config.admin_availability_views import (
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
)"""

new_import = """from config.admin_availability_views import (
    admin_availability,
    admin_create_habitual_schedule,
    admin_create_specialist_exception,
    admin_delete_habitual_schedule,
    admin_delete_specialist_exception,
    admin_manage_global_day,
    admin_update_habitual_schedule,
    admin_check_concurrency,
)"""

content = content.replace(old_import, new_import)

# Replace the availability routes block
old_routes = """    path("disponibilidad/", admin_availability, name="admin-availability-api"),
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
    ),"""

new_routes = """    path("disponibilidad/", admin_availability, name="admin-availability-api"),
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
    path(
        "disponibilidad/concurrencia/",
        admin_check_concurrency,
        name="admin-availability-check-concurrency-api",
    ),"""

content = content.replace(old_routes, new_routes)

with open(filepath, "w") as f:
    f.write(content)

print("Done api_urls")
