"""Configuration loader for the fingerprint agent.

Reads an INI file (see ``config.ini.example``) and exposes a typed
:class:`AgentConfig` object. The agent exits with a clear error on
missing or malformed config so the systemd unit can mark the failure
loudly.

We intentionally use ``configparser`` (stdlib) instead of pulling in
``pydantic-settings`` for the agent, mirroring the rest of the
project's preference for thin dependencies.
"""

from __future__ import annotations

import configparser
import logging
import os
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


DEFAULTS: dict[str, dict[str, str]] = {
    "server": {
        "bind": "127.0.0.1:8765",
        "log_level": "INFO",
        "fingerprint_username": "fingerprint-agent",
    },
    "auth": {
        "raw_token": "",
    },
    "backend": {
        "api_base": "",
        "agent_id": "0",
        "heartbeat_interval_seconds": "60",
    },
    "device": {
        "name_match": "4500",
        "enroll_timeout_seconds": "60",
        "verify_timeout_seconds": "30",
    },
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentConfig:
    """Typed, immutable view of the agent's config."""

    bind_host: str
    bind_port: int
    log_level: str
    fingerprint_username: str
    raw_token: str
    backend_api_base: str
    agent_id: int
    heartbeat_interval_seconds: int
    device_name_match: str
    enroll_timeout_seconds: int
    verify_timeout_seconds: int

    @property
    def bind_url(self) -> str:
        return f"http://{self.bind_host}:{self.bind_port}"


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class ConfigError(ValueError):
    """Raised when the agent's config file is unreadable or invalid."""


def _parse_int(value: str, *, default: int, field: str) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field} must be an integer, got {value!r}") from exc


def load_config(path: str | os.PathLike[str]) -> AgentConfig:
    """Load :class:`AgentConfig` from an INI file.

    Missing sections are filled from :data:`DEFAULTS`. Unknown sections
    are tolerated so the operator can add personal notes without
    breaking the loader.

    Raises :class:`ConfigError` if the file is missing, malformed, or
    any required field is empty.
    """
    cp = configparser.ConfigParser()
    # Seed defaults so missing keys still resolve.
    cp.read_dict(DEFAULTS)

    file_path = Path(path)
    if not file_path.exists():
        raise ConfigError(f"Config file not found: {file_path}")
    if not file_path.is_file():
        raise ConfigError(f"Config path is not a regular file: {file_path}")

    parsed = cp.read(str(file_path), encoding="utf-8")
    if not parsed:
        raise ConfigError(f"Config file is empty or unreadable: {file_path}")

    bind = cp.get("server", "bind", fallback="127.0.0.1:8765").strip()
    if ":" not in bind:
        raise ConfigError(f"server.bind must be in HOST:PORT form, got {bind!r}")
    host, _, port_str = bind.rpartition(":")
    host = host.strip()
    port = _parse_int(port_str, default=8765, field="server.bind port")

    raw_token = cp.get("auth", "raw_token", fallback="").strip()
    if not raw_token:
        raise ConfigError(
            "auth.raw_token is required. Generate a token via "
            "POST /api/biometric/agents/ and paste it here."
        )

    backend_api_base = cp.get("backend", "api_base", fallback="").strip()
    if backend_api_base and not backend_api_base.startswith(("http://", "https://")):
        raise ConfigError(
            f"backend.api_base must start with http:// or https://, got {backend_api_base!r}"
        )

    cfg = AgentConfig(
        bind_host=host,
        bind_port=port,
        log_level=cp.get("server", "log_level", fallback="INFO").strip().upper(),
        fingerprint_username=cp.get(
            "server", "fingerprint_username", fallback="fingerprint-agent"
        ).strip(),
        raw_token=raw_token,
        backend_api_base=backend_api_base.rstrip("/"),
        agent_id=_parse_int(
            cp.get("backend", "agent_id", fallback="0"),
            default=0,
            field="backend.agent_id",
        ),
        heartbeat_interval_seconds=_parse_int(
            cp.get("backend", "heartbeat_interval_seconds", fallback="60"),
            default=60,
            field="backend.heartbeat_interval_seconds",
        ),
        device_name_match=cp.get("device", "name_match", fallback="4500").strip(),
        enroll_timeout_seconds=_parse_int(
            cp.get("device", "enroll_timeout_seconds", fallback="60"),
            default=60,
            field="device.enroll_timeout_seconds",
        ),
        verify_timeout_seconds=_parse_int(
            cp.get("device", "verify_timeout_seconds", fallback="30"),
            default=30,
            field="device.verify_timeout_seconds",
        ),
    )
    logger.info(
        "Loaded agent config: bind=%s:%d heartbeat=%ds backend=%s",
        cfg.bind_host,
        cfg.bind_port,
        cfg.heartbeat_interval_seconds,
        cfg.backend_api_base or "(none)",
    )
    return cfg


__all__ = ["AgentConfig", "ConfigError", "load_config"]
