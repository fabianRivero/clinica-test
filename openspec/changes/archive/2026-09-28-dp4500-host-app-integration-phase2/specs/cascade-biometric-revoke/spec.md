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