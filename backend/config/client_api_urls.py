from django.urls import path
from config.client_api_views import (
    client_dashboard,
    client_treatments,
    client_payments,
    client_upload_payment_receipt,
    client_reservations,
    client_reservation_availability,
    client_edit_reservation_availability,
    client_create_reservation,
    client_update_reservation,
    client_cancel_reservation,
)

urlpatterns = [
    path("dashboard/", client_dashboard, name="client-dashboard-api"),
    path("tratamientos/", client_treatments, name="client-treatments-api"),
    path("pagos/", client_payments, name="client-payments-api"),
    path("pagos/cuotas/<int:quota_id>/comprobante/", client_upload_payment_receipt, name="client-upload-receipt-api"),
    path("reservas/", client_reservations, name="client-reservations-api"),
    path("operaciones/<int:operation_id>/disponibilidad/", client_reservation_availability, name="client-reservation-availability-api"),
    path("citas/<int:appointment_id>/disponibilidad/", client_edit_reservation_availability, name="client-edit-reservation-availability-api"),
    path("operaciones/<int:operation_id>/reservar/", client_create_reservation, name="client-reservation-create-api"),
    path("citas/<int:appointment_id>/actualizar/", client_update_reservation, name="client-reservation-update-api"),
    path("citas/<int:appointment_id>/cancelar/", client_cancel_reservation, name="client-reservation-cancel-api"),
]
