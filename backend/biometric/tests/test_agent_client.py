"""Tests for the mock agent client and the factory dispatch."""

from __future__ import annotations

import os
import unittest
from decimal import Decimal
from unittest import mock

from biometric.services.agent_client import (
    AgentUnavailableError,
    HttpAgentClient,
    MockAgentClient,
)
from biometric.services.factory import get_agent_client


class MockAgentClientTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("AGENT_FAIL_WITH", None)
        os.environ.pop("AGENT_QUALITY_SCORE", None)
        os.environ.pop("AGENT_MATCH_SCORE", None)

    def test_capture_returns_deterministic_template_for_token(self):
        client = MockAgentClient(quality_score=82, match_score=0.91)
        a = client.capture({"capture_token": "abc123"})
        b = client.capture({"capture_token": "abc123"})
        self.assertEqual(a.template_b64, b.template_b64)
        self.assertEqual(a.quality_score, 82)
        self.assertEqual(a.device_serial, "MOCK-DP-001")

    def test_capture_low_quality_returns_zero_template(self):
        client = MockAgentClient(quality_score=10, match_score=0.91)
        result = client.capture({"capture_token": "x"})
        self.assertEqual(result.quality_score, 10)
        self.assertEqual(result.template_b64, "")

    def test_match_returns_configured_score(self):
        client = MockAgentClient(quality_score=80, match_score=0.95)
        result = client.match(b"ignored", "token")
        self.assertEqual(result.score, Decimal("0.95"))

    def test_capture_raises_when_configured(self):
        client = MockAgentClient(fail_with="NO_IMAGE")
        with self.assertRaises(AgentUnavailableError):
            client.capture({"capture_token": "x"})

    def test_match_raises_when_agent_offline(self):
        client = MockAgentClient(fail_with="AGENT_OFFLINE")
        with self.assertRaises(AgentUnavailableError):
            client.match(b"x", "token")

    def test_quality_score_from_env(self):
        with mock.patch.dict(os.environ, {"AGENT_QUALITY_SCORE": "77"}):
            client = MockAgentClient()
            self.assertEqual(client.quality_score, 77)

    def test_match_score_from_env(self):
        with mock.patch.dict(os.environ, {"AGENT_MATCH_SCORE": "0.42"}):
            client = MockAgentClient()
            self.assertEqual(client.match_score, Decimal("0.42"))


class FactoryTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("AGENT_CLIENT_CLASS", None)

    def test_default_returns_mock(self):
        client = get_agent_client()
        self.assertIsInstance(client, MockAgentClient)

    def test_unknown_class_falls_back_to_mock(self):
        with mock.patch.dict(
            os.environ,
            {"AGENT_CLIENT_CLASS": "biometric.services.agent_client.DoesNotExist"},
        ):
            client = get_agent_client()
            self.assertIsInstance(client, MockAgentClient)

    def test_http_client_stub(self):
        # HttpAgentClient is intentionally a stub for PR #2.
        stub = HttpAgentClient()
        with self.assertRaises(NotImplementedError):
            stub.capture({"capture_token": "x"})
        with self.assertRaises(NotImplementedError):
            stub.match(b"x", "t")
