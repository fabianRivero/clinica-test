"""In-memory store for ``capture_token`` short-lived handles.

A ``capture_token`` is a UUID v4 the backend hands to the agent so the
front-end can correlate a wizard step with the eventual match/enroll
response. It must:

- Be unguessable (UUID v4 -> 122 bits of entropy).
- Expire quickly (5 minutes by default; config via
  ``BIOMETRIC_CAPTURE_TOKEN_TTL_SECONDS``).
- Not survive restarts (we deliberately use a Python ``dict`` so the
  test suite can reset it and so a leaked token becomes useless once
  the worker restarts).

PR #2 may swap this for ``django.core.cache``; for PR #1 the in-process
store keeps the surface small.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Optional


DEFAULT_TTL_SECONDS = 300  # 5 minutes


def _ttl_seconds() -> int:
    raw = os.getenv("BIOMETRIC_CAPTURE_TOKEN_TTL_SECONDS", str(DEFAULT_TTL_SECONDS))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_TTL_SECONDS


@dataclass
class _Entry:
    payload: dict
    expires_at: float


class CaptureTokenStore:
    """Thread-safe in-process store keyed by capture token."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}

    def create(self, payload: dict, ttl_seconds: Optional[int] = None) -> str:
        token = uuid.uuid4().hex  # 32 chars, hex-encoded UUIDv4 (122 bits entropy)
        ttl = ttl_seconds if ttl_seconds is not None else _ttl_seconds()
        expires = time.monotonic() + ttl
        with self._lock:
            self._purge_locked()
            self._entries[token] = _Entry(payload=dict(payload), expires_at=expires)
        return token

    def pop(self, token: str) -> Optional[dict]:
        with self._lock:
            self._purge_locked()
            entry = self._entries.pop(token, None)
        if entry is None:
            return None
        return entry.payload

    def peek(self, token: str) -> Optional[dict]:
        with self._lock:
            self._purge_locked()
            entry = self._entries.get(token)
        if entry is None:
            return None
        return dict(entry.payload)

    def set_score(self, token: str, score: float) -> None:
        """Attach a ``score`` to an existing capture token.

        Used by ``verify_init`` so the score from the agent's match
        call doesn't have to be re-fetched from the agent during
        ``verify_confirm``.
        """
        with self._lock:
            entry = self._entries.get(token)
            if entry is not None:
                entry.payload = {**entry.payload, "score": score}

    def reset(self) -> None:
        """Clear all entries. Test-only helper."""
        with self._lock:
            self._entries.clear()

    def _purge_locked(self) -> None:
        now = time.monotonic()
        stale = [k for k, v in self._entries.items() if v.expires_at <= now]
        for k in stale:
            self._entries.pop(k, None)


# Module-level singleton; tests can ``capture_token_store.reset()``.
capture_token_store = CaptureTokenStore()


__all__ = ["capture_token_store", "CaptureTokenStore", "DEFAULT_TTL_SECONDS"]
