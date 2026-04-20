from django.contrib import admin
from django.urls import include, path

from config.views import healthcheck


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/admin/", include("config.api_urls")),
    path("health/", healthcheck, name="healthcheck"),
]
