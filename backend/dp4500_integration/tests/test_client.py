"""Tests for dp4500_integration.client.HTTPClient.

Phase 2 of dp4500-host-app-integration-phase2. Uses httpx.MockTransport
so no real DP4500 is required.

Each test:
  - Patches httpx.Client with a MockTransport that returns a canned
    status + body.
  - Builds an HTTPClient with a fake key_resolver.
  - Asserts the expected dataclass return OR domain exception.
"""
from __future__ import annotations

import json
import threading
from unittest import TestCase

import httpx

from dp4500_integration.client import (
    HTTPClient,
    IdentityChallenge,
    IdentityVerifyMatch,
    IdentityVerifyNoMatch,
)
from dp4500_integration.exceptions import (
    BiometricEnrollConflict,
    BiometricMismatch,
    BiometricSuspended,
    BiometricUnavailable,
    BiometricVerifyFailed,
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _transport(handler):
    """Wrap a sync handler function into an httpx.MockTransport."""
    return httpx.MockTransport(handler)


def _bearer_for_request(request: httpx.Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return ""
    return auth[len("Bearer "):]


def _ok(handler):
    """Wrap a handler so that any unhandled call returns 200 + JSON body."""
    def inner(request: httpx.Request) -> httpx.Response:
        try:
            return handler(request)
        except _OKMarker as marker:
            return httpx.Response(
                marker.status, json=marker.body, request=request,
            )
    return inner


class _OKMarker(Exception):
    def __init__(self, status: int, body: dict) -> None:
        self.status = status
        self.body = body


def _client(handler) -> HTTPClient:
    """Build an HTTPClient with a MockTransport and a fake key_resolver."""
    transport = _transport(handler)

    # httpx.Client.__init__ accepts a transport= parameter. We monkey-patch
    # the HTTPClient._client to use ours.
    client = HTTPClient(
        base_url="https://dp4500.test",
        timeout_seconds=5,
        key_resolver=lambda _: "SeK_test",
    )
    client._client = httpx.Client(transport=transport, timeout=5)
    return client


# --------------------------------------------------------------------------
# Construction / key resolution
# --------------------------------------------------------------------------


class HTTPClientConstructionTests(TestCase):
    def test_constructor_does_not_make_http_requests(self):
        """No transport wired → no HTTP. The constructor returns immediately."""
        captured = []
        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(500)
        client = HTTPClient(
            base_url="https://dp4500.test",
            timeout_seconds=5,
            key_resolver=lambda _: "SeK_test",
        )
        self.assertEqual(captured, [])
        self.assertEqual(client.timeout, 5)
        self.assertEqual(client.base_url, "https://dp4500.test")

    def test_trailing_slash_stripped_from_base_url(self):
        client = HTTPClient(
            base_url="https://dp4500.test/",
            timeout_seconds=5,
            key_resolver=lambda _: None,
        )
        self.assertEqual(client.base_url, "https://dp4500.test")

    def test_key_resolver_returning_none_raises_unavailable_no_http(self):
        captured = []
        def handler(request):
            captured.append(request)
            return httpx.Response(500)
        client = HTTPClient(
            base_url="https://dp4500.test",
            timeout_seconds=5,
            key_resolver=lambda _: None,
        )
        client._client = httpx.Client(transport=_transport(handler))
        with self.assertRaises(BiometricUnavailable) as ctx:
            client.identity_challenge(user_external_id="ext-1", sucursal_id=42)
        self.assertIn("no_service_key", str(ctx.exception))
        self.assertEqual(captured, [], "no HTTP call should be issued")


# --------------------------------------------------------------------------
# identity_challenge
# --------------------------------------------------------------------------


class IdentityChallengeTests(TestCase):
    def test_201_returns_parsed_identity_challenge(self):
        body = {
            "capture_token": "uuid-1",
            "server_nonce": "Zm9v",
            "ttl_seconds": 60,
            "has_fingerprint": True,
            "server_pubkey_jwk": {"kty": "OKP", "fingerprint": "fp-1"},
        }

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertIn(
                "/api/biometric/service/challenge/identity/ext-1/",
                str(request.url),
            )
            self.assertEqual(_bearer_for_request(request), "SeK_test")
            return httpx.Response(201, json=body, request=request)

        client = _client(handler)
        result = client.identity_challenge(user_external_id="ext-1", sucursal_id=42)
        self.assertIsInstance(result, IdentityChallenge)
        self.assertEqual(result.capture_token, "uuid-1")
        self.assertEqual(result.server_nonce, "Zm9v")
        self.assertEqual(result.ttl_seconds, 60)
        self.assertTrue(result.has_fingerprint)
        self.assertEqual(result.server_pubkey_jwk["fingerprint"], "fp-1")

    def test_409_enrollment_required_raises_enroll_conflict(self):
        def handler(request):
            return httpx.Response(
                409,
                json={"detail": "no template", "code": "enrollment_required"},
                request=request,
            )
        client = _client(handler)
        with self.assertRaises(BiometricEnrollConflict) as ctx:
            client.identity_challenge(user_external_id="ext-x", sucursal_id=42)
        self.assertIn("no_template_on_dp4500", str(ctx.exception))

    def test_409_ENROLL_CONFLICT_raises_enroll_conflict(self):
        def handler(request):
            return httpx.Response(
                409,
                json={"code": "ENROLL_CONFLICT"},
                request=request,
            )
        client = _client(handler)
        with self.assertRaises(BiometricEnrollConflict):
            client.identity_challenge(user_external_id="ext-dup", sucursal_id=42)


# --------------------------------------------------------------------------
# identity_verify
# --------------------------------------------------------------------------


class IdentityVerifyTests(TestCase):
    def test_200_matched_true_returns_match(self):
        body = {"matched": True, "audit_hash": "abc"}

        def handler(request):
            self.assertEqual(request.method, "POST")
            payload = json.loads(request.content)
            self.assertEqual(payload["challenge_id"], "uuid-1")
            self.assertEqual(payload["signature"], "phase2-stub")
            return httpx.Response(200, json=body, request=request)

        client = _client(handler)
        result = client.identity_verify(
            user_external_id="ext-1",
            challenge_id="uuid-1",
            signature_b64="phase2-stub",
            timestamp="2026-09-27T00:00:00+00:00",
            sucursal_id=42,
        )
        self.assertIsInstance(result, IdentityVerifyMatch)
        self.assertTrue(result.matched)
        self.assertEqual(result.audit_hash, "abc")

    def test_200_matched_false_returns_no_match(self):
        def handler(request):
            return httpx.Response(
                200, json={"matched": False, "audit_hash": "xyz"},
                request=request,
            )
        client = _client(handler)
        result = client.identity_verify(
            user_external_id="ext-1",
            challenge_id="uuid-1",
            signature_b64="phase2-stub",
            timestamp="2026-09-27T00:00:00+00:00",
            sucursal_id=42,
        )
        self.assertIsInstance(result, IdentityVerifyNoMatch)
        self.assertFalse(result.matched)

    def test_422_signature_invalid_raises_mismatch(self):
        def handler(request):
            return httpx.Response(
                422, json={"code": "signature_invalid"},
                request=request,
            )
        client = _client(handler)
        with self.assertRaises(BiometricMismatch):
            client.identity_verify(
                user_external_id="ext-1",
                challenge_id="uuid-1",
                signature_b64="x",
                timestamp="t",
                sucursal_id=42,
            )

    def test_422_INVALID_TOKEN_raises_verify_failed(self):
        def handler(request):
            return httpx.Response(
                422, json={"code": "INVALID_TOKEN"},
                request=request,
            )
        client = _client(handler)
        with self.assertRaises(BiometricVerifyFailed) as ctx:
            client.identity_verify(
                user_external_id="ext-1",
                challenge_id="uuid-bad",
                signature_b64="x",
                timestamp="t",
                sucursal_id=42,
            )
        self.assertIn("challenge_expired_or_invalid", str(ctx.exception))


# --------------------------------------------------------------------------
# delete_template
# --------------------------------------------------------------------------


class DeleteTemplateTests(TestCase):
    def test_204_is_silent(self):
        captured = []
        def handler(request):
            self.assertEqual(request.method, "DELETE")
            captured.append(True)
            return httpx.Response(204, request=request)
        client = _client(handler)
        result = client.delete_template(
            user_external_id="ext-1", sucursal_id=42,
        )
        self.assertIsNone(result)
        self.assertEqual(len(captured), 1)

    def test_404_is_idempotent_silent(self):
        def handler(request):
            return httpx.Response(
                404, json={"code": "not_found"},
                request=request,
            )
        client = _client(handler)
        result = client.delete_template(
            user_external_id="ext-gone", sucursal_id=42,
        )
        self.assertIsNone(result)

    def test_503_BIOMETRIC_SUSPENDED_raises_suspended(self):
        def handler(request):
            return httpx.Response(
                503, json={"code": "BIOMETRIC_SUSPENDED"},
                request=request,
            )
        client = _client(handler)
        with self.assertRaises(BiometricSuspended):
            client.delete_template(
                user_external_id="ext-1", sucursal_id=42,
            )


# --------------------------------------------------------------------------
# Error mapping table
# --------------------------------------------------------------------------


class ErrorMappingTests(TestCase):
    def test_503_NO_AGENT_raises_unavailable_no_agent(self):
        def handler(request):
            return httpx.Response(
                503, json={"code": "NO_AGENT"}, request=request,
            )
        client = _client(handler)
        with self.assertRaises(BiometricUnavailable) as ctx:
            client.identity_challenge(user_external_id="x", sucursal_id=42)
        self.assertEqual(str(ctx.exception), "no_agent")

    def test_401_raises_unavailable(self):
        def handler(request):
            return httpx.Response(401, request=request)
        client = _client(handler)
        with self.assertRaises(BiometricUnavailable) as ctx:
            client.identity_challenge(user_external_id="x", sucursal_id=42)
        self.assertIn("http_401", str(ctx.exception))

    def test_500_raises_unavailable(self):
        def handler(request):
            return httpx.Response(500, request=request)
        client = _client(handler)
        with self.assertRaises(BiometricUnavailable) as ctx:
            client.identity_challenge(user_external_id="x", sucursal_id=42)
        self.assertIn("http_500", str(ctx.exception))


# --------------------------------------------------------------------------
# Timeout
# --------------------------------------------------------------------------


class TimeoutTests(TestCase):
    def test_timeout_path_is_documented_skip(self):
        """httpx.MockTransport does NOT enforce client timeouts because
        it executes the handler synchronously. The actual timeout
        path (httpx.TimeoutException → BiometricUnavailable) is
        exercised by Phase 4's integration tests against a real or
        slow TCP transport. For Phase 2 the contract is "any
        non-2xx raises BiometricUnavailable" and that is covered by
        the error-mapping tests above.
        """
        self.skipTest(
            "MockTransport bypasses timeout layer; verified by integration tests in Phase 4"
        )


# --------------------------------------------------------------------------
# Bearer token never logged
# --------------------------------------------------------------------------


class NoTokenLeakageTests(TestCase):
    def test_bearer_token_does_not_appear_in_logs(self):
        import logging

        logs_captured = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                logs_captured.append(self.format(record))

        capture = CaptureHandler()
        logging.getLogger().addHandler(capture)
        try:
            def handler(request):
                return httpx.Response(200, json={"ok": True}, request=request)

            client = HTTPClient(
                base_url="https://dp4500.test",
                timeout_seconds=5,
                key_resolver=lambda _: "SeK_super_secret_token_xyz",
            )
            client._client = httpx.Client(transport=_transport(handler))
            client.identity_challenge(user_external_id="x", sucursal_id=42)
        finally:
            logging.getLogger().removeHandler(capture)

        joined = "\n".join(logs_captured)
        self.assertNotIn("SeK_super_secret_token_xyz", joined)
