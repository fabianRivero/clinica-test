from django.urls import path

from config.worker_views import worker_availability


worker_urlpatterns = [
    path("disponibilidad/", worker_availability, name="worker-availability-api"),
]