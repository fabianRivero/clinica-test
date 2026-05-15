from django.urls import path

from config.ticket_views import (
    admin_ticket_open_permission,
    admin_ticket_open_permission_status,
    tickets_close,
    tickets_create,
    tickets_detail,
    tickets_list,
    tickets_reopen,
    tickets_reply,
)

urlpatterns = [
    path('', tickets_list, name='tickets-list'),
    path('crear/', tickets_create, name='tickets-create'),
    path('<int:ticket_id>/', tickets_detail, name='tickets-detail'),
    path('<int:ticket_id>/responder/', tickets_reply, name='tickets-reply'),
    path('<int:ticket_id>/cerrar/', tickets_close, name='tickets-close'),
    path('<int:ticket_id>/reabrir/', tickets_reopen, name='tickets-reopen'),
    path('permisos/apertura/', admin_ticket_open_permission, name='tickets-open-permission'),
    path('permisos/apertura/estado/', admin_ticket_open_permission_status, name='tickets-open-permission-status'),
]
