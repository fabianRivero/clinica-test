"""URL patterns for the dp4500_integration app.

Phase 2 of dp4500-host-app-integration-phase2. Two endpoints:

  - GET/POST /api/integration/dp4500/wizard/prospecto/<id>/step-4/
  - POST /api/integration/dp4500/citas/<cita_id>/verificar/

Mounted by the clinic's main ``config/urls.py`` under
``api/integration/dp4500/``.
"""
from __future__ import annotations

from django.urls import path

from dp4500_integration.views import (
    CitaBiometricVerifyView,
    ConversionStepBiometricView,
)


urlpatterns = [
    path(
        "wizard/prospecto/<int:prospect_id>/step-4/",
        ConversionStepBiometricView.as_view(),
        name="integration-wizard-step-4",
    ),
    path(
        "citas/<int:cita_id>/verificar/",
        CitaBiometricVerifyView.as_view(),
        name="integration-cita-verify",
    ),
]
