"""Entry point for the fingerprint agent.

Run via::

    python server.py --config /etc/fingerprint-agent/config.ini

The script parses arguments, loads the config, builds the FastAPI
app, and starts uvicorn. The bridge is constructed BEFORE the
server starts so any D-Bus / fprintd errors fail-fast at boot.

Environment variables:

- ``AGENT_BRIDGE``: ``fprintd`` (default) or ``memory``. ``memory``
  skips the D-Bus call and returns synthetic data — useful for smoke
  tests on developer laptops without a USB reader.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow the agent to fall back to system-distributed dbus-python +
# PyGObject when the venv cannot compile those C extensions (e.g. on
# Ubuntu 24.04 where the girepository-2.0 pkg-config file was removed
# from libgirepository1.0-dev). Harmless on systems where the venv
# already has them.
try:
    import dbus  # noqa: F401
    import gi  # noqa: F401
except ImportError:
    sys.path.insert(0, "/usr/lib/python3/dist-packages")
    import dbus  # noqa: F401
    import gi  # noqa: F401

import uvicorn

from agent.app import build_app
from agent.config import ConfigError, load_config
from agent.fprintd_bridge import build_bridge
from agent.logging_config import configure_logging


logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clinic fingerprint agent (DigitalPersona 4500).",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="/etc/fingerprint-agent/config.ini",
        help="Path to the agent config.ini file.",
    )
    parser.add_argument(
        "--bind",
        type=str,
        default=None,
        help="Override the bind HOST:PORT (defaults to config.ini).",
    )
    parser.add_argument(
        "--bridge",
        choices=("fprintd", "memory"),
        default=None,
        help="Bridge driver (defaults to AGENT_BRIDGE env or 'fprintd').",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate config and exit (no server).",
    )
    return parser.parse_args(argv)


def _resolve_bridge_name(args: argparse.Namespace) -> str:
    if args.bridge is not None:
        return args.bridge
    import os

    return os.getenv("AGENT_BRIDGE", "fprintd")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        # We deliberately print to stderr and exit non-zero so the
        # systemd unit can mark the failure loudly.
        sys.stderr.write(f"fingerprint-agent: {exc}\n")
        return 2

    configure_logging(config.log_level)
    logger.info("Loaded config from %s", args.config)

    if args.check:
        logger.info("Config OK; exiting --check.")
        return 0

    # Build the bridge eagerly so failures are surfaced before uvicorn
    # has a chance to bind the port.
    bridge = build_bridge(
        driver=_resolve_bridge_name(args),
        fingerprint_username=config.fingerprint_username,
        device_name_match=config.device_name_match,
        enroll_timeout_seconds=config.enroll_timeout_seconds,
        verify_timeout_seconds=config.verify_timeout_seconds,
    )

    app = build_app(config, bridge=bridge)

    # Allow --bind override for smoke tests.
    host = config.bind_host
    port = config.bind_port
    if args.bind:
        if ":" not in args.bind:
            sys.stderr.write("--bind must be in HOST:PORT form\n")
            return 2
        host, _, port_str = args.bind.rpartition(":")
        host = host.strip()
        try:
            port = int(port_str)
        except ValueError:
            sys.stderr.write(f"--bind port {port_str!r} is not an integer\n")
            return 2

    logger.info("Starting uvicorn on %s:%d (bridge=%s)", host, port, _resolve_bridge_name(args))
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=config.log_level.lower(),
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
