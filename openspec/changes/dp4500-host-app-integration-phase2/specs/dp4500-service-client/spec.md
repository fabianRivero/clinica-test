# dp4500-service-client Specification

## Purpose

Defines the HTTP client used by the clinic's `biometric/` Django app
to call DP4500's service API. Covers wire-level behavior: URL
construction, header shape (`Authorization: Bearer <key>`), per-branch
key lookup, error code mapping, and timeout/retry policy. The client
performs no crypto and never persists key bytes (Phase 4 introduces
the vault backend; Phase 2 only supports `env`).

This is Phase 2 of the host-app integration. The sibling Phase 1
spec (`service-biometric-operations` in `dp4500 estandar`) defines
the server side; this spec is the corresponding client.

---

## Requirements

### Requirement: Client construction

The system SHALL provide an `HTTPClient` class in
`apps/biometric/client.py`. The class SHALL accept a `base_url`,
`timeout_seconds`, and a callable `key_resolver(sucursal_id) -> str
| None`. The constructor SHALL NOT make any HTTP request.

#### Scenario: Client construction succeeds without I/O

- GIVEN a callable key resolver
- WHEN `HTTPClient(base_url="https://dp4500-prod", timeout_seconds=5, key_resolver=...)` is instantiated
- THEN the constructor returns immediately
- AND no HTTP request is emitted
- AND `client.timeout_seconds == 5`
- AND `client.base_url == "https://dp4500-prod"` (no trailing slash)

#### Scenario: Key resolver returning None produces 503, not KeyError

- GIVEN the client is constructed with a resolver that returns `None`
  when `sucursal_id` is unknown
- WHEN `client.verify("nonexistent-sucursal", user_external_id, ...)` is called
- THEN the client raises `BiometricUnavailable("no_service_key")`
- AND no HTTP request is emitted

---

### Requirement: Per-branch key resolution

The `key_resolver` callable SHALL receive a `sucursal_id` and return
the raw bearer token for that branch, or `None` when the branch has
no `dp4500_service_key_id` set. The `env`-backend implementation
reads `DP4500_SERVICE_KEY_SUCURSAL_<id>` from the environment; an
unknown branch returns `None`. The client never logs the raw token.

#### Scenario: env-var backend resolves a configured branch

- GIVEN `DP4500_SERVICE_KEY_SUCURSAL_42=SeK_abcdef` in os.environ
- WHEN the resolver is called with `sucursal_id=42`
- THEN it returns `"SeK_abcdef"`
- AND no log line contains `"SeK_abcdef"` after the call returns

#### Scenario: env-var backend returns None for unknown branch

- GIVEN no `DP4500_SERVICE_KEY_SUCURSAL_99` is set
- WHEN the resolver is called with `sucursal_id=99`
- THEN it returns `None`

---

### Requirement: Identity enrollment request shape

The `enroll(user_external_id, *, signature_b64, timestamp, sucursal_id)`
method SHALL issue `POST {base_url}/api/biometric/service/challenge/identity/<user_external_id>/`
with `Authorization: Bearer <resolved_key>`, an empty JSON body, and
a per-request timeout of `timeout_seconds`. On a non-2xx response,
the method SHALL raise a domain exception mapping the status to one
of:

- 201 → `BiometricEnrollOk` with the response payload (parsed).
- 503 + `code: BIOMETRIC_SUSPENDED` → `BiometricSuspended`.
- 503 + `code: NO_AGENT` → `BiometricUnavailable("no_agent")`.
- 409 + `code: enrollment_required` → `BiometricEnrollConflict("no_template_on_dp4500")`.
- Any other status → `BiometricUnavailable(f"http_{status}")`.

The 201 path returns the response body (which contains the `capture_token` /
`server_nonce` / `ttl_seconds` the verification view uses next). When
the client is in identity-only enrollment mode, the response is
discarded — Phase 2's enrollment just persists `user_external_id` on the
User row and returns; the actual capture is the stub in Phase 4.

#### Scenario: 201 with capture_token

- GIVEN the server returns 201 and `{"capture_token": "...", "server_nonce": "...", "ttl_seconds": 60, ...}`
- WHEN `client.enroll(...)` is called
- THEN it returns a `BiometricEnrollOk(capture_token="...", server_nonce=..., ttl_seconds=60, ...)` instance
- AND no exception is raised

#### Scenario: 503 NO_AGENT raises BiometricUnavailable

- GIVEN the server returns 503 with `{"code": "NO_AGENT", "detail": "..."}`
- WHEN `client.enroll(...)` is called
- THEN it raises `BiometricUnavailable("no_agent")`

#### Scenario: 503 BIOMETRIC_SUSPENDED raises BiometricSuspended

- GIVEN the server returns 503 with `{"code": "BIOMETRIC_SUSPENDED", "detail": "..."}`
- WHEN `client.enroll(...)` is called
- THEN it raises `BiometricSuspended`

#### Scenario: 409 enrollment_required raises BiometricEnrollConflict

- GIVEN the server returns 409 with `{"code": "enrollment_required", "detail": "..."}`
- WHEN `client.enroll(...)` is called
- THEN it raises `BiometricEnrollConflict("no_template_on_dp4500")`

#### Scenario: Timeout raises BiometricUnavailable

- GIVEN the server hangs longer than `timeout_seconds`
- WHEN `client.enroll(...)` is called
- THEN it raises `BiometricUnavailable("timeout")` after ~`timeout_seconds` + 0.5s

---

### Requirement: Identity verification request shape

The `verify(user_external_id, *, challenge_id, signature_b64, timestamp,
sucursal_id)` method SHALL issue
`POST {base_url}/api/biometric/service/verify/identity/`
with the `{challenge_id, signature, timestamp}` JSON body. Same
auth header / timeout / error mapping as enrollment.

#### Scenario: 200 matched=True returns BiometricVerifyMatch

- GIVEN the server returns 200 with `{"matched": true, "audit_hash": "..."}`
- WHEN `client.verify(...)` is called
- THEN it returns a `BiometricVerifyMatch(matched=True, audit_hash="...")` instance

#### Scenario: 200 matched=False returns BiometricVerifyNoMatch

- GIVEN the server returns 200 with `{"matched": false, "audit_hash": "..."}`
- WHEN `client.verify(...)` is called
- THEN it returns a `BiometricVerifyNoMatch(matched=False, audit_hash="...")`

#### Scenario: 422 INVALID_TOKEN raises BiometricVerifyFailed

- GIVEN the server returns 422 with `{"code": "INVALID_TOKEN", ...}`
- WHEN `client.verify(...)` is called
- THEN it raises `BiometricVerifyFailed("challenge_expired_or_invalid")`

#### Scenario: 422 signature_invalid raises BiometricMismatch

- GIVEN the server returns 422 with `{"code": "signature_invalid", ...}`
- WHEN `client.verify(...)` is called
- THEN it raises `BiometricMismatch`

---

### Requirement: Cascade revoke request shape

The `delete_template(user_external_id, *, sucursal_id)` method SHALL
issue
`DELETE {base_url}/api/biometric/service/templates/<user_external_id>/`.
Same auth header / timeout / error mapping. On 204 the call returns
silently; on 404 (no credential) the call also returns silently (the
client treats 404 as success for idempotency).

#### Scenario: 204 No Content is silent

- GIVEN the server returns 204
- WHEN `client.delete_template(...)` is called
- THEN the call returns `None` and no exception is raised

#### Scenario: 404 is silent (idempotent)

- GIVEN the server returns 404 (no active credential at DP4500)
- WHEN `client.delete_template(...)` is called
- THEN the call returns `None`
- AND no exception is raised (idempotent: the desired post-condition
  is already satisfied)

#### Scenario: 503 BIOMETRIC_SUSPENDED raises (caught by Celery for retry)

- GIVEN the server returns 503 with `{"code": "BIOMETRIC_SUSPENDED"}`
- WHEN `client.delete_template(...)` is called
- THEN it raises `BiometricSuspended`

---

### Requirement: No fingerprint bytes at the client

The client SHALL NOT log, persist, or print fingerprint bytes,
signatures, or template bytes. The `Authorization` header value is
the ONLY non-metadata field that uses the raw key; it is set on the
request and never written to disk or logs.

#### Scenario: Signature is not logged

- GIVEN the server returns 200 with `{matched: true, audit_hash: "0x..."}`
- WHEN `client.verify(...)` runs with `signature_b64 = "deadbeef"`
- THEN no log line in the captured output contains the literal
  `"deadbeef"` after the call returns

---

## Requirements (cross-cutting)

### Requirement: Bearer auth header shape

The header SHALL be exactly `Authorization: Bearer <key>` with the
`Bearer ` prefix and a single space. The client never sends other
auth schemes on the service endpoints.

#### Scenario: Header format

- GIVEN the resolved key is `"SeK_abcdef"`
- WHEN `client.enroll(...)` issues the HTTP request
- THEN the request's `Authorization` header is `"Bearer SeK_abcdef"`
- AND no other auth-related headers are present (no `X-Api-Key`, no
  cookies)

---

### Requirement: Per-request timeout enforcement

The client SHALL enforce `timeout_seconds` per request via httpx's
own timeout. A hung DP4500 SHALL raise `BiometricUnavailable("timeout")`
once the timeout fires; the caller (a Celery task or a DRF view) is
free to retry.

#### Scenario: Timeout fires at configured value

- GIVEN `timeout_seconds=2` and a server that hangs for 5 seconds
- WHEN `client.enroll(...)` is called
- THEN it raises `BiometricUnavailable("timeout")` within ~2.5 seconds
