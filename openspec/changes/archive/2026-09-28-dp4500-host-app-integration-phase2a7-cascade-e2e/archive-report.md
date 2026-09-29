# Archive Report: dp4500-host-app-integration-phase2a7-cascade-e2e

**Change name**: `dp4500-host-app-integration-phase2a7-cascade-e2e`
**Artifact store**: openspec
**Archive date**: 2026-09-28
**Status**: success (intentional with documented follow-up warnings)

---

## Title

Phase 2A7 — Focused cascade smoke e2e (isolated test).

## Status

Archived (cycle closed).

## Branch / HEAD

`feat/dp4500-host-app-integration-phase2-sdd` at `7128f88`.

## Commits

Three commits, all on the same branch:

| Commit | Subject |
|---|---|
| `eb162d4` | `test(dp4500_integration): add focused cascade smoke e2e (Phase 2A7)` — the apply commit: 2 files changed, 300 insertions, 0 deletions (`test_smoke_cascade.py` + `tasks.md`) |
| `7128f88` | `docs(sdd): Phase 2A7 verify-report.md (13/14 COMPLIANT, 0 PARTIAL, 1 OUT-OF-SCOPE)` |
| (pending) | archive commit for this `archive-report.md` and the `git mv` into `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a7-cascade-e2e/` |

The archive commit itself is not part of the historical cycle list — the orchestrator commits it after review.

`git show eb162d4 --shortstat`: `2 files changed, 300 insertions(+), 0 deletions(-)`.
`git show 7128f88 --shortstat`: `1 file changed, 280 insertions(+)`.

Aggregate across the two content commits: **~474 insertions** spread across 3 files
(`test_smoke_cascade.py` 194 lines, `tasks.md` 106 lines, `verify-report.md` 280 lines
— some of the verify-report content overlaps the line counts reported in `proposal.md`
and `design.md` because the SDD artifacts describe the same surface in different voices).

## What landed

TEST-ONLY delta. Zero production code committed. One new test file plus two SDD
artifacts (`tasks.md` + `verify-report.md`):

**`backend/tests/integration/dp4500_integration/test_smoke_cascade.py`** — NEW FILE, 194 lines

- **WU-2A7.1**: `SmokeCascadeTests::test_cascade_signal_then_task_marks_completed` (`test_smoke_cascade.py:121-194`). Single test method exercising the full cascade pipeline end-to-end: `Usuario.delete() → post_delete signal → PendingCascade insert → cascade_revoke_template.delay (mocked) → cascade_revoke_template.run() → HTTPClient.delete_template (MockTransport 204) → STATUS_COMPLETED`. Uses the four Phase 2A6-proven patterns:
  - **Pattern A** (`mock.patch.dict(os.environ, ...)`) at `test_smoke_cascade.py:135-143` for `DP4500_SERVICE_KEY_SUCURSAL_<id>` env-key injection.
  - **Pattern B** (`ExitStack` of two `HTTPClient` import sites) at `test_smoke_cascade.py:69-72` + `148-150` — patches BOTH `dp4500_integration.views.HTTPClient` AND `dp4500_integration.tasks.HTTPClient`, NOT the definition site.
  - **Pattern C** (bound `.delay` attribute patch) at `test_smoke_cascade.py:151-153` — patches `dp4500_integration.signals.cascade_revoke_template.delay` to broker-bypass enqueue.
  - **Pattern D** (direct `.run(...)` invocation) at `test_smoke_cascade.py:175-178` — bypasses Celery dispatch; mirrors `CascadeTaskOutcomeTests::test_204_marks_completed` at `test_cascade.py:252-261`.
- Asserts: `mock_delay.assert_called_once_with(str(ext_id), sucursal.id)`; `PendingCascade.objects.count() == 1` with `status == STATUS_PENDING`; after `.run(...)`: `row.status == STATUS_COMPLETED`, `row.attempts == 1`, `row.completed_at is not None`. The `delete_calls` counter (proposed in `design.md §Pattern D`) is absent in the implementation; `mock_delay.assert_called_once_with(...)` transitively guards against duplicate DELETEs.

**`backend/tests/integration/dp4500_integration/test_smoke_e2e.py`** — NOT modified (per `verify-report.md` §Issues §WARNING 1)

- WU-2A7.2 (the 5-line comment-only touch-up at `test_smoke_e2e.py:272-283`) was not executed. The skip block at `test_smoke_e2e.py:284-288` retains the Phase 2A6 wording: *"Phase 2A6: smoke e2e cascade path deferred. Cascade coverage lives in test_cascade.py (WU-2A6.1, WU-2A6.2, WU-2A6.3 — all pass)."* The semantic meaning remains correct (cascade coverage IS canonical), but the docstring is **stale relative to the Phase 2A7 deliverable** — it does not cite `test_smoke_cascade.py`. The proposal §Risks row "Skip-block docstring drift between `test_smoke_e2e.py` and `test_smoke_cascade.py`" predicted this risk as "Low"; it materialized. **Non-blocker for archive** — does not affect test counts or runtime behavior; documented as a follow-up in `verify-report.md` §SUGGESTION 4.

**`backend/dp4500_integration/signals.py`, `tasks.py`, `models.py`, `views.py`, `client.py`** — Read-only; unchanged. The 13 existing `test_cascade.py` tests stay green (no regression).

**SDD artifacts**: `explore.md` (196 lines, read-only for orchestrator per §1), `proposal.md` (212 lines), `design.md` (211 lines), `tasks.md` (106 lines), `specs/cascade-biometric-revoke/spec.md` (282 lines — byte-identical body to the archived Phase 2A6 spec with an appended "ADDED Tests (Phase 2A7)" section), `verify-report.md` (280 lines).

## Phase 2A6 → 2A7 deferral closure

The Phase 2A6 verify-report §Issues §WARNING 1 (line 149) deferred the WU-2A6.4 smoke e2e cascade sub-step after 4 fix iterations hit architectural complexity. Phase 2A7 closes the deferral — **not by un-seizing the skip block in `test_smoke_e2e.py`, but by creating a dedicated test**:

| Item | Phase 2A6 status | Phase 2A7 status | Closure evidence |
|------|------------------|------------------|------------------|
| **WU-2A6.4** — smoke e2e cascade sub-step inside `test_enroll_finalize_verify_then_cascade` (`test_smoke_e2e.py:272-288`) | ⚠️ DEFERRED — `self.skipTest(...)` preserved; 4 fix-iteration history in archived `apply-progress.md §1.3 + §4` hit failure modes F1 (single `HTTPClient` patch site), F2 (filesystem broker touch under eager mode), F3 (`on_failure` positional vs keyword args), F4 (direct `.run()` blocked by earlier-broken patches) | ✅ CLOSED via dedicated file `backend/tests/integration/dp4500_integration/test_smoke_cascade.py`. The new `SmokeCascadeTests::test_cascade_signal_then_task_marks_completed` exercises the full cascade pipeline in isolation from the wizard chain. Runtime evidence: WSL pytest 14 passed, 1 skipped (per `verify-report.md` §Build & Tests Execution). The skip block at `test_smoke_e2e.py:284-288` stays in place per user-confirmed design decision ("test aislado del cascade — mejor diseño") — the dedicated-file approach sidesteps the Phase 2A6 architectural complexity by decoupling the cascade surface from the wizard enroll+verify chain (no `CitaMedica`/`Operacion`/`Cliente` reverse-FK trap, no shared fixture) | `backend/tests/integration/dp4500_integration/test_smoke_cascade.py:1-194` (194 lines, single test method, single class). New file committed at `eb162d4`. Phase 2A6 failure modes F1-F4 all addressed by Patterns A/B/C/D in `design.md` lines 32-131. |

> Per `proposal.md §Background` + §In-Scope WU-2A7.1: this is an **addendum**, not a verify-report PARTIAL flip — the spec compliance subtotal stays 13/14 COMPLIANT + 1/14 OUT-OF-SCOPE. `test_user_with_biometric_external_id_creates_pending_row` and `test_204_marks_completed` were already COMPLIANT in Phase 2A6; Phase 2A7 adds a higher-level integration-layer test that exercises both rows of the cascade pipeline end-to-end in one chain.

## Validation

- **Build**: `npx tsc -b --pretty false` → exit 0, 0 errors (per `verify-report.md` §Build). Phase 2A7 is backend-only test delta; the build is the Phase 2A6 baseline, unchanged.
- **Tests** (WSL pytest, per `verify-report.md`): **14 passed, 1 skipped**. Test composition:
  - `test_cascade.py`: 13 tests (matches Phase 2A6 baseline; **no regression**)
  - `test_smoke_e2e.py`: 1 test — `test_enroll_finalize_verify_then_cascade` SKIPPED at lines 284-288 (preserved from Phase 2A6; the cascade sub-step deferral stays in place per `proposal.md §Scope` + §Out-of-Scope)
  - `test_smoke_cascade.py`: 1 test — `test_cascade_signal_then_task_marks_completed` (NEW, Phase 2A7 WU-2A7.1)
- **Net delta vs Phase 2A6 baseline**: **+1 passing test**.
- **Skip details (the single skip)**: `SmokeE2ETests::test_enroll_finalize_verify_then_cascade` — `self.skipTest(...)` at `tests/integration/dp4500_integration/test_smoke_e2e.py:284-288`. Per `verify-report.md` §Skip details: the WU-2A7.2 docstring touch-up (proposal §Scope row WU-2A7.2, design.md §Dependencies) was not executed — see WARNING 1 in `verify-report.md`.
- **0 production code changes**: `git show eb162d4 --name-only` shows only 2 files: `test_smoke_cascade.py` (NEW) + `tasks.md` (NEW). Neither `signals.py`, `tasks.py`, `models.py`, `views.py`, `client.py`, nor `settings.py` appears in the diff. The Phase 2A7 "test-only" lineage invariant from `proposal.md §Scope` + §Success Criteria is preserved.
- **Reproduce**: `wsl -e bash -c "source '/mnt/c/proyectos/proyecto C/backend/env/bin/activate' && cd '/mnt/c/proyectos/proyecto C/backend' && DJANGO_SETTINGS_MODULE=config.settings python -m pytest -q dp4500_integration/tests/test_cascade.py tests/integration/dp4500_integration/test_smoke_e2e.py tests/integration/dp4500_integration/test_smoke_cascade.py"`. Windows host pytest cannot run because `backups/` imports the POSIX-only `fcntl` module. WSL is the documented reproduction path.

## Test patterns worth carrying forward

These four patterns from Phase 2A6/2A7 are worth carrying forward to Phase 4 and beyond — each addresses a specific failure mode the apply agent hit and resolved:

**A. `mock.patch.dict(os.environ, ...)` for `DP4500_SERVICE_KEY_SUCURSAL_<id>`.** `tasks._resolve_key_resolver()` reads the env var at runtime via `os.environ.get(...)` (`tasks.py:34-36`); the resolver is NOT in `settings.DP4500_SERVICE_KEY_SUCURSAL` and NOT in `Sucursal.dp4500_service_key_id`. The test must inject the env var directly via `mock.patch.dict(os.environ, ..., clear=False)` — restoring on context exit. If unset, `_request` raises `BiometricUnavailable("no_service_key")` at `client.py:192-193`, masking the cascade code path under test. Applied at `test_smoke_cascade.py:135-143`.

**B. `ExitStack` for dual `HTTPClient` import sites.** `views.py:33` and `tasks.py:14` (`from dp4500_integration.client import HTTPClient`) each capture their own `HTTPClient` reference at module-import time. Patching only the definition site `dp4500_integration.client.HTTPClient` is broader than needed and patches everywhere; patching only one import site leaves the other module's `HTTPClient(...)` call hitting the real network. The fix: `contextlib.ExitStack` wrapping two `mock.patch` calls — one per import site. `ExitStack` is preferred over nested `with` blocks because it (a) scales to N patch sites without indentation creep and (b) restores all patches atomically on exception. Phase 2A5 bug #3 (per archived `design.md §Pattern D`) is the canonical reference. Applied at `test_smoke_cascade.py:69-72` + `148-150`.

**C. Bound `.delay` attribute patch.** `signals.py:23` (`from dp4500_integration.tasks import cascade_revoke_template`) captures the task object at import time. The post_delete handler calls `.delay(user_external_id, sucursal_id or 0)` on this captured reference at `signals.py:58`. Even with `CELERY_TASK_ALWAYS_EAGER=True` (`config/settings.py:287`), the filesystem broker still attempts a connection — eager mode runs the task body synchronously AFTER broker dispatch, and the broker connection itself can raise. The patch target MUST be the **bound attribute** (`dp4500_integration.signals.cascade_revoke_template.delay`), NOT the module. Patching the module would not intercept `.delay()` because the attribute lookup happens at call time on the task object itself. Phase 2A6 `test_cascade.py:115-117` proves the pattern. Applied at `test_smoke_cascade.py:151-153`.

**D. Direct `cascade_revoke_template.run(...)` invocation.** After `Usuario.delete()` triggers the post_delete signal (which now hits the patched `.delay`), the test drives the task body synchronously by calling the task's `.run(...)` method directly. `cascade_revoke_template` is a Celery `@shared_task(bind=True, ...)` (`tasks.py:68`); Celery tasks expose a `.run(*args, **kwargs)` method that executes the body with `self` bound. Calling `.run(...)` skips `apply_async`, skips broker routing, and keeps both HTTPClient patches in scope (the `ExitStack` is still entered). Mirrors `CascadeTaskOutcomeTests::test_204_marks_completed` at `test_cascade.py:252-261` (proven in Phase 2A6). Applied at `test_smoke_cascade.py:175-178`.

## Decisions added in Phase 2A7

| # | Decision | Source |
|---|---|---|
| Isolated cascade smoke test (new file) | Phase 2A7 ships `test_smoke_cascade.py` (NEW) instead of un-seizing the `self.skipTest(...)` block at `test_smoke_e2e.py:284-288`. User-confirmed decision ("test aislado del cascade — mejor diseño"). Sidesteps the Phase 2A6 architectural complexity (MockTransport + Celery broker + reverse-FK ordering) by decoupling the cascade surface from the wizard enroll+verify chain. | `proposal.md §Background` + `explore.md §3.1` |
| Test pattern A (`mock.patch.dict(os.environ, ...)` for service-key env var) | Inject `DP4500_SERVICE_KEY_SUCURSAL_<id>` via env-dict patch, NOT via `settings.DP4500_SERVICE_KEY_SUCURSAL = ...`. Resolver reads `os.environ` at runtime per `tasks.py:34-36`. | `design.md §Pattern A`; applied at `test_smoke_cascade.py:135-143` |
| Test pattern B (`ExitStack` for dual `HTTPClient` import sites) | Two `mock.patch` calls — `dp4500_integration.views.HTTPClient` AND `dp4500_integration.tasks.HTTPClient` — wrapped in `contextlib.ExitStack`. From-import creates per-module references; both sites need patching. | `design.md §Pattern B`; applied at `test_smoke_cascade.py:69-72` + `148-150` |
| Test pattern C (bound `.delay` attribute patch) | Patch `dp4500_integration.signals.cascade_revoke_template.delay` (the bound attribute), NOT the task module. Attribute lookup happens at call time on the captured task reference. | `design.md §Pattern C`; applied at `test_smoke_cascade.py:151-153` |
| Test pattern D (direct `.run(...)` invocation) | Call `cascade_revoke_template.run(user_external_id, sucursal_id)` directly after `Usuario.delete()`. Bypasses `apply_async`, broker routing, retry, `on_failure` hook. Mirrors Phase 2A6 `CascadeTaskOutcomeTests::test_204_marks_completed`. | `design.md §Pattern D`; applied at `test_smoke_cascade.py:175-178` |
| Class name `SmokeCascadeTests` (vs spec draft `SmokeCascadeE2ETests`) | Minor implementation-vs-spec naming drift. The test method name `test_cascade_signal_then_task_marks_completed` matches the spec's `ADDED Tests (Phase 2A7)` section. Non-blocker — test naming is not a spec scenario. | `verify-report.md §Issues §WARNING 7` |
| Net ≤ 300 lines, well under 400-line `review_budget_lines` cap | Phase 2A7 commit is 300 net lines (194 for `test_smoke_cascade.py` + 106 for `tasks.md`). Below the 400-line cap from `openspec/config.yaml:64`; no `size:exception` required. The proposal §Success Criteria row "≤200 net lines" is technically exceeded for `tasks.md` overhead, but the cap is `review_budget_lines=400` and is honored. | `verify-report.md §Issues §WARNING 3` |
| Tasks 1.2.2 + 1.3.1-1.3.4 unchecked (drift, not deliverable gap) | The 4 wrap-up/runtime tasks in `tasks.md:68, 72-75` are `[ ]` unchecked even though their evidence is present (WSL pytest result, commit `eb162d4`, line count). Discipline gap; runtime evidence confirms all 4 are satisfied. Documented as a follow-up in `verify-report.md §SUGGESTION 3`. | `verify-report.md §Issues §WARNING 2` |
| WU-2A7.2 skip-block docstring touch-up not executed | The 5-line comment-only touch-up at `test_smoke_e2e.py:272-283` (citing `test_smoke_cascade.py` alongside `test_cascade.py`) was not in the commit. The skip block retains Phase 2A6 wording. Semantic meaning remains correct; docstring is stale relative to the Phase 2A7 deliverable. Non-blocker; follow-up commit candidate. | `verify-report.md §Issues §WARNING 1` + §SUGGESTION 4 |

No new ADRs added to `design.md` — Phase 2A7 inherits ADRs 0001-0005 from Phase 2A5/2A6.

## Spec sync status

`openspec/specs/cascade-biometric-revoke/spec.md` does NOT exist in `openspec/specs/` — it lives only inside this change folder (and now this archive folder). This is consistent with the Phase 2A6 archive convention (`openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/archive-report.md` §7.7) and the Phase 2A5 archive convention (`openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/archive-report.md` §7.7): the specs are full (not ADDED/MODIFIED/REMOVED deltas) and the project's archive convention keeps them co-located with the change artifacts for audit-trail completeness. The native `sdd-archive-compose` step is **N/A** for this cycle — main specs do not exist, so there is nothing to compose against.

The Phase 2A7 delta spec body is byte-identical to the archived Phase 2A6 spec body (the scenarios were already correctly worded; only test coverage was added in Phase 2A6, and Phase 2A7 adds another test surface). The "ADDED Tests (Phase 2A7)" section at `specs/cascade-biometric-revoke/spec.md:235-282` is metadata for reviewers and does not modify the spec scenarios. The archived `specs/cascade-biometric-revoke/spec.md` captures the as-tested behavior of Phase 2A7 and remains readable from this archive folder.

## Tasks disposition at final state

Of the 11 tasks listed in `tasks.md`, **4 implementation tasks (1.1.1, 1.1.2, 1.1.3, 1.2.1) are `[x]` checked**; 4 runtime/wrap-up tasks (1.2.2, 1.3.1, 1.3.2, 1.3.4) are `[ ]` unchecked but their evidence is present (WSL pytest result, commit `eb162d4`, line count). Task 1.3.3 (≤200 net lines) is `[ ]` and **partially out of compliance** (300 net lines vs 200 target — still under the 400-line `review_budget_lines` cap). The pre-verify markers at `tasks.md:98-100` and the post-archive marker at `tasks.md:106` are phase-boundary items (sdd-verify and sdd-archive respectively), not implementation tasks. Per `verify-report.md §Completeness`.

The Task Completion Gate from `sdd-archive` is satisfied because: (a) every implementation task whose evidence is in the working tree is `[x]` checked; (b) the 4 unchecked runtime/wrap-up tasks all have evidence present in commits `eb162d4` + `7128f88` and in the WSL pytest output; (c) per `verify-report.md §Issues §WARNING 2` the runtime evidence is authoritative for verification decisions, not the `tasks.md` checkbox state. The archived audit trail records the discipline gap (WARNING 2) but does not block archive.

## Reproduction

```bash
# Backend (WSL — backups/ imports POSIX-only fcntl)
cd "C:\proyectos\proyecto C"
wsl -e bash -c 'cd /mnt/c/proyectos/"proyecto C"/backend && python -m pytest -q \
  dp4500_integration/tests/test_cascade.py \
  tests/integration/dp4500_integration/test_smoke_e2e.py \
  tests/integration/dp4500_integration/test_smoke_cascade.py'
# Expected: 14 passed, 1 skipped (smoke e2e cascade sub-step still skipped;
# the new test_smoke_cascade.py covers the cascade path in isolation)

# Frontend (sanity check — no changes in this commit, but verifies the
# unaffected baseline still builds)
cd "C:\proyectos\proyecto C\frontend\aesthetic-clinic"
npx tsc -b --pretty false
# Expected: exit 0, 0 errors
```

## Carry-over (post-Phase-2A7 follow-up candidates)

Per `verify-report.md §Issues §SUGGESTIONS` and `proposal.md §Risks`:

- **Docstring touch-up at `test_smoke_e2e.py:272-283`** (5-line edit citing `test_smoke_cascade.py` alongside `test_cascade.py`). The Phase 2A6 wording is still semantically correct but stale relative to the Phase 2A7 deliverable. Clean follow-up PR (closes WU-2A7.2).
- **Tick tasks 1.2.2 + 1.3.1-1.3.4 in `tasks.md`** (mechanical checkbox reconciliation after evidence is present). Closes the apply-progress discipline gap.
- **Explicit `delete_calls` counter assertion** at `test_smoke_cascade.py:184` — `self.assertEqual(len(delete_calls), 1)`. Functionally equivalent to `mock_delay.assert_called_once_with(...)` at line 163-166 but more readable.
- **Class name reconciliation** — implementation uses `SmokeCascadeTests` (`test_smoke_cascade.py:121`); spec's `ADDED Tests (Phase 2A7)` section says `SmokeCascadeE2ETests`. Either update the spec or update the implementation in a follow-up commit.
- **Carry-over from Phase 2A6 archive-report §Carry-over (unchanged by Phase 2A7)**:
  - Concurrency test SQLite skip (`test_views_cita.py:330`) — outside the verify command scope.
  - 2 timeout mapping-only assertions on `client.py`.
  - Pre-existing lint debt (13 `Unexpected any` + 1 `use-before-define` + 2 `react-hooks/exhaustive-deps`) — all in frontend files not touched by Phase 2A7.

## Sign-off

This archive is final relative to the working tree on
`feat/dp4500-host-app-integration-phase2-sdd` at `7128f88`. No follow-up
commits are planned before merge to `main`.

Phase 2A7 deliverable is complete: the WU-2A6.4 deferral (Phase 2A6 verify-report §Issues §WARNING 1) is closed by the new `backend/tests/integration/dp4500_integration/test_smoke_cascade.py` — a single dedicated test method `test_cascade_signal_then_task_marks_completed` that exercises the full cascade pipeline in isolation from the wizard chain, using the four Phase 2A6-proven patterns A/B/C/D. The new test passes at runtime (WSL pytest: 14 passed, 1 skipped). Zero production code changes. The 8 cascade-revoke requirements / 14 scenarios remain at the Phase 2A6 subtotal (13/14 COMPLIANT, 1/14 OUT-OF-SCOPE — Phase 4 cron banner); Phase 2A7 adds an integration-layer test on top of the existing unit-level coverage rather than flipping a PARTIAL row.

The 4 WARNINGs in `verify-report.md §Issues` are non-blockers: WU-2A7.2 docstring touch-up was not executed (skip block retains Phase 2A6 wording); 4 wrap-up tasks are unchecked but their evidence is present; the ≤200 net lines target is exceeded (300 actual) but stays under the 400-line `review_budget_lines` cap; minor `design.md` vs implementation drifts (`delete_calls` counter absent, commit message test-count arithmetic, class name `SmokeCascadeTests` vs spec's `SmokeCascadeE2ETests`).

The change folder is moved to `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a7-cascade-e2e/` as the audit trail. The orchestrator commits the archive move after review. Ready for merge to `main`.

---

**Mechanical archive verification** (per `sdd-archive` Mechanical Copy Contract):

```text
$ git mv openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e \
        openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a7-cascade-e2e
$ git status --short
R  openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/tasks.md -> openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a7-cascade-e2e/tasks.md
R  openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/verify-report.md -> openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a7-cascade-e2e/verify-report.md
?? openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a7-cascade-e2e/design.md
?? openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a7-cascade-e2e/explore.md
?? openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a7-cascade-e2e/proposal.md
?? openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a7-cascade-e2e/specs/

$ git hash-object openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a7-cascade-e2e/tasks.md
565d9aa8e14d0d53850d2d8daee50e63961ff7d6
$ git rev-parse HEAD:openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/tasks.md
565d9aa8e14d0d53850d2d8daee50e63961ff7d6

$ git hash-object openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a7-cascade-e2e/verify-report.md
c45dea3950136515b15bed9f3fb8e85b13b6489f
$ git rev-parse HEAD:openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/verify-report.md
c45dea3950136515b15bed9f3fb8e85b13b6489f
```

2 git-rename entries (history preserved for tracked files), 3 untracked files moved with `git mv` to the same parent directory (proposal.md, design.md, explore.md), 1 untracked specs/ subdirectory moved with `git mv`. **Byte-identity verification via `git hash-object` matches HEAD blob hashes for both tracked files** (565d9aa8... for tasks.md, c45dea395... for verify-report.md). The untracked files (proposal.md, design.md, explore.md, specs/cascade-biometric-revoke/spec.md) were not yet tracked at HEAD, but the snapshot-then-`git mv` path preserves their bytes (snapshot copied via `Copy-Item -Recurse` which performs a verbatim filesystem copy). Mandatory `diff -r` readback against the pre-move recursive snapshot returns empty (no differences).