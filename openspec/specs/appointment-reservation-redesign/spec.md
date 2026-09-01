# Appointment Reservation Redesign Specification

## Overview

This spec defines the extended reservation flow for medical appointments: planning data captured at reservation, real data captured at close, machinery catalog with role-scoped visibility, and always-editable notes & photos on each cita. It coexists with `appointment-states` spec, which owns the state machine.

## Goals

- Capture both the plan and the actual for every cita.
- Surface machinery conflicts to the admin without blocking the reservation.
- Give specialists a read-only view of the citas they are assigned to.
- Make cita notes & photos always editable for relevant roles.

## Non-Goals

- Backfilling old citas with new fields.
- Changing biometric confirmation flow.
- Changing CitaProspecto or CitaClienteLibre flows.
- Adding a slot-level reservation lock on maquinaria.

## Data Model Requirements

### Requirement: CitaMedica planning fields

`CitaMedica` MUST support the following additional fields, all OPTIONAL:
- `duracionEstimadaMinutos` (positive int, 1..480)
- `descripcionGeneral` (text)
- `notasPrevias` (text)
- `notasPost` (text)
- `fotoAntes` (image, optional)
- `fotoDespues` (image, optional)
- `procedimientoPlanificado` (text)
- `zonaCuerpoPlanificada` (text, max 200)

#### Scenario: Reservation with no optional fields

- GIVEN an admin creates a reservation
- WHEN none of the optional fields are provided
- THEN the reservation MUST succeed
- AND the cita MUST be persisted with all optional fields empty/null
- AND no validation error SHALL be raised.

#### Scenario: Reservation with duracion exceeding the limit

- GIVEN an admin provides `duracionEstimadaMinutos` greater than 480
- WHEN the reservation is submitted
- THEN the backend SHALL respond with HTTP 400
- AND the response SHALL include a validation error for `duracionEstimadaMinutos`.

---

### Requirement: CitaMedica real-time fields

`CitaMedica` MUST support the following additional fields, populated only at close time:
- `horaRealInicio` (datetime, optional)
- `horaRealFin` (datetime, optional)
- `procedimientoRealizado` (text)
- `zonaCuerpoRealizada` (text, max 200)

#### Scenario: Close with valid real hours

- GIVEN a cita in `PROGRAMADA`
- WHEN admin submits close with `horaRealFin > horaRealInicio >= fechaHora - 1h`
- THEN the backend SHALL transition the cita to `REALIZADA_PENDIENTE_VERIFICACION`
- AND SHALL persist the real fields.

#### Scenario: Close with invalid real hours

- GIVEN a cita in `PROGRAMADA`
- WHEN admin submits close with `horaRealFin <= horaRealInicio`
- THEN the backend SHALL respond with HTTP 400
- AND the cita state SHALL remain `PROGRAMADA`.

---

### Requirement: Maquinaria catalog

The system MUST provide a `Maquinaria` catalog with: nombre, marca (optional), descripción (optional), cantidadTotal (positive int, default 1), sucursal (nullable FK; null = global), activo (boolean).

#### Scenario: Admin general sees all maquinaría

- GIVEN an authenticated admin general
- WHEN they list the maquinaría catalog
- THEN the response MUST include global maquinaría AND maquinaría assigned to any sucursal.

#### Scenario: Admin de sucursal sees globales plus own

- GIVEN an authenticated admin de sucursal assigned to sucursal S
- WHEN they list the maquinaría catalog
- THEN the response MUST include maquinaría with `sucursal IS NULL` (globales) AND maquinaría with `sucursal = S`
- AND MUST NOT include maquinaría of other sucursales.

#### Scenario: Admin de sucursal cannot edit global maquinaría

- GIVEN an authenticated admin de sucursal
- WHEN they attempt to PUT a maquinaría with `sucursal IS NULL`
- THEN the backend SHALL respond with HTTP 403.

---

### Requirement: CitaMaquinaria items

Each cita MAY have zero or more `CitaMaquinaria` rows. Each row carries `cantidad` and `planificada` (boolean: true = reserved at booking, false = actually used at close).

#### Scenario: Multiple machinery rows in a single cita

- GIVEN a cita
- WHEN the admin reserves two distinct maquinaría with different `cantidad` values
- THEN the system MUST persist two `CitaMaquinaria` rows with the correct `cantidad`
- AND both MUST be marked `planificada = true`.

#### Scenario: Removing maquinaría from a cita

- GIVEN a cita with N `CitaMaquinaria` rows
- WHEN the admin removes one via the UI
- THEN the system MUST delete only that row
- AND MUST NOT touch the other N-1 rows.

---

### Requirement: CitaEspecialista items

Each cita MAY have zero or more `CitaEspecialista` rows. Each row carries `planificada` (boolean: true = expected, false = actually attended).

#### Scenario: Specialist appears in both planned and attended lists

- GIVEN a cita where the admin planned specialist S
- AND at close, the admin records S as having attended
- WHEN persisted
- THEN the cita MUST have two `CitaEspecialista` rows for S: one `planificada=true` and one `planificada=false`.

#### Scenario: Specialist appears only in planned

- GIVEN a cita where the admin planned specialist S but did NOT record attendance
- WHEN persisted
- THEN the cita MUST have exactly one `CitaEspecialista` row for S with `planificada=true`.

---

## API Requirements

### Requirement: Reservation endpoint extended payload

`POST /api/admin/clientes/<id>/operaciones/<opId>/reservar/` MUST accept the following OPTIONAL fields in addition to the current `branchId` and `dateTime`:
- `duracionEstimadaMinutos`
- `descripcionGeneral`
- `notasPrevias`
- `procedimientoPlanificado`
- `zonaCuerpoPlanificada`
- `especialistasPlanificados` (array of specialist IDs)
- `maquinariaPlanificada` (array of `{maquinariaId, cantidad}`)

#### Scenario: Reservation with specialists and machinery

- GIVEN an admin opens the reservation modal
- WHEN they fill the new optional fields and submit
- THEN the backend MUST persist them on the new `CitaMedica`
- AND MUST persist the planned `CitaEspecialista` and `CitaMaquinaria` rows.

---

### Requirement: Availability check extended response

`GET /api/admin/disponibilidad/concurrencia/` MUST continue to return the existing fields (`concurrency`, `horaInicio`, `horaFin`, `appointments`, `presentes`) AND MAY additionally return `maquinariaEnUso` (list of `{maquinariaId, nombre, cantidad, citaId, fechaHora}`) for the time window.

#### Scenario: Availability check returns existing fields

- GIVEN any sucursal, fecha, hora
- WHEN the admin clicks "Verificar disponibilidad"
- THEN the response MUST include `concurrency`, `appointments`, `presentes`
- AND MUST NOT remove or rename any existing field.

---

### Requirement: Machinery conflict check endpoint

`GET /api/admin/disponibilidad/check-maquinaria/` MUST accept query params `sucursalId`, `fecha`, `hora`, `duracionMinutos`, `maquinariaIds` (comma-separated) and return a list of conflicts per maquinaría.

A conflict on maquinaría M with `cantidadSolicitada` exists when the sum of `CitaMaquinaria.cantidad` for M where `planificada=true` AND the cita's `fechaHora` is within `[hora, hora + duracionMinutos]` AND the cita is in `PROGRAMADA` / `REALIZADA_PENDIENTE_VERIFICACION` is such that `cantidadSolicitada + suma > M.cantidadTotal`.

#### Scenario: Admin queries conflict for a single maquinaría

- GIVEN an admin selects maquinaría M (cantidadTotal=1) for a 1-hour window
- AND another cita already has 1 unit of M in the same window
- WHEN the admin clicks "Verificar disponibilidad"
- THEN the endpoint MUST return a conflict for M
- AND the conflict MUST include `cantidadSolicitada`, `cantidadDisponible`, and the list of `citasQueLaUsan`.

#### Scenario: Admin queries conflict for a free maquinaría

- GIVEN no other cita has M reserved in the window
- WHEN the admin queries conflicts
- THEN the response MUST NOT include a conflict for M.

#### Scenario: Conflict check never blocks reservation

- GIVEN any number of conflicts
- WHEN the admin submits the reservation
- THEN the reservation MUST succeed regardless of conflicts.

---

### Requirement: Close endpoint extended payload

`POST /api/admin/citas/<id>/pendiente-biometria/` MUST accept the following OPTIONAL fields:
- `horaRealInicio`, `horaRealFin`
- `procedimientoRealizado`, `zonaCuerpoRealizada`
- `especialistasAtendieron`
- `maquinariaUtilizada`

#### Scenario: Close with real data persists attended staff and used machinery

- GIVEN a `PROGRAMADA` cita
- WHEN the admin submits close with attended staff [3] and used machinery [{maquinariaId:12, cantidad:1}]
- THEN the backend MUST persist `CitaEspecialista` rows with `planificada=false` for staff [3]
- AND MUST persist `CitaMaquinaria` rows with `planificada=false` for the used machinery.

---

### Requirement: Notes PATCH endpoint

`PATCH /api/admin/citas/<id>/notas/` MUST accept any combination of:
- `descripcionGeneral`, `notasPrevias`, `notasPost` (text)
- `fotoAntes`, `fotoDespues` (image multipart)

The endpoint MUST be reachable regardless of the cita state.

#### Scenario: Specialist edits notes on assigned cita

- GIVEN an authenticated specialist assigned to cita C
- WHEN they PATCH `notasPrevias`
- THEN the backend MUST persist the change
- AND MUST respond HTTP 200.

#### Scenario: Non-assigned specialist is denied

- GIVEN an authenticated specialist NOT assigned to cita C
- WHEN they PATCH `notasPrevias`
- THEN the backend SHALL respond with HTTP 403.

---

### Requirement: Specialist mis-citas endpoint

`GET /api/especialista/mis-citas/` MUST return every cita where the authenticated specialist appears in `CitaEspecialista` (any `planificada`), excluding citas in `CANCELADA` or `NO_ASISTIO`.

#### Scenario: Specialist lists assigned citas

- GIVEN an authenticated specialist with 3 assigned citas
- WHEN they call `GET /api/especialista/mis-citas/`
- THEN the response MUST include exactly those 3 citas
- AND each entry MUST include `cliente`, `fecha`, `horaInicio`, `duracionEstimadaMinutos`, `procedimientoPlanificado`, `zonaCuerpoPlanificada`, `descripcionGeneral`, `notasPrevias`, `sucursal`, `estado`, `maquinaria`.

#### Scenario: Cancelled citas are excluded

- GIVEN a cita in `CANCELADA`
- WHEN the specialist lists their citas
- THEN that cancelled cita MUST NOT appear in the response.

---

## UI Requirements

### Requirement: Reservation modal

The admin interface at `cms/clientes/:id` and `cms/operaciones/:id` MUST open a `ReservationModal` instead of the existing inline form.

The modal MUST include:
- Tratamiento select (current behavior).
- Fecha and Hora inputs (current behavior).
- Duración estimada (minutos, default 60).
- Descripción general textarea.
- Notas previas textarea.
- Procedimiento planificado textarea.
- Zona del cuerpo planificada input.
- Especialistas planificados multi-select with "No seleccionado" placeholder.
- Maquinaria planificada rows (maquinaria select + cantidad input).
- "Verificar disponibilidad" button (current behavior).
- Availability result panel: concurrency, nearby appointments (1h ±), specialists on shift (current behavior).
- NEW: Maquinaria conflicts panel listing conflicting citas per selected maquinaría.
- "Confirmar reserva" button. This button MUST be enabled regardless of conflicts.

#### Scenario: Modal opens and shows current fields

- GIVEN an admin on the reservation page
- WHEN they click "Reservar cita"
- THEN the modal MUST open with empty defaults
- AND the "Verificar disponibilidad" button MUST be enabled.

#### Scenario: Conflict panel appears when there are conflicts

- GIVEN an admin has selected 1 unit of maquinaría M
- AND another cita already has M reserved in the same window
- WHEN the admin clicks "Verificar disponibilidad"
- THEN a conflicts panel MUST appear
- AND it MUST list the conflicting cita with date, time, client.

#### Scenario: Confirm succeeds despite conflicts

- GIVEN the conflicts panel is visible
- WHEN the admin clicks "Confirmar reserva"
- THEN the reservation MUST be created
- AND no error toast about conflicts SHALL be shown.

---

### Requirement: Close modal

The admin MUST be able to close a `PROGRAMADA` cita via a `CloseAppointmentModal` triggered by the "Cambiar a pendiente de verificación" action.

The modal MUST include:
- Hora real inicio (datetime-local).
- Hora real fin (datetime-local).
- Procedimiento realizado textarea (prepopulated from planificado).
- Zona del cuerpo realizada input (prepopulated).
- Especialistas que atendieron multi-select (prepopulated from planificados).
- Maquinaria utilizada rows (prepopulated).

#### Scenario: Modal prepopulates from planning data

- GIVEN a cita with `procedimientoPlanificado="Láser axilas"`, `zonaCuerpoPlanificada="Axilas"`, `especialistasPlanificados=[3]`, `maquinariaPlanificada=[{maquinariaId:12, cantidad:1}]`
- WHEN admin opens the close modal
- THEN those values MUST appear pre-filled in the form.

#### Scenario: Duration mismatch warning

- GIVEN `duracionEstimadaMinutos=60`
- WHEN admin enters `horaRealInicio=10:00` and `horaRealFin=13:00` (180 min)
- THEN a yellow warning SHOULD appear indicating the actual duration differs by >50% from the estimate.

---

### Requirement: Notes panel

Every cita detail MUST show a notes panel with editable fields for: `descripcionGeneral`, `notasPrevias`, `notasPost`, `fotoAntes`, `fotoDespues`.

#### Scenario: Admin edits notes

- GIVEN an admin viewing a cita detail
- WHEN they edit `notasPrevias` and save
- THEN the change MUST persist
- AND the panel MUST re-render with the new value.

#### Scenario: Photo upload

- GIVEN an admin uploads a JPG for `fotoAntes`
- WHEN the upload succeeds
- THEN the photo MUST be displayed in the panel
- AND the file MUST be stored under `media/citas/<id>/antes/`.

---

### Requirement: Specialist Mis Citas view

The specialist interface MUST expose a "Mis citas" page listing every cita the specialist is assigned to. The page MUST be read-only.

#### Scenario: Specialist sees their assigned citas

- GIVEN an authenticated specialist with 3 assigned citas
- WHEN they navigate to "Mis citas"
- THEN they MUST see a list of 3 rows
- AND each row MUST show cliente, fecha, hora, procedimiento, zona, descripción general, notas previas, sucursal, estado, maquinaria.

#### Scenario: Specialist view has no actions

- GIVEN the specialist is on "Mis citas"
- WHEN they look at any cita row
- THEN no edit, cancel, reschedule, or close buttons SHALL be visible.

---

## Edge Cases

| Case | Expected Behavior |
| --- | --- |
| Reservation with all optional fields null | Succeeds, cita persisted with empty optional fields |
| `duracionEstimadaMinutos = 0` | Backend rejects with 400 |
| Close modal opened twice on same cita | Second submit is idempotent (re-saves real fields) |
| Concurrent conflict-check + reservation by two admins | Both reservations succeed (no lock); both may show conflicts on each other's submissions after the fact |
| Specialist with no assigned citas | Mis citas page shows empty state |
| `foto_antes` file > 5 MB | Backend rejects with 400; UI shows error toast |
| Maquinaria with `cantidadTotal = 0` | Cannot be selected in the reservation modal (filtered out) |
| Cita with no especialista or no maquinaría | Persists fine; mis-citas page only shows the cita to specialists actually assigned |

## Compatibility

- Existing reservation endpoint keeps backward-compatible body: callers sending only `branchId` + `dateTime` continue to work and create citas with all new optional fields null.
- Existing `pendiente-biometria` callers (sending no body) continue to work and transition state without setting real-time fields.
- Existing `_client_appointment_item` shape preserves all current fields; new fields are additive.
- `appointment-states` spec remains the source of truth for state transitions; this spec extends but does not contradict it.

## Reference Specs

- `openspec/specs/appointment-states/spec.md` — state machine, transition rules.