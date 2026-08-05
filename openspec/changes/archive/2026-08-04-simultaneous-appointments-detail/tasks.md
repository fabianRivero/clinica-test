# Tasks: simultaneous-appointments-detail

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~180–240 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Full implementation | PR 1 | All 4 files; backend → frontend |

## Phase 1: Backend — Query Function

- [x] 1.1 In `backend/operations/scheduling.py`, add `get_concurrency_detail(sucursal_id, fecha, hora_inicio, hora_fin)` using `.values()` + `QuerySet.union()` across `CitasMedicas`, `CitasProspectos`, `CitasClientesLibres`
- [x] 1.2 Use `Coalesce` to render null `operacion__cliente__nombre` on `CitaMedica` as "Cliente no registrado" (do NOT filter out nulls)
- [x] 1.3 Annotate each queryset with `tipo` via `Value(...)` using `CharField()` output field
- [x] 1.4 Return ordered by `fecha_hora`; let DB count be the concurrency source

## Phase 2: Backend — ViewSet Integration

- [x] 2.1 In `backend/config/api/viewsets/disponibilidad.py`, update `concurrencia()` action to call `get_concurrency_detail()` instead of `get_concurrency()`
- [x] 2.2 Merge appointment list into response under key `appointments`; preserve `concurrency` as `len(appointments)` for backward compatibility
- [x] 2.3 Keep `presentes`, `hora_inicio`, `hora_fin`, `hora_seleccionada` unchanged

## Phase 3: Frontend — Type and Modal

- [x] 3.1 In `frontend/aesthetic-clinic/src/types/admin.ts`, add `appointments?: Array<{cliente_nombre: string | null, tratamiento_nombre: string | null, hora: string, tipo: 'CitasMedicas' | 'CitasProspectos' | 'CitasClientesLibres'}>` to `AdminConcurrencyCheckResponse`
- [x] 3.2 In `AdminProspectsPage.tsx`, add a "Citas simultáneas" section to the concurrency modal that iterates `concurrencyInfo?.appointments ?? []` and renders each entry with client name (use "Cliente no registrado" fallback), treatment, time, and type badge
- [x] 3.3 Gracefully handle empty `appointments` array (render message "Sin citas simultáneas")

## Phase 4: Verification

- [ ] 4.1 Unit test `get_concurrency_detail()`: seed 3 appointment types, verify shape and count match existing `get_concurrency()`
- [ ] 4.2 Unit test null client: `CitaMedica` with null `operacion` renders "Cliente no registrado" in result
- [ ] 4.3 Integration test `POST /disponibilidad/concurrencia/`: assert `appointments` array in response with correct fields
- [ ] 4.4 Manual verification: open concurrency modal in admin panel, confirm appointments list renders with placeholder for unregistered clients