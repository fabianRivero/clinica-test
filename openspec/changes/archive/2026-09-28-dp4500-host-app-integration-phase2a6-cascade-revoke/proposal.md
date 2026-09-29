# Proposal: Phase 2A6 — Close cascade revoke test gaps + end-to-end smoke

**Change name**: `dp4500-host-app-integration-phase2a6-cascade-revoke`
**Artifact store**: openspec
**Branch**: `feat/dp4500-host-app-integration-phase2-sdd` (no branch switch)
**Predecessor**: Phase 2A5 — `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/`

## Status

Draft (will be locked after `sdd-tasks` completes).

## Background / Context

Phase 2A5 archived on 2026-09-28 with verdict `pass_with_warnings` (see
`openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/verify-report.md`).
The verify-report flagged **3 PARTIAL scenarios on the `cascade-biometric-revoke`
spec** at rows 184–208 of the compliance matrix, expanded in issues §WARNING
4–6 (lines 294–298):

| Ref | Spec scenario | Spec § | Verify-report cell | Why PARTIAL |
|-----|---------------|--------|--------------------|-------------|
| G1  | "User without biometric_external_id is a no-op" | `specs/cascade-biometric-revoke/spec.md:44-49` | row 191 (verify-report.md:191) | `signals.py:32-33` returns early; covered transitively by `test_every_user_delete_creates_pending_cascade`. **No named assertion.** |
| G2  | "Sync insert failure does not roll back the local delete" | `specs/cascade-biometric-revoke/spec.md:51-58` | row 192 (verify-report.md:192) | `signals.py:41-55` wraps `PendingCascade.objects.create(...)` in `try/except`; logs at ERROR. **No explicit failure-path test.** |
| G3  | "Up to 5 retries on transient unavailability" | `specs/cascade-biometric-revoke/spec.md:96-103` | row 196 (verify-report.md:196) | Retry path (`tasks.py:96-105`) + `on_failure` hook (`tasks.py:113-128`) present; **no single test drives BOTH retry AND `status='failed'` after `max_retries=5`.** |

The implementation is already correct per Phase 2A5 lineage (`verify-report.md:186`
states "cascade revoke is fully exercised in `test_cascade.py`" — meaning
transitively, not explicitly). Phase 2A6 closes these 3 gaps by adding **3
dedicated named tests** to `test_cascade.py`.

In addition, the existing smoke test `test_enroll_finalize_verify_then_cascade`
in `backend/tests/integration/dp4500_integration/test_smoke_e2e.py:116-281`
explicitly skips the cascade sub-step at lines 278-281 via `self.skipTest(...)`.
The skip was originally placed because the cascade step was not part of
Phase 2A5 scope. Phase 2A6 un-siezes the skip and adds **1 cascade smoke
end-to-end test** (`WU-2A6.4`) that exercises the full chain:

```
create Usuario → enroll via DP4500 service endpoint → finalize → verify
   → delete Usuario → cascade signal → Celery eager task → MockTransport
       DELETE → PendingCascade.status='completed'
```

## Scope

**TEST-ONLY — no production code changes.**

### In Scope

| WU | Concern | File | Deliverable | Net lines |
|----|---------|------|-------------|-----------|
| **WU-2A6.1** | G1 closure | `backend/dp4500_integration/tests/test_cascade.py` (insert after line 113) | `test_user_without_biometric_external_id_is_no_op` — assert `PendingCascade.objects.count() == 0`, no `HTTPClient.delete_template` call | ~30 |
| **WU-2A6.2** | G2 closure | `backend/dp4500_integration/tests/test_cascade.py` (insert after WU-2A6.1) | `test_sync_insert_failure_does_not_rollback_local_delete` — patch `PendingCascade.objects.create` with `IntegrityError`, assert local delete commits, ERROR log fires, no Celery enqueue | ~40 |
| **WU-2A6.3** | G3 closure | `backend/dp4500_integration/tests/test_cascade.py` (insert after line 188) | `test_max_retries_exhausted_marks_failed` — patch `cascade_revoke_template.retry` to raise `MaxRetriesExceededError`, invoke `on_failure` directly, assert `status="failed"`, `attempts==1`, `last_error_code` starts with `"celery:"` | ~50 |
| **WU-2A6.4** | G4 cascade smoke e2e | `backend/tests/integration/dp4500_integration/test_smoke_e2e.py` (replace lines 272-281) | Remove `self.skipTest(...)`; after verify-call assertion (lines 269-271), wrap `Usuario.delete()` with `_patch_dp4500_handler(dp4500_handler)` returning 204 on `DELETE /templates/...`; assert `PendingCascade` row exists, `status==COMPLETED`, `completed_at is not None`, `attempts==1` | ~30 |
| **WU-2A6.5** | Verify all tests pass on WSL | n/a (test_command runs the suite) | Run `python -m pytest backend/dp4500_integration/tests/test_cascade.py backend/tests/integration/dp4500_integration/test_smoke_e2e.py` on WSL | 0 |

**Total: ≤150 net lines of new test code.** Well under the 400-line
`review_budget_lines` cap in `openspec/config.yaml:64`. No `size:exception`
required.

### Out of Scope

- **Production behavior changes** — no edits to `signals.py`, `tasks.py`,
  `models.py`, or `views.py`. Implementation is correct per Phase 2A5
  lineage.
- **New endpoints, new signal handlers, new Celery tasks** — Phase 2A6
  is a test-only patch.
- **Refactoring of the cascade signal or task** — the existing single-`try/except`
  design at `signals.py:41-55` stays as-is.
- **Replace of the `pending_cascade` table** — the
  `PendingCascade` model at `backend/dp4500_integration/models.py:23-...`
  is left untouched.
- **Migration generation** — no schema changes.
- **Exponential-backoff retry policy** — keep the existing
  `default_retry_delay=30` (fixed). This would be a Phase 2B concern.
- **Phase 4 cron-driven alert banner** — already deferred (`verify-report.md:199`,
  cascade-revoke §Alert after N retries scenario = OUT-OF-SCOPE).
- **Phase 2A5 carry-over PARTIALs not on cascade-revoke** — 2 timeout
  mapping-only assertions, the SQLite concurrency skip, the
  422-mismatch named-assertion gap. Those are documented in
  `verify-report.md` issues §WARNING 1-3 and are NOT in Phase 2A6 scope.

## Affected Components

| Area | Impact | Description |
|------|--------|-------------|
| `backend/dp4500_integration/tests/test_cascade.py` | Modified (+120 net lines) | Adds 3 new test methods to existing `CascadeSignalTests` (line ~55) and `CascadeTaskOutcomeTests` (line ~115) classes |
| `backend/tests/integration/dp4500_integration/test_smoke_e2e.py` | Modified (+30 net lines, −10 skip) | Replaces the `self.skipTest(...)` block at lines 272-281 with cascade-delete + 5 new assertions; the smoke user must have no FK dependents (existing `_build_smoke_graph` already guarantees this at lines 70-102) |
| Existing fixtures | Reused | `CascadeSignalTests` + `CascadeTaskOutcomeTests` fixtures (`test_cascade.py:32-110`); `_build_smoke_graph` (`test_smoke_e2e.py:70-102`); `_patch_dp4500_handler` helper (`test_smoke_e2e.py:144-160`) |
| `httpx.MockTransport` | Reused | The Phase 2A5 DP4500 impersonator already returns 204 on `DELETE /templates/...` (`test_smoke_e2e.py:245-246`); no changes needed |
| Celery `eager` mode | Reused | `CELERY_TASK_ALWAYS_EAGER=True` in `backend/conftest.py` makes `cascade_revoke_template.delay(...)` synchronous inside the `Usuario.delete()` call |
| Signal pre-save bypass technique | New (in WU-2A6.1) | Monkey-patch `accounts.signals.assign_biometric_external_id` (or assign `biometric_external_id=None` post-save, since the field is `null=True, blank=True` per `backend/accounts/models.py:55-64`) to exercise the early-return branch at `signals.py:32-33` |

## Open questions

None. The explore phase (file §4) resolved all design questions: which test
class, which patch surface, which insertion point, which assertions, and
the maximum-retries test isolation strategy (call `on_failure` directly
rather than loop the Celery retry machinery).

## Rollback plan

Pure test additions — rollback is `git revert` of the single commit. No
DB migration, no API contract change, no Celery schedule, no signal
listener. Reverting the PR removes:

- 3 new test methods in `test_cascade.py`
- The cascade-skip replacement + 5 new assertions in `test_smoke_e2e.py`
- The Phase 2A6 `archive-report.md` entry that flips the 3 PARTIAL rows
  on `cascade-revoke` to COMPLIANT

After `git revert`, the test suite returns to the Phase 2A5 baseline:
9 passed + 2 skipped (`verify-report.md:83-93`). No production behavior
is observably different to a deployed clinic.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| SQLite FK enforcement vs `IntegrityError` simulation in WU-2A6.2 | Low | `IntegrityError` is raised from the `mock.patch` call site itself — not from SQLite. The test asserts the signal's `try/except` catches it (`signals.py:48`). Works on SQLite and Postgres identically. |
| Eager Celery ordering vs the WU-2A6.4 smoke chain | Low | `CELERY_TASK_ALWAYS_EAGER=True` + the signal ordering test from Phase 2A4 (`test_smoke_e2e.py:251-265`) already lock down the chain. Phase 2A6 only extends, never alters, the chain. |
| `Usuario.delete()` FK cascade in WU-2A6.4 (CitaMedica PROTECT, BiometricAttempt SET_NULL, etc.) | Low | The existing `_build_smoke_graph` (`test_smoke_e2e.py:70-102`) creates the smoke `Usuario` with zero FK dependents. The deletion is intentional and idiomatic for this graph. |
| `MaxRetriesExceededError` patching surface in WU-2A6.3 | Low | Patch `tasks.cascade_revoke_template.retry` (the method bound at task-definition time). Already the canonical patch site per existing test patterns at `test_cascade.py:175-188`. |
| Test count growth (`test_cascade.py` 8 → 11) | Low | ~3 additional passing tests on WSL pytest; well below CI noise threshold. No CLAUDE.md or CI file edits needed. |
| Phase 2A5 `size:exception` precedent (~1340 net lines, 3.35× the 400-line budget) | n/a | Phase 2A6 stays ≤150 net lines — no exception needed. The `archive-report` will note this as a positive deviation. |
| The Phase 2A5 archive-report being re-edited in Phase 2A6 | Low | The new `archive-report.md` lives at `openspec/changes/dp4500-host-app-integration-phase2a6-cascade-revoke/archive-report.md`. The Phase 2A5 archive (`.../archive/2026-09-28-dp4500-host-app-integration-phase2/`) is **not** touched (see explore.md §4.5). |

## Dependencies

- **None.** Phase 2A6 is a test-only patch on already-shipped production code.
- Existing fixtures + helper functions in `test_cascade.py` and `test_smoke_e2e.py`
  are reused; no new test infrastructure is required.
- The `MaxRetriesExceededError` exception is imported from `celery.exceptions`
  (the canonical source per `tasks.py:113-128`).

## Success Criteria

Phase 2A6 is complete when:

- [ ] `python -m pytest backend/dp4500_integration/tests/test_cascade.py backend/tests/integration/dp4500_integration/test_smoke_e2e.py` exits 0 on WSL.
- [ ] `test_cascade.py` grows from 8 → 11 passing tests; `test_smoke_e2e.py` skip count drops by 1 (the cascade skip at lines 278-281 is removed).
- [ ] The 3 PARTIAL rows on `cascade-biometric-revoke` (verify-report.md rows 191, 192, 196) flip to COMPLIANT in the new `archive-report.md`.
- [ ] The WU-2A6.4 smoke chain (`enroll → finalize → verify → delete → cascade complete`) passes inside a single pytest session, with the `PendingCascade` row reaching `status=STATUS_COMPLETED`.
- [ ] No production code committed in this change (`git diff --stat` shows ≤150 net lines, all under `backend/dp4500_integration/tests/` and `backend/tests/integration/dp4500_integration/`).
- [ ] No `size:exception` annotation needed (≤150 net lines is under the 400-line review budget per `openspec/config.yaml:64`).

## References

- `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/verify-report.md` — rows 184–208 (cascade-revoke compliance matrix), issues §WARNING 4–6 (lines 294–298).
- `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/specs/cascade-biometric-revoke/spec.md` — canonical spec; sections 44–49 (G1), 51–58 (G2), 96–103 (G3) cited verbatim.
- `backend/dp4500_integration/signals.py:29-66` — post_delete handler under test.
- `backend/dp4500_integration/tasks.py:39-132` — Celery task + `on_failure` hook under test.
- `backend/dp4500_integration/tests/test_cascade.py:1-293` — existing 8 tests; insertion points at lines 113 (after WU-2A6.1/2 class boundary), 188 (after WU-2A6.3 class boundary).
- `backend/tests/integration/dp4500_integration/test_smoke_e2e.py:116-281` — existing smoke; skip replacement at lines 272-281.
- `openspec/changes/dp4500-host-app-integration-phase2a6-cascade-revoke/explore.md` — exploration that produced this proposal (§3 WU-1 through WU-5 + §4.3 task-budget table).
