"""Factory for the agent client.

Selects the agent client implementation based on the
``AGENT_CLIENT_CLASS`` env var (or Django setting). The default is
:class:`HttpAgentClient` (the real Cloudflare-Tunnel-exposed agent
introduced in PR #2). The mock remains available for tests and
management commands that want to run without hardware.
"""

from __future__ import annotations

import importlib
import os

from biometric.services.agent_client import (
    BaseAgentClient,
    HttpAgentClient,
    MockAgentClient,
)


DEFAULT_AGENT_CLASS = "biometric.services.agent_client.HttpAgentClient"


def get_agent_client() -> BaseAgentClient:
    """Return the configured agent client instance.

    Honors the ``AGENT_CLIENT_CLASS`` env var (or Django setting) so
    tests can swap in a fake. Defaults to :class:`HttpAgentClient`.
    Falls back to :class:`MockAgentClient` if the configured class
    can't be loaded so a misconfig never takes the whole backend down.
    """
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
