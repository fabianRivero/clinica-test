# Tasks: Operation Manual Closure

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~500-650 net (backend ~200, frontend ~400, migration ~10) |
| 400-line budget risk | Low |
| 800-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Replace auto-closure with manual audit-logged closure (FINALIZADA + SUSPENDIDA) end-to-end | PR 1 | `python manage.py test backend.operations backend.customers backend.tests.test_operation_closure_endpoint` | Dev server smoke at `/admin/operaciones/<id>` exercising both buttons | Revert migration + new `@action`s + frontend page changes; legacy `FINALIZADA` rows remain valid |

## Phase 1: Foundation (model + migration)

- [x] 1.1 In `backend/operations/models.py::Operacion.Estado`: append `SUSPENDIDA = "SUSPENDIDA", "Suspendida"`.
- [x] 1.2 Add nullable fields `finalized_by` (FK `Usuario`, `on_delete=SET_NULL`, `related_name="+"`), `finalized_at` (DateTime, `null=True`), `finalization_kind` (CharField 24, choices, `null=True`) on `Operacion`.
- [x] 1.3 Add exception `OperacionPrecondicionNoCumplida(operacion, report)` carrying `estado` + `preconditions` dict.
- [x] 1.4 Implement `Operacion.puede_cerrar() -> (bool, dict)` returning the design's JSON shape (sesiones/cuotas/monto + `failed[]`); reuse from finalize only.
- [x] 1.5 Implement `cerrar_como_finalizada(user)` and `cerrar_como_suspendida(user)` — atomic state guard, audit field write via `save(update_fields=...)`.
- [x] 1.6 Generate `backend/operations/migrations/0030_operacion_closure_audit.py` (3 AddField + AlterField); verify on existing DB.

## Phase 2: Cliente-side changes

- [x] 2.1 In `backend/customers/models.py::Cliente.actualizar_estado_automaticamente`: delete the 3-line block that auto-moves `EN_PROCESO → FINALIZADA`; keep every other branch intact.
- [x] 2.2 In `procedimiento_tiene_pendientes`: include `SUSPENDIDA` alongside existing terminal set in the early-return.
- [x] 2.3 Grep `Operacion.Estado.FINALIZADA` / `operacion.save` in `backend/` to confirm no other code path implicitly moves `EN_PROCESO → FINALIZADA`.

## Phase 3: API endpoints

- [x] 3.1 In `backend/config/api/viewsets/operaciones.py::OperacionesViewSet`: add `@action(detail=True, methods=["post"], url_path="finalizar")` and `url_path="suspender"`. Wrap in `transaction.atomic()` with `select_for_update(of=("self",))`.
- [x] 3.2 In `finalizar`: call `puede_cerrar`; on `(False, report)` raise `OperacionPrecondicionNoCumplida` → 409 `{estado, preconditions}`; on `True` invoke `cerrar_como_finalizada(user)`.
- [x] 3.3 In `suspender`: reject non-`EN_PROCESO` with 409 `{detail}`; otherwise `cerrar_como_suspendida(user)` (no precondition check).
- [x] 3.4 Both actions: reuse `AdminRequired`; after success call `paciente.actualizar_estado_automaticamente()`; return 200 with `_client_operation_item`.
- [x] 3.5 Confirm `backend/config/api/routers_operaciones.py` registers `OperacionesViewSet` via `operaciones_d8_router` with `trailing_slash=False`; verify URL resolves to `/finalizar/` and `/suspender/`.

## Phase 4: Frontend

- [x] 4.1 In `frontend/aesthetic-clinic/src/services/api/admin.ts`: add `finalizeAdminOperation(id)` and `suspendAdminOperation(id)` `postJson` helpers returning `OperationClosureResponse`.
- [x] 4.2 In `frontend/aesthetic-clinic/src/types/admin.ts`: add `OperationPreconditionsReport` and `OperationClosureResponse` types (decimal-strings) matching server shape.
- [x] 4.3 In `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx`: add inline `OperationClosureActions` at top of "Información principal"; render both buttons only when `estado == "En proceso"`; helper derives preconditions client-side; disabled tooltip names first failing precondition.
- [x] 4.4 Create `frontend/aesthetic-clinic/src/components/OperationClosureConfirmModal.tsx`: precondition list with pass/fail chips; "Confirmar" disabled if any fail; on server 409 repopulate from `preconditions`.
- [x] 4.5 Wire `useApiResource.reload()` after successful mutation; open success toast per existing pattern.

## Phase 5: Tests

- [x] 5.1 In `backend/operations/tests.py`: add `OperacionClosureTests` covering scenarios "Happy path closure", "Non-final cita blocks closure", "PENDIENTE or VENCIDA cuota blocks closure", "Sum mismatch", "Suspend success", "Suspend rejected", "Finalize records audit", "Suspend records audit", "SUSPENDIDA blocks new cita", "SUSPENDIDA blocks new cuota", "Terminal states no-pendientes".
- [x] 5.2 Rewrite the assertion at `backend/operations/tests.py:123` to assert `estado == EN_PROCESO` (regression: auto-closure no longer fires).
- [x] 5.3 Create `backend/tests/test_operation_closure_endpoint.py` with `APIClient` (mirrors `test_admin_cobrar_cita_endpoint.py`) covering "Finalize success 200", "Finalize precondition failure 409", "Suspend wrong source 409", "Non-admin 403".
- [x] 5.4 If a Playwright runner exists under `frontend/aesthetic-clinic/e2e/`: add scenarios "Buttons visible only in EN_PROCESO", "Finalizar disabled + tooltip when failing", "Server 409 re-renders modal". Drop otherwise and note.

## Phase 6: Verification

- [x] 6.1 Run `python manage.py makemigrations --check` to confirm no model/migration drift.
- [x] 6.2 Run `python manage.py test backend.operations backend.customers backend.tests.test_operation_closure_endpoint`; all pass.
- [x] 6.3 Run the targeted admin frontend test command (discover from repo); run Playwright if present.
- [x] 6.4 Manual smoke against running dev server: open `/admin/operaciones/<id>`; exercise both buttons on a real `EN_PROCESO` operacion.