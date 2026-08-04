"""Agent client abstraction.

The biometric backend talks to a per-PC ``fingerprint-agent`` running
on the admin's machine. Two implementations live in this module:

- :class:`MockAgentClient` — deterministic fake used while the agent
  is being built or in tests that don't want to hit the network.
- :class:`HttpAgentClient` — JSON-over-HTTPS client for the real
  Cloudflare-Tunnel-exposed service introduced in PR #2.

Both implementations honour the same :class:`BaseAgentClient`
protocol; the factory in :mod:`biometric.services.factory` selects
one based on the ``AGENT_CLIENT_CLASS`` setting / env var.
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol


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
    """Backend's view of the agent.

    Both methods take an :class:`AgentToken` instance so the client
    can pick up the public URL and the (Fernet-encrypted) raw bearer
    token. The mock implementation ignores those values and keeps
    returning deterministic data.
    """

    def capture(
        self,
        agent: Any,
        capture_token: str,
        finger_name: str = "any",
    ) -> CaptureResponse: ...

    def match(
        self,
        agent: Any,
        template_bytes: bytes,
        capture_token: str,
    ) -> MatchResponse: ...

    def release(
        self,
        agent: Any,
    ) -> None:
        """Reset the agent's device state.

        Called by the backend immediately before a match so fprintd's
        ``VerifyStart`` starts from a clean ``Release`` + ``Claim``
        cycle. Implementations must never raise on transport errors —
        a failed reset must not block the verify round-trip; the
        in-bridge ``_reset_claim`` is the second line of defence.
        """
        ...


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

    def capture(
        self,
        agent: Any,
        capture_token: str,
        finger_name: str = "any",
    ) -> CaptureResponse:
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
        token = capture_token or uuid.uuid4().hex
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

    def match(
        self,
        agent: Any,
        template_bytes: bytes,
        capture_token: str,
    ) -> MatchResponse:
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

    def release(self, agent: Any) -> None:
        """No-op for the in-memory agent.

        The mock never holds fprintd state, so there is nothing to
        reset. Keeping the method on the class honours
        :class:`BaseAgentClient` and lets views call it unconditionally.
        """
        return None

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
# Suspended implementation (change `suspend-fingerprint-integration`).
#
# Returned by :func:`biometric.services.factory.get_agent_client` while
# ``settings.BIOMETRIC_SUSPENDED`` is true. The class is intentionally
# fail-closed: ``capture``/``match``/``release`` all raise
# :class:`AgentUnavailableError` with code ``"BIOMETRIC_SUSPENDED"`` and
# never import ``httpx``, decrypt the agent token, resolve the public
# URL or open a socket. The factory short-circuits BEFORE dynamic class
# loading so even an unparseable ``AGENT_CLIENT_CLASS`` cannot reach the
# network while the flag is on.
#
# Unlike :class:`HttpAgentClient.release`, ``SuspendedAgentClient.release``
# raises the suspension error (not silently swallowed). The suspended
# mode is the operating state, not a transient transport failure, and
# callers should never silently "complete" a release they never issued.
# ---------------------------------------------------------------------------


class SuspendedAgentClient:
    """No-op client that refuses every operation while biometric
    integration is suspended.

    Implements the :class:`BaseAgentClient` protocol without inheriting
    from any active client. Holds no state. Any call to capture, match
    or release raises :class:`AgentUnavailableError` carrying the
    canonical ``BIOMETRIC_SUSPENDED`` code so the view layer can map
    the exception to the matching suspended HTTP 503 body.
    """

    _SUSPENDED_MESSAGE = "BIOMETRIC_SUSPENDED"

    def capture(
        self,
        agent: Any,
        capture_token: str,
        finger_name: str = "any",
    ) -> CaptureResponse:
        raise AgentUnavailableError(self._SUSPENDED_MESSAGE)

    def match(
        self,
        agent: Any,
        template_bytes: bytes,
        capture_token: str,
    ) -> MatchResponse:
        raise AgentUnavailableError(self._SUSPENDED_MESSAGE)

    def release(self, agent: Any) -> None:
        raise AgentUnavailableError(self._SUSPENDED_MESSAGE)


# ---------------------------------------------------------------------------
# Real HTTP client (PR #2)
# ---------------------------------------------------------------------------


class HttpAgentClient:
    """JSON-over-HTTPS client for the per-PC fingerprint agent.

    The agent is exposed publicly via a Cloudflare Tunnel (the
    hostname is stored on ``AgentToken.public_url``). The client
    fetches the raw bearer token from the encrypted blob on the
    ``AgentToken`` row and sends it as ``Authorization: Bearer <raw>``
    on every request.

    Errors are mapped to:

    - Any ``httpx`` transport failure → :class:`AgentUnavailableError`
      (the view layer maps that to a 503).
    - HTTP 4xx / 5xx → :class:`AgentUnavailableError` with the body
      snippet included so the view can pass a useful message.

    The client is intentionally direct (no retries, no pooling beyond
    httpx's connection pool) — the enroll/verify flow is
    human-driven and a retry on a transient failure would confuse
    the operator.
    """

    DEFAULT_TIMEOUT_SECONDS = 30.0

    def __init__(
        self,
        *,
        timeout_seconds: float | None = None,
        transport: Any | None = None,
    ) -> None:
        self._timeout = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else self.DEFAULT_TIMEOUT_SECONDS
        )
        # An optional transport (used by tests). When ``None`` we
        # build a fresh ``httpx.Client`` per call so import-time
        # side effects are limited (httpx keeps its own pool).
        self._transport = transport

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture(
        self,
        agent: Any,
        capture_token: str,
        finger_name: str = "any",
    ) -> CaptureResponse:
        """POST ``/capture`` to the agent and return the encrypted template."""
        url = self._agent_url(agent, "/capture")
        headers = self._auth_headers(agent)
        payload = {
            "capture_token": capture_token or uuid.uuid4().hex,
            "finger_name": finger_name or "any",
            "quality_required": 60,
        }

        logger.info("HttpAgentClient.capture -> %s token=%s", url, _hint(capture_token))
        data = self._post(url, headers, payload)
        return CaptureResponse(
            template_b64=str(data.get("template_b64", "")),
            quality_score=int(data.get("quality_score", 0)),
            device_serial=str(data.get("device_serial", "")),
            template_format=str(data.get("template_format", "DP_PROPRIETARY")),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
        )

    def match(
        self,
        agent: Any,
        template_bytes: bytes,
        capture_token: str,
    ) -> MatchResponse:
        """POST ``/match`` to the agent and return the raw score.

        Note: the captured template bytes are NOT sent in the wire
        payload. fprintd's D-Bus API doesn't expose a way to inject a
        reference template; the agent enforces the match against its
        own internal state. The bytes are kept here so we can evolve
        the protocol later without changing callers.
        """
        url = self._agent_url(agent, "/match")
        headers = self._auth_headers(agent)
        payload = {
            "capture_token": capture_token or uuid.uuid4().hex,
        }

        logger.info("HttpAgentClient.match -> %s token=%s", url, _hint(capture_token))
        data = self._post(url, headers, payload)
        return MatchResponse(
            score=Decimal(str(data.get("score", "0"))),
            captured_template_b64=str(data.get("captured_template_b64", "")),
        )

    def release(self, agent: Any) -> None:
        """POST ``/release`` to the agent to reset its fprintd state.

        Called by the view layer immediately before each
        ``/match`` so fprintd's ``VerifyStart`` starts from a clean
        Release+Claim cycle and the operator actually gets the full
        wait window to put a finger on the reader. We swallow every
        failure (``AgentUnavailableError``, ``httpx`` transport
        errors, non-2xx responses): a reset that fails must NEVER
        block the verify round-trip; the bridge's own
        ``_reset_claim`` is the second line of defence.
        """
        try:
            url = self._agent_url(agent, "/release")
            headers = self._auth_headers(agent)
        except AgentUnavailableError as exc:
            logger.info("HttpAgentClient.release skipped: %s", exc)
            return

        logger.info("HttpAgentClient.release -> %s", url)
        try:
            import httpx  # local import: optional dependency

            try:
                if self._transport is not None:
                    with httpx.Client(transport=self._transport, timeout=self._timeout) as client:
                        resp = client.post(url, headers=headers, json={})
                else:
                    with httpx.Client(timeout=self._timeout) as client:
                        resp = client.post(url, headers=headers, json={})
            except httpx.HTTPError as exc:
                logger.info("HttpAgentClient.release transport error (ignored): %s", exc)
                return
        except ImportError:  # pragma: no cover - install-time failure
            logger.info("HttpAgentClient.release skipped: httpx not installed")
            return

        if resp.status_code >= 400:
            logger.info(
                "HttpAgentClient.release got %d (ignored): %s",
                resp.status_code,
                (resp.text or "")[:200],
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _agent_url(self, agent: Any, path: str) -> str:
        public_url = getattr(agent, "public_url", None)
        if not public_url:
            raise AgentUnavailableError(
                "AgentToken has no public_url; cannot reach the agent."
            )
        # Normalize trailing slashes on the URL so the join is clean.
        base = str(public_url).rstrip("/")
        suffix = path if path.startswith("/") else f"/{path}"
        return f"{base}{suffix}"

    def _auth_headers(self, agent: Any) -> dict[str, str]:
        try:
            raw_token = agent.decrypt_raw_token()
        except Exception as exc:  # noqa: BLE001 - deliberately broad
            raise AgentUnavailableError(
                f"Could not decrypt agent token: {exc}"
            ) from exc
        return {
            "Authorization": f"Bearer {raw_token}",
            "Content-Type": "application/json",
        }

    def _post(self, url: str, headers: dict[str, str], payload: dict) -> dict:
        """POST ``payload`` to ``url`` and return the parsed JSON body.

        Transport construction is in its own method so tests can swap
        in a ``MockTransport`` without monkey-patching the module.
        """
        try:
            import httpx  # local import: optional dependency
        except ImportError as exc:  # pragma: no cover - install-time failure
            raise AgentUnavailableError(
                "httpx is required for HttpAgentClient. "
                "Install it via `pip install httpx>=0.27`."
            ) from exc

        try:
            if self._transport is not None:
                with httpx.Client(transport=self._transport, timeout=self._timeout) as client:
                    resp = client.post(url, headers=headers, json=payload)
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise AgentUnavailableError(
                f"HTTP transport error talking to {url}: {exc}"
            ) from exc

        if resp.status_code >= 400:
            snippet = (resp.text or "")[:200]
            if 400 <= resp.status_code < 500:
                # Operational rejection: bad quality, no finger, etc.
                # Decode the JSON body if possible to recover the
                # ``code`` + ``status`` so the view layer can build a
                # meaningful 400 response.
                code = "AGENT_OPERATION_FAILED"
                status = ""
                try:
                    payload = resp.json()
                    if isinstance(payload, dict):
                        detail = payload.get("detail")
                        if isinstance(detail, dict):
                            code = str(detail.get("code") or code)
                            status = str(detail.get("status") or status)
                except ValueError:
                    pass
                raise AgentOperationError(code=code, status=status)
            raise AgentUnavailableError(
                f"Agent returned {resp.status_code}: {snippet}"
            )

        try:
            return resp.json()
        except ValueError as exc:
            raise AgentUnavailableError(
                f"Agent returned non-JSON response: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hint(value: str | None) -> str:
    """Return a short, non-sensitive hint of a capture token for logs."""
    if not value:
        return "?"
    return value[:8] if len(value) >= 8 else value


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AgentUnavailableError(RuntimeError):
    """Raised when the agent cannot fulfill a capture/match request.

    Mapped to HTTP 503 at the view layer.
    """


class AgentOperationError(RuntimeError):
    """The agent rejected an operational request (low quality, no finger,
    invalid finger name, etc.). 4xx, not 5xx. Carries the agent's
    detail body as ``code`` and ``status`` (the agent's biometric status
    string, e.g. ``enroll-failed``).
    """

    def __init__(self, code: str, status: str) -> None:
        super().__init__(f"agent operation rejected: {code} ({status})")
        self.code = code
        self.status = status


__all__ = [
    "AgentOperationError",
    "AgentUnavailableError",
    "BaseAgentClient",
    "CaptureResponse",
    "HttpAgentClient",
    "MatchResponse",
    "MockAgentClient",
    "SuspendedAgentClient",
]
