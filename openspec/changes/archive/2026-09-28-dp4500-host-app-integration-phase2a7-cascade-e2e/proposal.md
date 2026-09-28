# Proposal: Phase 2A7 — Cascade smoke e2e (focused test isolated from the wizard smoke)

**Change name**: `dp4500-host-app-integration-phase2a7-cascade-e2e`
**Artifact store**: openspec
**Branch**: `feat/dp4500-host-app-integration-phase2-sdd` (no branch switch)
**Predecessor**: Phase 2A6 — `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/`

## Status

Draft (will be locked after `sdd-tasks` completes).

## Background / Context

Phase 2A6 archived on 2026-09-28 with verdict `pass_with_warnings` and
closed **3 of 4** cascade-revoke gaps on `specs/cascade-biometric-revoke`
(see `verify-report.md:115` — "13/14 COMPLIANT, 0/14 PARTIAL, 1/14
OUT-OF-SCOPE"). The 4th item — **the smoke e2e cascade step inside
`test_enroll_finalize_verify_then_cascade`** — was **deferred to
Phase 2A7** after the apply agent hit 4 fix-iteration failures in the
existing chain (`verify-report.md` §Issues §WARNING 1, line 149; full
history in `apply-progress.md` §1.3 + §4).

The 4 Phase 2A6 failure modes (root cause of the deferral — recorded as
"why we deferred", NOT as forward-looking risk):

| # | Failure mode | Root cause | Resolution needed |
|---|---|---|---|
| **F1** | Patch at `client.HTTPClient` left `views.HTTPClient` and `tasks.HTTPClient` reaching the real network. | `views.py` and `tasks.py` capture their own `HTTPClient` reference at import time (per `tasks.py:14` import statement). Each module's reference is independent. | Patch **both** import sites — `dp4500_integration.tasks.HTTPClient` AND `dp4500_integration.views.HTTPClient` — wrapped in `contextlib.ExitStack`. |
| **F2** | `.delay()` still touched the Celery filesystem broker under `CELERY_TASK_ALWAYS_EAGER=True`. | `settings.py:287` enables eager mode but the filesystem broker still attempts a connection. | Patch the **bound attribute** `dp4500_integration.signals.cascade_revoke_template.delay` (captured at `signals.py:23`) instead of the task module. |
| **F3** | `_cascade_revoke_template_on_failure` positional/keyword signature mismatch (`TypeError: takes 5 positional arguments but 6`). | Hook signature at `tasks.py:113` is `def _cascade_revoke_template_on_failure(self, exc, task_id, args, kwargs, einfo)` — positional, NOT keyword. | Not relevant to Phase 2A7 (happy path only; no `on_failure` hook exercised). Documented for future Phase 4 work. |
| **F4** | Inline `cascade_revoke_template.run(...)` was skipped because earlier patches were still broken. | The smoke chain's `_patch_dp4500_handler` only patches the verify view's `views.HTTPClient`; the cascade task imports `tasks.HTTPClient` separately. | After `Usuario.delete()` triggers the signal, call `cascade_revoke_template.run(str(ext_id), sucursal_id)` **directly** with both HTTPClient import sites still patched, mirroring `CascadeTaskOutcomeTests::test_204_marks_completed` at `test_cascade.py:252-261`. |

The user's confirmed decision (per the orchestrator prompt that launched
this change): **"test aislado del cascade (mejor diseño)"**. Phase 2A7
**splits** the cascade end-to-end coverage out of the wizard smoke:

- `test_smoke_e2e.py::test_enroll_finalize_verify_then_cascade` stays
  reduced — the cascade sub-step at lines 272–288 keeps its
  `self.skipTest(...)` block (with an updated docstring noting the new
  canonical coverage location).
- A **new dedicated file** `backend/tests/integration/dp4500_integration/test_smoke_cascade.py`
  exercises the cascade signal + Celery task end-to-end using the proven
  ExitStack + direct `.run()` patterns from Phase 2A6, with an
  **ORM-driven fixture** (not wizard-driven).

This change is the **Phase 2A6 §WARNING 1 addendum closure** — it does
NOT flip a PARTIAL row on the verify-report (there are no PARTIAL rows
remaining on cascade-revoke). The 13/14 cascade-revoke COMPLIANT
subtotal stays; Phase 2A7 adds end-to-end wiring coverage that
`test_cascade.py` provides only at the unit level.

## Scope

**TEST-ONLY — no production code changes.** Same lineage invariant as
Phase 2A6 (`apply-progress.md` §1.4 + `verify-report.md:123`).

### In Scope

| WU | Concern | File | Deliverable | Net lines |
|----|---------|------|-------------|-----------|
| **WU-2A7.1** | New focused cascade smoke test | `backend/tests/integration/dp4500_integration/test_smoke_cascade.py` (**NEW FILE**) | `SmokeCascadeTests::test_user_delete_triggers_cascade_to_completed` — ORM-driven fixture (no wizard), ExitStack of `views.HTTPClient` + `tasks.HTTPClient` patches, `httpx.MockTransport` returning 204 on `DELETE /service/templates/<ext_id>/`, `signals.cascade_revoke_template.delay` patched at the bound attribute, then direct `cascade_revoke_template.run(str(ext_id), branch.id)` invocation. Asserts: `mock_delay.assert_called_once_with(str(ext_id), branch.id)`; after `.run(...)`: `row.status == STATUS_COMPLETED`, `row.completed_at is not None`, `row.attempts == 1`, `row.last_error_code == ""`; exactly 1 DELETE to `/service/templates/<ext_id>/`. | ~120 |
| **WU-2A7.2** | Update skip-block docstring | `backend/tests/integration/dp4500_integration/test_smoke_e2e.py:272-288` | Touch up the comment block above the `self.skipTest(...)` to record that `test_smoke_cascade.py` (Phase 2A7 WU-2A7.1) is now the canonical end-to-end cascade coverage alongside `test_cascade.py`. The `self.skipTest(...)` body itself and the cascade-skip count stay unchanged. | ~5 |
| **WU-2A7.3** | Verify all tests pass on WSL | n/a (test_command runs the suite) | Run `python -m pytest backend/tests/integration/dp4500_integration/test_smoke_cascade.py backend/dp4500_integration/tests/test_cascade.py backend/tests/integration/dp4500_integration/test_smoke_e2e.py` on WSL | 0 |

**Total: ≤200 net lines of new test code.** Well under the 400-line
`review_budget_lines` cap in `openspec/config.yaml:64`. No `size:exception`
required.

### Out of Scope

- **Production behavior changes** — no edits to `signals.py`, `tasks.py`,
  `models.py`, `views.py`, or `client.py`. Implementation is correct
  per Phase 2A6 lineage.
- **New endpoints, new signal handlers, new Celery tasks** — Phase 2A7
  is a test-only patch.
- **Extending `test_smoke_e2e.py` with cascade logic** — the smoke chain
  stays reduced; the cascade sub-step remains skipped. Adding cascade
  logic inside the wizard chain would re-trigger F1–F4.
- **Adding tests to `test_cascade.py`** — the 13 existing tests there
  are the canonical unit-level cascade coverage and must not regress.
  Phase 2A7's new file is additive only.
- **Removing the `self.skipTest(...)` in `test_smoke_e2e.py:284-288`** —
  the skip stays. Only the comment above it (lines 272–283) gets a
  docstring update.
- **Migration generation** — no schema changes.
- **Phase 4 cron-driven alert banner** — pre-existing OUT-OF-SCOPE
  scenario (`verify-report.md:109`); not Phase 2A7 work.
- **Refactoring `signals.py:41-55` try/except into a narrower scope** —
  the existing single-`try/except` design stays as-is.
- **Replacing `PendingCascade` model fields or types** — model untouched.
- **Coverage tooling** (`coverage.py --include=dp4500_integration/*`) —
  not part of this verify command set; consistent with Phase 2A6
  (`verify-report.md:90`).
- **`DP4500_BASE_URL` default fix** (`settings.py:292`, committed at
  `6c5d29d`) — already in place; not relevant to a `MockTransport`-based
  test. Documented in `explore.md` §6 for future Phase 4 live-integration
  work only.
- **WSL gateway IP (`172.20.176.1`) cross-host HTTP** — same:
  `MockTransport` makes it irrelevant; documented for Phase 4 only.

## Affected Components

| Area | Impact | Description |
|------|--------|-------------|
| `backend/tests/integration/dp4500_integration/test_smoke_cascade.py` | **NEW FILE** (~120 net lines) | The only new file in Phase 2A7. Single `TestCase` class `SmokeCascadeTests` with one test method `test_user_delete_triggers_cascade_to_completed`. Module-level helper `_patch_dp4500_handler(handler)` mirrors `test_smoke_e2e.py:48-67` but adapted for the cascade surface (DELETE-only handler, not DELETE+POST+GET). |
| `backend/tests/integration/dp4500_integration/test_smoke_e2e.py` | **Modified (comment-only, ~5 lines)** | Lines 272–283 comment block updated to cite `test_smoke_cascade.py` as the canonical end-to-end cascade coverage alongside `test_cascade.py`. The `self.skipTest(...)` body (lines 284–288) and the surrounding test method are NOT touched. |
| `backend/dp4500_integration/tests/test_cascade.py` | Read-only | Existing 13 tests are the canonical unit-level coverage for cascade-revoke. Reused as the reference for the new test's ExitStack + direct `.run()` patterns (mirror `CascadeSignalTests` + `CascadeTaskOutcomeTests`). |
| `backend/dp4500_integration/signals.py` | Read-only | `cascade_revoke_on_user_delete` signal flow at lines 23–66 is the surface under test. Patched at the bound `.delay` attribute per Pattern C in `explore.md` §3.2. |
| `backend/dp4500_integration/tasks.py` | Read-only | `cascade_revoke_template` task body at lines 39–132 is the surface under test. `HTTPClient` import at line 14 is one of the two ExitStack patch targets per Pattern B in `explore.md` §3.2. |
| `backend/dp4500_integration/client.py` | Read-only | `HTTPClient` is the canonical definition site, but NOT a patch target. Patching `client.HTTPClient` would be broader than needed (Pattern B failure mode F1) — only `views.HTTPClient` and `tasks.HTTPClient` import sites get patched. |
| `backend/tests/integration/dp4500_integration/test_smoke_e2e.py:48-67` (`_patch_dp4500_handler`) | Reused as reference | The new file's helper mirrors this one's structure, adapted for DELETE-only. Not imported — duplicated in form because the new test owns its own handler. |

## Open questions

None. The explore phase (`explore.md` §3 + §5) resolved all design
questions:

- **Where to put the new test** — `backend/tests/integration/dp4500_integration/test_smoke_cascade.py`
  (new file, not extension of `test_smoke_e2e.py`). Rationale: F1–F4 are
  reproducible only if the cascade surface shares pytest fixtures with the
  wizard chain. Isolation is the cleanest fix (`explore.md` §3.1).
- **How to drive the task body** — direct `cascade_revoke_template.run(str(ext_id), branch.id)`
  after `Usuario.delete()`, mirroring `CascadeTaskOutcomeTests::test_204_marks_completed`
  at `test_cascade.py:252-261`. Confirmed working by Phase 2A6.
- **How to patch `HTTPClient`** — `contextlib.ExitStack` with two
  `mock.patch` calls: `dp4500_integration.tasks.HTTPClient` and
  `dp4500_integration.views.HTTPClient`. Proven by Phase 2A6
  (`apply-progress.md` §4 + `design.md` §Pattern D warn).
- **How to patch `.delay()`** — bound attribute
  `dp4500_integration.signals.cascade_revoke_template.delay`. Proven by
  Phase 2A6 (`test_cascade.py:116-117` + `apply-progress.md` §4).
- **How to bypass the wizard chain** — direct ORM fixture: create
  `Usuario` via `Usuario.objects.create_user(...)` with
  `biometric_external_id=uuid.uuid4()`, then a separate
  `PendingCascade.objects.create(...)` is NOT pre-created (the signal
  creates it as the test's first assertion). The wizard's
  `enroll → finalize` flow is orthogonal to the cascade surface.
- **Fixture FK ordering** — no FK dependents (the new `Usuario` has zero
  related rows), matching `test_cascade.py:32-110` existing fixture
  style. The reverse-FK ordering failure F3 was specific to the wizard
  chain's `_build_smoke_graph`; it does not apply here.

## Rollback plan

Pure test additions — rollback is `git revert` of the single commit. No
DB migration, no API contract change, no Celery schedule, no signal
listener. Reverting the PR removes:

- The new file `backend/tests/integration/dp4500_integration/test_smoke_cascade.py`
- The comment-only touch-up at `test_smoke_e2e.py:272-283` (reverts to
  Phase 2A6 wording, which is still semantically correct — it just
  doesn't mention the new file)
- The Phase 2A7 `archive-report.md` addendum noting the cascade end-to-end
  coverage closure

After `git revert`, the test suite returns to the Phase 2A6 baseline:
13 passed + 1 skipped in the verify command (per `verify-report.md:82`).
No production behavior is observably different to a deployed clinic.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Re-triggering F1 (only one `HTTPClient` patch site) | Low | Pattern B in `explore.md` §3.2 is explicit: two `mock.patch` calls wrapped in `ExitStack`. Apply agent MUST cite `views.py` and `tasks.py:14` import lines in the test source comment. |
| Re-triggering F2 (filesystem broker touch under eager mode) | Low | Pattern C: patch the bound attribute `dp4500_integration.signals.cascade_revoke_template.delay`, not the task module. Phase 2A6 already validates this at `test_cascade.py:116-117`. |
| Re-triggering F3 (positional vs keyword `on_failure` hook) | None | Not exercised in Phase 2A7 (happy path only — no `on_failure` invocation). Documented in `explore.md` §5.2 row F3 for future Phase 4 work. |
| Re-triggering F4 (skipped `.run()` because earlier patches broken) | Low | Pattern D: the test structure puts `.run(...)` AFTER `Usuario.delete()`, with both HTTPClient patches still in scope (ExitStack is still entered). Mirrors `CascadeTaskOutcomeTests::test_204_marks_completed` at `test_cascade.py:252-261`. |
| Test count growth (cascade-revoke coverage: 13 → 14 named tests) | Low | +1 passing test on WSL pytest; well below CI noise threshold. No CLAUDE.md or CI file edits needed. |
| Docstring-only edit at `test_smoke_e2e.py:272-283` accidentally removes the `self.skipTest(...)` body | Low | The proposal explicitly scopes the edit to the comment block (lines 272–283). Lines 284–288 (the skip body) are NOT touched. Apply agent MUST NOT collapse or replace lines 284–288. |
| Phase 2A7 net lines exceed 200 (proposed) and breach the 400-line review budget | Low | The 200-line proposed budget already includes the module docstring + import block + helper + class docstring + `setUp` + the test method + assertions. `explore.md` §5.3 targets 80–120 net lines — well within budget. Apply agent MUST NOT add multi-line narrative comments beyond what's in the explore template. |
| `Usuario.delete()` cascade side effects (CitaMedica PROTECT, BiometricAttempt SET_NULL) | Low | The new `Usuario` has zero FK dependents (mirroring `CascadeSignalTests.setUp` at `test_cascade.py:32-110`). The deletion is intentional and idiomatic. If the FK constraints tighten in Phase 2A8+, the test's `setUp` may need adjustment — but no production-code change is in Phase 2A7 scope. |
| Skip-block docstring drift between `test_smoke_e2e.py` and `test_smoke_cascade.py` | Low | Both cite the same canonical location: `test_cascade.py` (WU-2A6.1/2/3, unit-level) + `test_smoke_cascade.py` (Phase 2A7 WU-2A7.1, end-to-end). The same 2-way split rationale is documented in `explore.md` §3.1. |
| Phase 2A6 archive-report edits | None | The new `archive-report.md` lives at `openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/archive-report.md`. The Phase 2A6 archive (`.../archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/`) is **not** touched. |

## Dependencies

- **None.** Phase 2A7 is a test-only patch on already-shipped production
  code (Phase 2A5 → Phase 2A6 lineage).
- Existing fixtures + helper functions in `test_cascade.py` are reused
  as **reference patterns** (not imported). The new file is
  self-contained.
- `httpx.MockTransport`, `contextlib.ExitStack`, `unittest.mock.patch`,
  `django.test.TestCase`, and the Celery `cascade_revoke_template`
  task are all already in the dependency tree (no `requirements.txt`
  changes).
- The `DP4500_BASE_URL` default fix at `config/settings.py:292` is
  already committed at `6c5d29d` on the working branch — not a
  dependency, just a precondition noted in `explore.md` §6.

## Success Criteria

Phase 2A7 is complete when:

- [ ] `python -m pytest backend/tests/integration/dp4500_integration/test_smoke_cascade.py` exits 0 on WSL with the new test passing.
- [ ] `python -m pytest backend/dp4500_integration/tests/test_cascade.py backend/tests/integration/dp4500_integration/test_smoke_e2e.py` continues to exit 0 on WSL (13 passed + 1 skipped, no regressions).
- [ ] Total changed lines for this change ≤ 200 net (well under the 400-line `review_budget_lines` cap in `openspec/config.yaml:64`).
- [ ] `git diff --stat` shows zero production-code files (`signals.py`, `tasks.py`, `models.py`, `views.py`, `client.py`) in the diff. The only changes are the new `test_smoke_cascade.py` file + the comment-only touch-up in `test_smoke_e2e.py`.
- [ ] The new test `test_user_delete_triggers_cascade_to_completed` asserts all 4 behaviors from `explore.md` §3.3: PendingCascade row exists with `STATUS_PENDING`, `signals.cascade_revoke_template.delay` called exactly once with `(str(ext_id), branch.id)`, after `.run(...)` the row reaches `STATUS_COMPLETED` with `completed_at is not None`, `attempts == 1`, `last_error_code == ""`, and the `MockTransport` saw exactly 1 DELETE to `/service/templates/<ext_id>/`.
- [ ] The comment block at `test_smoke_e2e.py:272-283` is updated to cite `test_smoke_cascade.py` (Phase 2A7 WU-2A7.1) as the canonical end-to-end cascade coverage alongside `test_cascade.py` (WU-2A6.1/2/3). The `self.skipTest(...)` body at lines 284–288 is unchanged.
- [ ] No `size:exception` annotation needed (≤200 net lines is under the 400-line review budget per `openspec/config.yaml:64`).
- [ ] The Phase 2A7 `archive-report.md` records the WU-2A6.4 deferral closure as an addendum (not as a verify-report PARTIAL flip — the spec compliance subtotal stays 13/14 COMPLIANT + 1/14 OUT-OF-SCOPE).

## References

- `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/verify-report.md` — line 149 §Issues §WARNING 1 (WU-2A6.4 deferral rationale); lines 53–83 (test execution log); line 115 (13/14 compliance subtotal).
- `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/apply-progress.md` — §1.3 (smoke cascade deferred) + §4 (caveats on patch targets, broker touch, ExitStack pattern, hook signature).
- `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/design.md` — §Pattern D warn (multi-import-site `HTTPClient` patches) + §Pattern C (on_failure hook positional signature).
- `backend/dp4500_integration/tests/test_cascade.py` — 13 existing tests; lines 32–110 (fixture pattern), lines 88–129 (signal test reference), lines 252–261 (`test_204_marks_completed` — direct `.run()` pattern to mirror).
- `backend/dp4500_integration/signals.py:23-66` — post_delete handler + `.delay()` capture site (line 23).
- `backend/dp4500_integration/tasks.py:14, 39-132, 113` — `HTTPClient` import line, task body under test, `on_failure` hook signature.
- `backend/tests/integration/dp4500_integration/test_smoke_e2e.py:48-67` — `_patch_dp4500_handler` helper (template for the new file's helper); lines 272–288 (skip block + comment to touch up).
- `openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/explore.md` — full exploration that produced this proposal (§3.2 Patterns A–D, §3.3 assertions, §5.2 F1–F4 failure-mode mitigations, §5.3 tasks artifact).
