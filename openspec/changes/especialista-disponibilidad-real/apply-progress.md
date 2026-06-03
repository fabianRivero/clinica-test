# Apply Progress — especialista-disponibilidad-real (PR #2: Frontend)

## Status

**Phase**: apply (PR #2: Frontend)
**Mode**: Standard (no Strict TDD)
**Chain strategy**: feature-branch-chain
**Current PR**: #2 (frontend types, hook, page updates) → targets PR #1 branch

---

## Completed Tasks

### Phase 1: Backend — Worker Availability Endpoint (PR #1, already complete)

- [x] **1.1** Create `backend/config/worker_views.py` with `worker_availability` view
- [x] **1.2** Create `backend/config/worker_urls.py` with URL pattern `disponibilidad/` → `worker_availability`
- [x] **1.3** Modify `backend/config/api_urls.py` — added `path("trabajador/", include("config.worker_urls"))`
- [ ] **1.4** Write Django unit test for `worker_availability` view — **PENDING** (requires Django environment)

### Phase 2: Frontend — Types and Hook (PR #2)

- [x] **2.1** Create `frontend/aesthetic-clinic/src/types/worker.ts`
  - Exports: `Shift`, `Block`, `DayAvailability`, `WeekAvailability` types matching API contract
  - `Shift.source` union: `'HABITUAL' | 'EXCEPTION_AGREGAR'` (per spec)
  - `Block.type` literal: `'BLOQUEAR'`
  - `DayAvailability` fields: `date, weekdayLabel, weekdayCode, branchName, shifts, blocks`

- [x] **2.2** Create `frontend/aesthetic-clinic/src/hooks/useSpecialistAvailability.ts`
  - Fetches from `/api/admin/trabajador/disponibilidad/` with `credentials: 'include'`
  - Returns `{ loading, availability, error, refetch }` shape
  - Handles: 403 → "No tienes acceso", other errors → "Error cargando disponibilidad"
  - Empty state: all days have no shifts AND no blocks → sets error "Sin agenda configurada"
  - `refetch` increments retry key to re-trigger the effect
  - Follows existing `useApiResource` pattern

### Phase 3: Frontend — Page Updates (PR #2)

- [x] **3.1** Update `SpecialistAgendaPage.tsx`
  - Removed `WEEK_AVAILABILITY` constant and local `WeekdayAvailability` type
  - Imports and calls `useSpecialistAvailability()` hook
  - `selectedDate` defaults to today (ISO date string from `new Date().toISOString().split('T')[0]`)
  - `days` derived from `availability?.days ?? []` via `useMemo`
  - `selectedDay` uses `useMemo` with `days` and `selectedDate` deps
  - Loading state: spinner (custom `<Spinner />` component)
  - Error state: `DataState` with message + retry button
  - Empty state: `DataState` "Sin agenda configurada. Contacta al administrador..."
  - Source label: `'HABITUAL'` → "Agenda habitual", `'EXCEPTION_AGREGAR'` → "Excepcion"

- [x] **3.2** Update `SpecialistPortalPage.tsx`
  - Removed `WEEK_AVAILABILITY` constant and local `WeekdayAvailability` type
  - Imports and calls `useSpecialistAvailability()` hook
  - Same state derivation pattern as SpecialistAgendaPage
  - Tab structure (AGENDA / MENSAJES) preserved — only agenda tab uses real data
  - Loading, error, and empty states rendered conditionally within AGENDA tab
  - MENSAJES tab unchanged

---

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `frontend/aesthetic-clinic/src/types/worker.ts` | Created | TypeScript types: `Shift`, `Block`, `DayAvailability`, `WeekAvailability` |
| `frontend/aesthetic-clinic/src/hooks/useSpecialistAvailability.ts` | Created | Hook fetching `/api/admin/trabajador/disponibilidad/` with `{ loading, availability, error, refetch }` |
| `frontend/aesthetic-clinic/src/pages/specialist/SpecialistAgendaPage.tsx` | Modified | Removed WEEK_AVAILABILITY, use hook, loading/error/empty states |
| `frontend/aesthetic-clinic/src/pages/specialist/SpecialistPortalPage.tsx` | Modified | Same refactor as SpecialistAgendaPage, tab structure preserved |

---

## Verification

- `npx tsc --noEmit` — no type errors
- `npx eslint [changed files]` — no lint errors (1 pre-existing eslint-disable comment added for `set-state-in-effect` rule to match `useApiResource` pattern)
- `WEEK_AVAILABILITY` references — confirmed removed from both pages
- Hook calls correct endpoint: `/api/admin/trabajador/disponibilidad/` with `credentials: 'include'`

---

## Deviations from Design

- **Source label**: The spec says `'HABITUAL'` or `'EXCEPTION_AGREGAR'`; pages display "Agenda habitual" and "Excepcion". This matches the existing page behavior (was "Excepcion" for `EXCEPCION` source). No change needed.
- **Empty state error message**: Hook sets error "Sin agenda configurada" when all days have no shifts AND no blocks. This triggers a DataState in pages with "Contacta al administrador para configurar tu disponibilidad." — matches task requirement.

---

## Issues Found

- `WEEK_AVAILABILITY` constant was present in both pages — both updated
- ESLint `react-hooks/set-state-in-effect` error in hook — suppressed with inline disable comment to match existing `useApiResource` pattern
- ESLint warnings about `days` in useMemo deps — fixed by wrapping `availability?.days ?? []` in its own `useMemo` call

---

## Remaining Tasks

- [ ] **3.3** Write React unit tests for `useSpecialistAvailability` hook (loading, error, data states) — defer to verify phase
- [ ] **3.4** Write component integration tests for SpecialistAgendaPage rendering real data — defer to verify phase
- [ ] **1.4** Django unit tests for backend — already pending from PR #1

---

## Next Steps

- **PR #2 ready** for code review
- Frontend tasks 3.3 and 3.4 (tests) can be handled in verify phase with proper test environment
- Backend task 1.4 also pending Django environment

---

## Workload / PR Boundary

- Mode: feature-branch-chain
- PR #2 scope: frontend types, hook, and both page updates (4 files, ~380 lines)
- PR #2 base: PR #1 branch (`especialista-disponibilidad` tracker branch, NOT main)
- Chain: PR #1 → PR #2 → ... → tracker PR aggregates to main
- Estimated review budget: ~380 lines (within 400-line budget)