# Design: Phase 2A7 — Focused cascade smoke e2e (isolated test)

**Predecessor**: `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/design.md` (locked). **Phase 2A7 inherits the cascade pipeline design verbatim; this document captures only the new isolated test surface and the four mocking patterns proven by Phase 2A6.**

---

## Status

Draft (will lock after `sdd-tasks`).

## Architecture decision

**NO architecture changes from Phase 2A6.** The cascade pipeline
(`post_delete` signal → sync `PendingCascade` insert → `cascade_revoke_template.delay(...)` Celery enqueue → `_do_cascade(...)` body → `HTTPClient.delete_template(...)` → `_cascade_revoke_template_on_failure(...)` hook on retry exhaustion) is unchanged. Phase 2A5 §6 governs: `signals.py:29-66`, `tasks.py:39-132`, `models.py:23-60`, `client.py:82-274`, `views.py` and the `reconcile_pending_cascades.py` command are not edited. ADRs 0001-0005 stand.

Phase 2A7 closes the WU-2A6.4 deferral addendum (Phase 2A6 verify-report §Issues §WARNING 1, line 149) by adding **one new test file** with **one test method** in a new dedicated location that does **not** extend `test_smoke_e2e.py`. The cascade surface is tested in isolation from the wizard enroll+verify chain, against the proven Phase 2A6 mocking patterns A/B/C/D.

The 13/14 cascade-revoke COMPLIANT subtotal from Phase 2A6 stays; Phase 2A7 adds end-to-end wiring coverage (`Usuario.delete() → signal → PendingCascade → cascade_revoke_template.run → MockTransport DELETE → STATUS_COMPLETED`) that `test_cascade.py` provides only at the unit level.

## Test surface

| WU | File | Test class | Test method | Asserts (5-7 bullets) | Mocks used | Lines |
|---|---|---|---|---|---|---|
| **WU-2A7.1** | `backend/tests/integration/dp4500_integration/test_smoke_cascade.py` (NEW) | `SmokeCascadeTests` | `test_user_delete_triggers_cascade_to_completed` | • `mock_delay.assert_called_once_with(str(ext_id), branch.id)` (positional order matches `signals.py:58`).<br>• After `Usuario.delete()` + patched `.delay`, exactly 1 `PendingCascade` row exists with `status=STATUS_PENDING`, `attempts=0`, `user_external_id=<ext_id>`, `sucursal_id=branch.id`.<br>• After `cascade_revoke_template.run(str(ext_id), branch.id)` (direct body invocation), `row.status == STATUS_COMPLETED`.<br>• `row.completed_at is not None` (timezone-aware stamp).<br>• `row.attempts == 1` (incremented once at `tasks.py:91`).<br>• `row.last_error_code == ""` (no exception classified).<br>• `MockTransport` recorded exactly 1 `DELETE` request, and `str(request.url)` contains `f"/service/templates/{ext_id}/"`. | • `mock.patch("dp4500_integration.views.HTTPClient", side_effect=factory)` — Pattern B import site 1 (`views.py:33`).<br>• `mock.patch("dp4500_integration.tasks.HTTPClient", side_effect=factory)` — Pattern B import site 2 (`tasks.py:14`).<br>• `mock.patch("dp4500_integration.signals.cascade_revoke_template.delay")` — Pattern C bound attribute (`signals.py:23`).<br>• `mock.patch.dict(os.environ, {f"DP4500_SERVICE_KEY_SUCURSAL_{branch.id}": "SeK_smoke_test"}, clear=False)` — Pattern A env key resolver. | ~120 |

Reuses `httpx.MockTransport` (already in `requirements.txt`); mirrors `_patch_dp4500_with_handler` from `test_cascade.py:228-241` and `_patch_dp4500_handler` from `test_smoke_e2e.py:48-67` (DELETE-only variant, no POST handler needed because the cascade task only issues `DELETE /service/templates/<ext_id>/` per `client.py:170-174`).

## Test patterns

The four patterns below are the Phase 2A6-proven recipe. The apply agent MUST follow all four; failure to do so re-triggers F1-F4 from `apply-progress.md` §4 (Phase 2A6 deferred after 4 fix-iteration failures).

### Pattern A — `mock.patch.dict` for `os.environ` ServiceAPIKey

`tasks._resolve_key_resolver()` (`tasks.py:25-36`) reads `DP4500_SERVICE_KEY_SUCURSAL_<id>` from `os.environ` lazily inside the task body (NOT from Django settings, NOT from `Sucursal.dp4500_service_key_id`). The fixture must inject the env var directly via `mock.patch.dict(os.environ, ...)` — the test must NOT call `settings.DP4500_SERVICE_KEY_SUCURSAL = ...` because settings are not the lookup path.

```python
import os
from unittest import mock

# Inside the test (setUp or method body):
with mock.patch.dict(
    os.environ,
    {f"DP4500_SERVICE_KEY_SUCURSAL_{self.branch.id}": "SeK_smoke_test"},
    clear=False,
):
    # ... body — env restored on context exit
```

**Rationale**: `tasks.py:34-36` calls `os.environ.get(f"DP4500_SERVICE_KEY_SUCURSAL_{sucursal_id}")`. The `_do_cascade` body then passes this resolver to `HTTPClient(...)` at `tasks.py:48-52`; if the env var is unset, `_request` raises `BiometricUnavailable("no_service_key")` at `client.py:192-193`, masking the cascade code path under test.

### Pattern B — `ExitStack` for dual `HTTPClient` patch sites

`views.py:33` (`from dp4500_integration.client import HTTPClient`) and `tasks.py:14` (same import) each capture their own `HTTPClient` reference at module-import time. Patching the **definition site** `dp4500_integration.client.HTTPClient` is broader than needed (it patches everywhere) and is fragile to module-reload behavior. Patching only one import site leaves the other module's `HTTPClient(...)` call (`views.py` or `tasks.py`) hitting the real network. The new test must patch BOTH import sites, wrapped in `contextlib.ExitStack` so all patches enter and exit atomically.

```python
import contextlib
from unittest import mock

from dp4500_integration.client import HTTPClient
import httpx


def _patch_dp4500_handler(handler):
    """Return TUPLE of (views.HTTPClient patch, tasks.HTTPClient patch).
    Both share the same factory so the MockTransport routes identically
    across the verify view and the cascade task. Call sites MUST wrap
    this tuple in contextlib.ExitStack (NOT a single `with`).
    """
    def factory(*args, **kwargs):
        client = HTTPClient(
            base_url="https://dp4500.test",
            timeout_seconds=5,
            key_resolver=lambda _: "SeK_smoke_test",
        )
        client._client = httpx.Client(transport=httpx.MockTransport(handler))
        return client
    return (
        mock.patch("dp4500_integration.views.HTTPClient", side_effect=factory),
        mock.patch("dp4500_integration.tasks.HTTPClient", side_effect=factory),
    )


# Inside the test method:
delete_calls = []

def handler(request):
    if request.method == "DELETE" and "/templates/" in str(request.url):
        delete_calls.append(str(request.url))
        return httpx.Response(204, request=request)
    raise AssertionError(f"Unexpected {request.method} {request.url}")

with contextlib.ExitStack() as stack:
    for patch in _patch_dp4500_handler(handler):
        stack.enter_context(patch)
    with mock.patch(
        "dp4500_integration.signals.cascade_revoke_template.delay",
    ) as mock_delay:
        # ... Usuario.delete() + assertions ...
```

**Rationale**: `apply-progress.md` §4 line 58: `from X import Y` creates per-module references, so patching only `views.HTTPClient` leaves `tasks.HTTPClient` (used at `tasks.py:48`) pointing at the real `HTTPClient`. `ExitStack` is preferred over nested `with` blocks because it (a) scales to N patch sites without indentation creep and (b) restores all patches atomically on exception — if any patch enter fails, none of the others remain half-applied.

### Pattern C — Bound `.delay` attribute patch

`signals.py:23` (`from dp4500_integration.tasks import cascade_revoke_template`) captures the task object at import time. The post_delete handler calls `.delay(user_external_id, sucursal_id or 0)` on this captured reference at `signals.py:58`. Even with `CELERY_TASK_ALWAYS_EAGER=True` (`config/settings.py:287`), the filesystem broker still attempts a connection — eager mode runs the task body synchronously AFTER broker dispatch, and the broker connection itself can raise `ConnectionError` / `kombu.exceptions.OperationalError`. Patching the bound `.delay` attribute on the captured task reference keeps the test hermetic.

```python
with mock.patch(
    "dp4500_integration.signals.cascade_revoke_template.delay",
) as mock_delay:
    mock_delay.assert_called_once_with(str(ext_id), self.branch.id)
```

**Rationale**: `signals.py:23` imports the task as a symbol; `signals.py:58` invokes `.delay(...)` on that symbol. The patch target MUST be the **bound attribute** (`signals.cascade_revoke_template.delay`), NOT the module (`signals.cascade_revoke_template`). Patching the module would not intercept `.delay()` because the attribute lookup happens at call time on the task object itself. Phase 2A6 `test_cascade.py:115-117` (added at commit `156f639`) proves this is the right target.

### Pattern D — Direct `cascade_revoke_template.run(...)` invocation

After `Usuario.delete()` triggers the post_delete signal (which now hits the patched `.delay` instead of the broker), the test drives the task body synchronously by calling the task's `.run(...)` method directly. This bypasses Celery's broker, retry chain, and `on_failure` hook dispatch entirely — the test asserts the task body works, not Celery's dispatch semantics (those are mocked via A/B/C and unit-tested separately in `test_cascade.py::CascadeTaskOutcomeTests::test_max_retries_exhausted_marks_failed`).

```python
# After Usuario.delete() under ExitStack of A/B/C patches:
cascade_revoke_template.run(str(ext_id), self.branch.id)

row = PendingCascade.objects.get(user_external_id=ext_id, sucursal_id=self.branch.id)
self.assertEqual(row.status, PendingCascade.STATUS_COMPLETED)
self.assertIsNotNone(row.completed_at)
self.assertEqual(row.attempts, 1)
self.assertEqual(row.last_error_code, "")
self.assertEqual(len(delete_calls), 1)
self.assertIn(f"/service/templates/{ext_id}/", delete_calls[0])
```

**Rationale**: `cascade_revoke_template` is a Celery `@shared_task(bind=True, ...)` (`tasks.py:68`); Celery tasks expose a `.run(*args, **kwargs)` method that executes the body with `self` bound. Calling `.run(...)` skips `apply_async`, skips broker routing, skips `retry` (the task body still calls `self.retry(exc=exc)` at `tasks.py:101` if `_do_cascade` raises `BiometricUnavailable` — the test's MockTransport returns 204 so this branch is not exercised). Mirrors `CascadeTaskOutcomeTests::test_204_marks_completed` at `test_cascade.py:252-261` (proven in Phase 2A6).

## Fixture considerations

The new test creates its own `Sucursal` + `Rol` + `Usuario` directly via the ORM. **No FK dependents**:

```python
class SmokeCascadeTests(TestCase):
    def setUp(self):
        # Sucursal with a fixed id (so env_key_resolver lookup is predictable).
        self.branch = Sucursal.objects.create(nombre="Smoke-Cascade")
        # Rol: at least one for Usuario.rol FK; get_or_create is idempotent.
        self.rol, _ = Rol.objects.get_or_create(rol="CLIENTE")
        # Usuario — direct ORM fixture (no wizard finalize).
        # ``assign_biometric_external_id`` (accounts.signals) mints a UUID
        # on first save, so the cascade signal will fire on delete.
        self.user = Usuario.objects.create_user(
            username="smoke.cascade",
            password="Sup3rSecret!",
            primer_nombre="Smoke",
            apellido_paterno="Cascade",
            rol=self.rol,
            sucursal=self.branch,
        )
        self.ext_id = self.user.biometric_external_id
        self.assertIsNotNone(self.ext_id)
```

Key invariants:

- **No CitaMedica, no Operacion, no Cliente** — the smoke chain's `Cliente → Operacion(paciente=PROTECT, operations/models.py:58-62)` trap (Phase 2A6 failure F5 / `apply-progress.md` §1.3) does not apply. The new `Usuario` has zero reverse-FK dependents; `Usuario.delete()` triggers the cascade signal without any FK constraint violation.
- **PATCH BOTH HTTPClient import sites** — `views.py:33` and `tasks.py:14` are independent references (Phase 2A6 failure F1; `apply-progress.md` §4 line 58). Patching only one leaves the other reaching the real network.
- **PATCH the bound `.delay` attribute** — `signals.cascade_revoke_template.delay` (`signals.py:23` capture site; `apply-progress.md` §4 line 56). Eager mode + filesystem broker still touches the broker (Phase 2A6 failure F2).
- **CALL `.run(...)` directly** — not `.delay(...)` (Phase 2A6 failure F4). The body executes synchronously; broker + retry + `on_failure` are out of scope for this test.
- **No `BIOMETRIC_SUSPENDED` override needed** — the cascade DELETE path does not depend on `settings.BIOMETRIC_SUSPENDED` (the flag gates enrollment, not revocation; per `client.py:159-174`).

## Risks

| Risk | Mitigation |
|---|---|
| **WIP persistence risk.** The new test creates a `Usuario` + (transient) `PendingCascade`. If WIP state from a previous failed run pollutes the DB, the new test might assert on stale data (e.g., `PendingCascade.objects.count() == 1` fails because of a leftover row). | `Django TestCase` wraps each test in a transaction that is rolled back on teardown (`test_cascade.py:53` already uses `TestCase`). The `Usuario.objects.create_user(...)` and `PendingCascade.objects.create(...)` writes are scoped to the test method. No `addClassCleanup` is needed because `TestCase.__call__` rolls back atomically. If migration code changes the `Sucursal` model later, the `setUp` may need `Sucursal.objects.create(nombre=...)` — already proven against the Phase 2A6 baseline. |
| **Mock transport patching drift.** If `dp4500_integration.client.HTTPClient.__init__` signature changes (e.g., `key_resolver` becomes positional, `base_url` is renamed), the factory function in `_patch_dp4500_handler` would break. | The new test's helper is paired with `test_cascade.py:_patch_dp4500_with_handler` (lines 228-241, Phase 2A6 commit `156f639`); if the client signature changes, both factories break at once — the diff is grep-able across both files. The factory uses keyword arguments matching `client.py:89-95`, so the failure mode is a `TypeError` at factory call time, not silent. |
| **Real network leaks.** If either HTTPClient patch is omitted (e.g., from a refactor that moves the cascade task's `HTTPClient` import to a new module), the test would make a real HTTP call to `settings.DP4500_BASE_URL` (default `http://localhost:8000`, fixed at `settings.py:292`). In dev this hits a non-DP4500 listener and 404s; in CI it could hang on connection timeout. | The test uses `contextlib.ExitStack` (Pattern B) so all patches restore atomically on exit. An unhandled exception during the test would restore patches AND surface the error to the pytest runner — the test fails loudly, not silently. Additionally, the handler raises `AssertionError` on any unexpected URL (matching `test_smoke_e2e.py:247-249`); a missed DELETE that DOES route to MockTransport but the test expects `len(delete_calls) == 1` would catch a duplicate. |

## Dependencies

| File | Action | Net | WU |
|---|---|---|---|
| `backend/tests/integration/dp4500_integration/test_smoke_cascade.py` | **NEW FILE** — module docstring + import block + `_patch_dp4500_handler(handler)` helper + `SmokeCascadeTests(TestCase)` with `setUp` + 1 test method covering Patterns A/B/C/D | ~120 | WU-2A7.1 |
| `backend/tests/integration/dp4500_integration/test_smoke_e2e.py` | Comment-only touch-up at lines 272-283 (skip block at 284-288 unchanged). The new comment cites `test_smoke_cascade.py` as the canonical end-to-end cascade coverage alongside `test_cascade.py`. | ~5 | WU-2A7.2 |
| `openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/verify-report.md` | **NEW FILE** (written by the verify phase, not apply). Documents WU-2A7.1 PASS, Phase 2A6 PARTIAL closures still COMPLIANT, and the WU-2A6.4 deferral closure as a Phase 2A7 addendum (NOT a verify-report PARTIAL flip). | ~80 | WU-2A7.3 |

No production code, no fixtures, no migrations, no settings changes.

## Success criteria

Phase 2A7 is closed when:

- [ ] `python -m pytest backend/tests/integration/dp4500_integration/test_smoke_cascade.py` (WSL only — `backups/` imports `fcntl`) exits 0 with the new test passing.
- [ ] `python -m pytest backend/dp4500_integration/tests/test_cascade.py backend/tests/integration/dp4500_integration/test_smoke_e2e.py` continues to exit 0 on WSL — 13 passed + 1 skipped, no regressions; the 1 skipped test in `test_smoke_e2e.py` is the documented cascade sub-step deferral at lines 284-288.
- [ ] `git diff --stat main..HEAD` shows ≤ 200 net lines (the explore §5.3 estimate of 80-120 + the 5-line `test_smoke_e2e.py` touch-up = ≤ 125), all under `backend/tests/integration/dp4500_integration/` and `openspec/changes/.../`.
- [ ] `git diff --stat main..HEAD` shows zero production-code files (`signals.py`, `tasks.py`, `models.py`, `views.py`, `client.py`, `settings.py`) in the diff. The only changes are the new `test_smoke_cascade.py` file + the comment-only touch-up in `test_smoke_e2e.py`.
- [ ] The 3 PARTIAL → COMPLIANT flips from Phase 2A6 (`verify-report.md:115` — 13/14 cascade-revoke COMPLIANT) remain (all 13 `test_cascade.py` tests still pass).
- [ ] The WU-2A6.4 deferral note in the archived Phase 2A6 `verify-report.md:149` can be marked COMPLIANT in the new Phase 2A7 `verify-report.md` as an addendum (the spec compliance subtotal stays 13/14 COMPLIANT + 1/14 OUT-OF-SCOPE — Phase 4 cron banner).

## References

- `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/design.md` §Pattern D warn (multi-import-site `HTTPClient` patches) + §Pattern C (`on_failure` hook positional signature).
- `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/apply-progress.md` §1.3 (smoke cascade deferred) + §4 line 56-58 (caveats on patch targets, broker touch, ExitStack pattern, hook signature).
- `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/verify-report.md` line 149 §Issues §WARNING 1 (WU-2A6.4 deferral rationale); lines 53-83 (test execution log); line 115 (13/14 compliance subtotal).
- `backend/dp4500_integration/tests/test_cascade.py` — 13 existing tests; lines 88-129 (`test_user_with_biometric_external_id_creates_pending_row` — bound `.delay` patch reference); lines 228-241 (`_patch_dp4500_with_handler` — factory template); lines 252-261 (`test_204_marks_completed` — direct `.run()` pattern to mirror).
- `backend/dp4500_integration/signals.py:23, 29-66` — `cascade_revoke_template` capture site + post_delete handler + `.delay()` call site.
- `backend/dp4500_integration/tasks.py:14, 25-36, 39-65, 68-110` — `HTTPClient` import line, `_resolve_key_resolver` (reads `os.environ`), `_do_cascade` body, task wrapper under test.
- `backend/dp4500_integration/views.py:33` — second `HTTPClient` import site (verify view's patch target).
- `backend/dp4500_integration/client.py:82-99, 159-174` — `HTTPClient.__init__` (factory must use kwargs) + `delete_template` (only DELETE issued by cascade).
- `backend/tests/integration/dp4500_integration/test_smoke_e2e.py:48-67, 272-288` — `_patch_dp4500_handler` helper (template for the new file's helper) + skip block (lines 272-283 comment-only touch-up).
- `config/settings.py:287, 292` — `CELERY_TASK_ALWAYS_EAGER=True` (still touches filesystem broker — Pattern C) + `DP4500_BASE_URL` default (`http://localhost:8000`, fixed at `6c5d29d`).
- `openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/explore.md` §3.2 Patterns A-D, §3.3 assertions, §5.2 F1-F4 failure-mode mitigations, §5.3 tasks artifact.
- `openspec/changes/dp4500-host-app-integration-phase2a7-cascade-e2e/proposal.md` §Scope (In Scope WU-2A7.1/2/3, Out of Scope) + §Success Criteria + §References.
