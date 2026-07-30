"""Tests for the agent client implementations and the factory dispatch.

Covers:

- :class:`MockAgentClient` deterministic behavior (regression tests
  for PR #1 behavior, preserved through the PR #2 signature change).
- :class:`HttpAgentClient` wire contract (capture + match) tested
  with ``httpx.MockTransport`` so no real network is involved.
- Factory default and fallback behavior.
"""

from __future__ import annotations

import base64
import os
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import httpx
from django.test import SimpleTestCase

from biometric.services.agent_client import (
    AgentUnavailableError,
    HttpAgentClient,
    MockAgentClient,
)
from biometric.services.factory import get_agent_client


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------


class MockAgentClientTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("AGENT_FAIL_WITH", None)
        os.environ.pop("AGENT_QUALITY_SCORE", None)
        os.environ.pop("AGENT_MATCH_SCORE", None)

    def test_capture_returns_deterministic_template_for_token(self):
        client = MockAgentClient(quality_score=82, match_score=0.91)
        a = client.capture(agent=None, capture_token="abc123")
        b = client.capture(agent=None, capture_token="abc123")
        self.assertEqual(a.template_b64, b.template_b64)
        self.assertEqual(a.quality_score, 82)
        self.assertEqual(a.device_serial, "MOCK-DP-001")

    def test_capture_low_quality_returns_zero_template(self):
        client = MockAgentClient(quality_score=10, match_score=0.91)
        result = client.capture(agent=None, capture_token="x")
        self.assertEqual(result.quality_score, 10)
        self.assertEqual(result.template_b64, "")

    def test_match_returns_configured_score(self):
        client = MockAgentClient(quality_score=80, match_score=0.95)
        result = client.match(agent=None, template_bytes=b"ignored", capture_token="token")
        self.assertEqual(result.score, Decimal("0.95"))

    def test_capture_raises_when_configured(self):
        client = MockAgentClient(fail_with="NO_IMAGE")
        with self.assertRaises(AgentUnavailableError):
            client.capture(agent=None, capture_token="x")

    def test_match_raises_when_agent_offline(self):
        client = MockAgentClient(fail_with="AGENT_OFFLINE")
        with self.assertRaises(AgentUnavailableError):
            client.match(agent=None, template_bytes=b"x", capture_token="token")

    def test_quality_score_from_env(self):
        with mock.patch.dict(os.environ, {"AGENT_QUALITY_SCORE": "77"}):
            client = MockAgentClient()
            self.assertEqual(client.quality_score, 77)

    def test_match_score_from_env(self):
        with mock.patch.dict(os.environ, {"AGENT_MATCH_SCORE": "0.42"}):
            client = MockAgentClient()
            self.assertEqual(client.match_score, Decimal("0.42"))

    def test_release_is_noop_for_mock(self):
        """The mock has no device to reset; ``release`` must succeed
        and never raise (the view layer calls it unconditionally
        before every ``match``)."""
        client = MockAgentClient(quality_score=80, match_score=0.91)
        # Must not raise; returns None.
        self.assertIsNone(client.release(agent=None))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class FactoryTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("AGENT_CLIENT_CLASS", None)

    def test_default_returns_http(self):
        """PR #2 flipped the default to HttpAgentClient."""
        client = get_agent_client()
        self.assertIsInstance(client, HttpAgentClient)

    def test_unknown_class_falls_back_to_mock(self):
        with mock.patch.dict(
            os.environ,
            {"AGENT_CLIENT_CLASS": "biometric.services.agent_client.DoesNotExist"},
        ):
            client = get_agent_client()
            self.assertIsInstance(client, MockAgentClient)

    def test_explicit_mock(self):
        with mock.patch.dict(
            os.environ,
            {"AGENT_CLIENT_CLASS": "biometric.services.agent_client.MockAgentClient"},
        ):
            client = get_agent_client()
            self.assertIsInstance(client, MockAgentClient)


# ---------------------------------------------------------------------------
# HttpAgentClient
# ---------------------------------------------------------------------------


def _fake_agent(public_url: str = "https://agent.example.com", raw_token: str = "raw-token-xyz"):
    """Build a duck-typed AgentToken stand-in for unit tests.

    Avoids needing a real DB row. ``decrypt_raw_token`` is implemented
    so the client can fetch the bearer without round-tripping through
    Fernet.
    """

    class _Agent:
        def __init__(self):
            self.public_url = public_url
            self._raw_token = raw_token

        def decrypt_raw_token(self) -> str:
            return self._raw_token

    return _Agent()


class HttpAgentClientTests(SimpleTestCase):
    """Use ``httpx.MockTransport`` so we never open a real socket."""

    def test_capture_posts_bearer_and_returns_payload(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("Authorization")
            captured["body"] = request.read().decode("utf-8")
            return httpx.Response(
                200,
                json={
                    "template_b64": base64.b64encode(b"x" * 200).decode(),
                    "quality_score": 0.85,
                    "device_serial": "DP4500-USB",
                    "width": 256,
                    "height": 364,
                },
            )

        transport = httpx.MockTransport(handler)
        client = HttpAgentClient(transport=transport)
        resp = client.capture(
            agent=_fake_agent(),
            capture_token="abc-token-1",
            finger_name="any",
        )

        self.assertEqual(
            captured["auth"], "Bearer raw-token-xyz", "Bearer header must be present"
        )
        self.assertEqual(captured["url"], "https://agent.example.com/capture")
        self.assertIn('"capture_token":"abc-token-1"', captured["body"])
        self.assertEqual(resp.device_serial, "DP4500-USB")
        self.assertEqual(resp.width, 256)
        self.assertEqual(resp.height, 364)

    def test_match_sends_capture_token_only(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = request.read().decode("utf-8")
            return httpx.Response(
                200,
                json={
                    "score": 0.91,
                    "captured_template_b64": base64.b64encode(b"y" * 100).decode(),
                },
            )

        transport = httpx.MockTransport(handler)
        client = HttpAgentClient(transport=transport)
        template = b"\x01\x02\x03" * 32
        resp = client.match(
            agent=_fake_agent(),
            template_bytes=template,
            capture_token="cap-xyz",
        )

        self.assertEqual(captured["url"], "https://agent.example.com/match")
        # Wire payload only carries capture_token; the agent enforces
        # the match against its internal state (fprintd's D-Bus API
        # doesn't accept a reference template).
        self.assertIn('"capture_token":"cap-xyz"', captured["body"])
        self.assertNotIn("template_b64", captured["body"])
        self.assertEqual(resp.score, Decimal("0.91"))

    def test_capture_raises_on_5xx(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="agent offline")

        client = HttpAgentClient(transport=httpx.MockTransport(handler))
        with self.assertRaises(AgentUnavailableError):
            client.capture(agent=_fake_agent(), capture_token="x")

    def test_match_raises_on_network_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        client = HttpAgentClient(transport=httpx.MockTransport(handler))
        with self.assertRaises(AgentUnavailableError):
            client.match(
                agent=_fake_agent(),
                template_bytes=b"x",
                capture_token="y",
            )

    def test_capture_raises_when_public_url_empty(self):
        agent = SimpleNamespace(public_url="", decrypt_raw_token=lambda: "x")
        client = HttpAgentClient()
        with self.assertRaises(AgentUnavailableError):
            client.capture(agent=agent, capture_token="x")

    def test_capture_raises_when_token_decrypt_fails(self):
        agent = SimpleNamespace(
            public_url="https://agent.example.com",
            decrypt_raw_token=lambda: (_ for _ in ()).throw(RuntimeError("nope")),
        )
        client = HttpAgentClient()
        with self.assertRaises(AgentUnavailableError):
            client.capture(agent=agent, capture_token="x")

    def test_match_raises_on_non_json_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>oops</html>")

        client = HttpAgentClient(transport=httpx.MockTransport(handler))
        with self.assertRaises(AgentUnavailableError):
            client.match(agent=_fake_agent(), template_bytes=b"x", capture_token="y")

    def test_release_posts_bearer_and_returns_silently(self):
        """``release()`` POSTs to ``/release`` with the bearer token
        and swallows the response body — failures must never raise
        (a failed reset must not block the verify round-trip)."""
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("Authorization")
            captured["body"] = request.read().decode("utf-8")
            return httpx.Response(200, json={"status": "ok"})

        client = HttpAgentClient(transport=httpx.MockTransport(handler))
        # Must not raise.
        client.release(agent=_fake_agent())
        self.assertEqual(captured["url"], "https://agent.example.com/release")
        self.assertEqual(captured["auth"], "Bearer raw-token-xyz")
        self.assertEqual(captured["body"], "{}")

    def test_release_swallows_5xx(self):
        """A failing ``/release`` must not propagate — the bridge's
        defensive ``_reset_claim`` is the second line of defence."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="agent offline")

        client = HttpAgentClient(transport=httpx.MockTransport(handler))
        # Must NOT raise AgentUnavailableError.
        client.release(agent=_fake_agent())

    def test_release_swallows_transport_error(self):
        """A network-level failure must also be swallowed."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        client = HttpAgentClient(transport=httpx.MockTransport(handler))
        # Must NOT raise.
        client.release(agent=_fake_agent())

    def test_release_swallows_missing_public_url(self):
        """An agent with no ``public_url`` cannot be reached; the
        client must silently skip the reset instead of raising."""
        agent = SimpleNamespace(public_url="", decrypt_raw_token=lambda: "x")
        client = HttpAgentClient()
        # Must NOT raise.
        client.release(agent=agent)
