# cascade-biometric-revoke Specification — DELTA (Phase 4)
**Change**: `dp4500-host-app-integration-phase4-production-readiness`
**Branch**: `feat/dp4500-host-app-integration-phase2-sdd`

> **DELTA**: This file is a delta copy of the archived Phase 2A6 delta spec at
> `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/specs/cascade-biometric-revoke/spec.md`.
> The body below is byte-identical to that source (including the embedded "ADDED Tests (Phase 2A6)" block).
> An additional "ADDED Spec (Phase 4)" section is appended at the end to document the rotation-key overlap on the cascade revoke audit chain.

---

# Delta for cascade-biometric-revoke (Phase 2A6)

> **Phase 2A6 is a TEST-ONLY delta.** No production behavior changes.
>
> The 4 scenarios being closed by Phase 2A6 tests (WU-2A6.1, WU-2A6.2, WU-2A6.3, WU-2A6.4) are:
>
> - §6.6 "User without biometric_external_id is a no-op" (spec.md:44-49) → G1
> - §6.7 "Sync insert failure does not roll back the local delete" (spec.md:51-58) → G2
> - §6.10 "Up to 5 retries on transient unavailability" (spec.md:96-103) → G3
> - The cascade end-to-end smoke chain (implicit coverage of §6.1-§6.10) → G4
>
> **The spec body below is byte-identical to the archived spec** at
> `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/specs/cascade-biometric-revoke/spec.md`.
> The scenarios are already correctly worded — only test coverage is being added.
> See the appended "ADDED Tests (Phase 2A6)" section for the new test names.

---

# cascade-biometric-revoke Specification

## Purpose

Defines what happens when a `User` in the clinic is deleted and the
clinic must ask DP4500 to revoke the matching biometric template.
Covers the cascade hook, the persistent pending-cascade row, the
Celery-based retry policy, the operator-facing reconciliation
command, and the failure modes for an unavailable DP4500.

This is the cross-cutting integration that keeps the two systems in
sync across user lifecycle events. The plan names this as Q3; the
decision (cascade + soft retry) was locked in the proposal
§Decisions locked.

---

## Requirements

### Requirement: Cascade hook on User.delete

The system SHALL connect a `post_delete` signal handler to the User
model. The handler SHALL:

1. Skip if `user.biometric_external_id` is NULL (legacy user, nothing
   to revoke).
2. Synchronously insert a `PendingCascade` row (so retries survive
   worker crashes that lose the Celery queue).
3. Asynchronously enqueue the `cascade_revoke_template` Celery task
   with the user's `biometric_external_id` and `sucursal_id`.

The sync insert is non-fatal: if it raises (e.g. DB hiccup), the
signal logs the failure but does NOT roll back the local delete
(the operator's intent is honored locally regardless).

#### Scenario: User with biometric_external_id creates a pending row

- GIVEN user U has `biometric_external_id=UUID-1`, `sucursal_id=42`
- WHEN `U.delete()` is called
- THEN a `PendingCascade(user_external_id=UUID-1, sucursal_id=42,
  status="pending", attempts=0)` is inserted
- AND `cascade_revoke_template.delay(UUID-1, 42)` is enqueued

#### Scenario: User without biometric_external_id is a no-op

- GIVEN user U has `biometric_external_id=NULL`
- WHEN `U.delete()` is called
- THEN no `PendingCascade` row is inserted
- AND no Celery task is enqueued

#### Scenario: Sync insert failure does not roll back the local delete

- GIVEN the `PendingCascade.objects.create(...)` raises `IntegrityError`
- WHEN `U.delete()` is called
- THEN the local User delete still commits
- AND the failure is logged at `ERROR` level
- AND the user's biometric template remains at DP4500 (orphan)
- AND a future reconciliation command can pick this up

---

### Requirement: Celery task — cascade_revoke_template

The Celery task `cascade_revoke_template(user_external_id, sucursal_id)`
SHALL call the resolved service key's `delete_template` against
DP4500, classify the result, and update the `PendingCascade` row.

| Outcome | Action |
|---|---|
| `204` from DP4500 | Mark `PendingCascade.status="completed"`, `completed_at=now()` |
| `404` from DP4500 | Idempotent: same as 204 (no credential at DP4500 either) |
| `BiometricSuspended` (503 `BIOMETRIC_SUSPENDED`) | Mark `status="suspended"`; do NOT retry. Operator needs to advance manually. |
| `BiometricUnavailable("timeout")` or 5xx | Increment `attempts`; retry with `default_retry_delay=30` seconds, `max_retries=5` |
| Other exceptions (network, etc.) | Same retry policy as `BiometricUnavailable`. |

#### Scenario: Successful cascade marks completed

- GIVEN a `PendingCascade(status="pending", attempts=0)` for UUID-1
- WHEN `cascade_revoke_template(UUID-1, 42)` runs and DP4500 returns 204
- THEN the row's `status="completed"`, `completed_at=now()`, `attempts=1`

#### Scenario: Idempotent 404 marks completed without error

- GIVEN a `PendingCascade(status="pending", attempts=0)` for UUID-1
- WHEN the task runs and DP4500 returns 404
- THEN the row is marked completed (no exception, no retry)

#### Scenario: BiometricSuspended is non-retryable

- GIVEN a pending cascade for UUID-1
- WHEN the task runs and DP4500 returns 503 `BIOMETRIC_SUSPENDED`
- THEN the row's `status="suspended"`
- AND no further retry is scheduled (the operator must advance
  manually because Phase 1 has biometric integration off)

#### Scenario: Up to 5 retries on transient unavailability

- GIVEN a pending cascade for UUID-1 and DP4500 keeps returning 503
  `no_agent`
- WHEN the task retries up to `max_retries=5`
- THEN the row's `attempts` increments to 5
- AND the row's `status` is `"failed"` after the last retry
- AND no further retry is scheduled

---

### Requirement: Reconciliation management command

The system SHALL provide a management command
`reconcile_pending_cascades` that runs the same deletion logic
synchronously, ignoring `attempts`. It is the operator's manual
override when Celery is unavailable for an extended period.

#### Scenario: Manual reconciliation advances all pending rows

- GIVEN 7 `PendingCascade(status="pending")` rows
- WHEN `python manage.py reconcile_pending_cascades` is run
- THEN each row is processed by the same outcome table as §0
- AND the command exits 0 if all rows reach a terminal status
- AND the command exits 1 if any DP4500 call raises an unexpected
  exception (other than `BiometricSuspended`)

#### Scenario: Reconcile is idempotent

- GIVEN a `PendingCascade(status="completed")` row
- WHEN `reconcile_pending_cascades` runs
- THEN the row's status stays `"completed"` (no DP4500 call)

---

### Requirement: Alert after N retries

After `max_retries=5` retries the row's `status` is `"failed"`. The
clinic's cron (Phase 4 polish) checks for failed rows older than 24
hours and alerts the operator via the admin notification banner.

#### Scenario: Failed row is observable

- GIVEN a `PendingCascade(status="failed", attempts=5, created_at=<24h ago>)`
- WHEN the admin opens the clinic dashboard
- THEN a notification banner reads: "5 cascades pendientes a DP4500 —
  revisar ``reconcile_pending_cascades``."

---

## Requirements (cross-cutting)

### Requirement: PendingCascade model lives in the biometric app

The `PendingCascade` model lives at
`apps/biometric/models.py` (decision from proposal §5.1). It is
migration `0001_pendingcascade.py`.

#### Scenario: Model migration succeeds

- GIVEN a fresh clinic DB
- WHEN `manage.py migrate` runs
- THEN the `biometric_pendingcascade` table is created
- AND no other migration is altered

---

### Requirement: No fingerprint bytes in PendingCascade

`PendingCascade` carries only the UUID and the FK ids (sucursal,
audit timestamps). No template bytes, no signature, no nonce.

#### Scenario: Field inventory

- GIVEN the `PendingCascade` model definition
- WHEN inspected for byte-typed fields
- THEN none are present

---

### Requirement: Cross-DB foreign keys are forbidden

`PendingCascade.sucursal_id` is a plain `IntegerField`, NOT a `ForeignKey`
to the clinic's `Sucursal`. This keeps the cascade table insulated
from branch renames / deletes — a clinic can drop or rename a
sucursal without losing pending cascade records.

#### Scenario: Branch deletion does not cascade-delete pending rows

- GIVEN `Sucursal(id=42)` and `PendingCascade(sucursal_id=42)`
- WHEN `Sucursal(id=42).delete()` is called
- THEN the `PendingCascade` row survives
- AND the next reconciliation finds the orphan and (best-effort)
  fires the DELETE against DP4500 anyway

---

### Requirement: Cross-project FK discipline

No `PendingCascade` field references any model in the
`C:\proyectos\DP4500 estandar` Django project (Phase 1's `ServiceAPIKey` is
the only such target, and we never FK to it). Phase 2 stores only the
`sucursal_id` (clinic-side) and the `user_external_id` (UUID,
cross-project identifier). The raw key, the key hash, and the template
bytes never enter the clinic's DB.

#### Scenario: No cross-project FKs in the schema

- GIVEN the Phase 2 migrations list
- WHEN inspected for `ForeignKey` targets
- THEN every target's app label is local to this repo

## ADDED Tests (Phase 2A6)

> **Metadata for the reviewer only — does not change the spec scenarios above.**
> Phase 2A6 adds 4 dedicated tests that drive the 3 PARTIAL scenarios from the
> Phase 2A5 verify-report (§WARNING 4-6) plus the cascade smoke chain. The
> spec scenarios themselves are unchanged; only test coverage is being added.

| WU | Test name | File | Closes | One-line description |
|---|---|---|---|---|
| **WU-2A6.1** | `test_user_without_biometric_external_id_is_no_op` | `backend/dp4500_integration/tests/test_cascade.py` (insert after line 113) | G1 — §6.6 | Asserts `PendingCascade.objects.count() == 0` and `HTTPClient.delete_template` is never called when `biometric_external_id` is NULL. |
| **WU-2A6.2** | `test_sync_insert_failure_does_not_rollback_local_delete` | `backend/dp4500_integration/tests/test_cascade.py` (insert after WU-2A6.1) | G2 — §6.7 | Patches `PendingCascade.objects.create` with `IntegrityError`; asserts local delete commits, ERROR log fires, no Celery enqueue. |
| **WU-2A6.3** | `test_max_retries_exhausted_marks_failed` | `backend/dp4500_integration/tests/test_cascade.py` (insert after line 188) | G3 — §6.10 | Patches `cascade_revoke_template.retry` to raise `MaxRetriesExceededError` and invokes `_cascade_revoke_template_on_failure` directly; asserts `status="failed"`, `attempts==1`, `last_error_code` starts with `"celery:"`. |
| **WU-2A6.4** | (replaces skip block at `test_enroll_finalize_verify_then_cascade` lines 272-281) | `backend/tests/integration/dp4500_integration/test_smoke_e2e.py` | G4 — e2e smoke | Un-siezes the cascade sub-step in the existing smoke; wraps `Usuario.delete()` with `_patch_dp4500_handler(dp4500_handler)` returning 204 on `DELETE /templates/...`; asserts `PendingCascade` row exists, `status==STATUS_COMPLETED`, `completed_at is not None`, `attempts==1`. |
---

## ADDED Spec (Phase 4)

Phase 4 introduces `POST /api/biometric/service/keys/<id>/rotate/` (see the `service-api-authentication` ADDED Spec §SVC-ROT-1), which means the cascade revoke pipeline can be triggered or audit-tagged against a `ServiceAPIKey` whose own lifecycle is mid-rotation. Phase 4 documents the audit-chain behavior for that overlap: every `service.cascade_revoke` audit event emitted by `revoke_external_credential.py:53-64` carries `external_system=requesting_service_key.name`, which now also includes the case where the requesting key is a rotated predecessor or a freshly-minted successor. The existing Phase 2A6/2A7 cascade semantics are unchanged; this addition only describes how the rotation endpoint and the cascade revoke audit trail intersect.

### New Requirement CASC-ROT-1: Cascade audit chain participates in ServiceAPIKey rotation

When a `ServiceAPIKey` is rotated via `POST /api/biometric/service/keys/<id>/rotate/`, the cascade revoke pipeline SHALL emit a `BiometricAuditEvent` with `event_type="service.api_key_rotated"` AND, if the same rotation request subsequently triggers a cascade revoke (because the rotated key had pending templates linked through the cross-system identity handle), the cascade revoke audit row SHALL carry `external_system=<rotated_key_name>` where `<rotated_key_name>` is the *new* key name returned in the rotation response. The predecessor key name SHALL NOT appear in the cascade revoke audit row once the rotation has committed; it is preserved in the rotation audit row `metadata_json.old_key_name` only.

#### Scenario: Cascade revoke audit row references the new key name after rotation

- GIVEN a `ServiceAPIKey` row with `name="clinic-prod"` has pending cascade-revoke work linked via `User.biometric_external_id`
- WHEN `POST /api/biometric/service/keys/7/rotate/` succeeds with `{"name": "clinic-prod-2026"}` and the cascade revoke fires during the same request lifecycle
- THEN one `BiometricAuditEvent` with `event_type="service.api_key_rotated"`, `external_system="clinic-prod"`, and `metadata_json={"new_key_id": <new>, "old_key_id": 7, "new_key_name": "clinic-prod-2026"}` exists
- AND one `BiometricAuditEvent` with `event_type="service.cascade_revoke"`, `external_system="clinic-prod-2026"` (the new key name) exists
- AND no `service.cascade_revoke` audit row references `external_system="clinic-prod"` after the rotation has committed

#### Scenario: Cascade revoke audit row is unchanged when no rotation occurred in the same request

- GIVEN a `ServiceAPIKey` row with `name="clinic-prod"` has pending cascade-revoke work and no rotation endpoint has been called
- WHEN the cascade revoke pipeline fires for that key
- THEN the `service.cascade_revoke` audit row carries `external_system="clinic-prod"` exactly as in Phase 2A6
- AND no `service.api_key_rotated` audit row is emitted by this path
