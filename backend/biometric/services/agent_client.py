"""Agent client abstraction.

The biometric backend talks to a per-PC ``fingerprint-agent`` running
on the admin's machine; in PR #1 that agent does not exist yet, so we
ship a :class:`MockAgentClient` that returns deterministic fake
payloads. PR #2 will introduce :class:`HttpAgentClient` against the
real Cloudflare-Tunnel-exposed service.
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaptureResponse:
    """Payload returned by ``BaseAgentClient.capture``."""

    template_b64: str
    quality_score: int
    device_serial: str
    template_format: str = "DP_PROPRIETARY"
    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class MatchResponse:
    """Payload returned by ``BaseAgentClient.match``."""

    score: Decimal
    captured_template_b64: str


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class BaseAgentClient(Protocol):
    """Backend's view of the agent. PR #1's only impl is the mock."""

    def capture(self, enrollment_payload: dict) -> CaptureResponse: ...

    def match(self, template_bytes: bytes, capture_token: str) -> MatchResponse: ...


# ---------------------------------------------------------------------------
# Mock implementation
# ---------------------------------------------------------------------------


class MockAgentClient:
    """Deterministic fake used while the real agent is still under
    construction.

    Behavior is controlled via Django settings:

    - ``AGENT_QUALITY_SCORE`` (default ``80``)
    - ``AGENT_MATCH_SCORE`` (default ``0.93``)
    - ``AGENT_FAIL_WITH`` (default ``""``) — if set to a code like
      ``NO_IMAGE`` or ``LOW_QUALITY`` the client raises an exception
      so views can test their error-handling path.

    Captured templates are seeded from a fixed seed for the same
    ``capture_token`` so unit tests stay deterministic.
    """

    def __init__(
        self,
        quality_score: int | None = None,
        match_score: float | None = None,
        fail_with: str | None = None,
    ) -> None:
        self.quality_score = (
            int(os.getenv("AGENT_QUALITY_SCORE", "80"))
            if quality_score is None
            else quality_score
        )
        if match_score is None:
            raw_score = os.getenv("AGENT_MATCH_SCORE", "0.93")
            self.match_score = Decimal(str(raw_score))
        else:
            # Route floats through ``str`` so we never lose precision
            # to IEEE-754. ``Decimal(0.95)`` would otherwise yield
            # ``0.94999999999999995559107...``.
            self.match_score = Decimal(str(match_score))
        self.fail_with = (
            os.getenv("AGENT_FAIL_WITH", "")
            if fail_with is None
            else fail_with
        )

    def capture(self, enrollment_payload: dict) -> CaptureResponse:
        # Simulated hardware failure modes.
        if self.fail_with == "NO_IMAGE":
            raise AgentUnavailableError("NO_IMAGE: scanner returned no image")
        if self.fail_with == "LOW_QUALITY":
            return CaptureResponse(
                template_b64="",
                quality_score=10,
                device_serial="MOCK-LOW-Q",
                template_format="DP_PROPRIETARY",
            )

        # Deterministic template bytes for the given token so that an
        # enroll→match round trip works in tests.
        token = (enrollment_payload or {}).get("capture_token") or uuid.uuid4().hex
        template_bytes = self._seeded_template(token)
        quality = self.quality_score
        # When the configured quality is below the enrollment
        # acceptance threshold we return an empty template so the view
        # layer can short-circuit with a LOW_QUALITY error. This mirrors
        # the way a real DigitalPersona agent would only ship a
        # template once it considers the capture usable.
        if quality < 50:
            return CaptureResponse(
                template_b64="",
                quality_score=quality,
                device_serial="MOCK-LOW-Q",
                template_format="DP_PROPRIETARY",
            )
        return CaptureResponse(
            template_b64=template_bytes.hex(),
            quality_score=quality,
            device_serial="MOCK-DP-001",
            template_format="DP_PROPRIETARY",
            width=256,
            height=360,
        )

    def match(self, template_bytes: bytes, capture_token: str) -> MatchResponse:
        if self.fail_with == "AGENT_OFFLINE":
            raise AgentUnavailableError("AGENT_OFFLINE: tunnel not reachable")
        if self.fail_with == "NO_IMAGE":
            raise AgentUnavailableError("NO_IMAGE: scanner returned no image")

        # Re-emit a captured-template blob so the backend can store a
        # record of what the agent saw. The actual score is what we
        # report in ``score``; the spec keeps scoring server-side so
        # the agent's word is raw.
        return MatchResponse(
            score=self.match_score,
            captured_template_b64=secrets.token_hex(64),
        )

    @staticmethod
    def _seeded_template(capture_token: str) -> bytes:
        """Produce stable bytes for a given capture token.

        We hash the token with SHA-256 to get 32 bytes of "template".
        Tests can round-trip encrypt/decrypt this without depending on
        a real fingerprint scanner.
        """
        import hashlib

        return hashlib.sha256(capture_token.encode("utf-8")).digest()


# ---------------------------------------------------------------------------
# Stub HTTP client (PR #2 territory)
# ---------------------------------------------------------------------------


class HttpAgentClient:
    """Placeholder for the real HTTP client. PR #2."""

    def capture(self, enrollment_payload: dict) -> CaptureResponse:
        raise NotImplementedError(
            "HttpAgentClient is part of PR #2 (fingerprint-agent + tunnel)."
        )

    def match(self, template_bytes: bytes, capture_token: str) -> MatchResponse:
        raise NotImplementedError(
            "HttpAgentClient is part of PR #2 (fingerprint-agent + tunnel)."
        )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AgentUnavailableError(RuntimeError):
    """Raised when the agent cannot fulfill a capture/match request.

    Mapped to HTTP 503 at the view layer.
    """


__all__ = [
    "AgentUnavailableError",
    "BaseAgentClient",
    "CaptureResponse",
    "HttpAgentClient",
    "MatchResponse",
    "MockAgentClient",
]
