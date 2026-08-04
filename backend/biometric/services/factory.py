"""Factory for the agent client.

Selects the agent client implementation based on the
``AGENT_CLIENT_CLASS`` env var (or Django setting). The default is
:class:`HttpAgentClient` (the real Cloudflare-Tunnel-exposed agent
introduced in PR #2). The mock remains available for tests and
management commands that want to run without hardware.

When ``settings.BIOMETRIC_SUSPENDED`` is true the factory returns a
:class:`SuspendedAgentClient` and skips dynamic class loading entirely
so a misconfigured ``AGENT_CLIENT_CLASS`` cannot re-enable the network
while the operational suspension is in effect.
"""

from __future__ import annotations

import importlib
import os

from biometric.services.agent_client import (
    BaseAgentClient,
    HttpAgentClient,
    MockAgentClient,
    SuspendedAgentClient,
)


DEFAULT_AGENT_CLASS = "biometric.services.agent_client.HttpAgentClient"


def get_agent_client() -> BaseAgentClient:
    """Return the configured agent client instance.

    Honors the ``AGENT_CLIENT_CLASS`` env var (or Django setting) so
    tests can swap in a fake. Defaults to :class:`HttpAgentClient`.
    Falls back to :class:`MockAgentClient` if the configured class
    can't be loaded so a misconfig never takes the whole backend down.

    When ``settings.BIOMETRIC_SUSPENDED`` is true the function returns
    a :class:`SuspendedAgentClient` BEFORE inspecting
    ``AGENT_CLIENT_CLASS`` or touching ``importlib``. The flag is
    authoritative: even an explicit ``AGENT_CLIENT_CLASS=HttpAgentClient``
    cannot bypass the operational suspension.
    """
    # Authoritative suspension short-circuit (change
    # `suspend-fingerprint-integration`). Imports are deferred to keep
    # settings access cheap and to avoid touching Django at import time.
    from django.conf import settings

    if getattr(settings, "BIOMETRIC_SUSPENDED", False):
        return SuspendedAgentClient()

    class_path = os.getenv("AGENT_CLIENT_CLASS", DEFAULT_AGENT_CLASS)
    module_path, _, attr = class_path.rpartition(".")
    if not module_path:
        # Last-resort: the user set a bare class name.
        return HttpAgentClient()
    try:
        module = importlib.import_module(module_path)
        cls = getattr(module, attr)
        return cls()
    except (ImportError, AttributeError):
        # If the configured class can't be loaded, fall back to the
        # mock so the app keeps running (a misconfig shouldn't take
        # down the entire backend).
        return MockAgentClient()


__all__ = ["get_agent_client"]
