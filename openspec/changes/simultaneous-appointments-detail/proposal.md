# Proposal: simultaneous-appointments-detail

## Intent

Currently the "citas simultaneas" section in the booking modal only shows a count and specialist names. Admins need to see which specific appointments are overlapping — client name and treatment — to make informed decisions about double-booking.

## Scope

### In Scope
- Extend backend `POST /api/admin/disponibilidad/concurrencia/` to return an `appointments` array per simultaneous appointment (client name, treatment name, hour, type)
- Update `AdminConcurrencyCheckResponse` type in `types/admin.ts` to include the appointments array
- Update `AdminProspectsPage.tsx` modal to render the appointments list (client + treatment per entry)

### Out of Scope
- Changes to other concurrency check usages (`useClientDetail.ts` reschedule flow) — same type but different context; UI display not required there
- Pagination or filtering of appointments — return all within the 1-hour window
- Modifying `get_concurrency()` logic beyond returning records instead of count

## Capabilities

### Modified Capabilities
- `admin-concurrency-check`: Requirements changing — endpoint response now includes appointment details, not just count and specialists. Delta spec will document new fields.

## Approach

1. **Backend** (`disponibilidad.py`): Replace count-only query with a query that returns the actual appointment records. Join across `CitasMedicas`, `CitasProspectos`, `CitasClientesLibres` to get client name (from FK) and treatment name (from `proc_estetico.proceso`). Return as `appointments` array in the response.

2. **Frontend type** (`types/admin.ts`): Add `appointments: Array<{ cliente_nombre: string, tratamiento: string, hora: string, tipo: string }>` to `AdminConcurrencyCheckResponse`.

3. **Frontend UI** (`AdminProspectsPage.tsx`): Replace the simple count + specialists list with a compact appointments list showing client name + treatment for each overlapping appointment.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/config/api/viewsets/disponibilidad.py` | Modified | `concurrencia` endpoint returns `appointments` array |
| `backend/operations/scheduling.py` | Modified | `get_concurrency()` returns records instead of count |
| `frontend/aesthetic-clinic/src/types/admin.ts` | Modified | `AdminConcurrencyCheckResponse` extended with appointments array |
| `frontend/aesthetic-clinic/src/pages/admin/AdminProspectsPage.tsx` | Modified | Modal renders appointments list |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Performance regression from JOINs on three appointment tables | Medium | Add `.only()` / `.values()` to limit fetched fields; the window is bounded (2 hours total) |
| Breaking change to `AdminConcurrencyCheckResponse` type | Low | Type is used in other components (`useClientDetail.ts`); new fields are additive, not destructive |
| Data exposure across branches | Low | `sucursal_id` filter already enforced; verify no leaks |

## Rollback Plan

1. Revert `disponibilidad.py` — restore `get_concurrency()` to return count and `presentes` only
2. Revert `types/admin.ts` — remove `appointments` field from `AdminConcurrencyCheckResponse`
3. Revert `AdminProspectsPage.tsx` — restore count + specialists display
All three are atomic, same-day reversions.

## Dependencies

- None — all data already exists in the three appointment tables; no new models or external services required

## Success Criteria

- [ ] `POST /api/admin/disponibilidad/concurrencia/` returns `appointments` array with client name, treatment, hour, type for each overlapping appointment
- [ ] `AdminConcurrencyCheckResponse` type includes the new appointments field
- [ ] Modal displays a list of appointments with client + treatment (not just count and specialist names)
- [ ] Existing concurrency check in other components (reschedule flow) continues to work with same type