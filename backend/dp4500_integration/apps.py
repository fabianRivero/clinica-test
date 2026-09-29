"""Django AppConfig for the dp4500_integration app.

Phase 2 of dp4500-host-app-integration-phase2. The app holds the
clinic-side HTTP client + cascade signal + Celery tasks that consume
DP4500 estandar's service API.
"""
from django.apps import AppConfig


class Dp4500IntegrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dp4500_integration"
    verbose_name = "Integración DP4500 (host-app)"

    def ready(self) -> None:
        # Phase 2 of dp4500-host-app-integration-phase2. Importing
        # signals registers the post_delete handler on Usuario that
        # triggers the cascade revoke Celery task.
        from dp4500_integration import signals  # noqa: F401
