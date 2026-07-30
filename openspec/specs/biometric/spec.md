# Delta for Biometric

New domain; archive promotes this to canonical full spec. Scope: DigitalPersona 4500 integration via per-PC `fingerprint-agent` over Cloudflare Tunnel. Tablet kiosk and biometric login out of scope. Backend encrypts templates with Fernet and decides match threshold server-side.

## ADDED Requirements

### Requirement: Encrypted Template Storage

The system SHALL encrypt every fingerprint template with Fernet using a single key loaded from the `BIOMETRIC_FERNET_KEY` environment variable and SHALL store ciphertext in a `BinaryField`. Plaintext SHALL NOT be persisted. `BIOMETRIC_FERNET_KEY` SHALL be required; the system SHALL fail to start if it is missing or invalid.

#### Scenario: Template persisted encrypted

- GIVEN captured bytes `T`
- WHEN the backend persists the template
- THEN the stored column SHALL be a Fernet token of `T` and no plaintext SHALL appear

#### Scenario: Round-trip decryption succeeds

- GIVEN a row encrypted with the configured key
- WHEN the backend reads the row
- THEN decryption SHALL yield the original bytes

#### Scenario: Missing key fails fast at startup

- GIVEN `BIOMETRIC_FERNET_KEY` is unset or invalid
- WHEN the Django app initializes
- THEN startup SHALL fail with a clear error and the system SHALL NOT serve requests

#### Scenario: Wrong key fails closed

- GIVEN a row encrypted with K_X and current `BIOMETRIC_FERNET_KEY=K_Y` (different key)
- WHEN the backend decrypts
- THEN `InvalidToken` SHALL be raised and no plaintext SHALL appear in the message or logs

---

### Requirement: HuellaBiometricaCliente Model Updates

The model SHALL add `template_format`, `updated_at`, `last_match_at`, `last_match_score`. `device_serial` already exists (keep). `Proveedor` SHALL add `DIGITAL_PERSONA`. Legacy `MOCK` SHALL be renamed to `MOCK_LEGACY`. The model SHALL enforce `unique_together(cliente)` so each client has at most one fingerprint (cross-sucursal). The model SHALL NOT include `sucursal_id` or `dedo` (a client has one registered fingerprint, replaceable on re-enrollment).

#### Scenario: Migration adds fields and enum

- GIVEN the model has only legacy fields
- WHEN `makemigrations` runs
- THEN a migration SHALL add the new fields and the `DIGITAL_PERSONA` enum value

#### Scenario: Duplicate rejected

- GIVEN a client already has a `HuellaBiometricaCliente` row
- WHEN the API re-enrolls the same `cliente`
- THEN the backend SHALL reject with a uniqueness error

#### Scenario: No sucursal on model

- GIVEN a fresh database
- WHEN the migration runs
- THEN `HuellaBiometricaCliente` SHALL have no `sucursal_id` column

---

### Requirement: BiometricAttempt Audit Log

The system SHALL persist a `BiometricAttempt` per enrollment and verification with `cita_id`, `usuario_id`, `cliente_id`, `operation` (`VERIFY`|`ENROLL`), `success`, `score`, `failure_reason`, `agent_pc_id`, `created_at`. A composite index on `(cita_id, created_at)` SHALL exist.

#### Scenario: Successful verify logged

- GIVEN verify succeeds with score 0.91
- WHEN the backend finalizes
- THEN a `BiometricAttempt` row SHALL exist with `success=true`, `score=0.91`, `operation='VERIFY'`

#### Scenario: Failed verify records reason

- GIVEN the agent returned no image
- WHEN the backend finalizes
- THEN `BiometricAttempt(success=false, failure_reason='NO_IMAGE')` SHALL be written

#### Scenario: Query ordered by time

- GIVEN multiple attempts for one `cita_id`
- WHEN the API lists by `cita_id`
- THEN rows SHALL return ASC by `created_at` using the `(cita_id, created_at)` index

---

### Requirement: AgentToken Lifecycle

`AgentToken` SHALL store `name`, `sucursal_id`, `token_hash`, `public_url`, `is_active`, `last_seen_at`. On create the raw token SHALL be returned once and SHALL NOT be retrievable afterwards. Inactive tokens SHALL be rejected by the agent auth middleware.

#### Scenario: Raw token returned once

- GIVEN admin calls `POST /api/admin/fingerprint/agents/`
- WHEN the response returns
- THEN it SHALL include the raw token string and a subsequent `GET` SHALL return only `token_hash` metadata

#### Scenario: Inactive token rejected

- GIVEN an agent with `is_active=false`
- WHEN it calls any protected endpoint
- THEN the response SHALL be `401` and no biometric data SHALL be returned

#### Scenario: Heartbeat updates last_seen

- GIVEN an active agent calls the heartbeat
- WHEN the request completes
- THEN `last_seen_at` SHALL equal current UTC time

---

### Requirement: Enrollment Wizard Integration

`ConversionStepBiometric.tsx` SHALL call a backend endpoint returning `agent_url` and `capture_token`. The agent SHALL expose `POST /capture` returning `{template_b64, quality_score, device_serial}`. The backend SHALL encrypt and persist the template, write `BiometricAttempt(operation='ENROLL')`, and SHALL require explicit consent recorded before the capture step.

#### Scenario: Happy path enrollment

- GIVEN consent checkbox ticked
- WHEN the wizard calls enroll-init then agent POSTs `/capture`
- THEN the backend SHALL persist the encrypted template and write `BiometricAttempt(operation='ENROLL', success=true)`

#### Scenario: Missing consent blocks

- GIVEN no consent recorded
- WHEN enroll-init is called
- THEN the backend SHALL return `400` with code `CONSENT_REQUIRED`

#### Scenario: Low quality rejected

- GIVEN the agent returns `quality_score < 50`
- WHEN the backend receives the capture
- THEN no template SHALL be persisted and `BiometricAttempt(success=false, failure_reason='LOW_QUALITY')` SHALL be written

---

### Requirement: Verification Flow (Server Decides Match)

`POST /api/admin/citas/:id/verify-init/` SHALL return the encrypted template, `agent_url`, and `capture_token`. The agent SHALL POST to `/match` returning a RAW score only. The backend SHALL compare against the configured threshold and SHALL decide match/no-match. On match, `CitaMedica` SHALL become `CONFIRMADA` with `metodo_confirmacion='BIOMETRICO'`; the backend SHALL write `BiometricAttempt(operation='VERIFY', success=true)` and update `last_match_at`/`last_match_score`.

#### Scenario: Score above threshold confirms

- GIVEN appointment in `REALIZADA_PENDIENTE_VERIFICACION` and threshold 0.85
- WHEN the agent returns score 0.92
- THEN `estado=CONFIRMADA`, `metodo_confirmacion='BIOMETRICO'` and a successful `BiometricAttempt` SHALL be written

#### Scenario: Score below threshold leaves pending

- GIVEN the same appointment and threshold
- WHEN the agent returns score 0.71
- THEN `estado` SHALL remain `REALIZADA_PENDIENTE_VERIFICACION`, `BiometricAttempt(success=false, score=0.71)` SHALL be written, and the endpoint SHALL return `200` with `{matched: false, score: 0.71}`

#### Scenario: Verify-init requires pending-verification

- GIVEN `CitaMedica` in `CONFIRMADA`
- WHEN verify-init is called
- THEN the backend SHALL return `400` with code `INVALID_STATE`

---

### Requirement: Cross-Sucursal Fingerprint Reuse

Template lookup SHALL be filtered by `cliente_id` only. The system SHALL NOT enforce `sucursal_id` on the template. A client enrolled in any branch SHALL be verifiable in any other branch.

#### Scenario: Verify from different sucursal succeeds

- GIVEN client C enrolled in branch A
- WHEN an admin in branch B initiates verify for C
- THEN the backend SHALL locate C's template and SHALL NOT 404 due to sucursal mismatch

---

### Requirement: Manual Fallback When No Fingerprint

When a client has no `HuellaBiometricaCliente` row, the frontend SHALL NOT offer biometric verification; only the manual option SHALL render. The backend SHALL return a `has_fingerprint` flag in the appointment payload.

#### Scenario: No template hides biometric option

- GIVEN client C with no fingerprint row
- WHEN the frontend loads the appointment
- THEN `has_fingerprint=false` SHALL be in the payload and the UI SHALL render only "Confirmar manualmente"

#### Scenario: Enrollment available without template

- GIVEN the same client
- WHEN the admin opens the client profile
- THEN "Enroll fingerprint" SHALL be offered and the verify flow SHALL remain hidden

---

### Requirement: Sensitivity Threshold Policy

The system SHALL read the match threshold from env var `BIOMETRIC_MATCH_THRESHOLD` (float in `[0,1]`). Default SHALL be `0.85`. Threshold SHALL be enforced server-side; the agent SHALL receive no threshold and SHALL return raw scores only.

#### Scenario: Custom threshold enforced

- GIVEN `BIOMETRIC_MATCH_THRESHOLD=0.90`
- WHEN the agent returns score 0.88
- THEN the backend SHALL treat it as no-match and the threshold used SHALL be logged (value only)

#### Scenario: Missing env var uses default

- GIVEN `BIOMETRIC_MATCH_THRESHOLD` is unset
- WHEN the backend starts
- THEN the effective threshold SHALL be `0.85`

---

### Requirement: Agent Registration and Lifecycle

The system SHALL expose CRUD endpoints under `/api/admin/fingerprint/agents/` (create, list, retrieve, delete), restricted to `ADMIN_PRINCIPAL` and `ADMIN_SUCURSAL`. Creation SHALL generate a `secrets.token_urlsafe(32)` token and SHALL return it once.

#### Scenario: Admin lists agents

- GIVEN an admin with permission
- WHEN they call `GET /api/admin/fingerprint/agents/`
- THEN the response SHALL list `name`, `sucursal`, `public_url`, `is_active`, `last_seen_at` and SHALL NOT include `token_hash` or any raw token

#### Scenario: Delete deactivates token

- GIVEN an admin deletes agent X
- WHEN the agent next calls any protected endpoint
- THEN the response SHALL be `401`

---

### Requirement: Agent Heartbeat and Offline Detection

Each active agent SHALL POST a heartbeat every 60 seconds. The admin UI SHALL mark an agent "offline" when `last_seen_at > 5 minutes`. The heartbeat endpoint SHALL always return `204`, even on internal errors.

#### Scenario: Recent heartbeat shows online

- GIVEN `last_seen_at` is 30 seconds old
- WHEN the admin UI polls
- THEN the agent SHALL be marked online

#### Scenario: Stale heartbeat shows offline warning

- GIVEN `last_seen_at` is 6 minutes old
- WHEN the admin UI polls
- THEN the agent SHALL be marked offline with a warning badge

---

### Requirement: No Retry Limit on Failed Matches

The system SHALL NOT cap the number of verification attempts per appointment. Each attempt SHALL write a new `BiometricAttempt` row. Manual confirmation SHALL remain available regardless of failed biometric attempts.

#### Scenario: Unlimited attempts logged

- GIVEN a single appointment with 5 failed attempts
- WHEN a 6th attempt occurs
- THEN the attempt SHALL proceed normally and a 6th `BiometricAttempt` row SHALL be created

#### Scenario: Manual confirmation always available

- GIVEN any number of failed biometric attempts
- WHEN the admin confirms manually
- THEN the backend SHALL accept it and SHALL set `metodo_confirmacion='MANUAL'`

---

### Requirement: Permissions on Biometric Endpoints

The system SHALL restrict enroll and agent CRUD endpoints to `ADMIN_PRINCIPAL` and `ADMIN_SUCURSAL`. `RECEPCIONISTA` SHALL be permitted to verify but SHALL NOT enroll or delete templates. Workers and unauthenticated users SHALL receive `403` / `401`.

#### Scenario: Recepcionista can verify but not enroll

- GIVEN a user with role `RECEPCIONISTA`
- WHEN they call verify-init
- THEN the request SHALL succeed
- AND when they call enroll-init
- THEN the response SHALL be `403`

#### Scenario: Unauthenticated request rejected

- GIVEN no auth token
- WHEN any biometric endpoint is called
- THEN the response SHALL be `401`

---

### Requirement: Privacy of Template Material

The system SHALL NOT log, serialize in responses, or include in error messages any plaintext template, decrypted bytes, or base64/hex-encoded template body. `BiometricAttempt` SHALL store only metadata. Template blobs SHALL NOT appear in Django error pages, stack traces, or log lines.

#### Scenario: Error response omits template

- GIVEN a Fernet decryption failure during verify
- WHEN the backend returns the error
- THEN the response body SHALL contain only a generic code/message and SHALL NOT contain any base64 or binary template data

#### Scenario: Application logs scrubbed

- GIVEN an exception occurs while persisting a template
- WHEN the Django logger writes the traceback
- THEN no log line SHALL contain the captured template bytes (base64 or hex)

---

### Requirement: Frontend Replaces mockFingerprint.ts with biometricClient.ts

The frontend SHALL replace `frontend/src/services/fingerprint/mockFingerprint.ts` with `biometricClient.ts`, which calls backend `enroll-init` and `verify-init` and forwards the returned `agent_url` + `capture_token`. The mock service SHALL be removed from the bundle. No call site SHALL reference `mockFingerprint` after this change.

#### Scenario: Build no longer imports mock

- GIVEN `npm run build` succeeds
- WHEN a dependency scan runs
- THEN no module SHALL import from `services/fingerprint/mockFingerprint`

#### Scenario: Wizard calls new client

- GIVEN the enrollment wizard mounts
- WHEN it requests fingerprint capture
- THEN `biometricClient.enrollInit(clienteId)` SHALL be invoked and the legacy mock SHALL NOT be called

---

## Cross-Domain Effects

| Domain | Effect |
|--------|--------|
| `appointment-states` | Unchanged. Only the `CONFIRMADA` transition sets `metodo_confirmacion='BIOMETRICO'`. |
| `auth-me` | Unchanged. Biometric login out of scope. |
| `operations` | Unchanged. `TabletKiosko.set_clave()` remains the kiosk path. |