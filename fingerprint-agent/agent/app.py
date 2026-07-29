"""FastAPI app factory for the fingerprint agent.

Wires:

- ``GET  /health``  — unauthenticated (no bearer required).
- ``POST /capture`` — bearer-protected; defers to :mod:`agent.capture`.
- ``POST /match``   — bearer-protected; defers to :mod:`agent.match`.
- ``POST /heartbeat`` — bearer-protected; defers to :mod:`agent.heartbeat`.

The agent server is intended to be launched via ``server.py`` which
parses CLI args, loads config, and calls :func:`build_app`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI

from agent import capture, heartbeat, match


if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from agent.config import AgentConfig
    from agent.fprintd_bridge import FprintdBridge, InMemoryBridge


logger = logging.getLogger(__name__)


def build_app(
    config: "AgentConfig",
    *,
    bridge: "FprintdBridge | InMemoryBridge | None" = None,
) -> FastAPI:
    """Construct the FastAPI ``app`` instance.

    Parameters
    ----------
    config:
        Agent configuration (loaded from ``config.ini``).
    bridge:
        Optional pre-built bridge (mostly useful for tests). When
        ``None`` the app picks up the bridge from ``app.state`` which
        is set by ``server.py`` at startup.
    """

    app = FastAPI(
        title="Clinic Fingerprint Agent",
        version="0.2.0",
        description=(
            "Local HTTP service that wraps the DigitalPersona 4500 "
            "reader on each admin PC. Exposes /capture, /match, "
            "/heartbeat and /health."
        ),
    )

    # Store the bridge on app.state so request handlers can pull it
    # out of the lifespan if server.py assigns it before uvicorn
    # takes over.
    if bridge is not None:
        app.state.fprintd_bridge = bridge

    # ---------------------------------------------------------------
    # Health (unauthenticated)
    # ---------------------------------------------------------------
    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        bridge_name = getattr(app.state, "fprintd_bridge", None)
        return {
            "status": "ok",
            "device": getattr(bridge_name, "device_name", "unknown"),
        }

    # ---------------------------------------------------------------
    # Protected routes
    # ---------------------------------------------------------------
    capture.register(app, config)
    match.register(app, config)
    heartbeat.register(app, config)

    return app


__all__ = ["build_app"]
