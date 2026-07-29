"""Structured logging for the agent.

Two responsibilities:

1. Configure a single, configurable logger that the rest of the agent
   uses via ``logging.getLogger(__name__)``.
2. Define a base64 redaction filter that mirrors the backend's
   ``BiometricLogScrubber`` so any long base64-like blob (>=256 chars)
   is replaced with ``<biometric-redacted>`` BEFORE the log record is
   serialized. The same filter is exported under ``BiometricLogScrubber``
   so the backend's pytest suite can import it for parity tests if
   needed.

We deliberately only use stdlib logging + structlog so the agent
runtime surface stays small.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Base64 scrubber
# ---------------------------------------------------------------------------


_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/=]{256,}")
_REDACTION = "<biometric-redacted>"


class BiometricLogScrubber(logging.Filter):
    """Replaces long base64-like blobs in log records.

    This mirrors ``backend.biometric.log_filters.BiometricLogScrubber``
    so the agent and the backend have a single, consistent redaction
    contract. The exact threshold (256 chars) and redaction sentinel
    are kept identical to the backend on purpose.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - std API
        try:
            msg = record.getMessage()
        except Exception:
            # If the message can't be formatted we let the record pass
            # through; refusing to log would be worse than a scrub miss.
            return True

        scrubbed = _BASE64_BLOB.sub(_REDACTION, msg)
        if scrubbed == msg:
            return True

        # Re-pack the record so subsequent getMessage() calls (by any
        # handler) return the scrubbed text.
        record.msg = scrubbed
        record.args = ()
        return True


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger once.

    Idempotent: re-running keeps the existing handler list intact so
    tests and uvicorn hot-reload don't double-print.
    """
    root = logging.getLogger()
    if any(getattr(h, "_biometric_agent", False) for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler.setFormatter(
        logging.Formatter(
            fmt="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(BiometricLogScrubber())
    handler._biometric_agent = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Quiet down uvicorn's default access log; the agent emits concise
    # messages per request via the route handlers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper that returns a named logger."""
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def scrub(value: Any) -> str:
    """Return a representation of ``value`` safe for logging.

    - Long base64-like blobs are replaced with ``<biometric-redacted>``.
    - Bytes are hex-encoded (no base64 expansion).
    - Anything else is converted via ``repr``.
    """
    if isinstance(value, (bytes, bytearray)):
        rendered = bytes(value).hex()
    else:
        rendered = str(value)
    return _BASE64_BLOB.sub(_REDACTION, rendered)


__all__ = [
    "BiometricLogScrubber",
    "configure_logging",
    "get_logger",
    "scrub",
]
