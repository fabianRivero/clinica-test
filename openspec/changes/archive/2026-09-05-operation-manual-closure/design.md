# Design: Operation Manual Closure

## Technical Approach

Replace `Cliente`'s implicit `EN_PROCESO → FINALIZADA` auto-rule with explicit, manual, audit-logged closure. Add `SUSPENDIDA` terminal state. Expose two DRF `@action`s on `OperacionesViewSet` (Domain 8, `trailing_slash=False`). Server returns structured precondition report on 409; frontend mirrors it from the same payload.

## Architecture Decisions

| # | Choice | Alternatives | Rationale |
|---|---|---|---|
| 1 | Single precondition report via `Operacion.puede_cerrar() -> (bool, dict)` reused by service + frontend | (a) `GET /precondiciones-cierre/`; (b) free-form 409 string | One source of truth; detail re-renders the report; server authoritative on race. |
| 2 | Decimal fields serialized as **strings** (`"100.00"`) | Pass `Decimal` | Avoids `float` loss; matches `_client_operation_item` currency-string convention. |
| 3 | `transaction.atomic()` + `select_for_update(of=("self",))` on both `@action`s | (a) Optimistic save; (b) DB trigger | Matches `actualizar_detalles` / `actualizar_precio`; eliminates TOCTOU between preconditions check and audit write. |
| 4 | `OperacionPrecondicionNoCumplida(operacion, report)` → 409 `{estado, preconditions: report}` | `ValidationError` + 400 | Distinguishes precondition failure (structured 409) from source-state rejection (409 `{detail}`). |
| 5 | Block new citas/cuotas at **view layer** via existing `puede_reservar` / `actualizar-precio` guard — NOT at model | `Operacion.save()` raises if `SUSPENDIDA` | `CitaMedica.save()` calls `actualizar_estado_automaticamente` writing Operacion; model-level guard unsafe. View sites (`api_views.py:3825`, `client_api_views.py:1432`, `viewsets/clientes.py:645`) are the choke point. |
| 6 | Frontend: native `useState` + `useApiResource` (no TanStack Query) | Introduce TanStack Query | Page uses `useApiResource` + `reload()`; a mutation library for two buttons violates "follow existing patterns". |
| 7 | Audit fields nullable, single migration, no data migration | Backfill on existing rows | Legacy `FINALIZADA` rows have no historical admin; nullable is correct and migration reversible. |
| 8 | `puede_reservar` already returns False for SUSPENDIDA (first clause `estado == EN_PROCESO`) | Add explicit SUSPENDIDA short-circuit | First condition already excludes SUSPENDIDA; `motivo_bloqueo_reserva` already names "Solo los tratamientos en proceso". Verify via test. |

## Data Flow

### Finalize happy / 409 / Suspend / Button visibility
```
Browser → POST /api/operaciones/<id>/finalizar/
OperacionesViewSet.finalizar
 └─ atomic(): lock Operacion (select_for_update(of=("self",)))
    └─ puede_cerrar() → (ok, report)
    └─ cerrar_como_finalizada(user): set estado+3 audit fields;
       save(update_fields=[..., updated_at])
    └─ paciente.actualizar_estado_automaticamente()  # no-op now
    └─ refetch + return 200 {_client_operation_item}
On 409: raise OperacionPrecondicionNoCumplida → Response(
  {"estado": operacion.estado, "preconditions": report}, 409).
Suspend: same path, cerrar_como_suspendida() skips precondition
check; wrong source → 409 {"detail": ...}.
UI: estado == "En proceso" → [Finalizar][Suspender]; Finalizar
    disabled ← !puede_cerrar.ok; tooltip = first failing label.
    All other estados → no buttons.
```

## File Changes

| File | Action | Description |
|---|---|---|
| `backend/operations/models.py` | Modify | Add `Estado.SUSPENDIDA`; audit fields (`finalized_by` FK SET_NULL, `finalized_at` DateTime, `finalization_kind` CharField 24, all `null=True`); class `OperacionPrecondicionNoCumplida`; methods `puede_cerrar()`, `cerrar_como_finalizada(user)`, `cerrar_como_suspendida(user)`. |
| `backend/customers/models.py` | Modify | In `actualizar_estado_automaticamente`: delete the `if operacion.estado == "EN_PROCESO": operacion.estado = "FINALIZADA"; operacion.save(...)` block. In `procedimiento_tiene_pendientes`: add `SUSPENDIDA` to the terminal set. |
| `backend/operations/migrations/0030_operacion_closure_audit.py` | Create | 3 `AddField` (nullable) + `AlterField estado` adding `SUSPENDIDA`. No data migration. |
| `backend/config/api/viewsets/operaciones.py` | Modify | 2 `@action(detail=True, methods=["post"])`: `finalizar`, `suspender`. Catch `OperacionPrecondicionNoCumplida` → 409 `{estado, preconditions}`; source-state → 409 `{detail}`. Reuse `AdminRequired`. Call `actualizar_estado_automaticamente()` after success. |
| `backend/operations/tests.py` | Modify | New `OperacionClosureTests`. Rewrite the assertion at line 123 (currently expects `FINALIZADA`) into a regression: `actualizar_estado_automaticamente` must leave `EN_PROCESO` untouched. |
| `backend/tests/test_operation_closure_endpoint.py` | Create | DRF `APIClient`: 200 finalize/suspend, 409 structured (3 branches), 409 source-state, 403 non-admin, audit rollback on failure. |
| `frontend/.../types/admin.ts` | Modify | Add `OperationPreconditionsReport`, `OperationClosureResponse`. |
| `frontend/.../services/api/admin.ts` | Modify | Add `finalizeAdminOperation(id)` / `suspendAdminOperation(id)`. |
| `frontend/.../AdminOperationDetailPage.tsx` | Modify | Add inline `OperationClosureActions` at top of "Información principal" panel. Pure helper derives preconditions client-side from detail payload. On 409, populate modal from server `preconditions`. |
| `frontend/.../components/OperationClosureConfirmModal.tsx` | Create | Precondition list with pass/fail chips; "Confirmar" disabled if any fail. |

## Interfaces / Contracts

**Precondition report (shared by server 409 + frontend helper)**:

```json
{
  "ok": false,
  "sesiones": {"ok": false, "expected": 5, "confirmed": 3, "reserved": 1, "pending": 1, "missing": 1},
  "cuotas":  {"ok": false, "pending": [{"nroCuota": 2, "estado": "PENDIENTE"}, {"nroCuota": 4, "estado": "VENCIDA"}]},
  "monto":   {"ok": false, "precioTotal": "100.00", "sumaMontoProgramado": "95.00", "diff": "-5.00"}
}
```

Monetary fields are decimal-strings (2 dp). `diff = precioTotal − sumaMontoProgramado`. Enum `FinalizationKind {MANUAL_FINALIZADA, MANUAL_SUSPENDIDA}` for `finalization_kind`.

**Endpoints** — `POST /api/operaciones/<id>/finalizar/`, `POST /api/operaciones/<id>/suspender/`. Routes via `OperacionesViewSet.@action(url_path="finalizar"|"suspender")` registered on `operaciones_d8_router` (`trailing_slash=False`).

**200** (both): `{"detail": "...", "operation": <_client_operation_item>}`. **403**: existing `AdminRequired`.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (model) | `puede_cerrar` truth table (6 branches) + audit atomicity + source-state guard | `django.test.TestCase` in `operations/tests.py` (matches existing style). |
| Service regression | `actualizar_estado_automaticamente` no longer flips `EN_PROCESO → FINALIZADA` | Rewrite the existing assertion at `operations/tests.py:123` (currently expects `FINALIZADA`) into a regression that expects `EN_PROCESO`. |
| API integration | 200 finalize/suspend, 409 structured (3 branches), 409 source-state, 403 non-admin, audit rollback on failure | New `tests/test_operation_closure_endpoint.py` with `APIClient` (matches `test_admin_cobrar_cita_endpoint.py`). |
| Frontend e2e | Buttons visible only in `EN_PROCESO`; 409 re-renders modal; disabled tooltip | Playwright only (`aesthetic-clinic` e2e tree; no unit runner per `openspec/config.yaml`). No new unit tests. |

## Threat Matrix

**N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.** Touches only Django models, DRF `@action`s, a React page, and a migration.

## Migration / Rollout

`0030_operacion_closure_audit.py`: `AddField finalized_by` (FK SET_NULL, null, `related_name="+"`), `AddField finalized_at` (DateTime, null), `AddField finalization_kind` (CharField 24, choices, null), `AlterField estado` adding `SUSPENDIDA`. No data migration. Rollback: revert migration; legacy rows valid (nullable, `SUSPENDIDA` unused). No feature flag. Deploy: migrate → backend → frontend.

## Open Questions

None blocking. Pre-existing `trailing_slash` inconsistency between `operaciones_d8_router` (False) and `clientes_router` (True) — new actions follow the Domain 8 convention; surface during apply.