# wizard-biometric-enrollment Specification — DELTA (Phase 3)

**Change**: `dp4500-host-app-integration-phase3-capture-client`
**Branch**: `feat/dp4500-host-app-integration-phase2-sdd`

> **DELTA**: This file is a delta copy of the archived Phase 2 spec at
> `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/specs/wizard-biometric-enrollment/spec.md`.
> The body is byte-identical to the archived spec. Only an "ADDED Capture Surface (Phase 3)"
> section is appended at the end to document the real capture client wiring.

# wizard-biometric-enrollment Specification

## Purpose

Defines the wizard step 4 behavior in the prospect → cliente
conversion flow when the operator captures the new client's
fingerprint. Captures the integration between the prospect-convert
wizard and DP4500's identity enrollment endpoint, the data-model
side effects in the clinic, and the stub UI placeholder for Phase 4.

This is Phase 2's enrollment surface. The actual fingerprint
**capture mechanism** is deferred to Phase 4 (Open Q1 in the plan);
Phase 2 ships a "captura pendiente" stub that records the
`user_external_id` and lets the operator advance the wizard.

---

## Requirements

### Requirement: Step 4 advances only with biometric_external_id

The system SHALL require `User.biometric_external_id` to be set
before the operator can mark step 4 of the prospect → cliente
conversion wizard as complete. The pre_save signal on User
generates the UUID on first save; the wizard's "Continuar" button
is disabled while the field is empty.

#### Scenario: First prospect save generates the UUID

- GIVEN a new `Prospecto` whose conversion creates a `User`
- WHEN the user instance is first saved
- THEN `user.biometric_external_id` is a non-null UUID
- AND the value is stable across subsequent saves of the same user

#### Scenario: UUID is unique across users

- GIVEN two distinct User rows in the DB
- WHEN their `biometric_external_id` are compared
- THEN they are different
- AND the unique constraint on the field holds

---

### Requirement: Step 4 renders the capture pending stub

The view `ConversionStepBiometricView` (or its successor) SHALL
render the `templates/biometric/capture_pending.html` template when
`capture_strategy` is `pending` (the default for Phase 2). The
template SHALL display:

- The user's `biometric_external_id` (read-only, hidden by default).
- A "Continuar sin captura" button (operator override) that allows
  advancing the wizard WITHOUT biometric capture. The override
  logs an audit event (`manual_advance_without_biometric`) so the
  behavior is observable.

Phase 4 replaces this template with the real capture client (browser
Web SDK or Electron child process).

#### Scenario: Wizard step 4 renders the stub

- GIVEN the prospect-convert wizard is on step 4
- WHEN `ConversionStepBiometricView.get(...)` is rendered
- THEN it returns 200 with the capture_pending.html template
- AND the template displays the user's `biometric_external_id`
- AND a "Continuar sin captura" button is present

#### Scenario: Operator advances the wizard without biometric

- GIVEN the operator is on step 4
- WHEN they click "Continuar sin captura"
- THEN the wizard advances to step 5
- AND an audit event is appended to a local
  `WizardManualAdvanceAudit` row (or similar local model) carrying
  `user_id`, `prospect_id`, `wizard_step`, `at`
- AND no DP4500 call is made (the stub is purely local)

---

### Requirement: Biometric availability status

The view SHALL render a status banner showing whether biometric
capture is currently available at DP4500, by issuing an inexpensive
probe (a tiny `GET`/healthcheck style call, or the response of the
previous `challenge/identity/` call cached for 60 seconds). The
banner says:

- "Disponible" if DP4500 responds with a non-error status.
- "No disponible temporalmente — avance manual habilitado" if
  `BiometricUnavailable` was raised.

#### Scenario: Banner reflects available status

- GIVEN DP4500 returned 201 to the previous challenge call within
  the last 60 seconds
- WHEN the wizard is on step 4
- THEN the banner reads "Disponible" in green

#### Scenario: Banner reflects unavailable status

- GIVEN DP4500 returned 503 on the previous probe
- WHEN the wizard is on step 4
- THEN the banner reads "No disponible temporalmente — avance manual
  habilitado" in yellow

---

### Requirement: Local enrollment record

When the operator advances the wizard (with or without capture),
the clinic SHALL persist a local `BiometricEnrollmentRecord` row
capturing: `user_id`, `user_external_id`,
`enrollment_strategy` (one of `pending`, `mock`, `websdk`,
`electron`; `pending` in Phase 2), `advanced_at`, `advanced_by`,
`wizard_id`, `cancelled_at` (nullable).

#### Scenario: Manual advance creates the local record

- GIVEN the operator clicked "Continuar sin captura"
- WHEN the wizard advances
- THEN a `BiometricEnrollmentRecord(user_id=..., user_external_id=...,
  enrollment_strategy="pending", advanced_at=now, advanced_by=request.user)`
  is persisted

---

## Requirements (cross-cutting)

### Requirement: No fingerprint bytes in the local DB

The `BiometricEnrollmentRecord` model carries metadata, not bytes.
The template, signature, server nonce, and audit_hash live on the
DP4500 side; the clinic sees only the `user_external_id` and
strategy marker.

#### Scenario: Field inventory check

- GIVEN the `BiometricEnrollmentRecord` model definition
- WHEN the model is inspected for byte-typed fields (BinaryField,
  ImageField, etc.)
- THEN none are present

---

### Requirement: Cancellation

The operator can cancel step 4 (back to step 3, or abort the
wizard). Cancellation sets `cancelled_at` on the most recent
`BiometricEnrollmentRecord` for that user; no other side effects
(no DP4500 calls, no extra audit rows).

#### Scenario: Cancel advances back without side effects

- GIVEN step 4 has an open `BiometricEnrollmentRecord` (no
  `advanced_at` yet)
- WHEN the operator clicks "Cancelar"
- THEN the wizard returns to step 3
- AND the open record's `cancelled_at` is set to `now()`

## ADDED Capture Surface (Phase 3)

Phase 2 closed the integration with a placeholder `template_b64` (end-to-end validated in browser via DevTools). Phase 3 = Q1 decision: HOW the workstation actually captures fingerprints when real hardware arrives. User decision: **browser Web SDK direct** — vendorize `@digitalpersona/fingerprint` + `@digitalpersona/websdk` in node_modules. The original 2026-07-29 `fingerprint-agent` pattern is the **Phase 4 fallback** (not the default).

### New scenario §X.Y — Real capture (hardware-connected path)

Given: the workstation has a DigitalPersona 4500 reader connected via USB AND the HID Authentication Device Client is running (the WebChannel host).

When: the operator clicks "Activar lector" in step 4 of the prospect → cliente conversion wizard.

Then:
1. The frontend dynamically imports `@digitalpersona/fingerprint`.
2. The SDK initializes a `WebSdk.WebChannelClient` (or `WebSdk.Fingerprint.WebApi`).
3. `client.getDeviceList()` returns at least one device.
4. `device.AcquireFingerprint(FingerIndex.Any, ...)` captures the fingerprint image.
5. The image is processed into a template + quality score.
6. `template_b64` (base64url-encoded) and `quality_score` (0-100) are returned to the frontend.
7. The wizard sends `{template_b64: <non-empty>, quality_score: <real>, device_serial: <SDK-reported>}` to the existing DP4500 enroll endpoint.
8. DP4500 enroll returns 201 Created.
9. The wizard transitions to step 5 (pago) without error.

### Modified scenario §X.Y — Real capture dev fallback (NO_AGENT path) [PRESERVED]

Given: the workstation has NO DigitalPersona reader connected (or HID Authentication Device Client is NOT running).

When: the operator clicks "Activar lector" in step 4.

Then (UNCHANGED from Phase 2):
1. The wizard detects NO_AGENT via the legacy capture endpoint returning 503.
2. The frontend mints a UUID via `crypto.randomUUID()`.
3. The wizard calls `enrollIdentity(userExternalId, '', signingKey, fingerprintHex, 'DP_PROPRIETARY')`.
4. DP4500 enroll returns 201.
5. The wizard transitions to step 5.

**The Phase 3 implementation MUST preserve this NO_AGENT path verbatim** — `useConversionWizard.ts:842-859` is carved out as out-of-scope for any modification.

### Modified scenario §X.Y — Real capture error path (SDK init failure)

Given: the SDK fails to initialize (e.g. WebChannel host unreachable, browser blocks WebUSB).

When: the operator clicks "Activar lector".

Then:
1. The SDK throws an exception during `client = new WebSdk(...)` or `client.getDeviceList()`.
2. The frontend catches the error and falls back to the NO_AGENT path (Phase 2 behavior).
3. The wizard shows "Activando lector" for 3 seconds, then completes with the NO_AGENT success message.

### Modified scenario §X.Y — Real capture quality below threshold

Given: the SDK captures a fingerprint but `quality_score < 60`.

When: the operator clicks "Activar lector".

Then:
1. The wizard shows "Calidad insuficiente. Vuelve a intentarlo." (mirrors Phase 1's `dp4500_integration/templates/cita_medica_form.html` UI).
2. The operator can retry; no template is persisted.