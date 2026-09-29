```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:1111111111111111111111111111111111111111111111111111111111111111
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 8/8
scenarios: 14/14
test_command: wsl -e bash -c "source '/mnt/c/proyectos/proyecto C/backend/env/bin/activate' && cd '/mnt/c/proyectos/proyecto C/backend' && DJANGO_SETTINGS_MODULE=config.settings python -m pytest -q dp4500_integration/tests/test_cascade.py tests/integration/dp4500_integration/test_smoke_e2e.py tests/integration/dp4500_integration/test_smoke_cascade.py"
test_exit_code: 0
test_output_hash: sha256:de9e5824d532e62ff7e483a53155900b0f318c2b24cc78dedf78475ec07f5504
build_command: cd "C:\proyectos\proyecto C\frontend\aesthetic-clinic"; npx tsc -b --pretty false
build_exit_code: 0
build_output_hash: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## Verification Report

**Change**: `dp4500-host-app-integration-phase2a7-cascade-e2e` (Phase 2A7 — focused cascade smoke e2e, isolated from the wizard chain)
**Branch**: `feat/dp4500-host-app-integration-phase2-sdd`
**HEAD**: `eb162d4` (`test(dp4500_integration): add focused cascade smoke e2e (Phase 2A7)`)
**Mode**: Standard (Strict TDD not active)
**Artifact store**: openspec
**Verdict**: **PASS WITH WARNINGS**
**One-line reason**: Phase 2A7 closes the WU-2A6.4 deferral (smoke e2e cascade step) by adding `backend/tests/integration/dp4500_integration/test_smoke_cascade.py` — one new test method `test_cascade_signal_then_task_marks_completed` that exercises the full `Usuario.delete() → post_delete signal → PendingCascade insert → cascade_revoke_template.delay → cascade_revoke_template.run() → HTTPClient.delete_template (MockTransport 204) → STATUS_COMPLETED` pipeline using the four Phase 2A6-proven patterns (A env dict, B dual-HTTPClient ExitStack, C bound `.delay` attribute, D direct `.run()` invocation). The new test passes at runtime (14 passed, 1 skipped on WSL pytest per the orchestrator-provided evidence). The 8 cascade-revoke requirements / 14 scenarios stay at the Phase 2A6 subtotal (13/14 COMPLIANT, 1/14 OUT-OF-SCOPE), and the WU-2A6.4 deferral row is now closed via the new dedicated file.

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 11 (1.1.1, 1.1.2, 1.1.3, 1.2.1, 1.2.2, 1.3.1, 1.3.2, 1.3.3, 1.3.4, 2 pre-verify markers at lines 98–100, 1 post-archive marker at line 106) |
| Tasks complete (implementation) | 4 (1.1.1, 1.1.2, 1.1.3, 1.2.1) |
| Tasks complete (wrap-up/runtime) | 4 (1.2.2 + 1.3.1 + 1.3.2 + 1.3.4 confirmed by `git show eb162d4` + WSL pytest results) |
| Tasks incomplete (runtime deferred) | 1 (1.3.3 `git diff --stat main..HEAD` shows ≤ 200 net lines — see WARNING 3) |
| Pre-verify + post-archive markers | 4 unchecked (lines 98–100 + line 106 — belong to verify/archive phases, not implementation) |
| Specs read | 1 (`specs/cascade-biometric-revoke/spec.md` — delta copy of the archived Phase 2A6 spec, byte-identical body + appended "ADDED Tests (Phase 2A7)" section) |
| Spec requirements total | 8 |
| Spec scenarios total | 14 |

The 4 implementation tasks (1.1.1–1.2.1) are `[x]` checked in `tasks.md`. Task 1.2.2 ("GREEN: confirm the test passes in WSL pytest") is `[ ]` unchecked but **resolved by the orchestrator-provided WSL pytest result** (14 passed, 1 skipped) — see WARNING 2. Tasks 1.3.1 (single-file test exit 0), 1.3.2 (regression test exit 0), 1.3.4 (commit) are unchecked but their evidence is present in `git show eb162d4` (commit exists with correct message + 2 files: `test_smoke_cascade.py` + `tasks.md`) and the WSL pytest result. Task 1.3.3 (line count) is unchecked and **partially out of compliance** (see WARNING 3). The pre-verify markers at `tasks.md:98-100` are the sdd-verify phase's own checklist (this report fulfils them); the post-archive marker at line 106 is the sdd-archive phase's concern.

### Build & Tests Execution

**Build**: ✅ Passed (`tsc -b` exit 0, 0 errors)

```text
$ cd "C:\proyectos\proyecto C\frontend\aesthetic-clinic"
$ npx tsc -b --pretty false
$ echo $?
0
```

The 0-line stdout reflects a clean workspace — no diagnostics emitted. Phase 2A7 is a backend-only test delta (see WARNING 4 below for the test-side-only commit composition), so no `.ts`/`.tsx` changes are in this commit; the build is the Phase 2A6 baseline, unchanged by Phase 2A7.

**Tests** (WSL pytest, run by orchestrator): ✅ **14 passed, 1 skipped**

```text
$ wsl -e bash -c "source '/mnt/c/proyectos/proyecto C/backend/env/bin/activate' \
    && cd '/mnt/c/proyectos/proyecto C/backend' \
    && DJANGO_SETTINGS_MODULE=config.settings \
       python -m pytest -q \
              dp4500_integration/tests/test_cascade.py \
              tests/integration/dp4500_integration/test_smoke_e2e.py \
              tests/integration/dp4500_integration/test_smoke_cascade.py"
...
============================= test session starts ==============================
django: version: 5.2.8, settings: config.settings (from env)
collected 15 items

dp4500_integration/tests/test_cascade.py::PendingCascadeLifecycleTests::test_pending_cascade_defaults_to_pending PASSED
dp4500_integration/tests/test_cascade.py::CascadeSignalTests::test_every_user_delete_creates_pending_cascade PASSED
dp4500_integration/tests/test_cascade.py::CascadeSignalTests::test_sync_insert_failure_does_not_rollback_local_delete PASSED
dp4500_integration/tests/test_cascade.py::CascadeSignalTests::test_user_with_biometric_external_id_creates_pending_row PASSED
dp4500_integration/tests/test_cascade.py::CascadeSignalTests::test_user_without_biometric_external_id_is_no_op PASSED
dp4500_integration/tests/test_cascade.py::CascadeTaskOutcomeTests::test_204_marks_completed PASSED
dp4500_integration/tests/test_cascade.py::CascadeTaskOutcomeTests::test_404_is_idempotent_completed PASSED
dp4500_integration/tests/test_cascade.py::CascadeTaskOutcomeTests::test_503_BIOMETRIC_SUSPENDED_marks_suspended_no_retry PASSED
dp4500_integration/tests/test_cascade.py::CascadeTaskOutcomeTests::test_max_retries_exhausted_marks_failed PASSED
dp4500_integration/tests/test_cascade.py::ReconcileCommandTests::test_dry_run_does_not_modify PASSED
dp4500_integration/tests/test_cascade.py::ReconcileCommandTests::test_processes_pending_rows PASSED
dp4500_integration/tests/test_cascade.py::ReconcileCommandTests::test_skips_completed_rows PASSED
dp4500_integration/tests/test_cascade.py::BiometricEnrollmentRecordTests::test_round_trip PASSED
tests/integration/dp4500_integration/test_smoke_e2e.py::SmokeE2ETests::test_enroll_finalize_verify_then_cascade SKIPPED
tests/integration/dp4500_integration/test_smoke_cascade.py::SmokeCascadeTests::test_cascade_signal_then_task_marks_completed PASSED

14 passed, 1 skipped, 5 warnings in ~16s
```

Test composition (15 collected):
- `test_cascade.py`: 13 tests (matches Phase 2A6 baseline; **no regression**)
- `test_smoke_e2e.py`: 1 test — `test_enroll_finalize_verify_then_cascade` is `self.skipTest(...)` at lines 284–288 (preserved from Phase 2A6; the cascade sub-step deferral stays in place per `proposal.md` §Scope + §Out-of-Scope)
- `test_smoke_cascade.py`: 1 test — `test_cascade_signal_then_task_marks_completed` (NEW, Phase 2A7 WU-2A7.1)

Net delta vs Phase 2A6 baseline: **+1 passing test** (the new `test_smoke_cascade.py`).

Skip details (the single skip):
1. `SmokeE2ETests::test_enroll_finalize_verify_then_cascade` — `self.skipTest(...)` at `tests/integration/dp4500_integration/test_smoke_e2e.py:284-288`. The skip body (`"Phase 2A6: smoke e2e cascade path deferred. Cascade coverage lives in test_cascade.py (WU-2A6.1, WU-2A6.2, WU-2A6.3 — all pass)."`) is unchanged from Phase 2A6 (commit `156f639`). The WU-2A7.2 docstring touch-up (proposal §Scope row WU-2A7.2, design.md §Dependencies) that should have added `test_smoke_cascade.py` to the cited coverage list **was not executed** — see WARNING 1.

**Coverage**: ➖ Not measured at this layer. Per the Phase 2A6 lineage (archived verify-report §Coverage), the targets are 100% line on `client.py`, ≥90% on `views.py` / `signals.py`, ≥80% on `tasks.py`. The new `test_cascade_signal_then_task_marks_completed` covers the `signals.py:29-66` post_delete handler + `tasks.py:39-65` `_do_cascade` body + `tasks.py:68-110` task wrapper end-to-end, plus the `views.py:33` / `tasks.py:14` import-site interplay that the Phase 2A6 F1 failure exposed. Coverage tooling (`coverage.py --include=dp4500_integration/*`) is not part of the verify command set for this cycle, consistent with Phase 2A6 (`verify-report.md:90`).

### Spec Compliance Matrix

Status legend: ✅ **COMPLIANT** (covering test exists + passed at runtime) · ⚠️ **PARTIAL** (passing test but covers only part of scenario) · 🚫 **OUT-OF-SCOPE** (explicitly deferred, pre-existing) · ❌ **FAILING** (covering test exists but failed) · ❌ **UNTESTED** (no covering test found).

#### Spec: `cascade-biometric-revoke` — 8 requirements / 14 scenarios

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| **Cascade hook on User.delete** | User with biometric_external_id creates a pending row | `SmokeCascadeTests::test_cascade_signal_then_task_marks_completed` (`backend/tests/integration/dp4500_integration/test_smoke_cascade.py:130`) — **NEW Phase 2A7 end-to-end coverage** that exercises the same scenario at the integration layer (signal + bound `.delay` + PendingCascade insert via the real `signals.py:29-66` post_delete handler). Asserts `mock_delay.assert_called_once_with(str(graph["external_id"]), graph["sucursal"].id)` at `test_smoke_cascade.py:163-166`, `PendingCascade.objects.count() == 1` at line 167, `pending_row.status == PendingCascade.STATUS_PENDING` at lines 169-172. The pre-existing unit-level coverage in `CascadeSignalTests::test_user_with_biometric_external_id_creates_pending_row` (`backend/dp4500_integration/tests/test_cascade.py:88`) still passes and continues to be the canonical assertion contract. The new e2e test closes the WU-2A6.4 deferral by proving the wiring works through `signals.py → tasks.delay()` without the broker, with all import sites patched. | ✅ COMPLIANT |
| **Cascade hook on User.delete** | User without biometric_external_id is a no-op | `CascadeSignalTests::test_user_without_biometric_external_id_is_no_op` (`backend/dp4500_integration/tests/test_cascade.py:131`) — passes. Phase 2A6 PARTIAL G1 → COMPLIANT (per archived Phase 2A6 verify-report row 101). Unchanged by Phase 2A7. | ✅ COMPLIANT |
| **Cascade hook on User.delete** | Sync insert failure does not roll back the local delete | `CascadeSignalTests::test_sync_insert_failure_does_not_rollback_local_delete` (`backend/dp4500_integration/tests/test_cascade.py:167`) — passes. Phase 2A6 PARTIAL G2 → COMPLIANT (per archived Phase 2A6 verify-report row 102). Unchanged by Phase 2A7. | ✅ COMPLIANT |
| **Celery task cascade_revoke_template** | Successful cascade marks completed | `SmokeCascadeTests::test_cascade_signal_then_task_marks_completed` (`backend/tests/integration/dp4500_integration/test_smoke_cascade.py:130`) — **NEW Phase 2A7 coverage** that asserts this at the integration layer via `cascade_revoke_template.run(str(graph["external_id"]), graph["sucursal"].id)` (Pattern D, lines 175-178) with the MockTransport returning 204 (line 191). Asserts `row.status == PendingCascade.STATUS_COMPLETED` at line 182, `row.attempts == 1` at line 183, `row.completed_at is not None` at line 184. The pre-existing unit-level `CascadeTaskOutcomeTests::test_204_marks_completed` (`backend/dp4500_integration/tests/test_cascade.py:252`) still passes. The Phase 2A7 e2e test is the **WU-2A6.4 closure evidence** (Phase 2A6 verify-report §Issues §WARNING 1) — the end-to-end wiring now exercises both the signal AND the task body in one chain. | ✅ COMPLIANT |
| **Celery task cascade_revoke_template** | Idempotent 404 marks completed without error | `CascadeTaskOutcomeTests::test_404_is_idempotent_completed` (`backend/dp4500_integration/tests/test_cascade.py:263`) — passes. Unchanged by Phase 2A7. | ✅ COMPLIANT |
| **Celery task cascade_revoke_template** | BiometricSuspended is non-retryable | `CascadeTaskOutcomeTests::test_503_BIOMETRIC_SUSPENDED_marks_suspended_no_retry` (`backend/dp4500_integration/tests/test_cascade.py:275`) — passes. Unchanged by Phase 2A7. | ✅ COMPLIANT |
| **Celery task cascade_revoke_template** | Up to 5 retries on transient unavailability | `CascadeTaskOutcomeTests::test_max_retries_exhausted_marks_failed` (`backend/dp4500_integration/tests/test_cascade.py:297`) — passes. Phase 2A6 PARTIAL G3 → COMPLIANT (per archived Phase 2A6 verify-report row 106). Unchanged by Phase 2A7. | ✅ COMPLIANT |
| **Reconciliation management command** | Manual reconciliation advances all pending rows | `ReconcileCommandTests::test_processes_pending_rows` (`backend/dp4500_integration/tests/test_cascade.py:392`) — passes. Unchanged by Phase 2A7. | ✅ COMPLIANT |
| **Reconciliation management command** | Reconcile is idempotent | `ReconcileCommandTests::test_skips_completed_rows` (`backend/dp4500_integration/tests/test_cascade.py:416`) — passes. Unchanged by Phase 2A7. | ✅ COMPLIANT |
| **Alert after N retries** | Failed row is observable | Admin notification banner — Phase 4 cron polish per `design.md §11`; design explicitly defers this scenario to Phase 4. No test target. **Pre-existing OUT-OF-SCOPE** (flagged as such in archived Phase 2A5 verify-report row 199 + archived Phase 2A6 verify-report row 109). Unchanged by Phase 2A7. | 🚫 OUT-OF-SCOPE |
| **PendingCascade model lives in the biometric app** | Model migration succeeds | `dp4500_integration/migrations/0001_initial.py` — confirmed via archived Phase 2A4 archive-report (`manage.py makemigrations --check` exits 0). No Phase 2A7 migration changes. | ✅ COMPLIANT |
| **No fingerprint bytes in PendingCascade** | Field inventory | `PendingCascade` model (`backend/dp4500_integration/models.py:23-...`) carries `user_external_id` (UUIDField), `sucursal_id` (IntegerField), `status` (CharField), `attempts` (PositiveSmallIntegerField), `last_error_code` (CharField), `completed_at` (DateTimeField), `last_attempt_at` (DateTimeField), `created_at` (auto). Zero byte-typed fields. Phase 2A7 made no production code changes — model untouched. | ✅ COMPLIANT |
| **Cross-DB foreign keys are forbidden** | Branch deletion does not cascade-delete pending rows | `sucursal_id` is `IntegerField`, NOT a `ForeignKey` to the clinic's `Sucursal` (`backend/dp4500_integration/models.py`). `Sucursal.delete()` cannot cascade-delete `PendingCascade` rows. Phase 2A7 made no production code changes — model untouched. | ✅ COMPLIANT |
| **Cross-project FK discipline** | No cross-project FKs in the schema | `backend/dp4500_integration/migrations/0001_initial.py` has zero FKs to DP4500-side models (the `C:\proyectos\DP4500 estandar` project). `grep -r 'ForeignKey' backend/dp4500_integration/migrations/` confirms no DP4500-side targets. | ✅ COMPLIANT |

**Subtotal: 13/14 COMPLIANT, 0/14 PARTIAL, 1/14 OUT-OF-SCOPE, 0/14 FAILING, 0/14 UNTESTED.**

> Identical subtotal to Phase 2A6 baseline (archived `verify-report.md:115`). Phase 2A7 does NOT flip a PARTIAL row on the spec compliance matrix (per `proposal.md` §Background: "Phase 2A7 adds end-to-end wiring coverage that `test_cascade.py` provides only at the unit level"; per `design.md` §Architecture decision: "The 13/14 cascade-revoke COMPLIANT subtotal from Phase 2A6 stays"). The WU-2A6.4 deferral closure is an **addendum**, not a spec-row flip — `test_user_with_biometric_external_id_creates_pending_row` and `test_204_marks_completed` were already COMPLIANT in Phase 2A6; Phase 2A7 adds a higher-level integration-layer test that exercises both rows of the cascade pipeline end-to-end in one chain.

### Phase 2A6 PARTIAL → Phase 2A7 COMPLIANT Transitions (WU-2A6.4 closure)

The Phase 2A6 verify-report §Issues §WARNING 1 (line 149) flagged the WU-2A6.4 deferral: *"Smoke e2e cascade step (WU-2A6.4) deferred to Phase 2A7"*. Phase 2A7 closes this deferral.

| WU | Phase 2A6 status | Phase 2A7 status | Closure evidence | Rationale |
|----|------------------|------------------|------------------|-----------|
| **WU-2A6.4** | ⚠️ DEFERRED — `SmokeE2ETests::test_enroll_finalize_verify_then_cascade` cascade sub-step skipped at `tests/integration/dp4500_integration/test_smoke_e2e.py:284-288`. 4 fix-iteration history in `apply-progress.md §1.3 + §4` hit Phase 2A6 failure modes F1 (single `HTTPClient` patch), F2 (filesystem broker touch in eager mode), F3 (`on_failure` positional vs keyword args), F4 (direct `.run()` blocked by earlier-broken patches). | ✅ CLOSED via dedicated file. New `SmokeCascadeTests::test_cascade_signal_then_task_marks_completed` at `backend/tests/integration/dp4500_integration/test_smoke_cascade.py:130` exercises the full cascade pipeline in isolation from the wizard chain. The test passes at runtime (orchestrator-provided WSL pytest: 14 passed, 1 skipped). | `backend/tests/integration/dp4500_integration/test_smoke_cascade.py:1-194` (194 lines, single test method). New file committed at `eb162d4` (HEAD). Phase 2A6 apply-progress.md §4 failure modes F1-F4 all addressed by Patterns A/B/C/D in `design.md` (lines 32-131). | Per `proposal.md` §Background + §In-Scope WU-2A7.1: "test aislado del cascade (mejor diseño)". The dedicated-file approach sidesteps the Phase 2A6 architectural complexity by decoupling the cascade surface from the wizard enroll+verify chain (no CitaMedica/Operacion/Cliente reverse-FK trap, no shared fixture). |

### Phase 2A6 PARTIAL → Phase 2A7 COMPLIANT Transitions (carry-forward, no change)

For traceability, the three PARTIAL → COMPLIANT flips that Phase 2A6 already delivered (per archived `verify-report.md:117`) remain COMPLIANT at Phase 2A7:

| WU | Spec scenario | Test | Phase 2A6 status | Phase 2A7 status |
|----|---------------|------|------------------|------------------|
| **WU-2A6.1** | §6.6 User without biometric_external_id is a no-op | `test_user_without_biometric_external_id_is_no_op` (`test_cascade.py:131`) | ✅ COMPLIANT (Phase 2A6) | ✅ COMPLIANT (unchanged) |
| **WU-2A6.2** | §6.7 Sync insert failure does not roll back the local delete | `test_sync_insert_failure_does_not_rollback_local_delete` (`test_cascade.py:167`) | ✅ COMPLIANT (Phase 2A6) | ✅ COMPLIANT (unchanged) |
| **WU-2A6.3** | §6.10 Up to 5 retries on transient unavailability | `test_max_retries_exhausted_marks_failed` (`test_cascade.py:297`) | ✅ COMPLIANT (Phase 2A6) | ✅ COMPLIANT (unchanged) |

### Validation Evidence

**1. Git stat (single commit `eb162d4` vs parent `eb162d4~1` = `6c5d29d`)**

```text
$ git show --stat eb162d4
commit eb162d4cf11ae06cbe0ead5ea29977f5174ad10f
Author: Fabian Rivero <fabianarj@gmail.com>
Date:   Mon Sep 28 18:02:07 2026 -0400

    test(dp4500_integration): add focused cascade smoke e2e (Phase 2A7)
    ...

 .../dp4500_integration/test_smoke_cascade.py       | 194 +++++++++++++++++++++
 .../tasks.md                                       | 106 +++++++++++
 2 files changed, 300 insertions(+)
```

**Zero production-code files in the diff.** The only modified files are:
- `backend/tests/integration/dp4500_integration/test_smoke_cascade.py` — NEW (194 lines)
- `openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/tasks.md` — NEW (106 lines)

Neither `signals.py`, `tasks.py`, `models.py`, `views.py`, `client.py`, nor `settings.py` appears in the diff. The Phase 2A7 "test-only" lineage invariant from `proposal.md §Scope` + §Success Criteria is preserved.

**2. New test file (`backend/tests/integration/dp4500_integration/test_smoke_cascade.py`) — assertion inventory**

The orchestrator's input list (`1.` through `7.` below) is verified line-by-line against the actual file content:

| # | Required assertion | File:line | Verified |
|---|--------------------|-----------|----------|
| 1 | Creates a `Usuario` with `biometric_external_id` set | `test_smoke_cascade.py:100-111` — `external_id = uuid.uuid4()` + `Usuario(... biometric_external_id=external_id)` | ✅ |
| 2 | Uses `mock.patch.dict` for `DP4500_SERVICE_KEY_SUCURSAL_<id>` | `test_smoke_cascade.py:135-143` — `mock.patch.dict(os.environ, {f"DP4500_SERVICE_KEY_SUCURSAL_{graph['sucursal'].id}": "SeK_smoke_test"}, clear=False)` | ✅ |
| 3 | Patches BOTH `views.HTTPClient` AND `tasks.HTTPClient` via `ExitStack` | `test_smoke_cascade.py:69-72` (helper returns tuple) + `148-150` (`ExitStack` + `stack.enter_context(patcher)` loop) | ✅ |
| 4 | Patches the bound `signals.cascade_revoke_template.delay` attribute | `test_smoke_cascade.py:151-153` — `mock.patch("dp4500_integration.signals.cascade_revoke_template.delay") as mock_delay` | ✅ |
| 5 | Deletes the Usuario → asserts `mock_delay.assert_called_once_with(<uuid>, <sucursal_id>)` | `test_smoke_cascade.py:160` (`graph["enrolled"].delete()`) + `163-166` (`mock_delay.assert_called_once_with(str(graph["external_id"]), graph["sucursal"].id)`) | ✅ |
| 6 | Calls `cascade_revoke_template.run(<uuid>, <sucursal_id>)` directly | `test_smoke_cascade.py:175-178` — `cascade_revoke_template.run(str(graph["external_id"]), graph["sucursal"].id)` | ✅ |
| 7 | Asserts `PendingCascade.status == STATUS_COMPLETED`, `attempts == 1`, `completed_at is not None` | `test_smoke_cascade.py:182-184` — `self.assertEqual(row.status, PendingCascade.STATUS_COMPLETED)` + `self.assertEqual(row.attempts, 1)` + `self.assertIsNotNone(row.completed_at)` | ✅ |

All 7 items in the orchestrator's input list pass source inspection. The test passes at runtime per the orchestrator-provided WSL pytest output (1 new passed test: `test_smoke_cascade.py::SmokeCascadeTests::test_cascade_signal_then_task_marks_completed`).

**3. Cross-reference with the 8 cascade-revoke spec scenarios that the new test touches**

| Spec scenario | How the new test exercises it | Runtime evidence |
|----------------|-------------------------------|------------------|
| §6.4 User with biometric_external_id creates a pending row | `test_smoke_cascade.py:160-172` — `graph["enrolled"].delete()` fires the post_delete signal which calls `signals.cascade_revoke_on_user_delete(...)` (signals.py:29-66) → inserts `PendingCascade(status=pending)` synchronously → calls `.delay(ext_id, sucursal_id)` which is mocked. Asserts `mock_delay.assert_called_once_with(...)` + `PendingCascade.objects.count() == 1` + `pending_row.status == STATUS_PENDING`. | ✅ WSL pytest passed |
| §6.5 (Successful cascade marks completed) | `test_smoke_cascade.py:175-184` — direct `cascade_revoke_template.run(str(ext_id), sucursal_id)` invokes `_do_cascade` body (tasks.py:39-65), which creates `HTTPClient` via the patched factory (tasks.HTTPClient import site) and calls `delete_template`, which sends `DELETE /service/templates/<ext_id>/` to the MockTransport (returns 204, line 191). `tasks.py:91` increments `attempts` to 1; `tasks.py:96-98` marks `status=STATUS_COMPLETED` + `completed_at=now()`. Asserts all three: `status == STATUS_COMPLETED`, `attempts == 1`, `completed_at is not None`. | ✅ WSL pytest passed |

The new test does NOT exercise §6.6 (no-op branch), §6.7 (sync insert failure), §6.8 (404 idempotent), §6.9 (BiometricSuspended), §6.10 (max retries exhausted), §6.12 (reconcile advances all pending), §6.13 (reconcile is idempotent), §6.15 (alert banner — OUT-OF-SCOPE), §6.17 (migration succeeds), §6.19 (field inventory), §6.21 (branch deletion doesn't cascade-delete pending), §6.23 (no cross-project FKs) — those scenarios are covered by the 13 `test_cascade.py` tests + the migration files + the `models.py` source (per the Phase 2A6 compliance matrix, which Phase 2A7 inherits verbatim).

**4. MockTransport request count (per `proposal.md §Success Criteria` row 5)**

The new test exercises exactly 1 DELETE to `/service/templates/<ext_id>/` (the cascade task's only DELETE per `client.py:170-174`). The handler at `test_smoke_cascade.py:187-194` returns 204 for `DELETE /templates/...` and raises `AssertionError` on any unexpected URL/method — matching the design.md §Risks "Real network leaks" mitigation. Although the new test does not explicitly count `len(delete_calls)` (the design.md template suggested it as a `len(delete_calls) == 1` assertion; the actual implementation at lines 187-194 uses an unconditional 204 return + AssertionError fallback), the behavior is functionally equivalent: any duplicate DELETE would surface as `assert_called_once_with` failure at line 163-166 (since `mock_delay` is called exactly once, only one cascade task execution flows through `_do_cascade` → `delete_template`). See WARNING 5 for the minor design.md §Test surface vs implementation drift.

### Correctness (Cross-cutting)

| Property | Status | Notes |
|----------|--------|-------|
| Phase 2A7 is test-only (no production code modifications) | ✅ Verified | `git show eb162d4 --name-only` shows only 2 files: `test_smoke_cascade.py` (NEW) + `tasks.md` (NEW). Zero production-code files (`signals.py`, `tasks.py`, `models.py`, `views.py`, `client.py`, `settings.py`) in the diff. The 194-line new test file is **additive** — the 13 `test_cascade.py` tests are unchanged. |
| All 4 Phase 2A6 patterns (A/B/C/D) are applied | ✅ Verified | Pattern A (`mock.patch.dict(os.environ, ...)`) at lines 135-143. Pattern B (`ExitStack` over two `HTTPClient` import sites) at lines 69-72 + 148-150. Pattern C (bound `.delay` attribute patch) at lines 151-153. Pattern D (direct `cascade_revoke_template.run(...)`) at lines 175-178. |
| WU-2A6.4 deferral is closed | ✅ Verified | New dedicated file `test_smoke_cascade.py` exercises the full cascade pipeline end-to-end in isolation from the wizard chain. The 4 Phase 2A6 failure modes F1-F4 (per `proposal.md §Background` table + `apply-progress.md §4`) are all sidestepped: Pattern B fixes F1, Pattern C fixes F2, Pattern D fixes F4, and F3 (`on_failure` positional/keyword signature) is not exercised in the happy path. |
| No regression on the 13 existing `test_cascade.py` tests | ✅ Verified | Orchestrator-provided WSL pytest result lists all 13 `test_cascade.py` tests as PASSED. Zero changes to `test_cascade.py` in commit `eb162d4` (`git diff eb162d4~1..eb162d4 -- backend/dp4500_integration/tests/test_cascade.py` is empty). |
| MockTransport isolates the test from the network | ✅ Verified | The factory at `test_smoke_cascade.py:61-68` creates `HTTPClient` with `base_url="https://dp4500.test"` then swaps `client._client` for `httpx.Client(transport=httpx.MockTransport(handler))`. The `DP4500_BASE_URL` default at `settings.py:292` (committed at `6c5d29d`) is bypassed entirely. Per `design.md §Risks`: "The handler raises `AssertionError` on any unexpected URL — a missed DELETE that DOES route to MockTransport but the test expects `len(delete_calls) == 1` would catch a duplicate." |
| No real Celery broker touch | ✅ Verified | Pattern C patches the bound `.delay` attribute so the filesystem broker (configured at `config/settings.py` per `CELERY_TASK_ALWAYS_EAGER=True` + filesystem broker) is never reached. Pattern D's direct `.run(...)` invocation bypasses `apply_async` entirely. The test is hermetic. |
| Test creates Usuario with no reverse-FK dependents | ✅ Verified | `test_smoke_cascade.py:100-111` — the enrolled `Usuario` is created with only `biometric_external_id` set (no `Cliente`, no `Operacion`, no `CitaMedica`). `Usuario.delete()` triggers the post_delete signal without any FK constraint violation (the Phase 2A6 `Operacion.paciente=PROTECT` trap from the wizard chain does not apply here). |
| Commit message cites the 4 Phase 2A6 patterns | ✅ Verified | `git log -1 eb162d4` shows the commit body enumerates Patterns A, B, C, D with citations to `tasks.py:14`, `tasks.py:39-65`, `signals.py:23`, `test_cascade.py:252-261`. The commit message math is **slightly inaccurate** ("test_cascade.py 11 + test_smoke_cascade.py 1 + test_smoke_e2e.py 1 skipped + test_smoke_e2e.py 1 happy path" — but `test_cascade.py` has 13 tests, not 11, and `test_smoke_e2e.py` has only 1 test that skips — see WARNING 6). |

### Coherence (Design)

| Decision (from `design.md`) | Followed? | Notes |
|----------------------------|-----------|-------|
| **No architecture changes from Phase 2A6** — cascade pipeline (post_delete signal → sync PendingCascade → Celery `.delay()` → `_do_cascade()` → `HTTPClient.delete_template` → `on_failure` hook) unchanged. | ✅ Yes | `git show eb162d4 --stat` shows zero production-code files in the diff. ADRs 0001-0005 from Phase 2A5/2A6 stand. |
| **Test pattern A — env dict for `DP4500_SERVICE_KEY_SUCURSAL_<id>`** uses `mock.patch.dict(os.environ, ..., clear=False)`. | ✅ Yes | `test_smoke_cascade.py:135-143` — exact form. Rationale matches `design.md §Pattern A` line 32-49 (env var lookup at `tasks.py:34-36`). |
| **Test pattern B — `ExitStack` for dual `HTTPClient` patch sites** patches `views.HTTPClient` AND `tasks.HTTPClient`, NOT `client.HTTPClient`. | ✅ Yes | `test_smoke_cascade.py:69-72` returns a TUPLE of 2 `mock.patch` objects targeting `dp4500_integration.views.HTTPClient` and `dp4500_integration.tasks.HTTPClient`. `test_smoke_cascade.py:148-150` wraps both in `contextlib.ExitStack()`. The `from dp4500_integration.client import HTTPClient` source-of-truth site at `client.py:82` is NOT patched (correctly). |
| **Test pattern C — bound `.delay` attribute patch** targets `dp4500_integration.signals.cascade_revoke_template.delay`, NOT the task module. | ✅ Yes | `test_smoke_cascade.py:151-153` — `mock.patch("dp4500_integration.signals.cascade_revoke_template.delay")`. Mirrors Phase 2A6 proven pattern at `test_cascade.py:115-117`. |
| **Test pattern D — direct `cascade_revoke_template.run(...)` invocation** after `Usuario.delete()` with both HTTPClient patches still in scope. | ✅ Yes | `test_smoke_cascade.py:175-178` — `cascade_revoke_template.run(str(graph["external_id"]), graph["sucursal"].id)`. The `ExitStack` at line 148 is still entered (Pattern D requires both HTTPClient patches to remain active during `.run(...)`, which they do). Mirrors Phase 2A6 proven pattern at `test_cascade.py:252-261`. |
| **Net ≤200 test code lines, well under 400-line review budget** | ⚠️ See WARNING 3 | Actual: 194 lines for `test_smoke_cascade.py` + 106 lines for `tasks.md` = 300 net (per `git show eb162d4 --stat`). The test file itself is within the 200-line target; the tasks.md overhead pushes the total to 300 net. Below the 400-line `review_budget_lines` cap from `openspec/config.yaml:64`. **No `size:exception` required.** |
| **Self-contained test (no shared fixtures)** | ✅ Yes | The new test creates its own `Sucursal` + `Rol` + `Usuario` via `_make_graph()` at `test_smoke_cascade.py:75-118`. No imports from `test_cascade.py` or `test_smoke_e2e.py` (confirmed by reading imports at `test_smoke_cascade.py:30-44`). |
| **Class name `SmokeCascadeTests` (vs spec's `SmokeCascadeE2ETests`)** | ⚠️ See WARNING 7 | The implementation uses `SmokeCascadeTests` (`test_smoke_cascade.py:121`); the spec's `ADDED Tests (Phase 2A7)` section at `specs/cascade-biometric-revoke/spec.md:245` says `SmokeCascadeE2ETests`. Minor naming drift; the test method name `test_cascade_signal_then_task_marks_completed` matches. Both names describe the same single test. **Non-blocker** (test naming is not a spec scenario). |

### Issues Found

**CRITICAL**: None.

**WARNING**:

1. **WU-2A7.2 (skip-block docstring touch-up) was not executed** — The proposal §In-Scope table row WU-2A7.2 (and `design.md §Dependencies`) explicitly listed a 5-line comment-only touch-up at `backend/tests/integration/dp4500_integration/test_smoke_e2e.py:272-283` to cite `test_smoke_cascade.py` alongside `test_cascade.py` as the canonical end-to-end cascade coverage. The commit `eb162d4` does NOT touch `test_smoke_e2e.py` (`git diff eb162d4~1..eb162d4 -- backend/tests/integration/dp4500_integration/test_smoke_e2e.py` is empty). The skip block at `test_smoke_e2e.py:284-288` still says: *"Phase 2A6: smoke e2e cascade path deferred. Cascade coverage lives in test_cascade.py (WU-2A6.1, WU-2A6.2, WU-2A6.3 — all pass)."* — without mentioning `test_smoke_cascade.py` (Phase 2A7 WU-2A7.1). The semantic meaning is still correct (cascade coverage is canonical), but the docstring is **stale relative to the Phase 2A7 deliverable**. The proposal §Risks row "Skip-block docstring drift between `test_smoke_e2e.py` and `test_smoke_cascade.py`" predicted this risk as "Low" — it has materialized. **Resolution**: a 5-line follow-up commit adding the `test_smoke_cascade.py` citation to lines 272-283. **Non-blocker** — does not affect test counts or runtime behavior; the spec compliance subtotal stays at 13/14.

2. **Tasks 1.2.2 + 1.3.1–1.3.3 unchecked in `tasks.md`** — These 4 implementation-task rows are still `[ ]` in `tasks.md:68, 72-75` even though their evidence is present (WSL pytest result, commit `eb162d4`, line count). This is **drift between the apply agent's checkbox discipline and the actual deliverable**. The runtime evidence (orchestrator-provided pytest output + git log) confirms all 4 are satisfied:
   - 1.2.2 GREEN: confirmed by 14 passed / 1 skipped.
   - 1.3.1 single-file test: confirmed by the same pytest result covering `test_smoke_cascade.py`.
   - 1.3.2 no-regression test: confirmed by the same pytest result covering `test_cascade.py` (13 passed) + `test_smoke_e2e.py` (1 skipped, expected).
   - 1.3.4 commit: confirmed by `git show eb162d4` existing.
   Only task 1.3.3 (line count ≤ 200) is **partially out of compliance** — see WARNING 3. **Resolution**: a follow-up commit ticking these 4 checkboxes once the line-count reconciliation is finalized. **Non-blocker** — the verification decision is based on runtime + git evidence, not on `tasks.md` checkbox state.

3. **Task 1.3.3 (`git diff --stat main..HEAD` shows ≤ 200 net lines) is partially out of compliance** — The Phase 2A7 commit is 300 net lines (194 for `test_smoke_cascade.py` + 106 for `tasks.md`). Of that:
   - **194 lines for `test_smoke_cascade.py`** is within the proposal's ~120-line target (per `proposal.md §In-Scope WU-2A7.1`, `explore.md §5.3` estimate 80–120; actual 194 is 62–142% over the estimate range, but the file is heavily commented with explicit Pattern A/B/C/D citations + a 30-line module docstring — line count without comments would be ~80 lines).
   - **106 lines for `tasks.md`** is a NEW artifact (was not in the Phase 2A6 baseline; `tasks.md` lives under `openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/`, not under `backend/`). The proposal §In-Scope does not include `tasks.md` in the line budget — but the WU-2A7.1 table row cites "~120 net lines" for the test file only.
   - **300 net lines** is below the 400-line `review_budget_lines` cap from `openspec/config.yaml:64`, so **no `size:exception` is required**. The proposal §Success Criteria row "Total changed lines for this change ≤ 200 net" is technically exceeded (300 > 200), but this is **prose + test code, not production code**, and is documented as non-blocker in `proposal.md §Success Criteria` ("Well under the 400-line `review_budget_lines` cap"). **Non-blocker**.

4. **Test composition is test-side only (good — but the proposal §In-Scope row WU-2A7.2 promised 5 lines of `test_smoke_e2e.py` modification that didn't happen)** — This is the same WARNING 1 issue, viewed from the proposal-completeness angle. The commit message's "0 production code changes" claim is correct (per `git show eb162d4 --name-only`), but the WU-2A7.2 deliverable is **absent from the commit**. The total deliverable is **WU-2A7.1 (1/3 of proposal's work units) + WU-2A7.3 (test run, confirmed)**. **Non-blocker** — WU-2A7.1 is the core deliverable; WU-2A7.2 is documentation polish.

5. **`delete_calls` list assertion absent** — `design.md §Test surface` row WU-2A7.1 promises `MockTransport` records exactly 1 DELETE, and `design.md §Pattern D` line 129 shows `self.assertEqual(len(delete_calls), 1)`. The actual implementation at `test_smoke_cascade.py:186-194` uses an unconditional `httpx.Response(204)` for `DELETE /templates/...` without tracking `delete_calls`. The handler DOES raise `AssertionError` on any unexpected URL/method (lines 192-194), which catches re-routing mistakes but does NOT catch duplicate DELETEs to the same URL. Functionally, duplicates are caught upstream by `mock_delay.assert_called_once_with(...)` at line 163-166 (since `mock_delay` is called exactly once, only one cascade task execution flows through `_do_cascade` → `delete_template`). **Minor design.md vs implementation drift. Non-blocker** — the assertion contract is preserved end-to-end.

6. **Commit message test-count arithmetic is wrong** — `git log -1 eb162d4` body says "14 passed, 1 skipped on WSL pytest (test_cascade.py 11 + test_smoke_cascade.py 1 + test_smoke_e2e.py 1 skipped cascade sub-step + test_smoke_e2e.py 1 happy path)". Actual counts: `test_cascade.py` 13 (not 11), `test_smoke_cascade.py` 1, `test_smoke_e2e.py` 1 (skipped). The headline "14 passed, 1 skipped" matches the orchestrator-provided pytest result, so the **functional evidence is correct** — only the per-file arithmetic in the commit message is off. **Non-blocker** — a typo / mental-math error in the commit body.

7. **Class name mismatch: implementation `SmokeCascadeTests` vs spec `SmokeCascadeE2ETests`** — Per the comparison table in §Coherence. The implementation file at `test_smoke_cascade.py:121` declares `class SmokeCascadeTests(TestCase):`; the spec's `ADDED Tests (Phase 2A7)` section at `specs/cascade-biometric-revoke/spec.md:245` says `Class: SmokeCascadeE2ETests`. The test method name `test_cascade_signal_then_task_marks_completed` matches both. **Non-blocker** — class naming is not a spec scenario; pytest discovers the test by method name + file path. The compliance matrix in this report uses the actual class name (`SmokeCascadeTests`).

**SUGGESTION**:

1. **Document the Phase 2A7 spec.md name drift in `apply-progress.md` or `archive-report.md`** — The class name mismatch (`SmokeCascadeE2ETests` in spec vs `SmokeCascadeTests` in code) is small but creates a forensic blind spot. Future agents cross-referencing spec → code will benefit from a one-line "actual class is `SmokeCascadeTests`; spec draft used `SmokeCascadeE2ETests`" note.

2. **Add an explicit `delete_calls` counter to the handler for forensic clarity** — Even though the current `mock_delay.assert_called_once_with(...)` assertion at line 163-166 transitively guards against duplicate DELETEs, an explicit `len(delete_calls) == 1` assertion at line 184 (matching `design.md §Pattern D`) would make the test's contract more readable.

3. **Tick tasks 1.2.2 + 1.3.1–1.3.4 in `tasks.md` post-verification** — These are implementation tasks whose evidence is now present. A follow-up commit ticking the boxes would close the apply-progress discipline gap. (WU-2A7.2 should be retroactively removed or marked `[ ]` with rationale "deferred — docstring touch-up is for `sdd-archive` phase, not apply".)

4. **Refresh the `test_smoke_e2e.py:272-288` skip-block comment to cite `test_smoke_cascade.py`** — A 5-line follow-up commit would close WU-2A7.2 and prevent the docstring-drift risk called out in `proposal.md §Risks` row "Skip-block docstring drift between `test_smoke_e2e.py` and `test_smoke_cascade.py`".

5. **Note the new `SmokeCascadeTests` class in the Phase 2A7 `archive-report.md`** — The Phase 2A6 archive-report records the 13 `test_cascade.py` tests as the canonical coverage. Phase 2A7's `archive-report.md` should add the 1 `test_smoke_cascade.py` test to the canonical coverage list and flag the 14th test as the WU-2A6.4 deferral closure.

### Verdict

**PASS WITH WARNINGS**.

Phase 2A7 deliverable is complete at the spec-scenario level: the WU-2A6.4 deferral (Phase 2A6 verify-report §Issues §WARNING 1, line 149) is closed by the new `backend/tests/integration/dp4500_integration/test_smoke_cascade.py` — a single dedicated test method `test_cascade_signal_then_task_marks_completed` that exercises the full cascade pipeline (`Usuario.delete() → post_delete signal → PendingCascade insert → cascade_revoke_template.delay (mocked) → cascade_revoke_template.run() → HTTPClient.delete_template (MockTransport 204) → STATUS_COMPLETED`) in isolation from the wizard chain, using the four Phase 2A6-proven patterns A/B/C/D. The new test passes at runtime (orchestrator-provided WSL pytest: 14 passed, 1 skipped). Zero production code changes. The 8 cascade-revoke requirements / 14 scenarios remain at the Phase 2A6 subtotal (13/14 COMPLIANT, 1/14 OUT-OF-SCOPE — Phase 4 cron banner); Phase 2A7 adds an integration-layer test on top of the existing unit-level coverage rather than flipping a PARTIAL row.

The 4 WARNINGs are non-blockers:
- WU-2A7.2 (5-line `test_smoke_e2e.py:272-283` docstring touch-up) was not executed — the skip block remains Phase 2A6 wording.
- Tasks 1.2.2 + 1.3.1–1.3.4 are unchecked but their evidence is present (a discipline gap, not a deliverable gap).
- Task 1.3.3 (≤200 net lines) is partially out of compliance: 300 net lines (194 test + 106 tasks.md), still under the 400-line `review_budget_lines` cap.
- Minor design.md vs implementation drifts: `delete_calls` counter absent; commit message test-count arithmetic wrong; class name `SmokeCascadeTests` vs spec's `SmokeCascadeE2ETests`.

**Recommendation**: proceed to `sdd-archive` after the orchestrator's review commit. The Phase 2A7 `archive-report.md` should:
1. Record the WU-2A6.4 deferral closure (the WU-2A6.4 row of Phase 2A6's verify-report §Issues §WARNING 1 is now resolved).
2. Note the spec compliance subtotal stays 13/14 COMPLIANT + 1/14 OUT-OF-SCOPE (no row flips; Phase 2A7 is additive coverage at the integration layer).
3. Cite the 4 WARNINGs as post-Phase-2A7 follow-up candidates (especially WARNING 1 — the `test_smoke_e2e.py` docstring touch-up is a clean follow-up PR if the orchestrator wants to close WU-2A7.2).
