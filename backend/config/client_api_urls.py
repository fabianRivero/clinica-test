from django.urls import path

from config.client_api_views import (
    client_create_reservation,
    client_dashboard,
    client_payments,
    client_reservation_availability,
    client_reservations,
    client_treatments,
)


urlpatterns = [
    path("dashboard/", client_dashboard, name="client-dashboard-api"),
    path("tratamientos/", client_treatments, name="client-treatments-api"),
    path("pagos/", client_payments, name="client-payments-api"),
    path("reservas/", client_reservations, name="client-reservations-api"),
    path(
        "reservas/<int:operation_id>/disponibilidad/",
        client_reservation_availability,
        name="client-reservation-availability-api",
    ),
    path(
        "reservas/<int:operation_id>/crear/",
        client_create_reservation,
        name="client-reservation-create-api",
    ),
]
