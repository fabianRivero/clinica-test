"""Tests for the ``POST /capture`` endpoint."""

from __future__ import annotations


def test_capture_returns_synthetic_template(client, auth_headers):
    """Happy path: in-memory bridge returns a 256-byte template (hex)."""
    resp = client.post(
        "/capture",
        json={"capture_token": "tok-1234", "finger_name": "any"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["quality_score"] >= 50
    assert isinstance(body["template_b64"], str)
    assert len(body["template_b64"]) >= 256
    assert body["device_serial"].startswith("DP4500-")


def test_capture_rejects_missing_capture_token(client, auth_headers):
    """Pydantic-level validation rejects empty capture_token."""
    resp = client.post(
        "/capture",
        json={"capture_token": "", "finger_name": "any"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_capture_rejects_garbage_finger_name(client, auth_headers):
    """Pydantic-level validation rejects too-long finger_name."""
    resp = client.post(
        "/capture",
        json={"capture_token": "tok-1234", "finger_name": "x" * 200},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_capture_quality_required_below_score_returns_empty(client, auth_headers):
    """If the requested quality_required is above the in-memory score,
    the agent returns an empty template so the backend can raise
    LOW_QUALITY without ever shipping the bytes to disk.
    """
    resp = client.post(
        "/capture",
        json={
            "capture_token": "tok-1234",
            "finger_name": "any",
            "quality_required": 95,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["template_b64"] == ""
    assert body["quality_score"] < 95


def test_capture_rejects_bad_quality_required(client, auth_headers):
    """Negative or >100 quality_required → 422."""
    resp = client.post(
        "/capture",
        json={
            "capture_token": "tok-1234",
            "finger_name": "any",
            "quality_required": 200,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422
