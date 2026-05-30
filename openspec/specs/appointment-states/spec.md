# Appointment States Specification

## Overview

This document defines the appointment state machine, state values, transitions, and associated business rules for the clinical appointment system.

## State Machine

```
PROGRAMADA
    │
    │ [Admin clicks "Cambiar a pendiente de verificación"]
    ▼
REALIZADA_PENDIENTE_VERIFICACION
    │
    ├──────────────────┬────────────────────┐
    │                  │                    │
    │ [Admin clicks    │ [Admin clicks      │ [Admin confirms
    │  "Confirmar      │  "Cancelar" then    │  "Confirmar huella
    │   huella mock"]  │  confirms]         │   mock"]
    ▼                  ▼                    ▼
PROGRAMADA        PROGRAMADA           CONFIRMADA
(revert)          (cancel)
```

## State Values

| Enum Value | Display Label | Description |
|------------|---------------|-------------|
| `PROGRAMADA` | Programada | Appointment is scheduled |
| `CONFIRMADA` | Confirmada | Appointment confirmed |
| `CANCELADA` | Cancelada | Appointment cancelled |
| `REALIZADA_PENDIENTE_VERIFICACION` | Realizada Pendiente de Verificación | Appointment completed, awaiting biometric verification |
| `NO_ASISTIO` | No Asistió | Patient did not attend |
| `BLOQUEADA` | Bloqueada | Appointment blocked |

## Requirements

### Requirement: Appointment State `REALIZADA_PENDIENTE_VERIFICACION`

The appointment state `REALIZADA_PENDIENTE_VERIFICACION` SHALL only be reachable from `PROGRAMADA`. The display label SHALL be "Realizada Pendiente de Verificación". This state indicates the appointment has been completed but requires biometric verification.

**Rename mapping**:
| Old Value | New Value |
|-----------|-----------|
| `REALIZADA_PENDIENTE_BIOMETRIA` | `REALIZADA_PENDIENTE_VERIFICACION` |
| "Realizada pendiente biometria" | "Realizada Pendiente de Verificación" |

#### Scenario: Admin changes appointment to pending verification

- GIVEN an appointment with estado `PROGRAMADA`
- WHEN the admin clicks "Cambiar a pendiente de verificación"
- AND confirms the action in the dialog
- THEN the appointment estado changes to `REALIZADA_PENDIENTE_VERIFICACION`
- AND the UI reloads to reflect the new state

#### Scenario: Admin sees verification actions for pending appointment

- GIVEN an appointment with estado `REALIZADA_PENDIENTE_VERIFICACION`
- THEN the UI SHALL display "Confirmar huella mock" button
- AND the UI SHALL display "Cancelar" button
- AND no "Cambiar a pendiente de verificación" button SHALL appear

---

### Requirement: Cancel Verification Action

The system MUST provide a mechanism to revert an appointment from `REALIZADA_PENDIENTE_VERIFICACION` back to `PROGRAMADA`.

#### Scenario: Admin cancels verification with confirmation

- GIVEN an appointment with estado `REALIZADA_PENDIENTE_VERIFICACION`
- WHEN the admin clicks "Cancelar"
- THEN a confirmation dialog MUST appear with title "¿Está seguro?"
- AND the dialog message SHALL be "¿Está seguro que desea cancelar la verificación?"
- AND the dialog SHALL display "Confirmar" and "Cancelar" buttons

#### Scenario: Admin confirms cancellation

- GIVEN the confirmation dialog is displayed
- WHEN the admin clicks "Confirmar"
- THEN the system SHALL call `POST /api/admin/citas/:id/cancelar-verificacion/`
- AND on success the appointment estado SHALL revert to `PROGRAMADA`
- AND the appointment data SHALL reload automatically
- AND the dialog SHALL close

#### Scenario: Admin dismisses cancellation dialog

- GIVEN the confirmation dialog is displayed
- WHEN the admin clicks "Cancelar" (in the dialog)
- THEN the dialog SHALL close
- AND no API call SHALL be made
- AND the appointment state SHALL remain unchanged

---

### Requirement: `cancelar-verificacion` Endpoint

The system MUST expose `POST /api/admin/citas/:id/cancelar-verificacion/` which reverts an appointment from `REALIZADA_PENDIENTE_VERIFICACION` to `PROGRAMADA`.

#### Scenario: Valid cancellation request

- GIVEN an appointment with estado `REALIZADA_PENDIENTE_VERIFICACION`
- WHEN `POST /api/admin/citas/:id/cancelar-verificacion/` is called
- THEN the response status SHALL be `200`
- AND the response body SHALL contain `{"detail": "...", "appointment": {...}}`
- AND the appointment estado SHALL be `PROGRAMADA`
- AND `verif_biometria` SHALL be `false`

#### Scenario: Cancellation from wrong state returns 400

- GIVEN an appointment with estado `PROGRAMADA` (or any other state)
- WHEN `POST /api/admin/citas/:id/cancelar-verificacion/` is called
- THEN the response status SHALL be `400`
- AND the response body SHALL contain `{"detail": "Solo se puede cancelar la verificación de citas pendientes."}`

#### Scenario: Cancellation of non-existent appointment returns 404

- GIVEN no appointment exists with the given ID
- WHEN `POST /api/admin/citas/:id/cancelar-verificacion/` is called
- THEN the response status SHALL be `404`
- AND the response body SHALL contain `{"detail": "No encontramos la cita solicitada."}`

---

## API Contract: `POST /api/admin/citas/:id/cancelar-verificacion/`

**Request**: No body required.

**Response 200**:
```json
{
  "detail": "La verificación fue cancelada. La cita volvió a estado Programada.",
  "appointment": { /* _client_appointment_item */ }
}
```

**Response 400**:
```json
{ "detail": "Solo se puede cancelar la verificación de citas pendientes." }
```

**Response 404**:
```json
{ "detail": "No encontramos la cita solicitada." }
```

---

## Edge Cases

| Case | Expected Behavior |
|------|-----------------|
| Calling `cancelar-verificacion` on `PROGRAMADA` appointment | 400 response, no state change |
| Calling `cancelar-verificacion` on `CONFIRMADA` appointment | 400 response, no state change |
| Calling `cancelar-verificacion` on `CANCELADA` appointment | 400 response, no state change |
| Concurrent modification (appointment state changed between load and cancel) | 400 response, stale data warning |
| Network error on cancel API call | Error notification displayed, no data reload |
| Appointment not found (deleted between load and cancel) | 404 response, data reload shows appointment removed |