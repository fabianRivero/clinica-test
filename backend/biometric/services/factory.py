"""Factory for the agent client.

PR #1 always returns :class:`MockAgentClient`. PR #2 will swap to
:class:`HttpAgentClient` when the real agent goes live. Keeping a
factory here lets tests and management commands override the class
without touching view code.
"""

from __future__ import annotations

import importlib
import os

from biometric.services.agent_client import BaseAgentClient, MockAgentClient


DEFAULT_AGENT_CLASS = "biometric.services.agent_client.MockAgentClient"


def get_agent_client() -> BaseAgentClient:
    """Return the configured agent client instance.

    Honors the ``AGENT_CLIENT_CLASS`` env var (or Django setting) so
    tests can swap in a fake. Defaults to :class:`MockAgentClient`.
    """
    class_path = os.getenv("AGENT_CLIENT_CLASS", DEFAULT_AGENT_CLASS)
    module_path, _, attr = class_path.rpartition(".")
    if not module_path:
        # Last-resort: the user set a bare class name.
        return MockAgentClient()
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
