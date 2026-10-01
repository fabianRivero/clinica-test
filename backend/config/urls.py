from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from config.views import healthcheck
from config.api_views_media import media_signed_url


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
    # Cloud-storage-migration (slice 2 of 4). Authenticated
    # presigned-URL minting with fail-closed audit log; see
    # ``config.api_views_media.media_signed_url``.
    path(
        "api/media/signed-url/",
        media_signed_url,
        name="media-signed-url",
    ),
    path("health/", healthcheck, name="healthcheck"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
