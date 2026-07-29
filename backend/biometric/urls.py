"""URL routing for the biometric endpoints.

Mounted at ``/api/biometric/`` in ``config/urls``.

Because we use function-based views (matching the rest of the
codebase) and a single path serves both ``POST`` (create) and ``GET``
(list), the helpers in :mod:`biometric.routing` wrap the views with a
method dispatcher.
"""

from django.urls import path

from biometric import routing
from biometric import views


app_name = "biometric"


urlpatterns = [
    path(
        "clientes/<int:cliente_id>/huella/enroll/",
        views.enroll_init,
        name="cliente-huella-enroll",
    ),
    path(
        "prospectos/<int:prospect_id>/huella/enroll/",
        views.prospect_enroll_init,
        name="prospecto-huella-enroll",
    ),
    path(
        "clientes/<int:cliente_id>/huella/enroll/finalize/",
        views.enroll_finalize,
        name="cliente-huella-enroll-finalize",
    ),
    path(
        "citas/<int:cita_id>/huella/verify-init/",
        views.verify_init,
        name="cita-huella-verify-init",
    ),
    path(
        "citas/<int:cita_id>/huella/verify-confirm/",
        views.verify_confirm,
        name="cita-huella-verify-confirm",
    ),
    path(
        "citas/<int:cita_id>/huella/confirm-manual/",
        views.confirm_manual,
        name="cita-huella-confirm-manual",
    ),
    path(
        "agents/",
        routing.dispatch_agent_root,
        name="agent-root",
    ),
    path(
        "agents/<int:agent_id>/heartbeat/",
        views.agent_heartbeat,
        name="agent-heartbeat",
    ),
    path(
        "agents/<int:agent_id>/",
        routing.dispatch_agent_detail,
        name="agent-detail",
    ),
]


__all__ = ["urlpatterns"]
