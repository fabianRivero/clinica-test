# Proposal: Operation Manual Closure

## Intent

`Operacion` counters (`cuotas_totales`, `sesiones_totales`) are now flexible: admins may add or remove unrealized `CitaMedica` and `CuotaPlanPago` rows at any time. The current auto-closure rule in `Cliente.actualizar_estado_automaticamente` (auto-moves `EN_PROCESO → FINALIZADA` when "no pendientes" remain) is now wrong — all current items can be realized while the admin still intends to schedule more. This change replaces the auto rule with explicit, manual, audit-logged closure from `EN_PROCESO` to either `FINALIZADA` or a new `SUSPENDIDA` terminal state.

## Scope

### In Scope
- New `Operacion.Estado` value `SUSPENDIDA` (display "Suspendida").
- Model service methods `Operacion.cerrar_como_finalizada(user)` / `cerrar_como_suspendida(user)` plus a pure `puede_cerrar()` precondition checker.
- Audit fields on `Operacion`: `finalized_by` (FK User, nullable), `finalized_at` (DateTime, nullable), `finalization_kind` (`MANUAL_FINALIZADA | MANUAL_SUSPENDIDA`, nullable).
- Removal of the `EN_PROCESO → FINALIZADA` branch in `Cliente.actualizar_estado_automaticamente`. Other branches preserved.
- Update `Cliente.procedimiento_tiene_pendientes` so `SUSPENDIDA` and `FINALIZADA` both count as "no pendientes".
- Extend `Operacion.puede_reservar` (or equivalent) to reject new citas/cuotas while `SUSPENDIDA`.
- Two DRF endpoints: `POST /api/operaciones/<id>/finalizar/` and `POST /api/operaciones/<id>/suspender/` returning 200 on success, 409 with structured precondition detail on failure.
- Frontend: in `cms/operaciones/<id>`, two buttons visible only when `estado == EN_PROCESO`. "Finalizar" disabled with tooltip while any precondition fails; confirmation modal lists precondition status. "Suspender" enabled while `EN_PROCESO`.
- Tests covering `puede_cerrar()` truth table, audit field recording, 409 structured detail, and the regression that auto-closure no longer fires.

### Out of Scope
- Emails, notifications, PDFs at the moment of closure.
- Bulk closure of multiple operaciones.
- UI for reactivating a `SUSPENDIDA` (treated as terminal for this change).
- Any change to `CitaMedica` or `CuotaPlanPago` state machines.
- Editing `precio_total`.

## Capabilities

### New Capabilities
- `operation-manual-closure`: Owns the `Operacion` lifecycle rules for `SUSPENDIDA` and the manual `EN_PROCESO → FINALIZADA` transition — preconditions, audit fields, and the cliente/auto-closure interaction.

### Modified Capabilities
- None. There is no existing capability that captures `Operacion` lifecycle or `Cliente.actualizar_estado_automaticamente` (`grep` over `openspec/specs/` finds no match), so the closure domain is introduced as a fresh capability. `appointment-states` covers the cita state machine only; `appointment-payment` covers pago flow only; `operation-observations-photos` covers the observaciones section only.

## Approach

1. **Backend model** — extend `Operacion.Estado` TextChoices with `SUSPENDIDA`. Add `finalized_by` / `finalized_at` / `finalization_kind` fields (nullable, all optional on existing rows). Generate migration.
2. **Domain logic** — add `Operacion.puede_cerrar() -> (bool, dict)` returning a structured report (`sesiones_ok`, `cuotas_ok`, `monto_ok`, `failed[]`). Add `cerrar_como_finalizada(user)` / `cerrar_como_suspendida(user)` that call `puede_cerrar`, set audit fields in a single transaction, and raise a domain exception carrying the report when preconditions fail. Extend `puede_reservar` to block when `estado == SUSPENDIDA`.
3. **Cliente side** — delete the `EN_PROCESO → FINALIZADA` block in `actualizar_estado_automaticamente`; keep the rest. Add `SUSPENDIDA` to the `procedimiento_tiene_pendientes` terminal set.
4. **API** — two DRF `APIView`s under `/api/operaciones/<id>/...` with admin auth. Catch the domain exception, return `409` + `{estado, preconditions: {...}}`.
5. **Frontend** — in the operation detail page, add the two buttons inside an `OperationClosureActions` component. Compute `preconditions` client-side from the detail payload so the disabled state and modal reflect the same rules as the server. Confirmation modal for "Finalizar" lists each precondition with pass/fail.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/operations/models.py` | Modified | New `Estado`, audit fields, `puede_cerrar`, `cerrar_como_*`, `puede_reservar` guard. |
| `backend/customers/models.py` | Modified | Remove auto `EN_PROCESO → FINALIZADA`; treat `SUSPENDIDA` as terminal in `procedimiento_tiene_pendientes`. |
| `backend/operations/views.py` | Modified | New `finalizar` and `suspender` endpoints; structured 409. |
| `backend/operations/tests.py` | Modified | Truth-table tests for `puede_cerrar`, service tests, API 409 tests, auto-closure regression. |
| `frontend/.../cms/operaciones/<id>` | Modified | Two action buttons + confirmation modal with precondition list. |
| `openspec/changes/operation-manual-closure/migrations/` | New | Migration for `Operacion` schema additions. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Existing operaciones currently closed by the auto-rule will look "open" after the removal. | Med | Backfill: leave state as-is; the next admin save no longer fires auto-closure. Existing `FINALIZADA` rows stay. |
| Admin clicks "Finalizar" expecting auto-recovery from failed preconditions. | Med | Confirmation modal lists each precondition; server returns 409 with the same payload; tooltip explains why disabled. |
| `SUSPENDIDA` blocks new reservations in edge flows (e.g. legacy migration). | Low | Treat `SUSPENDIDA` as terminal in v1; reactivation is an explicit follow-up change. |
| Cents mismatch in `monto_programado` sum vs `precio_total`. | Med | `Decimal` accumulation; precondition is exact equality, error message names the diff. |
| Precondition logic diverges between client (disabled state) and server (409). | Med | Single `puede_cerrar` report shape consumed by both; server is authoritative. |

## Rollback Plan

1. Migration is additive (nullable fields, new enum value); reverting it leaves existing rows valid.
2. Re-add the `EN_PROCESO → FINALIZADA` branch in `Cliente.actualizar_estado_automaticamente` from git history.
3. Disable the new endpoints in `urls.py` and hide the two buttons in the frontend. No data loss: any `SUSPENDIDA` rows revert to `EN_PROCESO` via a one-line data migration if needed.

## Dependencies

- None external. Depends on `Operacion`, `CitaMedica`, `CuotaPlanPago`, and `Cliente` models already present in `backend/operations` and `backend/customers`.

## Success Criteria

- [ ] `Operacion.Estado` exposes `SUSPENDIDA` and persists through migration on existing rows.
- [ ] `puede_cerrar` truth table passes for: happy path, missing sesiones, pending cuota, mismatched sum, `BORRADOR`, `CANCELADA`.
- [ ] `cerrar_como_finalizada` / `cerrar_como_suspendida` set all three audit fields atomically and reject invalid source states.
- [ ] Both endpoints return `409` with structured `preconditions` payload when preconditions fail; `200` otherwise.
- [ ] `Cliente.actualizar_estado_automaticamente` no longer transitions `EN_PROCESO → FINALIZADA` (regression test).
- [ ] `procedimiento_tiene_pendientes` returns `False` for `SUSPENDIDA` and `FINALIZADA`.
- [ ] Frontend shows both buttons only when `estado == EN_PROCESO`; "Finalizar" disabled with tooltip when any precondition fails; confirmation modal mirrors server payload.
- [ ] New reservas/cuotas are rejected while `estado == SUSPENDIDA`.
