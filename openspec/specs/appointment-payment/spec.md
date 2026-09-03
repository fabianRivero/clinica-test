# Spec: appointment-payment

## Purpose

Admin users charge medical appointments (`CitaMedica` and `CitaClienteLibre`) at the consultorio using the same VIRTUAL/FISICO/MIXTO flow proven for `PagoRealizado`. Each cita carries its own `precio`; payments live in a sibling `PagoCita` table (separate from `PagoRealizado`) so the cuota payment surface stays untouched. Admin-only v1; receipt optional regardless of method.

## Shared Rules

The table below defines the per-method amount and receipt contract used by every admin cobrar endpoint in this spec.

| Method | `montoFisico` | `montoVirtual` | Receipt | Created state |
|--------|---------------|----------------|---------|---------------|
| `VIRTUAL` | `0` | `== amount` | optional | `PENDIENTE` |
| `FISICO` | `== amount` | `0` | optional | `PENDIENTE` |
| `MIXTO` | `>0` | `>0`; sum `amount` | optional | `PENDIENTE` |

Validation failures return HTTP 400 and create no row.

## Requirements

### Requirement: Appointment price is editable and defaults to zero

Both `CitaMedica` and `CitaClienteLibre` SHALL expose a `precio` `DecimalField`, default `0`, validated `>= 0`. Admins MAY set `precio` at booking or before any APROBADO charge.

#### Scenario: Legacy appointment stays non-billable

- GIVEN a `CitaMedica` predating this change
- WHEN the migration completes
- THEN the row has `precio == 0` and admin cannot charge it.

#### Scenario: Admin sets precio at booking

- GIVEN an admin creating a `CitaMedica` with `precio=150`
- WHEN the row is created
- THEN `precio=150` is persisted.

### Requirement: Admin charges a CitaMedica at the consultorio

The system SHALL expose `POST /operaciones/<id>/citas/<cita_id>/cobrar/`, gated by `AdminRequired` and branch isolation. Inputs: `paymentMethod`, `amount`, optional `montoFisico`/`montoVirtual`/`receiptFile`/`details`. Method rules are the Shared Rules table.

#### Scenario: FISICO without receipt

- GIVEN admin in the cita's branch, `precio=200`
- WHEN admin posts FISICO `amount=200` no receipt
- THEN server returns 201 and creates one `PagoCita` (FISICO, `monto_fisico=200`, `monto_virtual=0`, `PENDIENTE`).

#### Scenario: VIRTUAL without receipt

- GIVEN admin in the cita's branch
- WHEN admin posts VIRTUAL with no receipt
- THEN HTTP 201 (admin variant allows receipt optional).

#### Scenario: MIXTO with mismatched breakdown

- GIVEN `MIXTO`, `amount=100`, `montoFisico=40`, `montoVirtual=50`
- WHEN the server validates
- THEN HTTP 400 and no row created.

#### Scenario: Cita belongs to another branch

- GIVEN admin in branch A, cita in branch B
- WHEN admin posts to that cita
- THEN HTTP 403 and no row created.

#### Scenario: Cita is CANCELADA or NO_ASISTIO

- GIVEN a cita whose state is `CANCELADA` or `NO_ASISTIO`
- WHEN admin posts any cobrar payload
- THEN HTTP 400 and no row created.

#### Scenario: Cita precio is zero

- GIVEN `precio == 0`
- WHEN admin posts any cobrar payload
- THEN HTTP 400 ("Debes asignar un precio a la cita antes de cobrar.") and no row.

#### Scenario: Over-payment guard

- GIVEN `precio=100` and APROBADO `PagoCita` sum `80`
- WHEN admin posts any cobro that would push APROBADO past `100`
- THEN HTTP 400 and no row.

### Requirement: Admin charges a CitaClienteLibre at the consultorio

The system SHALL expose `POST /citas-medicas-libres/<id>/cobrar/`, gated by `AdminRequired` and branch isolation. Method rules and rejections mirror the CitaMedica endpoint exactly.

#### Scenario: FISICO charge succeeds

- GIVEN admin in the cita's branch, `precio=180`
- WHEN admin posts FISICO `amount=180`
- THEN HTTP 201 and one `PagoCita` in `PENDIENTE`.

#### Scenario: Cross-branch rejected

- GIVEN admin in branch A, cita in branch B
- WHEN admin posts to that cita
- THEN HTTP 403 and no row.

#### Scenario: Over-payment rejected

- GIVEN `precio=50` and one APROBADO `PagoCita` of `50`
- WHEN admin posts any cobro
- THEN HTTP 400 and no row.

### Requirement: estado_verificacion controls paid amount

Only `APROBADO` `PagoCita` rows count toward the cita's paid amount. `PENDIENTE`, `RECHAZADO`, `CANCELADO` do not.

#### Scenario: Approval decreases saldo pendiente

- GIVEN `precio=200`, one `PENDIENTE` `PagoCita` of `50`
- WHEN admin approves it
- THEN detail payload shows `saldoPendiente = 150`.

#### Scenario: Rejection leaves saldo pendiente unchanged

- GIVEN `precio=200`, one `PENDIENTE` `PagoCita` of `50`
- WHEN admin rejects it
- THEN `saldoPendiente` stays `200`.

#### Scenario: Cancelling APROBADO raises saldo pendiente

- GIVEN `precio=200`, one APROBADO `PagoCita` of `80`
- WHEN admin cancels it
- THEN `saldoPendiente` returns to `200`.

### Requirement: Cancellation does not delete PagoCita rows

When a cita transitions to `CANCELADA` or `NO_ASISTIO`, existing `PagoCita` rows MUST remain visible for audit, and new cobrar calls MUST be rejected.

#### Scenario: CANCELADA preserves audit trail

- GIVEN a cita with two `PagoCita` rows
- WHEN it transitions to `CANCELADA`
- THEN both rows remain listed and a new cobrar returns HTTP 400.

#### Scenario: NO_ASISTIO preserves audit trail

- GIVEN a cita with one APROBADO `PagoCita`
- WHEN it transitions to `NO_ASISTIO`
- THEN the row remains visible and a new cobrar returns HTTP 400.

### Requirement: Read serializers expose appointment price and payment breakdown

Admin detail payloads (both cita kinds) MUST include `precio`, `saldoPendiente`, `pagos_count`, and a `pagos` array of `{id, monto_pagado, metodo_pago, monto_fisico, monto_virtual, comprobante_url, estado_verificacion, created_at, detalles_pago}`.

#### Scenario: Two PENDIENTE charges on a CitaMedica

- GIVEN `precio=300` and two `PENDIENTE` `PagoCita` of `100` each
- WHEN admin loads the detail
- THEN payload shows `precio=300`, `saldoPendiente=300`, `pagos_count=2`, `pagos[]` length 2.

#### Scenario: One APROBADO charge on a CitaClienteLibre

- GIVEN `precio=150` and one APROBADO `PagoCita` of `150`
- WHEN admin loads the detail
- THEN `saldoPendiente=0`.

### Requirement: Branch isolation helper

A new `assert_cita_in_user_branch(request, cita)` SHALL raise `PermissionDenied` (HTTP 403) when `cita.sucursal_id != request.user.sucursal_id`.

#### Scenario: Cross-branch rejected

- GIVEN admin in branch A, cita in branch B
- WHEN admin charges
- THEN helper raises and endpoint returns 403.

#### Scenario: Same-branch accepted

- GIVEN admin and cita both in branch B
- WHEN admin charges
- THEN helper is silent and endpoint returns 201.

### Requirement: Receipt storage path is distinct from cuota receipts

`PagoCita.comprobante_url` SHALL use `upload_to="comprobantes_citas/%Y/%m/"`.

#### Scenario: Receipt lands in the new path

- GIVEN an admin uploads a receipt on a `PagoCita`
- WHEN the file is saved
- THEN it lands under `media/comprobantes_citas/YYYY/MM/`, never `media/comprobantes_pagos/`.

### Requirement: Frontend "Cobrar cita" modal

A reusable `AdminRegisterAppointmentPaymentModal` (parameter variant of `AdminRegisterPaymentModal`) SHALL accept an `appointment` prop (`CitaMedica` or `CitaClienteLibre`) instead of `quota`. The modal MUST show `precio`, `saldoPendiente`, the VIRTUAL/FISICO/MIXTO selector with optional receipt, and disable submit when client-side over-payment is detected.

#### Scenario: Modal opens with derived saldo

- GIVEN admin on a `CitaMedica` detail page
- WHEN admin clicks "Cobrar cita"
- THEN modal opens with `saldoPendiente = precio - sum(approved)`.

#### Scenario: FISICO submission without receipt

- GIVEN modal open with `saldoPendiente > 0`
- WHEN admin submits FISICO no receipt
- THEN HTTP 201, modal closes, detail refreshes with updated `pagos[]`.

#### Scenario: Over-payment blocked on both sides

- GIVEN `saldoPendiente=0`
- WHEN admin opens the modal
- THEN submit is disabled and any tampered POST returning 400 is shown as a field error.
