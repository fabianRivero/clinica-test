from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from config.views import healthcheck


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/admin/", include("config.api_urls")),
    path("api/client/", include("config.client_api_urls")),
    path("api/auth/", include("config.auth_urls")),
    path("api/tickets/", include("config.ticket_urls")),
    path("api/notifications/", include("config.notification_urls")),
    path("api/biometric/", include("biometric.urls")),
    path("api/especialista/", include("config.especialista_urls")),
    # Phase 2 of dp4500-host-app-integration-phase2. New namespace
    # for the host-app-side surface that consumes DP4500 estandar's
    # service API. Kept distinct from the legacy
    # ``api/biometric/`` (fprintd flow, deprecated in Phase 4).
    path(
        "api/integration/dp4500/",
        include("dp4500_integration.urls"),
    ),
    path("health/", healthcheck, name="healthcheck"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
