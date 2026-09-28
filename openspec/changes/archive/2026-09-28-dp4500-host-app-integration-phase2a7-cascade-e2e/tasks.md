# Tasks: Focused cascade smoke e2e (Phase 2A7 of dp4500-host-app-integration-phase2)

**Change name**: `dp4500-host-app-integration-phase2a7-cascade-e2e`
**Artifact store**: openspec
**Delivery strategy**: `ask-on-risk`
**Predecessors**: proposal.md + design.md + specs/cascade-biometric-revoke/spec.md (locked)

> **Status**: TEST-ONLY delta. No production code committed in this change.
> Phase 2A7 isolates the cascade smoke test from the wizard flow. The existing
> 3 cascade tests in `test_cascade.py` (Phase 2A6) cover signal+task failures.
> This change adds 1 focused end-to-end test that exercises the full cascade
> signal → PendingCascade → cascade_revoke_template → MockTransport DELETE
> → STATUS_COMPLETED pipeline.

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
| WU-2A7.1 | New dedicated cascade e2e smoke test (isolated from wizard chain) | PR 1 | `python -m pytest backend/tests/integration/dp4500_integration/test_smoke_cascade.py -q` (WSL only) | Celery eager + `httpx.MockTransport` returning 204 on `DELETE /service/templates/<ext_id>/` + `ExitStack` of `views.HTTPClient` + `tasks.HTTPClient` + bound `.delay` patch on `signals.cascade_revoke_template.delay` | Delete `test_smoke_cascade.py`; cascade coverage reverts to the 13 unit tests in `test_cascade.py` |
| WU-2A7.2 | Skip-block docstring touch-up (no body change) | PR 1 | `python -m pytest backend/tests/integration/dp4500_integration/test_smoke_e2e.py -q` (WSL only) | Reuses existing `test_smoke_e2e.py` harness; only comment lines 272-283 change | `git checkout HEAD~ -- backend/tests/integration/dp4500_integration/test_smoke_e2e.py` (single-file revert of lines 272-283) |

---

## Phase 2A7: Focused cascade smoke e2e (Commit 1)

### 1.1 Imports + fixture helpers (Pattern A + Pattern B)

- [x] 1.1.1 RED `backend/tests/integration/dp4500_integration/test_smoke_cascade.py` (NEW file). Add imports: `from contextlib import ExitStack`, `from unittest import mock`, `import os`, `from django.contrib.auth.hashers import make_password`, `from django.test import Client, TestCase, override_settings`, `import httpx`, plus project models (`accounts.models.{Rol, Usuario}`, `catalogs.models.Sucursal`, `dp4500_integration.models.PendingCascade`, `dp4500_integration.tasks.cascade_revoke_template`).

- [x] 1.1.2 Define `_patch_dp4500_handler(handler)` factory function that returns a TUPLE of two `mock.patch` objects — one for `dp4500_integration.views.HTTPClient` and one for `dp4500_integration.tasks.HTTPClient`. The factory creates an `HTTPClient` instance, swaps its `_client` attribute for an `httpx.Client(transport=httpx.MockTransport(handler))`, and returns it. Cite `design.md §5 Pattern B` and `apply-progress.md §4 F1` as the rationale.

- [x] 1.1.3 Define `_make_graph()` fixture builder that creates the Sucursal + Roles + admin Usuario + biometric_enrolled Usuario with `biometric_external_id = uuid.uuid4()`. Returns a dict.

### 1.2 WU-2A7.1 — Smoke cascade test (Pattern A + B + C + D)

- [x] 1.2.1 RED `SmokeCascadeTests::test_cascade_signal_then_task_marks_completed`. Inside the test:
  - Build the graph via `_make_graph()`.
  - Set `os.environ[f"DP4500_SERVICE_KEY_SUCURSAL_{graph['sucursal'].id}"] = "SeK_smoke_test"` via `mock.patch.dict(os.environ, ..., clear=False)`.
  - Open `ExitStack()`. Enter both HTTPClient patches (Pattern B) + a `mock.patch("dp4500_integration.signals.cascade_revoke_template.delay")` (Pattern C).
  - The handler returns `httpx.Response(204, request=request)` for `DELETE /templates/...`.
  - `client.force_login(graph["admin"])`. `graph["enrolled"].delete()` — fires the signal. The bound `.delay` is mocked so no broker call.
  - Assert `mock_delay.assert_called_once_with(str(graph["external_id"]), graph["sucursal"].id)`.
  - Assert `PendingCascade.objects.count() == 1` with `status='pending'`.
  - Call `cascade_revoke_template.run(str(graph["external_id"]), graph["sucursal"].id)` directly (Pattern D) — bypasses broker, runs the body synchronously. The MockTransport DELETE returns 204 → `_do_cascade` returns `STATUS_COMPLETED`.
  - `row = PendingCascade.objects.get(user_external_id=graph["external_id"])`.
  - Assert `row.status == PendingCascade.STATUS_COMPLETED`.
  - Assert `row.attempts == 1`.
  - Assert `row.completed_at is not None`.

- [ ] 1.2.2 GREEN: confirm the test passes in WSL pytest. Cite `design.md §5 Pattern D` and `test_cascade.py:252-261` (proven mirror).

### 1.3 Commit wrap-up

- [ ] 1.3.1 `python -m pytest backend/tests/integration/dp4500_integration/test_smoke_cascade.py` (WSL only) exits 0 with the new test passing.
- [ ] 1.3.2 `python -m pytest backend/dp4500_integration/tests/test_cascade.py backend/tests/integration/dp4500_integration/test_smoke_e2e.py` (WSL only) continues to exit 0 (no regressions; 1 skipped test in `test_smoke_e2e.py` is expected).
- [ ] 1.3.3 `git diff --stat main..HEAD` shows ≤ 200 net lines, all under `backend/tests/integration/dp4500_integration/` and `openspec/changes/.../`.
- [ ] 1.3.4 Commit `test(dp4500_integration): add focused cascade smoke e2e (Phase 2A7)`.

**End of Commit 1.**

---

## Out-of-scope tasks (explicit non-tasks)

These are NOT in this change. Listed here so reviewers don't expect them:

- ❌ Any production code change to `signals.py`, `tasks.py`, `models.py`, `views.py`, or `client.py` — implementation is correct per Phase 2A6 lineage.
- ❌ New endpoints, new signal handlers, new Celery tasks.
- ❌ Removing the `self.skipTest(...)` body at `test_smoke_e2e.py:284-288` — the skip stays; only the comment above (lines 272-283) gets a docstring touch-up.
- ❌ Adding tests to `test_cascade.py` — the 13 existing tests are the canonical unit-level cascade coverage and must not regress.
- ❌ Phase 4 cron-driven alert banner after N retries (already deferred from Phase 2A5).
- ❌ Exponential-backoff retry policy (stays at fixed `default_retry_delay=30` — Phase 2B concern).
- ❌ `DP4500_BASE_URL` default fix (`settings.py:292`, committed at `6c5d29d`) — already in place; not relevant to a `MockTransport`-based test.
- ❌ WSL gateway IP (`172.20.176.1`) cross-host HTTP — same: `MockTransport` makes it irrelevant.

---

## Pre-apply (verify phase)

- [ ] WU-2A6.4 deferral note in the archived Phase 2A6 verify-report can be marked COMPLIANT in the new Phase 2A7 verify-report.
- [ ] No new lint errors introduced (eslint on the touched frontend files — should be 0 since this change is backend-only).
- [ ] The Phase 2A5 e2e smoke (`test_smoke_e2e`) still skips the cascade sub-step (preserved per Phase 2A6 deferral).

---

## Post-apply (archive phase)

- [ ] Write `archive-report.md` for Phase 2A7 at `openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/archive-report.md` covering the 1 commit, the WU-2A6.4 deferral flip, and the test counts.
