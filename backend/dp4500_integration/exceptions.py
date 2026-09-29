"""Domain exceptions raised by the dp4500_integration client + views.

The mapping table (HTTP status + body.code → exception) lives in
``client.HTTPClient._request``. The view layer maps domain
exceptions to HTTP responses.

Hierarchy:

  BiometricError (base)
  ├── BiometricUnavailable       DP4500 is down or 5xx or timeout
  ├── BiometricSuspended         DP4500 returned 503 BIOMETRIC_SUSPENDED
  ├── BiometricMismatch          Ed25519 / signature_invalid
  ├── BiometricVerifyFailed      422 INVALID_TOKEN (challenge expired)
  └── BiometricEnrollConflict    409 enrollment_required or ENROLL_CONFLICT
"""
from __future__ import annotations


class BiometricError(Exception):
    """Base for all dp4500_integration domain errors."""


class BiometricUnavailable(BiometricError):
    """DP4500 is unreachable, returned 5xx, or the request timed out.

    The cascade task retries up to 5x on this exception; the cite
    verification view surfaces 503 + Retry-After: 60 to the operator.
    """


class BiometricSuspended(BiometricError):
    """DP4500 returned 503 BIOMETRIC_SUSPENDED.

    Non-retryable. The operator must wait until the suspension flag is
    lifted on the DP4500 side.
    """


class BiometricMismatch(BiometricError):
    """Ed25519 signature did not verify (422 signature_invalid).

    Phase 1 stub: the wire accepts any non-empty signature payload as
    "ok"; Phase 4 wires real Ed25519 via the capture client.
    """


class BiometricVerifyFailed(BiometricError):
    """The challenge_id was unknown, consumed, or expired (422 INVALID_TOKEN).

    Distinct from ``BiometricMismatch`` (bad signature) — this is a
    state-of-the-challenge error, not a cryptographic error.
    """


class BiometricEnrollConflict(BiometricError):
    """Enroll path failed: 409 ENROLL_CONFLICT or 409 enrollment_required."""
