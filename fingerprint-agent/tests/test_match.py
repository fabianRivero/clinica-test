"""Tests for the ``POST /match`` endpoint."""

from __future__ import annotations


def test_match_returns_score_and_captured_bytes(client, auth_headers):
    """Happy path: the in-memory bridge returns score 0.92 and synthetic bytes."""
    resp = client.post(
        "/match",
        json={"capture_token": "tok-1234", "template_b64": "00" * 32},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["matched"] is True
    assert 0.0 <= body["score"] <= 1.0
    assert isinstance(body["captured_template_b64"], str)
    assert len(body["captured_template_b64"]) >= 256


def test_match_rejects_invalid_template_hex(client, auth_headers):
    """Garbage in template_b64 → 400 INVALID_TEMPLATE."""
    resp = client.post(
        "/match",
        json={"capture_token": "tok-1234", "template_b64": "ZZ" * 32},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_TEMPLATE"


def test_match_accepts_empty_template_b64(client, auth_headers):
    """An empty template is a valid sentinel (no enrolled template)."""
    resp = client.post(
        "/match",
        json={"capture_token": "tok-1234", "template_b64": ""},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.content


def test_match_rejects_missing_token(client, auth_headers):
    """Pydantic-level validation rejects missing capture_token."""
    resp = client.post(
        "/match",
        json={"template_b64": "00" * 32},
        headers=auth_headers,
    )
    assert resp.status_code == 422
