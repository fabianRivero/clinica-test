# Specialist Self-Availability Specification

## Purpose

The system SHALL provide authenticated specialists with a real-time view of their weekly availability combining habitual schedules and exception overrides.

## API Contract

**Endpoint**: `GET /api/trabajador/disponibilidad/`
**Authentication**: Session authentication, TRABAJADOR role required
**Scope**: Current week (Monday to Sunday)

### Response Shape

```json
{
  "weekStart": "2026-06-02",
  "weekEnd": "2026-06-08",
  "days": [
    {
      "date": "2026-06-02",
      "weekdayLabel": "Martes",
      "weekdayCode": 1,
      "branchName": "Sucursal Norte",
      "shifts": [
        { "start": "08:00", "end": "14:00", "source": "HABITUAL" }
      ],
      "blocks": [
        { "reason": "Bloqueo por capacitacion interna (todo el dia)", "type": "BLOQUEAR" }
      ]
    }
  ]
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `weekStart` | string (date) | Monday of current week, ISO format |
| `weekEnd` | string (date) | Sunday of current week, ISO format |
| `days[].date` | string (date) | ISO format YYYY-MM-DD |
| `days[].weekdayLabel` | string | Spanish day name (Lunes, Martes, etc.) |
| `days[].weekdayCode` | integer | 0=Lunes .. 6=Domingo |
| `days[].branchName` | string | Specialist's `sucursal_base.nombre` |
| `days[].shifts` | array | Active work ranges for this day |
| `days[].shifts[].start` | string (time) | HH:MM format |
| `days[].shifts[].end` | string (time) | HH:MM format |
| `days[].shifts[].source` | string | `HABITUAL` or `EXCEPTION_AGREGAR` |
| `days[].blocks` | array | Full-day blocks and reasons |
| `days[].blocks[].reason` | string | Human-readable block description |
| `days[].blocks[].type` | string | Always `BLOQUEAR` |

---

## Requirements

### Requirement: Return current week availability

The endpoint MUST return exactly 7 day entries (Monday through Sunday) for the current week. Week boundaries MUST be calculated using `date.today()` and `timedelta(days=date.today().weekday())`.

#### Scenario: Authenticated specialist requests availability

- GIVEN the request is authenticated as a TRABAJADOR user
- WHEN `GET /api/trabajador/disponibilidad/` is called
- THEN the response status SHALL be `200`
- AND `weekStart` SHALL be the Monday of the current week
- AND `weekEnd` SHALL be the Sunday of the current week
- AND `days` array SHALL contain exactly 7 entries

---

### Requirement: Aggregate habitual shifts

For each day, the system MUST query `AgendaHabitualEspecialista` where `fecha_inicio <= date <= fecha_fin`, `activo=True`, and the specialist's habitual agenda includes the weekday. Each matching agenda adds one shift with `source: HABITUAL`.

**DiaSemana mapping**: Python weekday (0=Mon .. 6=Sun) to Django choices (0=Sun, 1=Mon .. 6=Sat):
`Python 0→Django 1, 1→2, 2→3, 3→4, 4→5, 5→6, 6→0`

#### Scenario: Specialist with habitual schedule only

- GIVEN a specialist has `AgendaHabitualEspecialista` with `fecha_inicio <= 2026-06-02 <= fecha_fin`, `activo=True`
- AND that agenda includes Tuesday (weekday 1) in its `dias`
- WHEN the specialist calls `GET /api/trabajador/disponibilidad/`
- THEN Tuesday's `shifts` SHALL contain one entry with `start`, `end`, `source: "HABITUAL"`

#### Scenario: Multiple habitual rules merged on same day

- GIVEN a specialist has two `AgendaHabitualEspecialista` records active for 2026-06-02
- AND both include Tuesday (weekday 1) in their `dias`
- WHEN the specialist calls `GET /api/trabajador/disponibilidad/`
- THEN Tuesday's `shifts` SHALL contain two entries
- AND both SHALL have `source: "HABITUAL"`
- AND each SHALL have its respective `start`/`end` from the matching agenda

---

### Requirement: Apply exception overrides

For each day, the system MUST query `AgendaExcepcionEspecialista` where `fecha = date` and `activo=True`.

- `AGREGAR` exceptions MUST be appended to `shifts` with `source: "EXCEPTION_AGREGAR"`
- `BLOQUEAR` exceptions MUST be appended to `blocks` with the exception's `detalle` as `reason` and `type: "BLOQUEAR"`

#### Scenario: Exception adds shift on habitual day

- GIVEN a specialist has habitual shift on Tuesday 08:00–14:00
- AND an `AgendaExcepcionEspecialista` exists for 2026-06-02 with `tipo=AGREGAR`, `hora_inicio=15:00`, `hora_fin=18:00`, `activo=True`
- WHEN the specialist calls `GET /api/trabajador/disponibilidad/`
- THEN Tuesday's `shifts` SHALL contain two entries
- AND one SHALL have `source: "HABITUAL"` with `start: "08:00", end: "14:00"`
- AND one SHALL have `source: "EXCEPTION_AGREGAR"` with `start: "15:00", end: "18:00"`

#### Scenario: BLOQUEAR exception overrides habitual day

- GIVEN a specialist has habitual shift on Tuesday 08:00–14:00
- AND an `AgendaExcepcionEspecialista` exists for 2026-06-02 with `tipo=BLOQUEAR`, `detalle="Vacaciones"`, `activo=True`
- WHEN the specialist calls `GET /api/trabajador/disponibilidad/`
- THEN Tuesday's `shifts` SHALL be empty
- AND Tuesday's `blocks` SHALL contain one entry with `reason: "Vacaciones"`, `type: "BLOQUEAR"`

---

### Requirement: Report branch name

The `branchName` field for every day entry MUST be the `nombre` of the specialist's `sucursal_base`.

#### Scenario: Branch name is returned for all days

- GIVEN a specialist has `sucursal_base.nombre = "Sucursal Norte"`
- WHEN the specialist calls `GET /api/trabajador/disponibilidad/`
- THEN every day entry SHALL have `branchName: "Sucursal Norte"`

---

### Requirement: Empty state

When a day has no habitual shifts AND no exception blocks, the system MUST include one block with `reason: "Sin agenda configurada"` and `type: "BLOQUEAR"`.

#### Scenario: Specialist with no schedule at all

- GIVEN a specialist has no `AgendaHabitualEspecialista` records
- AND no `AgendaExcepcionEspecialista` records for any day of the week
- WHEN the specialist calls `GET /api/trabajador/disponibilidad/`
- THEN every day entry SHALL have `shifts: []`
- AND every day entry SHALL have one block with `reason: "Sin agenda configurada"`, `type: "BLOQUEAR"`

---

### Requirement: Authentication and authorization

The endpoint MUST return `401 Unauthorized` for unauthenticated requests and `403 Forbidden` for authenticated users who are not TRABAJADOR role.

#### Scenario: Unauthenticated request returns 401

- GIVEN no user is authenticated
- WHEN `GET /api/trabajador/disponibilidad/` is called
- THEN the response status SHALL be `401`

#### Scenario: Non-TRABAJADOR authenticated user receives 403

- GIVEN an authenticated user exists but has no `Especialista` record linked to a TRABAJADOR user
- WHEN `GET /api/trabajador/disponibilidad/` is called
- THEN the response status SHALL be `403`

---

## Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| Specialist has no `Especialista` record | 403 response |
| Weekday with both HABITUAL and EXCEPTION_AGREGAR | Shifts merged, ordered by start time |
| AGREGAR exception on day with no habitual | Shifts contains only the exception shift |
| Exception with `activo=False` | Ignored (not included) |
| Habitual agenda where `fecha_inicio > today` | Ignored for current week |
| `hora_inicio == hora_fin` (zero-length shift) | Include as `{start, end}` with same values |