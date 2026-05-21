from django.urls import path

from notifications.views import mark_all_notifications_read, mark_notification_read, my_notifications

urlpatterns = [
    path("", my_notifications, name="notifications-list"),
    path("mark-all-read/", mark_all_notifications_read, name="notifications-mark-all-read"),
    path("<int:notification_id>/read/", mark_notification_read, name="notifications-mark-read"),
]
