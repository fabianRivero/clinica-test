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
