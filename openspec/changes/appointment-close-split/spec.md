# Appointment Close Split Specification

## Overview

This spec amends the existing `appointment-states` state machine contract by splitting the appointment close flow into two explicit administrative steps:

1. **Mark as pending verification** (`POST /api/admin/citas/<id>/pendiente-biometria/`) — pure state transition `PROGRAMADA → REALIZADA_PENDIENTE_VERIFICACION`. Does NOT capture real-time fields.
2. **Close cita with real data** (`POST /api/admin/citas/<id>/cerrar/`, new) — fills in the real-time fields on a `CONFIRMADA` cita. Does NOT change state.

The two existing transitions (`REALIZADA_PENDIENTE_VERIFICACION → CONFIRMADA` via biometric or manual confirmation) are unchanged.

## Goals

- Eliminate the asymmetry where `cms/clientes/:id` and `cms/operaciones/:id` perform the same transition with different payload shapes.
- Decouple "the session happened" from "here is what actually went on" so the practitioner can fill close data after client confirmation, not at the moment of marking attendance.
- Make the UI's intent obvious: the button label and modal title reflect the action being performed.

## Non-Goals

- Changing the underlying state machine values or transitions.
- Specialist-side close capture (deferred to a follow-up change).
- Notifications, audit logs beyond what the existing `save()` overrides already capture.
- Data migration of existing citas (any cita already in `REALIZADA_PENDIENTE_VERIFICACION` or `CONFIRMADA` is left as-is; admins can backfill close data later via `cerrar`).

## Data Model Requirements

### Requirement: `pendiente-biometria` accepts no body

`POST /api/admin/citas/<id>/pendiente-biometria/` MUST ignore the request body. If any real-time field is present (`horaRealInicio`, `horaRealFin`, `procedimientoRealizado`, `zonaCuerpoRealizada`, `especialistasAtendieron`, `maquinariaUtilizada`), the server MUST ignore it. The transition is a pure state change.

The endpoint MUST still return `400` if the cita is not in `PROGRAMADA`, and `404` if the cita does not exist.

#### Scenario: Empty body transitions PROGRAMADA to REALIZADA_PENDIENTE_VERIFICACION

- GIVEN a cita in `PROGRAMADA`
- AND no real-time data was previously persisted on it
- WHEN the admin POSTs to `/api/admin/citas/<id>/pendiente-biometria/` with `{}` or no body
- THEN the cita MUST transition to `REALIZADA_PENDIENTE_VERIFICACION`
- AND the response MUST include `appointment.estado === "REALIZADA_PENDIENTE_VERIFICACION"`
- AND `hora_real_inicio`, `hora_real_fin`, `procedimiento_realizado`, `zona_cuerpo_realizada` MUST all remain `null` / empty.

#### Scenario: Body with real-time data is ignored

- GIVEN a cita in `PROGRAMADA`
- AND no real-time data was previously persisted
- WHEN the admin POSTs with a body containing `horaRealInicio`, `horaRealFin`, `procedimientoRealizado`, `zonaCuerpoRealizada`, `especialistasAtendieron`, and `maquinariaUtilizada`
- THEN the cita MUST still transition to `REALIZADA_PENDIENTE_VERIFICACION`
- AND the real-time fields MUST remain `null` / empty (the body is ignored).
- AND the response MUST NOT echo the ignored values back as persisted data.

#### Scenario: Wrong state returns 400

- GIVEN a cita in `CONFIRMADA`
- WHEN the admin POSTs to `pendiente-biometria/`
- THEN the server MUST return HTTP 400
- AND the response MUST include the existing detail string ("Solo se pueden cerrar citas que aun esten programadas.").

---

### Requirement: New endpoint `cerrar` captures real-time data on CONFIRMADA

`POST /api/admin/citas/<id>/cerrar/` MUST fill in the real-time fields on a cita that is already in `CONFIRMADA`. The endpoint MUST return `400` if the cita is not in `CONFIRMADA`. The endpoint MUST NOT change the cita's state.

All real-time fields are optional. Empty / missing fields are accepted and the cita stays `CONFIRMADA` with the fields empty.

When `especialistasAtendieron` or `maquinariaUtilizada` are provided, the server MUST replace any existing `CitaEspecialista(planificada=False)` / `CitaMaquinaria(planificada=False)` rows with the new ones (idempotent close).

#### Scenario: Close with full payload persists all fields

- GIVEN a cita in `CONFIRMADA`
- AND no real-time data was previously persisted
- WHEN the admin POSTs to `/cerrar/` with `horaRealInicio`, `horaRealFin`, `procedimientoRealizado`, `zonaCuerpoRealizada`, `especialistasAtendieron`, `maquinariaUtilizada`
- THEN the cita MUST remain in `CONFIRMADA`
- AND `hora_real_inicio`, `hora_real_fin`, `procedimiento_realizado`, `zona_cuerpo_realizada` MUST be persisted with the sent values.
- AND `CitaEspecialista(planificada=False)` rows MUST be created for each id in `especialistasAtendieron`.
- AND `CitaMaquinaria(planificada=False)` rows MUST be created for each entry in `maquinariaUtilizada` with the sent `cantidad`.

#### Scenario: Close with empty body is accepted

- GIVEN a cita in `CONFIRMADA`
- WHEN the admin POSTs to `/cerrar/` with `{}`
- THEN the cita MUST remain in `CONFIRMADA`
- AND the real-time fields MUST stay empty (no overwrites of pre-existing values).

#### Scenario: Close is idempotent

- GIVEN a cita in `CONFIRMADA` already has `CitaEspecialista(planificada=False)` for specialists `[1]` and `CitaMaquinaria(planificada=False)` for maquinaría `[12]`
- WHEN the admin POSTs to `/cerrar/` with `especialistasAtendieron=[3]` and `maquinariaUtilizada=[{maquinariaId: 14, cantidad: 2}]`
- THEN the previous rows for specialist 1 and maquinaría 12 MUST be deleted.
- AND new rows for specialist 3 and maquinaría 14 MUST be created.
- AND no duplicates MUST exist for specialist 1 or maquinaría 12.

#### Scenario: Wrong state returns 400

- GIVEN a cita in `PROGRAMADA` (or any state other than `CONFIRMADA`)
- WHEN the admin POSTs to `/cerrar/`
- THEN the server MUST return HTTP 400
- AND the response MUST include the existing detail string ("Solo se pueden cerrar citas confirmadas.").

#### Scenario: Invalid hour range

- GIVEN a cita in `CONFIRMADA`
- WHEN the admin POSTs with `horaRealFin <= horaRealInicio`
- THEN the server MUST return HTTP 400
- AND `errors.horaRealFin` MUST be present.

#### Scenario: Inicio before scheduled -1h

- GIVEN a cita in `CONFIRMADA` with `fecha_hora = 2026-09-01T10:00:00`
- WHEN the admin POSTs with `horaRealInicio = 2026-09-01T05:00:00` (5 hours before scheduled)
- THEN the server MUST return HTTP 400
- AND `errors.horaRealInicio` MUST mention the 1-hour tolerance.

---

## API Requirements

### Requirement: Updated `pendiente-biometria` payload

`POST /api/admin/citas/<id>/pendiente-biometria/` accepts no fields. The previous optional real-time fields are dropped from the contract.

**Request**: empty body `{}` (or no body).

**Response 200**:
```json
{
  "detail": "La cita quedo realizada y pendiente de confirmaciòn.",
  "appointment": { "id": "CIT-0001", "rawId": 1, "status": "Realizada Pendiente de Verificación", ... },
  "operation": { ... }
}
```

**Response 400** (wrong state):
```json
{ "detail": "Solo se pueden cerrar citas que aun esten programadas." }
```

**Response 404**: standard `{ "detail": "No encontramos la cita solicitada." }`.

### Requirement: New `cerrar` endpoint

`POST /api/admin/citas/<int:appointment_id>/cerrar/`

**Request** (all fields optional):
```json
{
  "horaRealInicio": "2026-09-01T10:05:00-04:00",
  "horaRealFin":    "2026-09-01T11:00:00-04:00",
  "procedimientoRealizado": "Limpieza facial profunda",
  "zonaCuerpoRealizada":    "Rostro",
  "especialistasAtendieron": [3, 7],
  "maquinariaUtilizada":      [{ "maquinariaId": 12, "cantidad": 1 }]
}
```

**Response 200**:
```json
{
  "detail": "La cita quedo cerrada con los datos reales.",
  "appointment": { ... },
  "operation":   { ... }
}
```

**Response 400** (wrong state):
```json
{ "detail": "Solo se pueden cerrar citas confirmadas." }
```

**Response 400** (validation):
```json
{ "detail": "Datos invalidos.", "errors": { "horaRealFin": "La hora real de fin debe ser posterior a la de inicio." } }
```

**Response 404**: standard.

---

## UI Requirements

### Requirement: Button per cita state (cms/operaciones/:id and cms/clientes/:id)

`AdminOperationDetailPage` and `AdminClientDetailPage` / `ClientAppointmentSection` MUST render the action buttons for each cita based on its current `estado`:

| Estado | Buttons |
| --- | --- |
| `PROGRAMADA` | Reprogramar reserva, Marcar como pendiente, Cancelar reserva |
| `REALIZADA_PENDIENTE_VERIFICACION` | Confirmar (via biometric), Cancelar verificación (revert to PROGRAMADA) |
| `CONFIRMADA` | Cerrar cita (opens `CerrarCitaModal`) |

Reprogramar and Cancelar MUST only be visible when `canManage` is true (i.e. for `PROGRAMADA` and `NO_ASISTIO`).

#### Scenario: PROGRAMADA cita shows the three-step buttons

- GIVEN a cita in `PROGRAMADA`
- WHEN the operation detail page renders
- THEN the action row MUST show Reprogramar, Marcar como pendiente, and Cancelar.
- AND MUST NOT show Cerrar cita.

#### Scenario: CONFIRMADA cita shows Cerrar cita

- GIVEN a cita in `CONFIRMADA`
- WHEN the operation detail page renders
- THEN the action row MUST show Cerrar cita.
- AND MUST NOT show Reprogramar or Cancelar (since `canManage` is false for CONFIRMADA).

---

### Requirement: `CerrarCitaModal` captures real-time data on CONFIRMADA

The modal is the renamed/refactored `CloseAppointmentModal.tsx`. It MUST:

- Open from the "Cerrar cita" button on a `CONFIRMADA` cita.
- Prepopulate fields from the cita's planning data (`procedimientoPlanificado`, `zonaCuerpoPlanificada`, `especialistasPlanificados`, `maquinariaPlanificada`) where available.
- Submit to `POST /api/admin/citas/<id>/cerrar/` (not `pendiente-biometria/`).
- Show the same yellow duration-mismatch warning if `(fin - inicio)` differs > 50% from `duracionEstimadaMinutos`.
- Show inline warning when the admin enters `cantidad > cantidadTotal` for a maquinaría (handled by the existing front-end stock check).

#### Scenario: Modal prepopulates from planning

- GIVEN a cita in `CONFIRMADA` with `procedimientoPlanificado="Limpieza facial"`, `zonaCuerpoPlanificada="Rostro"`, `especialistasPlanificados=[3]`, `maquinariaPlanificada=[{maquinariaId: 12, cantidad: 1}]`
- WHEN the admin clicks Cerrar cita
- THEN the modal opens with `procedimientoRealizado="Limpieza facial"`, `zonaCuerpoRealizada="Rostro"`, `especialistas` prepopulated with `[3]`, and the maquinaria row pre-filled with `maquinariaId=12, cantidad=1`.

#### Scenario: Submit persists real-time fields

- GIVEN a CONFIRMADA cita
- WHEN the admin fills in the modal and submits
- THEN the backend MUST respond with HTTP 200
- AND the cita MUST stay `CONFIRMADA`
- AND the real-time fields MUST be persisted.

#### Scenario: Modal does NOT change state

- GIVEN a CONFIRMADA cita
- WHEN the modal submits successfully
- THEN the cita's estado MUST remain `CONFIRMADA` (no transition to a new state).

---

## Edge Cases

| Case | Expected Behavior |
| --- | --- |
| Admin POSTs `pendiente-biometria` with a body containing real-time data | Body is ignored. State transitions. Real-time fields stay empty. |
| Admin POSTs `cerrar` on a PROGRAMADA cita | 400. No state change, no fields written. |
| Admin re-closes a CONFIRMADA cita with different staff | Old `planificada=False` rows deleted. New ones created. No duplicates. |
| Admin opens CerrarCitaModal but cancels | Modal closes. No fields written. Cita unchanged. |
| Multiple admins open CerrarCitaModal on the same cita simultaneously | Last write wins. The endpoint is not transactionally locked (acceptable per spec — admins coordinate via the UI). |

## Compatibility

- Existing `cms/clientes/:id` flow: keeps working. The "Cambiar a pendiente de verificación" button calls the no-body wrapper; now it does the same thing (state transition) and any body that happened to be sent is ignored.
- Existing `cms/operaciones/:id` flow: changes. The current `CloseAppointmentModal` button disappears from the `PROGRAMADA` action row. A simple "Marcar como pendiente" button replaces it. The modal only opens on `CONFIRMADA`.
- The `appointment-reservation-redesign` spec's `pendiente-biometria` requirement (lines 202-244 of `openspec/specs/appointment-reservation-redesign/spec.md`) is amended by this change: the real-time-field capture moves to the new `cerrar/` endpoint.
- The existing `appointment-states` spec's state machine diagram and transition rules stay unchanged.

## Reference Specs

- `openspec/specs/appointment-states/spec.md` — state machine + transition rules (unchanged).
- `openspec/specs/appointment-reservation-redesign/spec.md` — the real-time field contract that this change amends. The fields themselves are still captured; only the endpoint that captures them moves from `pendiente-biometria` to `cerrar`.
