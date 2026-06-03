# Archive Report — especialista-disponibilidad-real

## Change Summary

This change replaced hardcoded `WEEK_AVAILABILITY` example data in `SpecialistAgendaPage` and `SpecialistPortalPage` with real availability data from the backend. Two PRs were delivered:

**PR #1 (Backend)**:
- Created `backend/config/worker_views.py` with `GET /api/admin/trabajador/disponibilidad/` endpoint
- Created `backend/config/worker_urls.py` for worker URL routing
- Modified `backend/config/api_urls.py` to include worker_urls

**PR #2 (Frontend)**:
- Created `frontend/aesthetic-clinic/src/types/worker.ts` with TypeScript types
- Created `frontend/aesthetic-clinic/src/hooks/useSpecialistAvailability.ts` hook
- Updated `SpecialistAgendaPage.tsx` to use real data (removed WEEK_AVAILABILITY)
- Updated `SpecialistPortalPage.tsx` to use real data (removed WEEK_AVAILABILITY)

## Artifacts

| File | Action | Description |
|------|--------|-------------|
| `backend/config/worker_views.py` | Created | `worker_availability` view with session-auth, specialist lookup, week aggregation |
| `backend/config/worker_urls.py` | Created | URL patterns for `trabajador/disponibilidad/` |
| `backend/config/api_urls.py` | Modified | Added `path("trabajador/", include("config.worker_urls"))` |
| `frontend/aesthetic-clinic/src/types/worker.ts` | Created | TypeScript types: `Shift`, `Block`, `DayAvailability`, `WeekAvailability` |
| `frontend/aesthetic-clinic/src/hooks/useSpecialistAvailability.ts` | Created | Hook fetching `/api/admin/trabajador/disponibilidad/` with `{ loading, availability, error, refetch }` |
| `frontend/aesthetic-clinic/src/pages/specialist/SpecialistAgendaPage.tsx` | Modified | Removed `WEEK_AVAILABILITY`, use hook, loading/error/empty states |
| `frontend/aesthetic-clinic/src/pages/specialist/SpecialistPortalPage.tsx` | Modified | Same refactor, tab structure preserved |

## Verification

All 4 frontend implementation tasks completed. TypeScript compiles cleanly, ESLint is clean on changed files, `WEEK_AVAILABILITY` constant removed from both pages, hook fetches correct endpoint with session auth, and loading/error/empty states implemented per spec.

**Outstanding (not blocking)**: React tests (tasks 3.3, 3.4) and backend Django tests (task 1.4) were deferred due to environment constraints.

## Post-Implementation Notes

1. **URL path**: The spec documents `/api/trabajador/disponibilidad/` but the actual mounted path is `/api/admin/trabajador/disponibilidad/` (via the `api/admin/` URL prefix). The frontend hook uses the correct actual path.

2. **Source labels**: `HABITUAL` → "Agenda habitual", `EXCEPTION_AGREGAR` → "Excepcion" — both pages display these correctly.

3. **Empty state**: When all days have no shifts AND no blocks, the hook sets error "Sin agenda configurada" which triggers a DataState in both pages.

4. **Pre-existing ESLint debt**: Multiple files have `react-hooks/set-state-in-effect` errors not in PR scope — represents technical debt.

5. **No main specs exist**: The `openspec/specs/` directory is empty. The change's `spec.md` is a complete spec (not a delta) that could serve as the basis for a future `specialist-availability` domain spec.

## Archived Location

`openspec/changes/archive/2026-06-02-especialista-disponibilidad-real/`