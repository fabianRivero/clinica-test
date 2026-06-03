# Proposal: Especialistas — Disponibilidad Real en Agenda

## Intent

Replace hardcoded `WEEK_AVAILABILITY` static data in SpecialistAgendaPage and SpecialistPortalPage with real availability data fetched from a new backend endpoint, so specialists see their actual weekly schedule (habitual agenda + exceptions) without admin intervention.

## Scope

### In Scope
- New backend endpoint `GET /api/trabajador/disponibilidad/` returning the current week (Mon–Sun) availability for the authenticated specialist
- Combine `AgendaHabitualEspecialista` (active ranges where today is between fecha_inicio and fecha_fin, filtered by day-of-week) with `AgendaExcepcionEspecialista` (AGREGAR and BLOQUEAR exceptions for current week)
- SpecialistAgendaPage replaces `WEEK_AVAILABILITY` constant with API call; renders shifts and blocks
- SpecialistPortalPage same refactor — unified data source across both pages
- Auth: endpoint resolves `Especialista.objects.get(usuario=request.user)` from the logged-in session

### Out of Scope
- Admin-facing availability management (already exists)
- Modifying or creating agenda records via this endpoint
- Multi-branch or cross-specialist queries
- Frontend E2E tests (Playwright) for this feature

## Capabilities

### New Capabilities
- `specialist-self-availability`: Specialist can view their own weekly availability (habitual schedule + exceptions) via a dedicated authenticated endpoint. Returns structured day-by-day blocks with source attribution (HABITUAL vs EXCEPCION) and full-day blocks.

### Modified Capabilities
- None (existing appointment-states and other specs unaffected)

## Approach

**Backend**: New viewset/endpoint in staff or operations, authenticated as TRABAJADOR role. Query current week boundaries (Monday and Sunday). For each day:
1. Query `AgendaExcepcionEspecialista` for that day → add AGREGAR ranges as shifts, BLOQUEAR as full-day blocks
2. Query `AgendaHabitualEspecialista` where `fecha_inicio <= today <= fecha_fin` and the agenda's `dias` includes the weekday
3. Merge: exception shifts supplement habitual shifts; exception BLOQUEAR overrides habitual (full-day block)
4. Return `{ week: [{ date, weekday_label, branch, shifts: [{start, end, source}], blocks: [{reason}] }] }`

**Frontend**: Both pages add `useEffect` fetching `/api/trabajador/disponibilidad/` on mount. Replace static `WEEK_AVAILABILITY` with state-backed data. Maintain same UI components and layout — only data source changes.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/config/api_views.py` | Modified | New endpoint `GET /api/trabajador/disponibilidad/` |
| `backend/operations/models.py` | Read-only | AgendaHabitualEspecialista, AgendaExcepcionEspecialista |
| `frontend/aesthetic-clinic/src/pages/specialist/SpecialistAgendaPage.tsx` | Modified | Remove static WEEK_AVAILABILITY, consume API |
| `frontend/aesthetic-clinic/src/pages/specialist/SpecialistPortalPage.tsx` | Modified | Same refactor as AgendaPage |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| DiaSemana enum mismatch (Python 0=Lunes vs Django choices) | Medium | Explicit weekday mapping; verify with seed data |
| Week boundary edge case (Mon 00:00 vs current time) | Low | Use date-only comparisons, not datetime |
| Specialist with no agenda records returns empty array | Low | Frontend already handles empty shifts via DataState |
| Auth: specialist has no related Usuario record | Low | Return 401 if Especialista lookup fails |

## Rollback Plan

1. Revert backend endpoint (remove view/URL route)
2. Restore `WEEK_AVAILABILITY` constant in both TSX files
3. No database migration needed — models unchanged
4. Deploy in a single commit to allow immediate revert

## Dependencies

- Django session authentication (existing — TRABAJADOR role)
- `Especialista.usuario` FK relationship to auth.User (already exists)
- `AgendaHabitualEspecialista.dias` relation via `AgendaHabitualDia` (already exists)

## Success Criteria

- [ ] `GET /api/trabajador/disponibilidad/` returns 200 for authenticated specialist with agenda records
- [ ] Response contains 7 days (Mon–Sun) with shifts having `start`, `end`, `source` fields
- [ ] Blocks (BLOQUEAR exceptions or no-habitual-days) appear with `reason` field
- [ ] SpecialistAgendaPage renders real data with no hardcoded dates
- [ ] SpecialistPortalPage renders real data with no hardcoded dates
- [ ] Unauthenticated request returns 401
- [ ] Specialist with no agenda returns `{ week: [...] }` with all days having empty shifts and blocks