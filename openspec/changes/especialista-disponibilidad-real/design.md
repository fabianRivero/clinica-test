# Design: Especialistas — Disponibilidad Real en Agenda

## Technical Approach

Backend delivers a new session-authenticated endpoint that aggregates `AgendaHabitualEspecialista` (filtered to active, in-date-range, matching weekday) and `AgendaExcepcionEspecialista` (active, within the week) into a 7-day structure. Frontend replaces the `WEEK_AVAILABILITY` constant with a `useSpecialistAvailability` hook that fetches from this endpoint.

## Architecture Decisions

### Decision: Endpoint lives in a new worker submodule

**Choice**: Create `config/worker_views.py` with a single view `worker_availability`, mounted at `trabajador/disponibilidad/`
**Alternatives considered**: Adding to existing `api_views.py` (already 4500+ lines, concerns mixed) or `admin_availability_views.py` (wrong namespace/auth model)
**Rationale**: The view uses session auth (not admin auth) and is worker-facing, not admin-facing. A dedicated submodule matches the existing URL convention (`/api/trabajador/...`) and keeps auth logic clean.

### Decision: Week boundary uses Python weekday() with explicit Django mapping

**Choice**: `python_to_django_weekday = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 0}`
**Alternatives considered**: Django's `date.isoweekday()` (returns 1=Lunes, 7=Domingo — wrong for DiaSemana which starts at 0=Domingo)
**Rationale**: `DiaSemana` enum is 0=Domingo, 1=Lunes, … 6=Sábado (standard Python `date.weekday()` ordering shifted by one). The explicit dict is verbose but unambiguous and matches the spec's documented mapping.

### Decision: BLOQUEAR exception clears habitual shifts for that day

**Choice**: If a `BLOQUEAR` exception exists for a day, that day's `shifts` array is empty and `blocks` contains the exception detail.
**Alternatives considered**: Return both habitual shifts and BLOQUEAR block (confusing UI), or treat BLOQUEAR as a filter on appointment scheduling only (requires broader change)
**Rationale**: Per spec requirement "BLOQUEAR overrides habitual day" — a full-day block means no availability, consistent with the empty-state behavior on both frontend pages.

### Decision: Frontend uses a custom hook, not a generic fetch wrapper

**Choice**: `useSpecialistAvailability` hook with `{ loading, availability, error, refetch }` shape
**Alternatives considered**: Generic `useApiResource('/api/trabajador/disponibilidad/')` from existing `useApiResource` hook
**Rationale**: The endpoint is specialist-specific and returns a fixed week structure. A dedicated hook keeps type safety tight and matches the spec's `WeekAvailability` shape directly. The existing `useApiResource` is geared toward CRUD collections.

## Data Flow

```
Browser (SpecialistAgendaPage)
    │ fetch('/api/trabajador/disponibilidad/', { credentials: 'include' })
    ▼
Django: worker_availability view
    │ request.user → Usuario → Especialista
    ▼
Query AgendaHabitualEspecialista (activo=True, fecha_inicio≤today≤fecha_fin, dias contains weekday)
    │
Query AgendaExcepcionEspecialista (activo=True, fecha in [mon..sun])
    │
Merge per day: shifts (HABITUAL + EXCEPTION_AGREGAR), blocks (BLOQUEAR)
    │
Return { weekStart, weekEnd, days: [{ date, weekdayLabel, weekdayCode, branchName, shifts, blocks }] }
    │
Browser: setAvailability(data) → selectedDay derived → UI renders
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/config/worker_views.py` | Create | `worker_availability` view with session-auth, specialist lookup, week aggregation |
| `backend/config/worker_urls.py` | Create | URL patterns for `/trabajador/disponibilidad/` |
| `backend/config/api_urls.py` | Modify | Add `path("trabajador/", include("config.worker_urls"))` |
| `frontend/aesthetic-clinic/src/hooks/useSpecialistAvailability.ts` | Create | Hook fetching and parsing the availability endpoint |
| `frontend/aesthetic-clinic/src/pages/specialist/SpecialistAgendaPage.tsx` | Modify | Remove `WEEK_AVAILABILITY` constant; use `useSpecialistAvailability()` hook |
| `frontend/aesthetic-clinic/src/pages/specialist/SpecialistPortalPage.tsx` | Modify | Same refactor as SpecialistAgendaPage |

## Interfaces / Contracts

### Backend Response

```python
{
    "weekStart": "YYYY-MM-DD",   # Monday
    "weekEnd": "YYYY-MM-DD",     # Sunday
    "days": [
        {
            "date": "YYYY-MM-DD",
            "weekdayLabel": "Lunes|Martes|...",   # from DiaSemana label
            "weekdayCode": 0..6,                   # 0=Lunes .. 6=Domingo
            "branchName": "Sucursal Norte",
            "shifts": [
                {"start": "HH:MM", "end": "HH:MM", "source": "HABITUAL"},
                {"start": "HH:MM", "end": "HH:MM", "source": "EXCEPTION_AGREGAR"},
            ],
            "blocks": [
                {"reason": "Vacaciones", "type": "BLOQUEAR"},
            ]
        },
        ...
    ]
}
```

### Frontend Types

```typescript
type WeekAvailability = {
  weekStart: string
  weekEnd: string
  days: DayAvailability[]
}
type DayAvailability = {
  date: string
  weekdayLabel: string
  weekdayCode: number
  branchName: string
  shifts: Shift[]
  blocks: Block[]
}
type Shift = { start: string; end: string; source: 'HABITUAL' | 'EXCEPTION_AGREGAR' }
type Block = { reason: string; type: 'BLOQUEAR' }
```

### Auth / Error Cases

| Request | Response |
|---------|----------|
| Unauthenticated | 401 `{"detail": "Autenticacion requerida."}` |
| Authenticated but not TRABAJADOR | 403 `{"detail": "No tienes acceso a esta información."}` |
| Authenticated TRABAJADOR with no agenda | 200 with all 7 days having `shifts: []`, `blocks: [{"reason": "Sin agenda configurada", "type": "BLOQUEAR"}]` |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `worker_availability` view logic (week boundary, merge, mapping) | Django test with mocked Especialista queryset |
| Integration | Full request cycle with session auth | Django client test with `force_login` as TRABAJADOR user |
| Unit (frontend) | `useSpecialistAvailability` hook state transitions | React Testing Library with mocked fetch |
| Integration (frontend) | SpecialistAgendaPage renders real data after fetch | Component test with MSW or fetch mock |

## Migration / Rollout

No database migration required — models are unchanged. Rollout is a single atomic commit:

1. Deploy backend with new endpoint and URL route
2. Deploy frontend with hook and updated pages
3. Immediate rollback: revert both deployments or remove the route/hook

## Open Questions

- [ ] Specialist with `es_trabajador=True` but no `Especialista` record linked to the user — does the current auth flow handle this gracefully, or does the FK relationship already prevent it?
- [ ] Should the endpoint be cached? The data changes when an admin modifies an agenda or exception. Add cache invalidation on those events, or leave uncached for simplicity?