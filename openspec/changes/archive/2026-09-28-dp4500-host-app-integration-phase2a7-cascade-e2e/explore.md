# Exploration: dp4500-host-app-integration-phase2a7-cascade-e2e

**Prepared**: 2026-09-28
**Branch under review**: `feat/dp4500-host-app-integration-phase2-sdd` at `6c5d29d`
**Companion archive**: `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/` (Phase 2A6, just archived) and `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/` (Phase 2A5)
**Purpose**: Define the scope of Phase 2A7 — ship a **dedicated, isolated test file** for the cascade revoke path. Phase 2A6 closed the 3 PARTIAL scenarios on `cascade-biometric-revoke` (`backend/dp4500_integration/tests/test_cascade.py`, WU-2A6.1/2/3) but deferred the smoke e2e cascade step (WU-2A6.4) after 4 fix iterations hit architectural complexity (MockTransport + Celery broker + reverse-FK ordering).

This file is read-only for the orchestrator. It does NOT modify the SDD artifacts.

---

## 1. Goal

Phase 2A7 = "add a focused, isolated smoke test for the cascade revoke path **without** extending the existing enroll+verify smoke chain".

The Phase 2A6 verify-report (`openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/verify-report.md` §Issues §WARNING 1 at line 149) explicitly deferred the WU-2A6.4 cascade smoke step to Phase 2A7 after 4 fix-iterations could not get the cascade sub-step of `test_enroll_finalize_verify_then_cascade` working alongside the verify chain in a single test. The user has confirmed the better design: **TEST-ONLY delta, no production code modifications, with the cascade path tested in its own dedicated file** (`test_smoke_cascade.py`) that **does not** extend the existing smoke test.

The new test will:

1. Create `Usuario` + `PendingCascade` rows **directly via the ORM**, skipping the `enroll → finalize` wizard flow that `test_smoke_e2e.py` already covers (it is orthogonal — the enroll+verify chain is the canonical coverage for the wizard path).
2. Exercise the cascade signal (`signals.cascade_revoke_on_user_delete`) and the Celery task (`tasks.cascade_revoke_template`) using the right mocking pattern (proven by Phase 2A6):
   - `mock.patch("dp4500_integration.tasks.HTTPClient", side_effect=...)` impersonating DP4500 with `httpx.MockTransport` returning `204` on `DELETE /service/templates/<external_id>/`.
   - `mock.patch("dp4500_integration.signals.cascade_revoke_template.delay")` to broker-bypass the enqueue.
   - **Direct `cascade_revoke_template.run(...)` invocation** to bypass the broker entirely (proven by `CascadeTaskOutcomeTests` in `test_cascade.py:252-298`).
3. Manage multiple `HTTPClient` import-site patches with `contextlib.ExitStack` (Phase 2A6 `apply-progress.md` §4 + `design.md` §Pattern D warn: views and tasks consume `HTTPClient` via different import paths).

---

## 2. What landed in Phase 2A6 (already covered — DO NOT regress)

The Phase 2A6 archived verify-report (`verify-report.md:53-83`) confirms the test delta committed at `156f639`:

| WU | File | Lines | Closes | Status |
|---|---|---|---|---|
| **WU-2A6.1** | `backend/dp4500_integration/tests/test_cascade.py` | `CascadeSignalTests::test_user_without_biometric_external_id_is_no_op` (lines 131-165) | G1 / spec §6.6 (no-op branch) | ✅ COMPLIANT |
| **WU-2A6.2** | `backend/dp4500_integration/tests/test_cascade.py` | `CascadeSignalTests::test_sync_insert_failure_does_not_rollback_local_delete` (lines 167-220) | G2 / spec §6.7 (sync insert failure → graceful) | ✅ COMPLIANT |
| **WU-2A6.3** | `backend/dp4500_integration/tests/test_cascade.py` | `CascadeTaskOutcomeTests::test_max_retries_exhausted_marks_failed` (lines 297-358) | G3 / spec §6.10 (max retries → `status='failed'`) | ✅ COMPLIANT |
| **WU-2A6.1-mod** | `backend/dp4500_integration/tests/test_cascade.py` | `CascadeSignalTests::test_user_with_biometric_external_id_creates_pending_row` (lines 88-129, modified in Phase 2A6) | Hardened to patch `signals.cascade_revoke_template.delay` (bound attribute) instead of relying on `CELERY_TASK_ALWAYS_EAGER=True` filesystem broker | ✅ PASSING |

Net result: 3 PARTIAL rows from Phase 2A5 flipped to COMPLIANT; `test_cascade.py` grew from 8 → 13 tests (`verify-report.md:88` + `apply-progress.md` §1.1). Phase 2A6 sub-total: **13/14 cascade-revoke scenarios COMPLIANT, 1/14 OUT-OF-SCOPE** (Phase 4 cron-driven alert banner — pre-existing deferral).

---

## 3. What's still missing (Phase 2A7 scope)

**One test file. One test. New file. ORM-driven fixture, NOT wizard-driven.**

| WU | Test name | File | Closes | Asserts |
|---|---|---|---|---|
| **WU-2A7.1** | `SmokeCascadeTests::test_user_delete_triggers_cascade_to_completed` | `backend/tests/integration/dp4500_integration/test_smoke_cascade.py` (NEW FILE) | WU-2A6.4 deferred addendum (Phase 2A6 verify-report §Issues §WARNING 1 line 149) | `Usuario.delete()` fires the cascade signal; `cascade_revoke_template.delay` is called **once** with `(str(ext_id), sucursal_id)`; under eager Celery the row reaches `PendingCascade.STATUS_COMPLETED` with `completed_at is not None`, `attempts == 1`, `last_error_code == ""`. |

### 3.1 Why a new file (not extending `test_smoke_e2e.py`)

The Phase 2A6 apply agent attempted this 4 times within the existing `test_smoke_e2e.py::test_enroll_finalize_verify_then_cascade` and hit three independent layers of complexity (`apply-progress.md` §1.3 + §4, lines 26, 54):

1. **MockTransport + Celery broker + FK ordering coupling** — the existing test already wraps step 4 (verify POST) in `_patch_dp4500_handler(dp4500_handler)` which patches `dp4500_integration.views.HTTPClient` at line 65. The cascade task's `_do_cascade` calls `HTTPClient` from `dp4500_integration.tasks.HTTPClient` (different import site per `tasks.py:14`); patching only `views.HTTPClient` leaves the cascade task reaching the real network (or `localhost:8000`).
2. **Phase 2A6 proof (`design.md` §Pattern D, line 33)** — the canonical fix is to patch **both** import sites via `ExitStack` and run the task body directly with `cascade_revoke_template.run(...)` to bypass the broker. Doing this inside the enroll+verify chain requires rewiring the verify chain's handler to also satisfy the cascade DELETE in the same call sequence, which the 4 attempts could not stabilize.
3. **No real benefit** — extending the existing smoke conflates two orthogonal surfaces (the wizard enrollment path and the cascade revoke path). The wizard is fully covered by steps 1-4 in the existing test; the cascade signal is fully covered by the unit-level `CascadeSignalTests` + `CascadeTaskOutcomeTests` in `test_cascade.py`. What is missing is a **thin end-to-end check that the signal → Celery → HTTP DELETE → row=completed pipeline works when wired together**, not a re-test of the wizard.

User-confirmed decision (per orchestrator prompt): the smoke e2e cascade step stays reduced (skip block at `test_smoke_e2e.py:272-288` is preserved), and Phase 2A7 ships a **NEW dedicated test file** that uses the proven ExitStack + direct `.run()` pattern.

### 3.2 Mocking strategy (mirrors Phase 2A6 patterns A-D)

| Pattern | Source | What to patch | Why |
|---|---|---|---|
| **A — direct ORM fixture** | Phase 2A6 design.md §Pattern A (line 30) | `Usuario.objects.create_user(...)`; `PendingCascade.objects.create(...)` | Skips the wizard chain entirely; the cascade surface is orthogonal to enrollment mechanics. |
| **B — ExitStack for `HTTPClient` import sites** | Phase 2A6 apply-progress.md §4 (line 58) | Two `mock.patch` calls — one on `dp4500_integration.tasks.HTTPClient`, one on `dp4500_integration.views.HTTPClient` — both wrapping the same `httpx.MockTransport(handler)` factory | Patching only `views.HTTPClient` leaves the cascade task reaching the real network; patching only `tasks.HTTPClient` leaves the verify view doing the same. Both import sites reference the `HTTPClient` symbol independently (per `views.py` and `tasks.py` import statements). |
| **C — patch `signals.cascade_revoke_template.delay`** | Phase 2A6 test_cascade.py:116-117 + apply-progress.md §4 (line 56) | `dp4500_integration.signals.cascade_revoke_template.delay` (bound attribute) | `signals.py:23` captures `cascade_revoke_template` at import time and calls `.delay(...)` on the captured reference. Even with `CELERY_TASK_ALWAYS_EAGER=True` (`config/settings.py:287`), the filesystem broker still attempts a connection; patching the bound `.delay` keeps the test hermetic. |
| **D — direct `cascade_revoke_template.run(...)` invocation** | Phase 2A6 test_cascade.py:256-258 | After `Usuario.delete()` triggers the signal (which patches `.delay`), call `cascade_revoke_template.run(str(ext_id), sucursal_id)` directly with the same handler still patched | Bypasses the in-process Celery broker; the task body executes synchronously. Used identically by `CascadeTaskOutcomeTests::test_204_marks_completed` at lines 252-261. |

### 3.3 Assertions (final shape)

```python
# After Usuario.delete() under ExitStack of the two HTTPClient patches:
#   1. PendingCascade row exists with the right (user_external_id, sucursal_id).
row = PendingCascade.objects.get(user_external_id=ext_id, sucursal_id=branch.id)
self.assertEqual(row.status, PendingCascade.STATUS_PENDING)

#   2. signals.cascade_revoke_template.delay was called exactly once with the
#      right positional payload.
mock_delay.assert_called_once_with(str(ext_id), branch.id)

#   3. After driving the task body synchronously via .run(...) under the same
#      ExitStack, the row reaches STATUS_COMPLETED with completed_at stamped.
cascade_revoke_template.run(str(ext_id), branch.id)
row.refresh_from_db()
self.assertEqual(row.status, PendingCascade.STATUS_COMPLETED)
self.assertIsNotNone(row.completed_at)
self.assertEqual(row.attempts, 1)
self.assertEqual(row.last_error_code, "")

#   4. The MockTransport saw exactly one DELETE to /service/templates/<ext_id>/.
self.assertEqual(len(delete_calls), 1)
self.assertIn(f"/service/templates/{ext_id}/", delete_calls[0])
```

---

## 4. Open work (numbered, concrete)

1. **Create `backend/tests/integration/dp4500_integration/test_smoke_cascade.py`** with:
   - File header (module docstring) referencing Phase 2A6 §WARNING 1 deferral and Phase 2A7 user-confirmed "test aislado del cascade" decision.
   - Import block: `httpx`, `uuid`, `contextlib.ExitStack`, `from unittest import mock`, `from django.test import TestCase`, `from accounts.models import Rol, Usuario`, `from catalogs.models import Sucursal`, `from dp4500_integration.client import HTTPClient`, `from dp4500_integration.models import PendingCascade`, `from dp4500_integration.tasks import cascade_revoke_template`.
   - Module-level helper `_patch_dp4500_handler(handler)` mirroring the one in `test_smoke_e2e.py:48-67` (factory returns a `HTTPClient` whose `_client` is wrapped by `httpx.MockTransport(handler)`).
   - `class SmokeCascadeTests(TestCase):` with `setUp` that creates a `Sucursal` + `Rol("ADMIN_PRINCIPAL")` + `Usuario` via `Usuario.objects.create_user(...)` (do NOT use the wizard finalize).
   - Single test method `test_user_delete_triggers_cascade_to_completed` covering WU-2A7.1 per §3.2 + §3.3 above.

2. **Add a sibling docstring to the existing skip block in `test_smoke_e2e.py:272-288`** noting that the cascade coverage is now split:
   - `test_cascade.py` (WU-2A6.1/2/3) — unit-level coverage of the signal + task + reconcile.
   - `test_smoke_cascade.py` (Phase 2A7 WU-2A7.1) — end-to-end coverage of `Usuario.delete()` → cascade → MockTransport DELETE → row=completed.
   - DO NOT touch the `self.skipTest(...)` body itself or remove the skip — the existing smoke stays reduced by user decision.

3. **No other files change.** Specifically:
   - ❌ No edits to `backend/dp4500_integration/tests/test_cascade.py` (Phase 2A6's 13 tests are the canonical unit coverage; do not regress).
   - ❌ No edits to `backend/dp4500_integration/signals.py`, `tasks.py`, `models.py`, `client.py`, `views.py` (production code untouched per Phase 2A6 lineage).
   - ❌ No edits to `config/settings.py` (eager Celery + `DP4500_BASE_URL` defaults already correct at `settings.py:287` + `settings.py:292`).
   - ❌ No migration, no fixture, no management command.

---

## 5. Recommendation for proposal / design / tasks

The Phase 2A7 design and apply phases must enforce the **test-only, no-production-code** invariant from Phase 2A6 lineage (`apply-progress.md` §1.4 line 28, `proposal.md` §Scope line 46). Specifically:

### 5.1 Spec delta (proposal §Scope)

- **In Scope**: 1 new test file (`test_smoke_cascade.py`) with 1 test method (`test_user_delete_triggers_cascade_to_completed`).
- **Out of Scope**: any production-code change, any modification to `test_cascade.py`, any modification to `test_smoke_e2e.py` body (only a docstring touch-up is allowed), any extension of the existing enroll+verify chain.
- **Closes**: Phase 2A6 verify-report §Issues §WARNING 1 (the WU-2A6.4 deferral addendum, line 149). This is an **addendum**, not a verify-report PARTIAL flip — the spec compliance subtotal stays 13/14 COMPLIANT + 1/14 OUT-OF-SCOPE (Phase 4 cron banner). Phase 2A7 makes the 14/14 a "wired end-to-end" coverage rather than a unit-level coverage.

### 5.2 Design patterns (proposal §Test patterns)

The apply agent MUST follow all four patterns from §3.2 above. **The 4 Phase 2A6 failure modes MUST be addressed** so the apply agent doesn't repeat them:

| # | Failure mode (Phase 2A6) | Phase 2A7 mitigation |
|---|---|---|
| **F1** | **Patching `dp4500_integration.client.HTTPClient` (definition site) instead of `views.HTTPClient` / `tasks.HTTPClient` (import sites).** Symptom: views + tasks continue calling real `HTTPClient` because each module captured its own reference at import time. | Pattern B (§3.2). Use **two** `mock.patch` calls — one per import site — wrapped in `contextlib.ExitStack`. Cite `views.py` and `tasks.py:14` as the import lines. |
| **F2** | **`.delay()` actually touches the Celery filesystem broker even with `CELERY_TASK_ALWAYS_EAGER=True`.** Symptom: `ConnectionError` or `kombu.exceptions.OperationalError` from `cascade_revoke_template.delay(...)`. The Phase 2A5 test relied on eager mode + filesystem broker; the Phase 2A6 hardened test patches the bound `.delay` attribute. | Pattern C (§3.2). Patch `dp4500_integration.signals.cascade_revoke_template.delay` (the **bound attribute**, not the module). Cite `signals.py:23` for why the bound reference is the right patch target. |
| **F3** | **`_cascade_revoke_template_on_failure` is positional, NOT keyword.** Symptom: `TypeError: ... takes 5 positional arguments but 6 were given` when applying the Phase 2A5 test's `task_self=mock.Mock(), exc=...` keyword form. The hook signature at `tasks.py:113` is `def _cascade_revoke_template_on_failure(self, exc, task_id, args, kwargs, einfo)`. | **Not relevant to Phase 2A7** (no on_failure hook in the smoke cascade test — happy path only). Document this so future Phase 4 work doesn't re-hit it. |
| **F4** | **Direct `.run()` invocation was attempted but skipped because the test was scoped to `.delete()`'s side effects only.** Phase 2A6's WU-2A6.4 intended to verify the row reaches `STATUS_COMPLETED` after `Usuario.delete()` under eager Celery + 204 handler, but the inline run inside the test was never reached because earlier patches were still broken. | Pattern D (§3.2). Call `cascade_revoke_template.run(str(ext_id), branch.id)` **after** `Usuario.delete()` to drive the task body synchronously. Mirror `CascadeTaskOutcomeTests::test_204_marks_completed` at `test_cascade.py:252-261`. |

The apply agent should NOT need to retry the F1-F4 fix loop if it follows Patterns A-D from §3.2 verbatim.

### 5.3 Tasks artifact (tasks.md §Suggested Work Units)

| Unit | Goal | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|
| **WU-2A7.1** | Add `test_smoke_cascade.py` with the cascade end-to-end smoke | `pytest backend/tests/integration/dp4500_integration/test_smoke_cascade.py -q` | Celery eager + `httpx.MockTransport` returning 204 on `DELETE /templates/<ext_id>/` + ExitStack of `views.HTTPClient` and `tasks.HTTPClient` | Delete the file; cascade coverage reverts to the 13 unit tests in `test_cascade.py` |

Net test-side line target: ~80-120 lines (1 file, 1 test, helpers, docstring). Well under the 400-line `review_budget_lines` cap from `openspec/config.yaml:64`.

### 5.4 Pre-apply + Post-apply checklist

- **Pre-apply** (verify phase): confirm `test_smoke_cascade.py` exists, is hermetic (no broker, no real network), and reads `(13 + 1) = 14` tests passing for cascade-revoke coverage across `test_cascade.py` + `test_smoke_cascade.py`. The `test_smoke_e2e.py` skip count stays at 1 (the cascade sub-step).
- **Post-apply** (archive phase): `archive-report.md` records the WU-2A6.4 deferral closure as a Phase 2A7 addendum, citing this `explore.md` and the design rationale. Compliance subtotal stays 13/14 COMPLIANT + 1/14 OUT-OF-SCOPE (Phase 4 cron banner); the 14th scenario now has both unit-level and end-to-end coverage.

---

## 6. Caveats from Phase 2A6 + Phase 2A7 testing today

Two environmental changes happened during Phase 2A6 end-to-end testing that **the new test does NOT need** (because it uses `httpx.MockTransport`), but that **future integration tests against a real DP4500 host** must respect:

1. **`DP4500_BASE_URL` default fix** (`config/settings.py:292`, committed at `6c5d29d` on the working branch):
   - **Before fix**: `os.getenv("DP4500_BASE_URL", "http://localhost:8000")` — the clinic itself (the Django backend binds to `:8001` in dev).
   - **After fix**: `os.getenv("DP4500_BASE_URL", "http://localhost:8001")` — the DP4500 dev server.
   - **Impact** before fix: `CitaBiometricVerifyView` calling `HTTPClient(base_url=...)` with `base_url="http://localhost:8001"` would call the clinic itself, getting `transport:ConnectError` (wrong port for any real DP4500 listener) or `404` (no route at that path on the clinic). Operators who did not override the env var saw a working backend that silently could not reach DP4500.
   - **Phase 2A7 status**: not relevant because `test_smoke_cascade.py` uses `MockTransport` and does not resolve `DP4500_BASE_URL`. The fix at `settings.py:292` benefits future live integration tests only.

2. **WSL gateway IP for cross-host HTTP** (`172.20.176.1`):
   - Discovered during Phase 2A6 end-to-end testing: when the clinic (Windows process) needs to call DP4500 (WSL process) over the loopback adapter, `localhost` resolves differently for Windows-attached clients vs WSL-attached clients. The WSL gateway IP `172.20.176.1` is the canonical cross-host endpoint.
   - **Phase 2A7 status**: not relevant because `test_smoke_cascade.py` uses `MockTransport`. Documented here for any Phase 4 live-integration test (e.g., `test_integration_dp4500_live.py`) that hits the real DP4500 device.

The new test is **architecturally insulated** from both caveats. Any future live integration test should set `DP4500_BASE_URL=http://172.20.176.1:8000` in WSL or use `dp4500.test` if the test is restricted to MockTransport.

---

## 7. Affected areas

- `backend/tests/integration/dp4500_integration/test_smoke_cascade.py` — **NEW FILE** (the only file Phase 2A7 creates).
- `backend/tests/integration/dp4500_integration/test_smoke_e2e.py` — **docstring touch-up at lines 272-288** (skip block preserved; rationale note updated to mention `test_smoke_cascade.py` as the canonical end-to-end cascade coverage alongside `test_cascade.py`).
- `openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/proposal.md` (Phase 2A7 proposal — next phase).
- `openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/design.md` (Phase 2A7 design — next phase).
- `openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/tasks.md` (Phase 2A7 tasks — next phase).

No production code files affected. No migrations. No settings changes.

---

## 8. Ready for proposal

**Yes.** The change is small, well-scoped, has a single test target (WU-2A7.1), and the apply agent's failure surface is fully characterized by §5.2 F1-F4 above. The orchestrator should proceed to `sdd-propose` with the following guidance:

- **One-test scope**: do not let the proposal expand to "fix the cascade smoke in `test_smoke_e2e.py`" — the user-confirmed decision is "test aislado del cascade (mejor diseño)". The skip block in `test_smoke_e2e.py` stays.
- **No production code**: the proposal must explicitly state "TEST-ONLY delta" in the §Scope section to avoid drift during apply.
- **No chain PRs**: this is a single-test change (≤120 net lines), well under the 400-line review budget.
- **Rollback path**: drop `test_smoke_cascade.py`; revert the docstring touch-up in `test_smoke_e2e.py`. Cascade coverage reverts to the 13 unit tests in `test_cascade.py` (no functional regression).
