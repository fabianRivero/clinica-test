"""URL routing for the specialist-only API surface."""

from django.urls import path

from config.api_views import especialista_mis_citas


urlpatterns = [
    path(
        "mis-citas/",
        especialista_mis_citas,
        name="especialista-mis-citas-api",
    ),
]