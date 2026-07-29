"""Shared pytest fixtures for the fingerprint agent tests.

The test suite runs without a real DigitalPersona reader. We swap in
the ``InMemoryBridge`` so ``/capture`` and ``/match`` return synthetic
data without touching the system bus.

For the dbus smoke test (``test_dbus_capture.py``) we expose a
``fprintd_installed`` fixture so the test can decide whether to skip
itself.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from agent.app import build_app
from agent.config import AgentConfig
from agent.fprintd_bridge import InMemoryBridge


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@pytest.fixture
def agent_config() -> AgentConfig:
    """Return a deterministic :class:`AgentConfig` for tests."""
    return AgentConfig(
        bind_host="127.0.0.1",
        bind_port=8765,
        log_level="WARNING",
        fingerprint_username="fingerprint-agent-test",
        raw_token="test-token-xyz",
        backend_api_base="",
        agent_id=0,
        heartbeat_interval_seconds=60,
        device_name_match="4500",
        enroll_timeout_seconds=10,
        verify_timeout_seconds=10,
    )


# ---------------------------------------------------------------------------
# App / client
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_bridge() -> InMemoryBridge:
    """Return a fresh in-memory bridge for tests."""
    return InMemoryBridge()


@pytest.fixture
def app(agent_config: AgentConfig, in_memory_bridge: InMemoryBridge):
    """Build the FastAPI app bound to the in-memory bridge."""
    return build_app(agent_config, bridge=in_memory_bridge)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    """Wrap the app in a FastAPI ``TestClient``."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Authorization helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return the bearer authorization header for the test token."""
    return {"Authorization": "Bearer test-token-xyz"}


@pytest.fixture
def bad_auth_headers() -> dict[str, str]:
    """Return an obviously wrong bearer header."""
    return {"Authorization": "Bearer wrong-token"}


# ---------------------------------------------------------------------------
# Smoke-test helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fprintd_installed() -> bool:
    """True if the system actually has fprintd installed."""
    return shutil.which("fprintd-list") is not None


# ---------------------------------------------------------------------------
# Config file temp dir
# ---------------------------------------------------------------------------


@pytest.fixture
def config_file(tmp_path: Path, agent_config: AgentConfig) -> Path:
    """Write a real config.ini file to a tmp_path and return its path."""
    path = tmp_path / "config.ini"
    path.write_text(
        "\n".join(
            [
                "[server]",
                f"bind = {agent_config.bind_host}:{agent_config.bind_port}",
                f"log_level = {agent_config.log_level}",
                f"fingerprint_username = {agent_config.fingerprint_username}",
                "",
                "[auth]",
                f"raw_token = {agent_config.raw_token}",
                "",
                "[backend]",
                "api_base = ",
                "agent_id = 0",
                "",
                "[device]",
                f"name_match = {agent_config.device_name_match}",
                f"enroll_timeout_seconds = {agent_config.enroll_timeout_seconds}",
                f"verify_timeout_seconds = {agent_config.verify_timeout_seconds}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path
