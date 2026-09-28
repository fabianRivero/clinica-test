# Tasks: Cascade revoke test closure (Phase 2A6 of dp4500-host-app-integration-phase2)

**Change name**: `dp4500-host-app-integration-phase2a6-cascade-revoke`
**Artifact store**: openspec
**Delivery strategy**: `ask-on-risk`
**Predecessors**: proposal.md + design.md + specs/cascade-biometric-revoke/spec.md (locked)

> **Status**: TEST-ONLY delta. No production code committed in this change.
> Phase 2A6 closes the 3 PARTIAL cascade-revoke scenarios flagged by the
> Phase 2A5 verify-report (`openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/verify-report.md`,
> rows 191, 192, 196 + issues §WARNING 4-6 at lines 294-298) and un-siezes the
> cascade step in the existing smoke e2e test.

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150 (range 100-200). All test additions; no production code. |
| 400-line budget risk | None — well within range. |
| Chained PRs recommended | No — single PR acceptable. |
| Suggested commit split | One commit (all tests share fixture patterns). |
| Delivery strategy | ask-on-risk |
| Chain strategy | n/a (single PR) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a (single PR)
400-line budget risk: None

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| WU-2A6.1 | G1 named test: no-op when `biometric_external_id is NULL` | PR 1 | `pytest backend/dp4500_integration/tests/test_cascade.py::CascadeSignalTests::test_user_without_biometric_external_id_is_no_op -q` | Celery eager + `httpx.MockTransport` | Drop the new method; `signals.py:32-33` early-return remains covered transitively |
| WU-2A6.2 | G2 named test: sync insert failure → graceful | PR 1 | `pytest backend/dp4500_integration/tests/test_cascade.py::CascadeSignalTests::test_sync_insert_failure_does_not_rollback_local_delete -q` | `mock.patch` on `PendingCascade.objects.create` | Drop the new method; `signals.py:41-55` `try/except` remains covered by code review |
| WU-2A6.3 | G3 named test: max retries → `status="failed"` | PR 1 | `pytest backend/dp4500_integration/tests/test_cascade.py::CascadeTaskOutcomeTests::test_max_retries_exhausted_marks_failed -q` | Patch `cascade_revoke_template.retry` to raise `MaxRetriesExceededError`; call `_cascade_revoke_template_on_failure` directly | Drop the new method; `tasks.py:113-128` hook remains covered by 204/404/suspended siblings |
| WU-2A6.4 | G4 cascade smoke e2e (replace skip) | PR 1 | `pytest backend/tests/integration/dp4500_integration/test_smoke_e2e.py::SmokeE2ETests::test_enroll_finalize_verify_then_cascade -q` | `httpx.MockTransport` returning 204 on `DELETE /templates/...` under eager Celery | Restore `self.skipTest(...)` block at `test_smoke_e2e.py:272-281` |

---

## Phase 2A6: Cascade revoke test closure (Commit 1)

### 1.1 No-op when no template exists (WU-2A6.1, closes verify-report PARTIAL G1 / spec §6.6)

- [x] 1.1.1 RED `backend/dp4500_integration/tests/test_cascade.py::CascadeSignalTests::test_user_without_biometric_external_id_is_no_op` (insert after line 113). Create Usuario; bypass the `assign_biometric_external_id` pre_save signal by setting `biometric_external_id = None` post-save via `Usuario.objects.filter(pk=u.pk).update(biometric_external_id=None)` then `u.refresh_from_db()`. Mock `signals.cascade_revoke_template.delay` (not the module, the bound `.delay` attribute). `u.delete()`. Assert `PendingCascade.objects.count() == 0` and `.delay` was NOT called.

- [x] 1.1.2 GREEN: no production code change — confirm the existing `cascade_revoke_on_user_delete` signal handler already short-circuits when `instance.biometric_external_id` is None. Cite `backend/dp4500_integration/signals.py:32-33` in the assertion.

### 1.2 Sync insert failure → graceful handling (WU-2A6.2, closes PARTIAL G2 / spec §6.7)

- [x] 1.2.1 RED `backend/dp4500_integration/tests/test_cascade.py::CascadeSignalTests::test_sync_insert_failure_does_not_rollback_local_delete` (insert after WU-2A6.1). Create Usuario WITH `biometric_external_id = 'aaaaaaaa-...'` set. Patch `dp4500_integration.signals.PendingCascade.objects.create` to raise `django.db.utils.IntegrityError('unique violation')`. Use `with self.assertLogs('dp4500_integration.signals', level='ERROR') as cm:` to capture the log. `u.delete()`. Assert Usuario row is gone, `PendingCascade.objects.count() == 0`, `'sync insert failed' in cm.records[0].getMessage()`, `.delay` was NOT called.

- [x] 1.2.2 GREEN: confirm the existing signal handler catches `IntegrityError` and emits an ERROR log without re-raising. Cite `backend/dp4500_integration/signals.py:48`.

### 1.3 Max retries exhausted → status=failed (WU-2A6.3, closes PARTIAL G3 / spec §6.10)

- [x] 1.3.1 RED `backend/dp4500_integration/tests/test_cascade.py::CascadeTaskOutcomeTests::test_max_retries_exhausted_marks_failed` (insert after line 188). Create Usuario + PendingCascade(status=PENDING). Mock `cascade_revoke_template.retry` to raise `celery.exceptions.MaxRetriesExceededError('5 retries')`. Mock `HTTPClient.delete_template` to raise `BiometricUnavailable('no_agent')`. Call the on_failure hook directly per the signature at `backend/dp4500_integration/tasks.py:113`:

  ```python
  from celery.exceptions import MaxRetriesExceededError
  from dp4500_integration.tasks import _cascade_revoke_template_on_failure
  _cascade_revoke_template_on_failure(
      task_self=mock.Mock(),  # mock with .request.retries = 5
      exc=MaxRetriesExceededError('5 retries'),
      task_id='test-task-id',
      args=('aaaaaaaa-...', <sucursal_id>),
      kwargs={},
      einfo=None,
  )
  ```

  Assert `PendingCascade.objects.get(...).status == PendingCascade.STATUS_FAILED`, `.attempts == 1`, `.last_error_code` starts with `'celery:'`.

- [x] 1.3.2 GREEN: confirm the existing `_cascade_revoke_template_on_failure` hook handles `MaxRetriesExceededError`. Cite `backend/dp4500_integration/tasks.py:113-128`.

### 1.4 End-to-end smoke (WU-2A6.4, replaces skip block in `test_smoke_e2e.py`)

- [x] 1.4.1 RED `backend/tests/integration/dp4500_integration/test_smoke_e2e.py::SmokeE2ETests::test_enroll_finalize_verify_then_cascade`. Replace the `self.skipTest(...)` block at lines 272-281 with the cascade assertions. The smoke test currently ends at step 4 (verify POST → 200 OK); extend it to step 5:
  - Delete the `CitaMedica` row first (FK cascade in reverse).
  - `cliente.usuario.delete()` (which fires the cascade signal).
  - `PendingCascade.objects.get(user_external_id=external_id)` and assert `status == STATUS_COMPLETED`, `completed_at is not None`, `attempts == 1`.

- [x] 1.4.2 GREEN: confirm the smoke test runs end-to-end with `httpx.MockTransport` returning 204 on `DELETE /templates/...`.

### 1.5 Commit wrap-up

- [ ] 1.5.1 `npx tsc -b --pretty false` exits 0.
- [ ] 1.5.2 `python -m pytest backend/dp4500_integration/tests/test_cascade.py backend/tests/integration/dp4500_integration/test_smoke_e2e.py` (WSL only) → 11+ tests pass, 0 fail, ≤2 skipped (existing SQLite concurrent skip + no new skips).
- [ ] 1.5.3 Commit `test(dp4500_integration): close Phase 2A6 cascade revoke test gaps + e2e smoke` (single atomic commit).

**End of Commit 1.**

---

## Out-of-scope tasks (explicit non-tasks)

These are NOT in this change. Listed here so reviewers don't expect them:

- ❌ Any production code change to `signals.py`, `tasks.py`, `models.py`, or `views.py` — implementation is correct per Phase 2A5 lineage.
- ❌ New endpoints, new signal handlers, new Celery tasks.
- ❌ Exponential-backoff retry policy (stays at fixed `default_retry_delay=30` — Phase 2B concern).
- ❌ Phase 4 cron-driven alert banner after N retries (already deferred).
- ❌ Phase 2A5 carry-over PARTIALs not on `cascade-revoke` (2 timeout mapping-only assertions, SQLite concurrency skip, 422-mismatch named-assertion gap) — out of scope for Phase 2A6.

---

## Pre-apply (verify phase)

- [ ] All 4 PARTIAL cascade-revoke rows in `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/verify-report.md` flip to COMPLIANT in the new Phase 2A6 verify-report.
- [ ] No new lint errors introduced (eslint on the touched frontend files — should be 0 since this change is backend-only).
- [ ] The Phase 2A5 e2e smoke (`test_smoke_e2e`) no longer skips; runs end-to-end.

---

## Post-apply (archive phase)

- [ ] Write `archive-report.md` for Phase 2A6 at `openspec/changes/dp4500-host-app-integration-phase2a6-cascade-revoke/archive-report.md` covering the 1 commit, the 4 PARTIAL→COMPLIANT flips, and the test counts.
