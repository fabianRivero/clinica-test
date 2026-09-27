from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Cuentas de usuario"

    def ready(self) -> None:
        # Phase 2 of dp4500-host-app-integration-phase2. Importing the
        # signals module registers the pre_save handler on Usuario that
        # mints biometric_external_id. Load LAST so the signal chain
        # order is deterministic.
        from accounts import signals  # noqa: F401
