# Tasks: Especialistas — Disponibilidad Real en Agenda

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 550–700 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (backend) → PR 2 (frontend) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Backend: worker availability endpoint | PR 1 | Base = main; 3 files; testable in isolation |
| 2 | Frontend: types, hook, and both pages | PR 2 | Base = main; depends on PR 1 for integration |

## Phase 1: Backend — Worker Availability Endpoint

- [x] 1.1 Create `backend/config/worker_views.py` with `worker_availability` view — session auth, `es_trabajador=True` check, lookup `Usuario→Especialista`, query `AgendaHabitualEspecialista` (activo, in-date-range, weekday match), query `AgendaExcepcionEspecialista` (activo, within week), merge shifts/blocks per day, return 7-day structure
- [x] 1.2 Create `backend/config/worker_urls.py` with `path("disponibilidad/", worker_availability)` pattern
- [x] 1.3 Modify `backend/config/api_urls.py` — add `path("trabajador/", include("config.worker_urls"))`
- [ ] 1.4 Write Django unit test for `worker_availability` view (mock Especialista queryset, test week boundary, habitual merge, exception override, empty state, auth rejection)

## Phase 2: Frontend — Types and Hook

- [x] 2.1 Create `frontend/aesthetic-clinic/src/types/worker.ts` — export `WeekAvailability`, `DayAvailability`, `Shift`, `Block` types matching API contract
- [x] 2.2 Create `frontend/aesthetic-clinic/src/hooks/useSpecialistAvailability.ts` — fetch `/api/admin/trabajador/disponibilidad/` with credentials; return `{ loading, availability, error, refetch }`; handle loading/error/empty states

## Phase 3: Frontend — Page Updates

- [x] 3.1 Update `frontend/aesthetic-clinic/src/pages/specialist/SpecialistAgendaPage.tsx` — remove `WEEK_AVAILABILITY` constant, import and call `useSpecialistAvailability()`, replace hardcoded data with real availability, render loading/error/empty states
- [x] 3.2 Update `frontend/aesthetic-clinic/src/pages/specialist/SpecialistPortalPage.tsx` — same refactor as SpecialistAgendaPage (remove constant, use hook, handle states)
- [ ] 3.3 Write React unit tests for `useSpecialistAvailability` hook (loading, error, data states) using fetch mock
- [ ] 3.4 Write component integration tests for SpecialistAgendaPage rendering real data (mock fetch or MSW handler)

## Phase 4: Integration Verification

- [ ] 4.1 Verify `GET /api/trabajador/disponibilidad/` returns 401 unauthenticated, 403 non-TRABAJADOR, 200 with correct shape for authenticated TRABAJADOR
- [ ] 4.2 Verify SpecialistAgendaPage renders shifts and blocks from API response
- [ ] 4.3 Verify SpecialistPortalPage renders shifts and blocks from API response
