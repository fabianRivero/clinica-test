# Design: Phase 2A6 — Cascade revoke test closure (no design changes)

**Predecessor**: `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/design.md` (locked). **Phase 2A6 inherits that design verbatim; this document captures the test surface only.**

---

## Status

Draft (locks after `sdd-tasks`).

## Architecture decision

**No architecture changes from Phase 2A5.** The cascade pipeline (`post_delete` signal → sync `PendingCascade` → Celery `.delay()` → `_do_cascade()` → `HTTPClient.delete_template` → `on_failure` hook) is unchanged. Phase 2A5 §6 governs: `signals.py:29-66`, `tasks.py:39-132`, `models.py:23-60`, `reconcile_pending_cascades.py` are not edited. ADRs 0001-0005 stand.

Phase 2A6 adds **4 named tests** closing the 3 PARTIAL scenarios on `cascade-biometric-revoke` (Phase 2A5 verify-report rows 191, 192, 196 + §WARNING 4-6) and extends the existing smoke so it no longer skips the cascade sub-step. Implementation is correct; only the test surface grows.

## Test surface

| WU | Test name | File | Closes | Asserts |
|---|---|---|---|---|
| **WU-2A6.1** | `CascadeSignalTests::test_user_without_biometric_external_id_is_no_op` | `backend/dp4500_integration/tests/test_cascade.py` (after line 113) | G1, `spec.md:44-49` | `PendingCascade.objects.count() == 0` and `HTTPClient.delete_template` never called when `biometric_external_id is None`. |
| **WU-2A6.2** | `CascadeSignalTests::test_sync_insert_failure_does_not_rollback_local_delete` | same (after WU-2A6.1) | G2, `spec.md:51-58` | `mock.patch("dp4500_integration.signals.PendingCascade.objects.create", side_effect=IntegrityError(...))`; `Usuario.delete()` commits, no `PendingCascade`, ERROR log (`assertLogs("dp4500_integration.signals", level="ERROR")`), `delay` never called. |
| **WU-2A6.3** | `CascadeTaskOutcomeTests::test_max_retries_exhausted_marks_failed` | same (after line 188) | G3, `spec.md:96-103` | Patches `cascade_revoke_template.retry` to raise `MaxRetriesExceededError`; invokes `_cascade_revoke_template_on_failure(self, exc, task_id, args, kwargs, einfo=None)` directly per `tasks.py:113`. `status=="failed"`, `attempts==1`, `last_error_code.startswith("celery:")`. |
| **WU-2A6.4** | `SmokeE2ETests::test_enroll_finalize_verify_then_cascade` (extended; replaces skip at `test_smoke_e2e.py:272-281`) | `backend/tests/integration/dp4500_integration/test_smoke_e2e.py` | G4, end-to-end | Reverse-FK deletes (below) + `_patch_dp4500_handler(...)` returning 204 on `DELETE /templates/...` around `Usuario.delete()`; row exists, `status==STATUS_COMPLETED`, `completed_at is not None`, `attempts==1`. |

Reuses existing fixtures (`CascadeSignalTests.setUp` `test_cascade.py:50-53`; `_patch_dp4500_handler` `test_smoke_e2e.py:48-67`; `_build_smoke_graph` 70-102). Net ≈150 lines; under `review_budget_lines: 400`.

## Test patterns

- **A — Pre-save bypass (WU-2A6.1).** `accounts.signals.assign_biometric_external_id` mints a UUID on first INSERT. Exercise `signals.py:32-33` early-return with `User.objects.filter(pk=u.pk).update(biometric_external_id=None)` after `create_user()` — `update()` bypasses `save()` and both signals. `refresh_from_db()` then sees None.
- **B — DB error injection (WU-2A6.2).** Patch at `dp4500_integration.signals.PendingCascade.objects.create`. `IntegrityError` subclasses `Exception`, so `try/except Exception` at `signals.py:48` catches it. Combine `mock.patch` with `assertLogs("dp4500_integration.signals", level="ERROR")`; assert `Usuario` gone, `PendingCascade.objects.count() == 0`.
- **C — `on_failure` invocation (WU-2A6.3).** Patch `tasks.cascade_revoke_template.retry` → raises `MaxRetriesExceededError`; one `cascade_revoke_template.run(...)` exits the loop. Then call `_cascade_revoke_template_on_failure(task_self, exc, task_id, args, kwargs, einfo=None)` per `tasks.py:113`. Hook reads `kwargs.get("user_external_id")` / `kwargs.get("sucursal_id")` — pass both via `kwargs={...}`. Refresh; assert `status == STATUS_FAILED`.
- **D — `MockTransport` impersonation (WU-2A6.4).** Reuse `_patch_dp4500_handler` `test_smoke_e2e.py:48-67`; 204 branch already at line 245-246. **Phase 2A5 bug #3**: patch `dp4500_integration.views.HTTPClient` (view import site), NOT `dp4500_integration.client.HTTPClient` (definition site). Helper already correct.

## Fixture considerations

After `finalize`, the smoke user has these dependents: `customers.Cliente` (`OneToOneField(CASCADE)` on `Usuario`); `operations.Operacion.paciente` (FK to `Cliente`, `PROTECT`, `operations/models.py:58-62`); `CitaMedica.operacion` (CASCADE); `CitaMedica.medico` (PROTECT, NULL in the smoke).

A naive `cliente.usuario.delete()` trips `ProtectedError` because removing `Cliente` violates `Operacion.paciente=PROTECT` — the reason the skip at lines 272-281 was placed. **WU-2A6.4 deletes in reverse-FK order**:

```python
cita.delete()             # medico NULL → no PROTECT
operacion.delete()        # PROTECT blocks deletion of the Cliente, NOT Operacion
cliente.delete()          # Operacion gone; usuario CASCADE clean
cliente.usuario.delete()  # cascade_revoke_on_user_delete fires here
```

Wrap step 4 (or all four) in `_patch_dp4500_handler(dp4500_handler)`. Under `CELERY_TASK_ALWAYS_EAGER=True` (`config/settings.py:287`) the cascade runs synchronously inside `Usuario.delete()` and the row reaches `STATUS_COMPLETED` before assertions.

## Risks

| Risk | Mitigation |
|---|---|
| **Pattern A pre_save re-fire.** `u.save()` would re-mint the UUID; use `User.objects.filter(pk=u.pk).update(biometric_external_id=None)` — bypasses both signals. |
| **Pattern B `IntegrityError` source.** Patch `dp4500_integration.signals.PendingCascade.objects.create`, not the model class; error originates at the mock — SQLite/Postgres parity. |
| **Celery eager mode required.** WU-2A6.4 needs `.delay()` synchronous; `CELERY_TASK_ALWAYS_EAGER=True` default (`config/settings.py:287`). |
| **Pattern C retry isolation.** Patching `retry` raises `MaxRetriesExceededError` and isolates `_cascade_revoke_template_on_failure`; no Celery loop, single bulk `update(...)`, no SQLite serialization concern. |
| **Pattern D patch surface drift.** Cascade task vs views consume `HTTPClient` via different import paths. WU-2A6.4 helper patches views; WU-2A6.3 sibling `_patch_dp4500_with_handler` (`test_cascade.py:121-134`) patches tasks. Both exist. |

## Dependencies

| File | Action | Net | WU |
|---|---|---|---|
| `backend/dp4500_integration/tests/test_cascade.py` | Insert 3 new test methods into `CascadeSignalTests` (after line 113) + `CascadeTaskOutcomeTests` (after line 188). | +120 | WU-2A6.1, WU-2A6.2, WU-2A6.3 |
| `backend/tests/integration/dp4500_integration/test_smoke_e2e.py` | Replace `self.skipTest(...)` block at lines 272-281 with reverse-FK deletes + cascade assertions. | −10 / +40 | WU-2A6.4 |

No production code, fixtures, migrations, or settings.

## Success criteria

- [ ] `npx tsc -b --pretty false` exits 0.
- [ ] WSL pytest on `dp4500_integration/tests/test_cascade.py` + `tests/integration/dp4500_integration/test_smoke_e2e.py` exits 0 with ≥11 passed, ≤2 skipped.
- [ ] `test_cascade.py` 8 → 11; `test_smoke_e2e.py` skip count 2 → 1.
- [ ] 3 PARTIAL rows on `cascade-biometric-revoke` (verify-report rows 191, 192, 196) flip to COMPLIANT in the Phase 2A6 `archive-report.md` (separate phase).

## References

- `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/design.md` §6 — locked design.
- `.../verify-report.md` rows 184-208 + §WARNING 4-6.
- `signals.py:29-66`; `tasks.py:39-132` (under test).
- `operations/models.py:58-62` — `Operacion.paciente=PROTECT` (smoke blocker).
- `customers/models.py:169-173` — `Cliente.usuario` CASCADE.
- `accounts/signals.py:21-31` — pre_save (Pattern A); `config/settings.py:287` — `CELERY_TASK_ALWAYS_EAGER=True`.
