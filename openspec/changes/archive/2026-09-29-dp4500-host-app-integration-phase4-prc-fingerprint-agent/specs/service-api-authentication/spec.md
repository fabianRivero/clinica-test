# service-api-authentication Specification — DELTA (Phase 4)
**Change**: `dp4500-host-app-integration-phase4-production-readiness`
**Branch**: `feat/dp4500-host-app-integration-phase2-sdd`

> **DELTA**: This file is a delta copy of the canonical spec at
> `openspec/changes/dp4500-host-app-integration-phase1/specs/service-api-authentication/spec.md` (DP4500 estandar; Phase 1 capability).
> The body below is byte-identical to that source. Only an
> "ADDED Spec (Phase 4)" section is appended at the end to document the Phase 4 deliverables (rotation endpoint, mTLS handshake, vault resolver plugin).

---

# service-api-authentication Specification

## Purpose

Defines the behavior by which a trusted external system (initially the clinic at `C:\proyectos\proyecto C`) authenticates itself to DP4500's biometric endpoints without impersonating a human user. Covers a per-system API key model, a bearer-token authentication class, active-key lifecycle, and rate-limited freshness updates. This is the bedrock on which the rest of the host-app integration (`service-biometric-operations`) is built.

## Requirements

### Requirement: ServiceAPIKey model

The system SHALL provide a `ServiceAPIKey` model in `apps/accounts` (or a new `apps/services` app — see proposal §9, decided at design time) with the fields `id, name, key_hash, created_at, last_used_at, is_active, rotated_from_id`. The raw key value SHALL be a `secrets.token_urlsafe(32)` string, returned exactly once at creation, and SHALL be stored only as a SHA-256 hash.

#### Scenario: Management command mints a new service key

- GIVEN no existing `ServiceAPIKey` with `name="clinic-prod"`
- WHEN an admin runs `python manage.py create_service_api_key --name clinic-prod`
- THEN the response prints `{name, raw_token}` where `raw_token` is a 43-character url-safe base64 string
- AND a `ServiceAPIKey` row exists with `key_hash = SHA-256(raw_token)`, `is_active=True`, `created_at = now()`

#### Scenario: Raw token is never persisted

- GIVEN a `ServiceAPIKey` row exists
- WHEN an operator queries the DB for that row's columns
- THEN the row exposes `key_hash` (a 64-char hex string) and no column matching the raw 43-char token
- AND no log line printed during creation contains the raw token value after the command returns

---

### Requirement: ServiceAPIKeyAuthentication class

The system SHALL provide a `ServiceAPIKeyAuthentication` class in `apps/biometric/api/permissions.py`. The class SHALL read `Authorization: Bearer <raw>` headers, compute `SHA-256(raw)`, look up the matching active `ServiceAPIKey` row, and on success attach the row instance to `request.service_key`. On any of (1) missing header, (2) malformed bearer, (3) unknown hash, (4) inactive key, the class SHALL return `None` (so the request falls through to DRF's permission machinery which will respond 401).

#### Scenario: Active key authenticates the request

- GIVEN a `ServiceAPIKey` row with `name="clinic-prod"`, `key_hash=X`, `is_active=True`
- WHEN a request arrives with header `Authorization: Bearer <raw>` where `SHA-256(raw) == X`
- THEN the authentication class returns the `ServiceAPIKey` instance
- AND `request.service_key` is the row
- AND downstream views can read `request.service_key.name`

#### Scenario: Inactive key rejected

- GIVEN the same row but `is_active=False`
- WHEN the same request arrives
- THEN the authentication class returns `None`
- AND the view returns HTTP 401 with code `service_key_inactive`

#### Scenario: Missing or malformed header rejected

- GIVEN no Authorization header (or a non-Bearer scheme)
- WHEN any request arrives at a service endpoint
- THEN the authentication class returns `None`
- AND the view returns HTTP 401 with code `service_key_missing`

#### Scenario: Unknown token rejected

- GIVEN an active `ServiceAPIKey` with `key_hash=X`
- WHEN a request arrives with `Authorization: Bearer <wrong>` where `SHA-256(wrong) != X`
- THEN the authentication class returns `None`
- AND the view returns HTTP 401 with code `service_key_unknown`

---

### Requirement: last_used_at refresh with rate limiting

The system SHALL update `last_used_at` on the `ServiceAPIKey` row at most once per minute per key. The implementation SHALL compare the current `last_used_at` to the in-memory "last write" timestamp held in the request thread; if the difference is under 60 seconds, the update is skipped.

#### Scenario: Frequent requests do not hot-write the row

- GIVEN an active `ServiceAPIKey` with `last_used_at = T0`
- WHEN 100 authenticated requests arrive within the next 30 seconds
- THEN the row's `last_used_at` is updated at most once (when the first request passes the 60s gate after `T0`)
- AND subsequent requests within the same minute do not write to the row

#### Scenario: Idle key gets a fresh timestamp after quiet period

- GIVEN a key with `last_used_at = T0`
- WHEN no request has used the key for 90 seconds
- AND a new authenticated request arrives
- THEN the row's `last_used_at` is updated to the new request time

---

### Requirement: Per-key rate limit

The system SHALL enforce a per-key rate limit of `DP4500_SERVICE_RATE_LIMIT_PER_MINUTE` requests per 60-second window, default `1000`. The class SHALL integrate with `apps.biometric.api.throttles.ServiceAPIKeyThrottle` (a new throttle class).

#### Scenario: Within limit

- GIVEN a key with 50 requests already served this minute
- WHEN another authenticated request arrives
- THEN it is allowed (DRF throttle returns None)

#### Scenario: Over limit

- GIVEN a key with `1000` requests already served this minute
- WHEN another authenticated request arrives
- THEN the view returns HTTP 429 with code `service_key_rate_limited`
---

## ADDED Spec (Phase 4)

Phase 4 adds three capabilities on top of the existing `ServiceAPIKey` model and `ServiceAPIKeyAuthentication` class: a `POST /api/biometric/service/keys/<id>/rotate/` endpoint that atomically mints a successor key and deactivates the predecessor; an mTLS handshake requirement between the workstation (browser or `fingerprint-agent`) and DP4500 when `DP4500_REQUIRE_MTLS=true`; and a Vault-backed plugin resolver selected by `ACCOUNTS_KEY_STORE_BACKEND=vault`.

### New Requirement SVC-ROT-1: POST /api/biometric/service/keys/<id>/rotate/ endpoint

The system SHALL expose a DRF view behind the existing `ServiceAPIKeyAuthentication` class at the URL pattern `POST /api/biometric/service/keys/<int:key_id>/rotate/`. The request body SHALL accept `{"name": "<new-key-name>"}`. Inside a single `transaction.atomic()` block the view SHALL: (1) mint a fresh `secrets.token_urlsafe(32)` raw token, (2) create a new `ServiceAPIKey` row with `key_hash = SHA-256(raw_token)`, `is_active=True`, and `rotated_from_id=<old_key_id>`, (3) set `<old_key>.is_active=False` and persist that change, (4) emit one `BiometricAuditEvent` with `event_type="service.api_key_rotated"`, `external_system=requesting_service_key.name`, and `metadata_json={"new_key_id": new.pk, "old_key_id": old.pk}`. The response SHALL be HTTP 201 with body `{"new_key_id": <int>, "raw_token": "<43-char urlsafe-base64>", "rotated_from": <int>}`. The `raw_token` is returned exactly once and SHALL NOT be re-emitted by any subsequent endpoint.

#### Scenario: Rotation mints a successor and deactivates the predecessor in one transaction

- GIVEN an active `ServiceAPIKey` row with `id=7`, `name="clinic-prod"`, `is_active=True`
- WHEN `POST /api/biometric/service/keys/7/rotate/` is called with body `{"name": "clinic-prod-2026"}` and a valid `Authorization: Bearer <old_raw>`
- THEN a new `ServiceAPIKey` row exists with `name="clinic-prod-2026"`, `key_hash=SHA-256(raw_token)`, `is_active=True`, `rotated_from_id=7`
- AND the predecessor row 7 has `is_active=False`
- AND the response is HTTP 201 with `raw_token` (a 43-character urlsafe-base64 string)
- AND a `BiometricAuditEvent` row exists with `event_type="service.api_key_rotated"`, `external_system="clinic-prod"`, `metadata_json` containing both `new_key_id` and `old_key_id`

#### Scenario: Replaying the rotation against the now-inactive predecessor fails

- GIVEN predecessor row 7 has been deactivated by a successful rotation
- WHEN `POST /api/biometric/service/keys/7/rotate/` is called again with the original raw token
- THEN the `ServiceAPIKeyAuthentication` class returns `None` (the key is inactive)
- AND the view returns HTTP 401 with code `service_key_inactive`
- AND no new `ServiceAPIKey` row is created

### New Requirement SVC-MTLS-1: mTLS handshake requirement between workstation and DP4500

When `DP4500_REQUIRE_MTLS=true` the `ServiceAPIKeyAuthentication` class SHALL additionally verify that the SHA-256 client certificate fingerprint attached to the request (read by `client_cert_middleware` from the `HTTP_X_SSL_CLIENT_FINGERPRINT` or `HTTP_X_FORWARDED_CLIENT_CERT_FINGERPRINT` header) matches the value of `ServiceAPIKey.client_cert_fingerprint` on the resolved row. On mismatch the class SHALL return `None` and the view SHALL return HTTP 401 with code `client_cert_mismatch`. When the middleware does not attach a fingerprint the class SHALL return `None` and the view SHALL return HTTP 401 with code `mtls_required`. The `DP4500_REQUIRE_MTLS=false` default (dev / Vite proxy) preserves the existing bearer-only behavior unchanged.

#### Scenario: Valid bearer + matching client-cert fingerprint succeeds when mTLS is required

- GIVEN `DP4500_REQUIRE_MTLS=true` and `ServiceAPIKey(id=7, key_hash=X, client_cert_fingerprint="AB:CD:...")`
- WHEN a request arrives with `Authorization: Bearer <raw>` (where `SHA-256(raw)==X`) AND `HTTP_X_SSL_CLIENT_FINGERPRINT=AB:CD:...`
- THEN the authentication class returns the `ServiceAPIKey` instance and the view proceeds normally

#### Scenario: Valid bearer + missing client-cert fingerprint is rejected when mTLS is required

- GIVEN `DP4500_REQUIRE_MTLS=true` and `ServiceAPIKey(id=7, client_cert_fingerprint="AB:CD:...")`
- WHEN a request arrives with `Authorization: Bearer <raw>` (valid) but without `HTTP_X_SSL_CLIENT_FINGERPRINT`
- THEN the view returns HTTP 401 with code `mtls_required`

#### Scenario: Valid bearer + mismatched client-cert fingerprint is rejected when mTLS is required

- GIVEN `DP4500_REQUIRE_MTLS=true` and `ServiceAPIKey(id=7, client_cert_fingerprint="AB:CD:...")`
- WHEN a request arrives with valid bearer and `HTTP_X_SSL_CLIENT_FINGERPRINT=11:22:...`
- THEN the view returns HTTP 401 with code `client_cert_mismatch`

### New Requirement SVC-VAULT-1: Vault key-resolver plugin backend

The system SHALL expose a `vault_service_key_resolver(sucursal_id: int) -> str | None` function in `apps/accounts/vault.py` that reads `secret/clinic/dp4500/service-key-<sucursal_id>` from a Vault KV v2 secrets engine and returns the `raw_token` field. The `get_service_key_resolver()` plugin dispatch SHALL return this function when `ACCOUNTS_KEY_STORE_BACKEND=vault` and SHALL fall back to the existing `env_key_resolver` when the setting is `env` (default) or when `VAULT_ADDR` is unset (dev). When `ACCOUNTS_KEY_STORE_BACKEND=vault` is active the rotation endpoint SHALL write the new raw token to Vault before the HTTP response and SHALL DELETE the predecessor raw token from Vault before returning; if either Vault call fails the rotation transaction is rolled back and the database is unchanged.

#### Scenario: Vault backend resolves the service key for the requesting sucursal

- GIVEN `ACCOUNTS_KEY_STORE_BACKEND=vault` and `VAULT_ADDR=https://vault.local:8200` and a Vault KV v2 entry `secret/clinic/dp4500/service-key-42=raw_token="<43-char>"`
- WHEN `get_service_key_resolver()(42)` is called
- THEN it returns the 43-character raw token string
- AND no environment variable `DP4500_SERVICE_KEY_SUCURSAL_42` is consulted

#### Scenario: env backend fallback when VAULT_ADDR is unset in vault mode

- GIVEN `ACCOUNTS_KEY_STORE_BACKEND=vault` but `VAULT_ADDR` is unset (or empty)
- WHEN `get_service_key_resolver()(42)` is called
- THEN the dispatch falls back to `env_key_resolver`
- AND if neither vault nor env resolves, the function returns `None` and the caller surfaces 401 `service_key_unknown`

#### Scenario: Rotation writes the new token to vault and deletes the predecessor atomically with the DB update

- GIVEN `ACCOUNTS_KEY_STORE_BACKEND=vault` and a vault entry exists for sucursal 42
- WHEN `POST /api/biometric/service/keys/<old_id>/rotate/` succeeds
- THEN a new vault entry `secret/clinic/dp4500/service-key-42` exists with the new raw_token
- AND the predecessor vault entry has been DELETED
- AND if either vault call fails the database `ServiceAPIKey` writes are rolled back
