"""HTTPClient wrapping DP4500 estandar's /api/biometric/service/* surface.

Phase 2 of dp4500-host-app-integration-phase2. The client is the
clinic-side counterpart to the server side built in Phase 1.

What the client does:
  - Per-call bearer resolution via an injected ``key_resolver``.
  - Per-call timeout enforced by httpx.
  - Status + body.code mapping into domain exceptions.
  - Returns frozen dataclasses for success shapes.

What the client does NOT do:
  - No fingerprint bytes at rest or in logs.
  - No retry: the caller (a Celery task or a DRF view) is responsible.
  - No persistence of the raw bearer token.

Wire contract lives at
``openspec/changes/dp4500-host-app-integration-phase2/specs/dp4500-service-client/spec.md``
and the corresponding Phase 1 server-side spec at
``openspec/changes/dp4500-host-app-integration-phase1/specs/service-biometric-operations/spec.md``
in the DP4500 estandar repo.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

import httpx

from dp4500_integration.exceptions import (
    BiometricEnrollConflict,
    BiometricMismatch,
    BiometricSuspended,
    BiometricUnavailable,
    BiometricVerifyFailed,
)


logger = logging.getLogger(__name__)


# Type alias for the key resolver. Returns the raw token or None
# (None is treated as "no key configured for this branch").
KeyResolver = Callable[[int], str | None]


# ---------------------------------------------------------------------------
# Result types (frozen dataclasses per spec §service-client §Result types)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdentityChallenge:
    """Successful response from POST /service/challenge/identity/<id>/."""
    capture_token: str
    server_nonce: str
    ttl_seconds: int
    has_fingerprint: bool
    server_pubkey_jwk: dict


@dataclass(frozen=True)
class IdentityVerifyMatch:
    """200 {matched: true, audit_hash, ...}"""
    matched: bool = True
    audit_hash: str = ""


@dataclass(frozen=True)
class IdentityVerifyNoMatch:
    """200 {matched: false, audit_hash, ...}"""
    matched: bool = False
    audit_hash: str = ""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class HTTPClient:
    """Thin httpx wrapper for DP4500's service API.

    Construction does NOT make HTTP requests; each method issues
    exactly one HTTP call.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: int,
        key_resolver: KeyResolver,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds
        self._key_resolver = key_resolver
        self._client = httpx.Client(timeout=timeout_seconds)

    # -- High-level operations ------------------------------------------------

    def identity_challenge(
        self,
        *,
        user_external_id: str,
        sucursal_id: int,
    ) -> IdentityChallenge:
        """POST /service/challenge/identity/<external_id>/ with empty body."""
        body = self._request(
            "POST",
            f"/api/biometric/service/challenge/identity/{user_external_id}/",
            sucursal_id=sucursal_id,
            json_body={},
        )
        return IdentityChallenge(
            capture_token=body.get("capture_token", ""),
            server_nonce=body.get("server_nonce", ""),
            ttl_seconds=int(body.get("ttl_seconds", 60)),
            has_fingerprint=bool(body.get("has_fingerprint", False)),
            server_pubkey_jwk=body.get("server_pubkey_jwk") or {},
        )

    def identity_verify(
        self,
        *,
        user_external_id: str,
        challenge_id: str,
        signature_b64: str,
        timestamp: str,
        sucursal_id: int,
    ) -> IdentityVerifyMatch | IdentityVerifyNoMatch:
        """POST /service/verify/identity/ with {challenge_id, signature, timestamp}.

        Phase 2 passes ``"phase2-stub"`` as the signature (Phase 4 wires
        the real Ed25519 sign via the capture client).
        """
        body = {
            "challenge_id": challenge_id,
            "signature": signature_b64,
            "timestamp": timestamp,
        }
        result = self._request(
            "POST",
            "/api/biometric/service/verify/identity/",
            sucursal_id=sucursal_id,
            json_body=body,
        )
        if result.get("matched") is True:
            return IdentityVerifyMatch(
                matched=True,
                audit_hash=result.get("audit_hash", ""),
            )
        return IdentityVerifyNoMatch(
            matched=False,
            audit_hash=result.get("audit_hash", ""),
        )

    def delete_template(
        self,
        *,
        user_external_id: str,
        sucursal_id: int,
    ) -> None:
        """DELETE /service/templates/<external_id>/ (idempotent).

        Returns silently on 204 and 404; raises ``BiometricUnavailable``
        on 5xx and ``BiometricSuspended`` on 503 BIOMETRIC_SUSPENDED.
        """
        self._request(
            "DELETE",
            f"/api/biometric/service/templates/{user_external_id}/",
            sucursal_id=sucursal_id,
        )

    # -- Internal helper -----------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        sucursal_id: int,
        json_body: dict | None = None,
    ) -> dict:
        """Single HTTP call + status/code → exception or parsed JSON.

        Raises a domain exception on any non-2xx. Returns the parsed
        JSON body on success (or an empty dict for 204 / DELETE).
        """
        key = self._key_resolver(sucursal_id)
        if not key:
            raise BiometricUnavailable("no_service_key")
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {key}"}

        try:
            response = self._client.request(
                method,
                url,
                headers=headers,
                json=json_body,
            )
        except httpx.TimeoutException as exc:
            raise BiometricUnavailable("timeout") from exc
        except httpx.HTTPError as exc:
            raise BiometricUnavailable(f"transport:{type(exc).__name__}") from exc

        # DELETE returns 204 with no body; treated as silent success.
        if response.status_code == 204:
            return {}
        # DELETE also returns 404 when the template was already revoked
        # upstream — per design §3.5, this is silent (idempotent). The
        # caller cannot tell from ``None`` whether the template existed;
        # both endpoints reach the desired post-condition.
        if method == "DELETE" and response.status_code == 404:
            return {}

        body = {}
        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text[:200]}

        # 2xx with body — parse JSON.
        if 200 <= response.status_code < 300:
            try:
                return body if body else response.json()
            except ValueError as exc:
                raise BiometricUnavailable("non_json_2xx") from exc

        return self._classify_failure(response.status_code, body)

    @staticmethod
    def _classify_failure(status_code: int, body: dict) -> dict:
        """Translate (status_code, body.code) → domain exception or dict.

        Per design §3.5 error code mapping table. The decision tree is
        ordered from most-specific to least-specific.
        """
        code = (body or {}).get("code", "")

        # Auth / not-found first — these don't depend on the body code.
        if status_code in (401, 403):
            raise BiometricUnavailable(f"http_{status_code}")
        if status_code == 404:
            raise BiometricVerifyFailed("not_found")
        if status_code == 409:
            if code == "ENROLL_CONFLICT":
                raise BiometricEnrollConflict("duplicate_external_id_enrollment")
            if code == "enrollment_required":
                raise BiometricEnrollConflict("no_template_on_dp4500")
            # Generic 409 from a cita_no_longer_pending style conflict.
            raise BiometricUnavailable(f"http_409:{code}")
        if status_code == 422:
            if code == "signature_invalid":
                raise BiometricMismatch()
            if code == "INVALID_TOKEN":
                raise BiometricVerifyFailed("challenge_expired_or_invalid")
            raise BiometricUnavailable(f"http_422:{code}")
        if status_code == 503:
            if code == "BIOMETRIC_SUSPENDED":
                raise BiometricSuspended()
            if code == "NO_AGENT":
                raise BiometricUnavailable("no_agent")
            raise BiometricUnavailable(f"http_503:{code}")
        if status_code >= 500:
            raise BiometricUnavailable(f"http_{status_code}")

        # Unknown non-2xx — treat as unavailable.
        raise BiometricUnavailable(f"http_{status_code}:{code}")

    def close(self) -> None:
        self._client.close()
