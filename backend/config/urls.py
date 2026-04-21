from django.contrib import admin
from django.urls import include, path

from config.views import healthcheck


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/admin/", include("config.api_urls")),
    path("api/client/", include("config.client_api_urls")),
    path("api/auth/", include("config.auth_urls")),
    path("health/", healthcheck, name="healthcheck"),
]
