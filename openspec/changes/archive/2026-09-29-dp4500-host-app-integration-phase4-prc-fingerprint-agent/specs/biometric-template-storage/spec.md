# biometric-template-storage Specification — DELTA (Phase 4)
**Change**: `dp4500-host-app-integration-phase4-production-readiness`
**Branch**: `feat/dp4500-host-app-integration-phase2-sdd`

> **DELTA**: This file is a delta copy of the canonical spec at
> `openspec/specs/biometric-template-storage/spec.md` (DP4500 estandar; the original Phase 1 capability).
> The body below is byte-identical to that source. Only an
> "ADDED Spec (Phase 4)" section is appended at the end to document the Phase 4 deliverables.

---

# biometric-template-storage Specification

## Purpose

Defines how fingerprint templates are stored at rest, encrypted and separated from primary user data, and how encryption keys are versioned and rotated. The system MUST keep templates physically separate from `User`, MUST encrypt every template with per-record AES-GCM under a KMS-held KEK, and MUST support KEK rotation without service downtime.

This is a NEW capability (greenfield). The workspace has no prior biometric behavior.

---

## Requirements

### Requirement: Physical Separation from User PII

The system SHALL persist all biometric material in tables dedicated to the `biometrics` app. The `BiometricTemplate` table SHALL live in its own migration under that app. No column from `User`, `Profile`, or any other existing PII table SHALL be added or referenced for biometric storage.

The system SHALL NOT create foreign-key constraints from `BiometricTemplate` to non-biometric tables other than `User`. From the perspective of a backup that excludes the `biometrics` schema, no biometric material SHALL be present.

#### Scenario: Biometric tables are in a separate app

- GIVEN the Django app `biometrics` is registered in `INSTALLED_APPS`
- WHEN migrations are listed
- THEN they include `biometrics.0001_initial` creating `biometric_template`, `biometric_audit_event`, `approval_challenge`, `lawful_basis_record`
- AND no biometric table appears under any other Django app

#### Scenario: Backup excluding the biometrics app contains no template data

- GIVEN a `pg_dump --exclude-schema=biometrics` is taken
- WHEN the dump is searched for any column named `encrypted_fmd`, `client_pubkey_fingerprint`, or `server_aead_nonce`
- THEN zero rows match in the dump output

---

### Requirement: Per-Record AES-GCM Envelope

The system SHALL encrypt every stored FMD with AES-GCM using a fresh 96-bit random nonce per write. The system SHALL NEVER reuse a (key, nonce) pair across any two rows under the same `key_version`.

Each `BiometricTemplate` row SHALL carry: `encrypted_fmd` (ciphertext), `server_aead_nonce` (96-bit), `server_aead_tag` (128-bit), `key_version` (integer). No column SHALL contain plaintext FMD material.

The system SHALL NOT log cleartext FMD bytes, cleartext nonces together with their ciphertexts, or the user's passphrase at any layer (server or client beyond the live session).

#### Scenario: Each new template gets a unique nonce

- GIVEN N templates written by the same backing key under the same `key_version`
- WHEN the `server_aead_nonce` column is read for all N rows
- THEN every value SHALL be distinct

#### Scenario: FMD ciphertext equals AES-GCM under stated nonce and key

- GIVEN a row R with `key_version=2`, `server_aead_nonce=N`, `encrypted_fmd=C`, `server_aead_tag=T`
- WHEN the value is decrypted with the per-record DEK-2 and nonce N
- THEN the AES-GCM tag verifies and the recovered plaintext equals a valid FMD FeatureSet of the SDK's declared `format_version`

#### Scenario: Cleartext FMD never appears in logs or error responses

- GIVEN any successful or failed enrollment attempt
- WHEN the server's application logs, request logs, error responses, and audit events are inspected
- THEN none of them contain cleartext FMD, raw minutiae data, or raw fingerprint image bytes

---

### Requirement: Key Versioning and Rotation

The system SHALL support KEK rotation by tracking a `key_version` integer on every `BiometricTemplate`. Templates written under version V SHALL remain decryptable using DEKs produced by the KEK at version V. New enrollments SHALL write the latest active `key_version`.

The system SHALL provide a management command `migrate_biometric_key_version` that rewraps DEKs from an old `key_version` to a new one in batches, leaving the envelope (ciphertext, nonce, tag) unchanged but updating the `key_version` column. The command SHALL be idempotent: re-running it SHALL not duplicate work or corrupt rows.

#### Scenario: Old templates remain readable after a new KEK is added

- GIVEN templates T1..T10 exist with `key_version=1`
- WHEN the operator activates `key_version=2` for new writes (without running the migration command)
- THEN `T1..T10` continue to be readable (any code path that loads them passes the version to the KMS adapter)
- AND `T11..Tn` (newly enrolled) SHALL carry `key_version=2`

#### Scenario: Migration command advances old rows to the new version

- GIVEN templates T1..T10 with `key_version=1` and a new KEK at `key_version=2` is activated
- WHEN `manage.py migrate_biometric_key_version --from 1 --to 2` runs to completion
- THEN every row whose `key_version=1` is updated to `key_version=2` with a freshly wrapped DEK
- AND running the command a second time reports 0 rows updated and exits 0

#### Scenario: Unknown key_version is rejected on read

- GIVEN a template row with `key_version=99` and no active KEK at that version
- WHEN any code path attempts to load and decrypt the template
- THEN an `UnknownKeyVersion` error SHALL be raised and no plaintext SHALL be returned
- AND an audit event `decrypt_key_version_unknown` SHALL be recorded

---

### Requirement: KMS Boundary for the KEK

The system SHALL hold the KEK in an external KMS (AWS KMS or HashiCorp Vault). The Django process SHALL NOT have access to the raw KEK bytes. Per-record DEKs SHALL be unwrapped on demand through the `BiometricVerifierPort` adapter; the unwrapped DEK SHALL live in process memory only for the duration of the cryptographic operation.

In the event of a KMS outage, new enrollments SHALL fail with HTTP 503 and code `kms_unavailable`. Existing verifications SHALL continue to function if the cached DEKs and key-version bindings are intact.

#### Scenario: KMS outage blocks new enrollment

- GIVEN the KMS endpoint is unreachable
- WHEN `/api/biometric/enrollment/finalize` is called
- THEN the response is HTTP 503 with code `kms_unavailable`
- AND the challenge is NOT consumed (it expires naturally)
- AND an audit event `enrollment_kms_unavailable` is recorded

#### Scenario: Verification works during a partial KMS outage if cached DEKs are available

- GIVEN the KMS endpoint is unreachable but the in-memory DEK cache for the affected template is warm
- WHEN `/api/biometric/approvals/finalize` is called for a bound approval challenge
- THEN verification proceeds against the cached DEK
- AND an audit event `kms_unavailable_cached_dek_used` is recorded

#### Scenario: Raw KEK bytes are never present in Django process memory after startup

- GIVEN the Django process is running and the app is initialized
- WHEN the process memory is inspected (or a debugger breakpoint placed on any decrypt operation)
- THEN no contiguous byte region SHALL match the KEK
- AND only DEK bytes for the currently in-flight decryption SHALL appear, and only for the duration of the call

---

## Requirements Coverage

| Requirement | Proposal § |
|---|---|
| Physical Separation from User PII | §2.4 (storage model — separate table), openspec config `data_storage` |
| Per-Record AES-GCM Envelope | §2.4 encryption clause, §4 Key Choice 3 (AES-GCM + KEK), explore §"Encryption" |
| Key Versioning and Rotation | §2.4 (`key_version`), §4 Key Choice 3 (MultiFernet-style wrapping) |
| KMS Boundary for the KEK | §4 Key Choice 3, §5 (Django `KMS adapter (Vault/AWS KMS)`), §6 Risk 2 |
---

## ADDED Spec (Phase 4)

Phase 4 swaps the placeholder envelope written by `enroll_service_identity.py:114-150` (12 random nonce + 16 zero tag + 32 zero `wrapped_dek`) with the same KMS-backed envelope the Knox flow already uses at `finalize_enrollment.py:115-138`. The `wrapped_dek` column MUST carry KMS-bound ciphertext, never zero bytes.

### New Requirement SVC-KMS-1: KMS-backed wrap on the service-flow enrollment path

The system SHALL wrap the per-record DEK through `BiometricVerifierPort.wrap_dek` (or the equivalent `kms.wrap_dek` adapter selected by `BIOMETRIC_KMS_BACKEND`) before persisting a `BiometricTemplate` row from the service-flow enrollment use case. The `wrapped_dek` column MUST NOT contain 32 zero bytes; it MUST contain the KMS-returned ciphertext whose length matches the KMS adapter's `WRAPPED_DEK_LEN` constant. The `key_version` written to the row MUST equal `kms.current_key_version()` at the moment of wrap. The same envelope shape (fresh 96-bit nonce, 128-bit AES-GCM tag, ciphertext, `key_version`) already required by the existing `Per-Record AES-GCM Envelope` requirement applies unchanged. The system SHALL NOT bypass the KMS adapter on the service-flow path even when the template bytes are empty (the dev/no-hardware path).

#### Scenario: Service-flow enrollment writes a non-zero wrapped_dek under the active key version

- GIVEN `BIOMETRIC_KMS_BACKEND=aws` (or `localstack`) is configured and `BIOMETRIC_ACTIVE_KEK_VERSION=2`
- WHEN `POST /api/biometric/service/identity/enroll/` is called with a non-empty `client_encrypted_fmd`
- THEN the persisted `BiometricTemplate.wrapped_dek` is NOT 32 zero bytes
- AND `BiometricTemplate.key_version` equals 2
- AND `kms.unwrap_dek(wrapped_dek, 2) + aesgcm_decrypt(nonce, ciphertext, tag, dek)` recovers the original template bytes

#### Scenario: Service-flow enrollment unwraps the DEK at verification time

- GIVEN a `BiometricTemplate` row written by the service-flow path at `key_version=2`
- WHEN the matching approval-challenge verification endpoint loads the row
- THEN the KMS adapter unwraps the `wrapped_dek` for `key_version=2`
- AND verification proceeds against the recovered plaintext without raising `UnknownKeyVersion`

### New Requirement SVC-KMS-2: KMS-unavailable failure path on service-flow enrollment

When the KMS adapter raises an availability error during service-flow enrollment, the system SHALL fail the enrollment with HTTP 503 and code `kms_unavailable`. The challenge MUST NOT be consumed; the audit row MUST be `event_type=service.enrollment_kms_unavailable` with `external_system=requesting_service_key.name`. Cached DEKs continue to satisfy the existing `KMS Boundary for the KEK` requirement for in-flight verifications, but no new service-flow row MAY be persisted while the KMS is unreachable.

#### Scenario: KMS outage blocks service-flow enrollment with 503 kms_unavailable

- GIVEN the KMS endpoint is unreachable and no cached DEK exists for the target `key_version`
- WHEN `POST /api/biometric/service/identity/enroll/` is called
- THEN the response is HTTP 503 with code `kms_unavailable`
- AND the challenge is NOT consumed (it expires naturally)
- AND a `BiometricAuditEvent` with `event_type=service.enrollment_kms_unavailable` is persisted
- AND no `BiometricTemplate` row is written by this request
