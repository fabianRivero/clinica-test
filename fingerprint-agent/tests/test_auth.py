"""Bearer-token authentication tests."""

from __future__ import annotations


def test_health_does_not_require_auth(client):
    """GET /health is the only unauthenticated endpoint."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_capture_rejects_missing_bearer(client):
    """Missing Authorization header → 401."""
    resp = client.post(
        "/capture",
        json={"capture_token": "abc12345", "finger_name": "any"},
    )
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate", "").lower() == "bearer"


def test_capture_rejects_wrong_bearer(client, bad_auth_headers):
    """Wrong bearer token → 401."""
    resp = client.post(
        "/capture",
        json={"capture_token": "abc12345", "finger_name": "any"},
        headers=bad_auth_headers,
    )
    assert resp.status_code == 401


def test_capture_rejects_malformed_authorization(client):
    """Authorization without 'Bearer' prefix → 401."""
    resp = client.post(
        "/capture",
        json={"capture_token": "abc12345", "finger_name": "any"},
        headers={"Authorization": "Token abc"},
    )
    assert resp.status_code == 401


def test_match_rejects_wrong_bearer(client, bad_auth_headers):
    """Same gate on /match."""
    resp = client.post(
        "/match",
        json={"capture_token": "abc12345", "template_b64": "00" * 8},
        headers=bad_auth_headers,
    )
    assert resp.status_code == 401


def test_heartbeat_is_unauthenticated(client):
    """POST /heartbeat is intentionally a no-op on the agent side.

    The backend-facing heartbeat flow is the *outbound* loop in
    ``heartbeat.py``. The inbound ``POST /heartbeat`` is provided for
    manual ping-from-CLI and is not protected so operators can curl
    it during install debugging.
    """
    # 204 because the backend is not configured in the test fixture.
    resp = client.post("/heartbeat")
    assert resp.status_code in (204, 503)
