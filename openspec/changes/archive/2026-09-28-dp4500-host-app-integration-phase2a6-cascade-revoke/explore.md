# Exploration: dp4500-host-app-integration-phase2a6-cascade-revoke

**Prepared**: 2026-09-28
**Branch under review**: `feat/dp4500-host-app-integration-phase2-sdd` at `c7d872b`
**Companion archive**: `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/` (Phase 2A5)
**Purpose**: Define the scope of Phase 2A6 — close the 3 PARTIAL scenarios flagged for `cascade-biometric-revoke` in the Phase 2A5 verify-report, plus ship a smoke e2e test that walks the full cascade path through an `httpx.MockTransport`-impersonated DP4500.

This file is read-only for the orchestrator. It does NOT modify the SDD artifacts.

---

## 1. Goal

Phase 2A6 = "close the 3 PARTIAL cascade-revoke scenarios from Phase 2A5 verify + add 1 e2e smoke test".

The Phase 2A5 verify-report (`openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/verify-report.md`, rows 184-208 + issues §WARNING 4-6 at lines 294-298) flagged three cascade-revoke scenarios as PARTIAL because the existing tests cover the code path transitively but lack a dedicated single-test assertion:

1. **no-op when no template exists** (`signals.py:32-33`) — implementation review confirms the early return; no dedicated test exists.
2. **sync insert fails → graceful handling** (`signals.py:41-55`) — `try/except Exception` wraps `PendingCascade.objects.create(...)`; the local delete commits; no explicit named test exercises the failure path.
3. **max retries exhausted → `status='failed'`** (`tasks.py:68-105` + `tasks.py:113-128`) — retry path + `on_failure` hook are present, but a single named test that drives both the retry AND the terminal `status='failed'` after `max_retries=5` is missing.

Plus a smoke e2e test in `backend/tests/integration/dp4500_integration/test_smoke_e2e.py` that:
- Impersonates DP4500 with `httpx.MockTransport`
- Creates User → enrolls via DP4500 service endpoint → deletes User
- Verifies the cascade signal fires → Celery eager task runs → verifies the HTTP DELETE to DP4500 → asserts `PendingCascade.status='completed'`

The existing `test_enroll_finalize_verify_then_cascade` smoke test (`test_smoke_e2e.py:116-281`) explicitly skips the cascade step at line 278-281 — Phase 2A6 will unsieze it.

---

## 2. What's implemented vs what's missing

### 2.1 Already implemented (Phase 1 + 2A1-A5 — do NOT regress)

| File | Lines | Behaviour |
|---|---|---|
| `backend/dp4500_integration/signals.py` | 29-66 | `post_delete` on `Usuario`: early return when `biometric_external_id` is NULL (lines 32-33); sync `PendingCascade` insert wrapped in `try/except` (lines 41-55); `.delay()` best-effort (lines 57-66). |
| `backend/dp4500_integration/tasks.py` | 39-65 | `_do_cascade()` helper: returns `"completed"` on 204/404, `"suspended"` on `BiometricSuspended`, re-raises `BiometricUnavailable` for caller to retry. |
| `backend/dp4500_integration/tasks.py` | 68-110 | `cascade_revoke_template` `@shared_task(bind=True, max_retries=5, default_retry_delay=30)`: filter pending row, increment `attempts`, `last_attempt_at`, classify outcome, save terminal state. |
| `backend/dp4500_integration/tasks.py` | 113-132 | `_cascade_revoke_template_on_failure`: bulk-update `status="failed"` after retries exhaust; wired via `cascade_revoke_template.on_failure = ...` (line 132). |
| `backend/dp4500_integration/management/commands/reconcile_pending_cascades.py` | 29-84 | `--dry-run` (lines 53-61), `--limit N` (lines 48-49), synchronous `_do_cascade()` invocation (lines 63-72), exit-code 0/1 semantics (lines 81-83). |
| `backend/dp4500_integration/models.py` | 23-60 | `PendingCascade` with `STATUS_PENDING` / `STATUS_COMPLETED` / `STATUS_SUSPENDED` / `STATUS_FAILED` enum; `sucursal_id` is `IntegerField` (not FK, per design §6.1 invariant). |
| `backend/dp4500_integration/tests/test_cascade.py` | 1-293 | 8 tests: lifecycle (32-42), signal happy path (84-113), task outcomes 204/404/suspended (145-188), reconcile command (200-261), enrollment record round-trip (270-292). |

### 2.2 Missing test coverage (Phase 2A6 close-out)

| Gap | Spec scenario | Spec requirement | Current state |
|---|---|---|---|
| **G1**: dedicated no-op test | `Scenario: User without biometric_external_id is a no-op` (spec.md:44-49) | Cascade hook on User.delete | `signals.py:32-33` returns early; covered transitively by `test_every_user_delete_creates_pending_cascade` (`test_cascade.py:55-82`). No named assertion. |
| **G2**: dedicated sync-insert-failure test | `Scenario: Sync insert failure does not roll back the local delete` (spec.md:51-58) | Cascade hook on User.delete | `signals.py:41-55` wraps `PendingCascade.objects.create(...)` in `try/except` and logs at ERROR. No explicit named test exercises the failure path. |
| **G3**: dedicated max-retries test | `Scenario: Up to 5 retries on transient unavailability` (spec.md:96-103) | Celery task cascade_revoke_template | Retry path (`tasks.py:96-105`) + `on_failure` hook (`tasks.py:113-128`) both present; the 204/404/suspended sibling tests cover the single-call shape but no single test exercises BOTH retry AND `status='failed'` after `max_retries=5`. |
| **G4**: cascade smoke e2e | implicit end-to-end coverage | All 8 requirements | `test_smoke_e2e.py:278-281` explicitly skips cascade step (`self.skipTest(...)`); the smoke chain enroll → finalize → verify → delete is wired but not exercised. |

---

## 3. Open work (numbered, with concrete file paths and line numbers)

### WU-1: G1 — Named test for "no biometric_external_id → no-op"

**File**: `backend/dp4500_integration/tests/test_cascade.py`
**Insert after**: line 113 (end of `test_user_with_biometric_external_id_creates_pending_row`)
**Class**: `CascadeSignalTests`

Test shape:
1. Monkey-patch `accounts.signals.assign_biometric_external_id` (or directly set `biometric_external_id = None` AFTER save; the field is `null=True, blank=True` per `accounts/models.py:55-64`).
2. Mock `dp4500_integration.tasks.HTTPClient` so any accidental call would raise.
3. Call `user.delete()`.
4. Assert `PendingCascade.objects.count() == 0`.
5. Assert `mock_client_class.return_value.delete_template` was NEVER called.

Risk: the existing pre_save signal `assign_biometric_external_id` mints a UUID on first INSERT. The test must work around that — either by assigning `None` post-save (the field is nullable, no `null=False` constraint) or by patching the signal. Phase 2A4 lineage note: the prior test had this issue and the workaround was to assert `objects.count() == 1` because the signal fires on every Usuario. The new test must NOT depend on that workaround — Phase 2A6 should explicitly assert "zero pending cascades when biometric_external_id is None".

### WU-2: G2 — Named test for sync insert failure → graceful handling

**File**: `backend/dp4500_integration/tests/test_cascade.py`
**Insert after**: WU-1
**Class**: `CascadeSignalTests`

Test shape:
1. `mock.patch("dp4500_integration.signals.PendingCascade.objects.create", side_effect=IntegrityError("simulated FK violation"))` — `IntegrityError` from `django.db` is the canonical "sync insert fails" scenario the spec cites.
2. Call `user.delete()`.
3. Assert the local `Usuario` row is gone (the FK cascade / explicit delete committed).
4. Assert NO `PendingCascade` row exists.
5. Assert the ERROR-level log fired (use `self.assertLogs("dp4500_integration.signals", level="ERROR")`).
6. Assert `cascade_revoke_template.delay` was NEVER called (because the signal returns early after the IntegrityError, line 55).

Key subtlety: the `try/except Exception` at `signals.py:48` wraps the `transaction.atomic()` block. `IntegrityError` is a subclass of `Exception`, so it IS caught. The test must prove the local delete still commits (no rollback propagated up to `U.delete()`).

### WU-3: G3 — Named test for max-retries-exhausted → status='failed'

**File**: `backend/dp4500_integration/tests/test_cascade.py`
**Insert after**: line 188 (end of `test_503_BIOMETRIC_SUSPENDED_marks_suspended_no_retry`)
**Class**: `CascadeTaskOutcomeTests`

Test shape:
1. `mock.patch("dp4500_integration.tasks.cascade_revoke_template.retry", side_effect=MaxRetriesExceededError())` to short-circuit the Celery retry machinery — the unit under test is the `_cascade_revoke_template_on_failure` hook at `tasks.py:113-128`, NOT Celery itself.
2. `mock.patch("dp4500_integration.tasks.HTTPClient.delete_template", side_effect=BiometricUnavailable("no_agent"))` so every attempt re-raises the transient.
3. Create a `PendingCascade(status=pending, attempts=0)`.
4. Invoke `cascade_revoke_template.run(uuid, sucursal_id)` — first call increments `attempts` to 1, raises `BiometricUnavailable`, hits `self.retry(...)` which (under the patched retry) raises `MaxRetriesExceededError`.
5. Manually invoke `_cascade_revoke_template_on_failure(task_self, exc, task_id, args={"user_external_id": uuid, "sucursal_id": sid}, kwargs={}, einfo=None)` (the signature at `tasks.py:113`).
6. Refresh the row; assert `status == STATUS_FAILED`, `attempts == 1` (single in-process call), `last_error_code` starts with `"celery:"` (per `tasks.py:127`).

Alternative simpler shape: patch `cascade_revoke_template.retry` to raise `MaxRetriesExceededError` immediately, then call `cascade_revoke_template.on_failure(...)` directly. This isolates the unit under test (`_cascade_revoke_template_on_failure`) and avoids forcing the task into a loop. This is the recommended approach.

### WU-4: G4 — Cascade smoke e2e (replaces the skip in test_smoke_e2e.py)

**File**: `backend/tests/integration/dp4500_integration/test_smoke_e2e.py`
**Replace**: lines 272-281 (the `self.skipTest(...)` block)

New shape:
1. After the verify-call assertion at line 269-271, continue.
2. Build a `dp4500_handler` that returns 204 on `DELETE /templates/...` (already present at line 245-246).
3. Wrap `_patch_dp4500_handler(dp4500_handler)` around the entire `cliente.usuario.delete()` invocation.
4. Call `cliente.usuario.delete()` (note: must use the underlying `Usuario`, not the `Cliente` wrapper — the signal is on `Usuario` per `signals.py:29`).
5. Refresh `PendingCascade.objects.filter(user_external_id=external_id).first()`.
6. Assert row exists, `status == STATUS_COMPLETED`, `completed_at is not None`, `attempts == 1`.
7. Remove the `self.skipTest(...)` at lines 278-281.

Subtleties:
- `Usuario.delete()` will trip FK constraints on `customers.Cliente` (OneToOneField, `customers/models.py:54` cascade), `staff.Especialista` (OneToOneField, `staff/models.py:20` cascade), `biometric.*` (`biometric/models.py:48, 147` PROTECT/SET_NULL), `notifications.*` (CASCADE on `notifications/models.py:22, 54, 68-69, 85`), `operations.BranchAdminAuditLog.actor` (SET_NULL on `operations/models.py:1086`). The smoke must use a User with no FK dependents — the existing `_build_smoke_graph` (lines 70-102) already creates the user via `Usuario.objects.create_user(...)` with no FK rows pointing at it, so this is already safe. The deletion will succeed.
- The `Cliente` row tied to the `Usuario` will CASCADE-delete (line 32 of `customers/models.py` uses `CASCADE`), but `test_smoke_e2e.py` doesn't assert on the `Cliente` row post-delete — only the `PendingCascade`. No regression.
- Eager Celery (`CELERY_TASK_ALWAYS_EAGER=True`) means `cascade_revoke_template.delay(...)` runs synchronously inside `cliente.usuario.delete()`. The signal chain is signal → sync insert → eager task → HTTP DELETE via `MockTransport` → row marked `completed`. Single observable endpoint: row status.

### WU-5: Optional — Phase 2A4 lineage cleanup

The `test_cascade.py:55-82` test `test_every_user_delete_creates_pending_cascade` documents (in its docstring, lines 56-64) that the original test asserted `objects.count() == 0` assuming a NULL-UUID skip. The pre_save signal `assign_biometric_external_id` makes that assertion moot. Phase 2A6 should add a code comment or refactor that test's docstring to clarify the intent (the test now exists for the "every user has a UUID → cascade always fires" invariant, NOT for the "no UUID → skip" invariant that G1 now covers).

---

## 4. Recommendation for proposal/design/tasks updates

The Phase 2A6 change is **test-only** — no production code changes are required. The implementation is already correct per Phase 2A5 lineage (verify-report §WARNING 4-6 call out the lack of dedicated tests, NOT implementation defects). The next agent (sdd-propose) should:

### 4.1 `proposal.md`

1. Add a §"Out of scope (Phase 2A6 deferred)" line confirming the cascade e2e is now in scope.
2. State the Phase 2A6 scope: "Close the 3 PARTIAL cascade-revoke scenarios + ship a cascade smoke e2e. No production code changes."
3. Reference the Phase 2A5 verify-report issues §WARNING 4-6 as the source of the gaps.

### 4.2 `design.md`

No structural changes needed. Optionally add a §"Phase 2A6 test surface" subsection that lists the 4 new tests by name so the reviewer can grep for them.

### 4.3 `tasks.md`

Work units (single PR, ≤400 net lines budget per `openspec/config.yaml:64`):

| WU | Title | File(s) | Net lines | Phase |
|---|---|---|---|---|
| WU-2A6.1 | G1: `test_user_without_biometric_external_id_is_no_op` | `backend/dp4500_integration/tests/test_cascade.py` | ~30 | Write |
| WU-2A6.2 | G2: `test_sync_insert_failure_does_not_rollback_local_delete` | same file | ~40 | Write |
| WU-2A6.3 | G3: `test_max_retries_exhausted_marks_failed` | same file | ~50 | Write |
| WU-2A6.4 | G4: cascade smoke e2e (un-skip + 5 new assertions) | `backend/tests/integration/dp4500_integration/test_smoke_e2e.py` | ~30 (replace skip block + extend verify chain) | Write |
| WU-2A6.5 | Verify all 4 tests pass on WSL pytest | n/a | 0 (test_command runs the suite) | Verify |

Total: ≤150 net lines. Well under the 400-line `review_budget_lines` cap. The PR is a docs-and-tests-only patch — no production code touched.

### 4.4 Specs

No spec edits. The 4 affected scenarios in `specs/cascade-biometric-revoke/spec.md` (lines 44-49, 51-58, 96-103, and the implicit "end-to-end" coverage) are already correctly written. Phase 2A6 closes them by adding dedicated tests, not by changing the spec.

### 4.5 Archive-report

The new archive-report will live at `openspec/changes/dp4500-host-app-integration-phase2a6-cascade-revoke/archive-report.md` and will replace the 3 PARTIAL rows from the Phase 2A5 verify-report matrix with COMPLIANT rows. No edit to the existing Phase 2A5 archive.

---

## 5. Quick-reference: what changed where

| Concern | Phase 2A5 reality | Phase 2A6 will ship |
|---|---|---|
| G1 no-op test | Transitive coverage via `test_every_user_delete_creates_pending_cascade` | Named test `test_user_without_biometric_external_id_is_no_op` with explicit `objects.count() == 0` assertion |
| G2 sync-insert-failure test | Implementation review only | Named test with `IntegrityError` patch + `assertLogs` ERROR-level assertion + local-delete-commits assertion |
| G3 max-retries test | Coverage split across `test_204`/`test_404`/`test_suspended` + `_cascade_revoke_template_on_failure` review | Named test that exercises the `on_failure` hook directly with `MaxRetriesExceededError` |
| G4 cascade smoke e2e | `self.skipTest(...)` at `test_smoke_e2e.py:278-281` | Skip removed; 5 new assertions on `PendingCascade` post-`Usuario.delete()` |

---

## 6. Risks & constraints

1. **SQLite FK enforcement**: WSL pytest runs against SQLite. `IntegrityError` simulation (G2) is reliable on SQLite. No regression risk vs Phase 2A5.
2. **Eager Celery + signal ordering**: `cascade_revoke_template.delay(...)` is synchronous under `CELERY_TASK_ALWAYS_EAGER=True`. The smoke test (G4) MUST run inside the same transaction-isolation context as the verify step — the existing test already does this (lines 251-265). No new fixture complexity.
3. **`Usuario.delete()` FK cascade**: The smoke user must have NO FK dependents (no Cliente, Especialista, BiometricAttempt, Ticket, etc.). The existing `_build_smoke_graph` (lines 70-102) already creates the user via `Usuario.objects.create_user(...)` without dependents. The cascade via `customers.Cliente.usuario` (CASCADE) + `notifications.*` (CASCADE) does not break the test — the user is intended to delete cleanly. No fixture surgery needed.
4. **Mock patching surface for G3**: `cascade_revoke_template.retry` is bound at task-definition time. Patching `tasks.cascade_revoke_template.retry` (the method on the task instance, accessed inside `tasks.py:101`) is the correct call-site per existing test patterns. The test must import `MaxRetriesExceededError` from `celery.exceptions` (the same source `tasks.py:113-128` would receive in production).
5. **Test count growth**: Phase 2A6 adds 4 tests; total `test_cascade.py` grows from 8 → 11 and `test_smoke_e2e.py` stays at 1 (no longer skipped). WSL pytest run on the verify command line in the verify-report (line 9) gains ~4 passing tests, 1 fewer skip.
6. **Phase 2A5 line-budget carry**: Phase 2A5 had a `size:exception` (~1340 net lines, 3.35× the 400-line budget per `verify-report.md:316`). Phase 2A6 stays ≤150 net lines — no exception needed.

---

## 7. Ready for next phase

**Yes** — the four new tests in §3 are sufficient to drive a new change directory `dp4500-host-app-integration-phase2a6-cascade-revoke` or to amend in place. The orchestrator should:

1. Confirm the test-only scope with the user (no production code changes).
2. Land the `proposal.md` / `design.md` / `tasks.md` edits per §4 as a docs-only commit.
3. Open the apply phase (sdd-apply) for WU-2A6.1 through WU-2A6.5.
4. Run the verify phase (sdd-verify) with `python -m pytest backend/dp4500_integration/tests/test_cascade.py backend/tests/integration/dp4500_integration/test_smoke_e2e.py` on WSL.
5. Archive the change (sdd-archive) once verify is green.

**Blocked** if the user wants production-code hardening (e.g. exponential backoff instead of fixed 30s, or circuit-breaker after N failures) — those are out of scope for the 3 PARTIAL scenarios and would expand Phase 2A6 into a Phase 2A6+/2B change.

---

## 8. Files referenced

| File | Role | Lines |
|---|---|---|
| `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/specs/cascade-biometric-revoke/spec.md` | Canonical spec | 206 |
| `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/verify-report.md` | PARTIAL matrix + §WARNING 4-6 | 184-208, 294-298 |
| `backend/dp4500_integration/signals.py` | post_delete handler | 66 |
| `backend/dp4500_integration/tasks.py` | Celery task + on_failure hook | 132 |
| `backend/dp4500_integration/models.py` | PendingCascade model | 108 |
| `backend/dp4500_integration/management/commands/reconcile_pending_cascades.py` | operator override | 84 |
| `backend/dp4500_integration/tests/test_cascade.py` | current test suite (8 tests) | 293 |
| `backend/tests/integration/dp4500_integration/test_smoke_e2e.py` | smoke e2e with cascade skip | 286 |
| `backend/operations/models.py` | CitaMedica.save() reference (no change needed) | 1093 |
| `backend/accounts/models.py` | Usuario model with biometric_external_id | 109 |
| `openspec/config.yaml` | review_budget_lines: 400, strict_tdd: true | 76 |