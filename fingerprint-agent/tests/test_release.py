"""Tests for the ``POST /release`` endpoint.

The release endpoint resets the agent's fprintd state by calling
``bridge.release()``. The in-memory bridge makes that a no-op, so
the test mostly asserts the wire contract:

- Auth is enforced (401 without bearer).
- 200 + ``{"status": "ok"}`` on success.
- Calling ``release()`` before ``match()`` does not break the match
  path (defensive reset never raises).
"""

from __future__ import annotations


def test_release_requires_auth(client):
    """Missing bearer → 401."""
    resp = client.post("/release", json={})
    assert resp.status_code == 401


def test_release_returns_ok(client, auth_headers):
    """Happy path: in-memory bridge.release() is a no-op and the
    endpoint returns the canonical success body."""
    resp = client.post("/release", json={}, headers=auth_headers)
    assert resp.status_code == 200, resp.content
    assert resp.json() == {"status": "ok"}


def test_release_then_match_still_succeeds(client, auth_headers):
    """The defensive reset must not corrupt the subsequent match.

    The in-memory bridge survives a release() call (it's a no-op) so
    the next /match still returns a score. This mirrors the real
    bridge's ``_reset_claim`` behaviour which swallows errors.
    """
    rel = client.post("/release", json={}, headers=auth_headers)
    assert rel.status_code == 200

    match_resp = client.post(
        "/match",
        json={"capture_token": "tok-1234", "template_b64": "00" * 32},
        headers=auth_headers,
    )
    assert match_resp.status_code == 200, match_resp.content
    body = match_resp.json()
    assert body["matched"] is True
    assert 0.0 <= body["score"] <= 1.0


def test_release_accepts_empty_body(client, auth_headers):
    """An empty JSON body is valid — the schema is permissive by design."""
    # Empty body fails Pydantic parsing as 422; the schema uses ``pass``
    # so it actually expects an empty object.
    resp = client.post(
        "/release",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 200


def test_release_calls_bridge_release(client, auth_headers, monkeypatch):
    """The endpoint must call ``bridge.release()`` exactly once."""
    from agent.app import build_app

    calls = []

    class _SpyBridge:
        @property
        def device_name(self) -> str:
            return "SPY"

        def enroll(self, finger_name: str = "any"):
            raise NotImplementedError

        def verify(self, finger_name: str = "any"):
            raise NotImplementedError

        def release(self) -> None:
            calls.append("release")

    spy = _SpyBridge()
    from fastapi.testclient import TestClient

    from agent.config import AgentConfig

    cfg = AgentConfig(
        bind_host="127.0.0.1",
        bind_port=8765,
        log_level="WARNING",
        fingerprint_username="spy",
        raw_token="test-token-xyz",
        backend_api_base="",
        agent_id=0,
        heartbeat_interval_seconds=60,
        device_name_match="4500",
        enroll_timeout_seconds=10,
        verify_timeout_seconds=10,
    )
    app = build_app(cfg, bridge=spy)
    with TestClient(app) as c:
        resp = c.post("/release", json={}, headers=auth_headers)
        assert resp.status_code == 200

    assert calls == ["release"]