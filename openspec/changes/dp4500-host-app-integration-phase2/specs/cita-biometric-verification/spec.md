# cita-biometric-verification Specification

## Purpose

Defines how the clinic's cita check-in flow transitions a
`CitaMedica` from `REALIZADA_PENDIENTE_VERIFICACION` → `CONFIRMADA`
via a successful biometric verification call to DP4500. Covers the
two-step challenge/verify dance, success and failure semantics, and
the data-model side effects (the three biometric fields on
`CitaMedica`).

This is the second main user-facing flow of Phase 2 (after enrollment).

---

## Requirements

### Requirement: Verification flow happy path

The system SHALL expose `POST /api/biometric/citas/<cita_id>/verificar/`
which, when the operator clicks "Confirmar por huella" in the admin
UI, issues the full challenge/verify dance against DP4500:

1. Look up the cita, the cliente, the sucursal, the service key.
2. Call `client.challenge_identity(user_external_id, sucursal_id)`
   → get a `capture_token`.
3. Call `client.verify(user_external_id, challenge_id, signature,
   timestamp, sucursal_id)` → get `matched` + `audit_hash`.
4. On `matched=True`: in a `transaction.atomic()`, set
   `cita.estado = CONFIRMADA`,
   `cita.metodo_confirmacion = 'BIOMETRICO'`,
   `cita.biometric_challenge_id = <capture_token>`,
   `cita.biometric_match_confidence = <score>`,
   `cita.biometric_verified_at = now()`. Return 200.
5. On `matched=False` / `BiometricMismatch` / `BiometricVerifyFailed`:
   do NOT mutate the cita. Return 422 with the failure code.
6. On `BiometricSuspended` / `BiometricUnavailable`: do NOT mutate.
   Return 503 with the upstream code.

#### Scenario: Successful match transitions the cita

- GIVEN cita C is in `REALIZADA_PENDIENTE_VERIFICACION`, cliente has
  an active biometric template, and DP4500 returns
  `{matched: true, audit_hash: "abc123"}`
- WHEN the operator POSTs `/api/biometric/citas/<C>/verificar/`
- THEN the response is 200 with `{ok: true, audit_hash: "abc123"}`
- AND `C.estado == CONFIRMADA`
- AND `C.metodo_confirmacion == "BIOMETRICO"`
- AND `C.biometric_challenge_id` equals the challenge issued
- AND `C.biometric_match_confidence` equals the score from the response
- AND `C.biometric_verified_at` is set

#### Scenario: Mismatch leaves the cita pending

- GIVEN DP4500 returns `{matched: false, audit_hash: "..."}`
- WHEN the operator POSTs the verification endpoint
- THEN the response is 422 with `code: biometric_mismatch`
- AND `C.estado` is unchanged (still `REALIZADA_PENDIENTE_VERIFICACION`)
- AND the three biometric fields on `C` stay NULL

#### Scenario: Manual fallback after biometric mismatch

- GIVEN three biometric verification attempts have failed
- WHEN the operator clicks "Confirmar manualmente"
- THEN the existing `confirm_manual` endpoint takes over
- AND `C.estado == CONFIRMADA`
- AND `C.metodo_confirmacion == "MANUAL"`
- AND the three biometric fields stay NULL (no DP4500 audit link)

---

### Requirement: Field population rules

`CitaMedica` biometric fields SHALL follow these invariants at all
times:

- **All three are NULL OR all three are populated together.** Partial
  writes are not allowed. The view writes them inside a single
  `transaction.atomic()` block.
- **`biometric_challenge_id`** carries the `capture_token` returned by
  DP4500's identity challenge (not the verify's `audit_hash`).
- **`biometric_match_confidence`** stores the score from the verify
  response as a `Decimal(max_digits=5, decimal_places=4)` (range
  `[0.0000, 9.9999]`).
- **`biometric_verified_at`** is the local Django clock at the
  moment of the verify response.

#### Scenario: All three written atomically

- GIVEN a 200 response with `audit_hash` and `confidence=0.93`
- WHEN the view writes the cita
- THEN `cita.biometric_challenge_id` is non-null
- AND `cita.biometric_match_confidence` is `Decimal("0.9300")`
- AND `cita.biometric_verified_at` is non-null
- AND no commit leaves any of the three NULL while another is populated

---

### Requirement: Concurrency

Two concurrent verify calls for the same cita SHALL serialize
without losing updates. The first call to acquire the
`CitaMedica` row's lock transitions the cita; the second call sees
`estado != REALIZADA_PENDIENTE_VERIFICACION` after the first commits
and returns 409 `cita_no_longer_pending`.

#### Scenario: Concurrent verify returns 409 to the loser

- GIVEN cita C is in `REALIZADA_PENDIENTE_VERIFICACION`
- WHEN two requests POST `/verificar/` for C at the same time
- AND both succeed against DP4500
- THEN exactly one returns 200 and transitions C
- AND the other returns 409 with `code: cita_no_longer_pending`
- AND only one `BiometricAuditEvent` row is created (per the
  audit-write ordering inside the transaction)

---

### Requirement: No service key is logged

The view SHALL NOT log or persist the raw bearer token in any path.
A regression in this invariant (`print(bearer)` or similar) is a
blocking violation.

#### Scenario: Bearer token does not appear in capture output

- GIVEN a successful verification with raw bearer `"SeK_secret"`
- WHEN the view returns and the operator looks at logs / response body
- THEN no log line contains `"SeK_secret"`
- AND the response body's JSON does not include the bearer

---

## Requirements (cross-cutting)

### Requirement: Errors that surface to the operator are actionable

When a verify call surfaces `BiometricUnavailable` (DP4500 down),
the view returns 503 with a clear operator-facing message in the
response body: `detail: "DP4500 no responde — reintentar en 60
segundos o confirmar manualmente."`. The 503 includes `Retry-After:
60` so the admin UI can show a countdown.

#### Scenario: DP4500 downtime returns 503 with Retry-After

- GIVEN the verification HTTP call times out
- WHEN the view returns
- THEN the response is 503
- AND the body's `detail` is operator-readable Spanish
- AND the response header `Retry-After` is `60`
- AND the cita's three biometric fields remain NULL
- AND the cita's `estado` is unchanged

---

### Requirement: Audit link preserved

When a cita is biometric-confirmed, the view SHALL NOT duplicate the
audit event (DP4500 already wrote one). The local model carries
`biometric_challenge_id` and `biometric_match_confidence`; the audit
chain itself stays on DP4500's side. An optional Phase 4 trace ID
ties the local audit log to DP4500's via the `audit_hash` echo.

#### Scenario: Biometric-confirm does not duplicate the audit row

- GIVEN a successful verify with `audit_hash="abc123"`
- WHEN the view writes the cita
- THEN the local DB has exactly one row mutation
- (the DP4500-side audit chain gained exactly one row, written by
  DP4500 itself; the clinic's local model stores the hash echo only)