"""Biometric app config.

Registers the DigitalPersona 4500 backend integration: encrypted template
storage, audit log, agent token lifecycle, and HTTP/JSON endpoints.
"""

from django.apps import AppConfig


class BiometricConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "biometric"
    verbose_name = "Biometria DigitalPersona 4500"
