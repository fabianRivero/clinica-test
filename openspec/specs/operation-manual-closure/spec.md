# Operation Manual Closure Specification

## Purpose

Defines the rules, audit trail, and API/UI contract for manually closing an `Operacion` from `EN_PROCESO` to either `FINALIZADA` (when all sesiones/cuotas reconcile) or a new terminal `SUSPENDIDA` state. Also defines the interaction with the `Cliente` auto-state machine.

## Requirements

### Requirement: Operation Lifecycle States

The `Operacion` lifecycle SHALL expose five states: `BORRADOR`, `EN_PROCESO`, `FINALIZADA`, `CANCELADA`, `SUSPENDIDA`. `BORRADOR` and `EN_PROCESO` are non-terminal. `FINALIZADA`, `CANCELADA`, and `SUSPENDIDA` are terminal — the system MUST NOT transition out of any terminal state.

#### Scenario: New state visible after migration

- GIVEN an `Operacion` in any of the four existing states
- WHEN the schema migration runs
- THEN `Operacion.Estado` SHALL include `SUSPENDIDA`
- AND pre-existing rows SHALL retain their state.

### Requirement: Manual Closure to FINALIZADA — Preconditions

The system MUST transition `Operacion` from `EN_PROCESO` to `FINALIZADA` ONLY when ALL preconditions hold: every `CitaMedica` is in a final state such that `sesiones_totales == sesiones_confirmadas + reservas_activas + sesiones_pendientes_confirmacion`; every `CuotaPlanPago` is `PAGADO` or `NO_PAGADA`; and `SUM(cuotas.monto_programado)` equals `precio_total` exactly (cents-precise, no rounding). Any failure MUST surface as a structured precondition report and MUST NOT mutate state.

#### Scenario: Happy path closure

- GIVEN an `EN_PROCESO` operacion with all citas final, all cuotas `PAGADO`/`NO_PAGADA`, and `SUM(monto_programado) == precio_total`
- WHEN the admin invokes finalize
- THEN state SHALL become `FINALIZADA`.

#### Scenario: Non-final cita blocks closure

- GIVEN an `EN_PROCESO` operacion with one `CitaMedica` in `PROGRAMADA`
- WHEN the admin invokes finalize
- THEN state SHALL remain `EN_PROCESO`
- AND the report SHALL identify the offending cita.

#### Scenario: PENDIENTE or VENCIDA cuota blocks closure

- GIVEN an `EN_PROCESO` operacion with one cuota in `PENDIENTE` or `VENCIDA`
- WHEN the admin invokes finalize
- THEN state SHALL remain `EN_PROCESO`
- AND the report SHALL identify the cuota.

#### Scenario: Sum mismatch (over or under) blocks closure

- GIVEN `precio_total = 100` and `SUM(monto_programado) = 105` or `95`
- WHEN the admin invokes finalize
- THEN state SHALL remain `EN_PROCESO`
- AND the report SHALL state the cents-exact diff.

### Requirement: Manual Closure to SUSPENDIDA

The system MUST transition `Operacion` from `EN_PROCESO` to `SUSPENDIDA` with NO preconditions beyond the source state. `SUSPENDIDA` is terminal. The system MUST reject suspension from any state other than `EN_PROCESO`.

#### Scenario: Suspend succeeds unconditionally

- GIVEN an `EN_PROCESO` operacion with unresolved sesiones, pending cuotas, and sum mismatch
- WHEN the admin invokes suspend
- THEN state SHALL become `SUSPENDIDA`.

#### Scenario: Suspend rejected from non-EN_PROCESO source

- GIVEN an operacion in `BORRADOR`, `FINALIZADA`, `CANCELADA`, or `SUSPENDIDA`
- WHEN the admin invokes suspend
- THEN state SHALL be unchanged
- AND the system SHALL return a source-state rejection.

### Requirement: Closure Audit Trail

Every successful manual closure MUST atomically persist three nullable audit fields: `finalized_by` (FK User), `finalized_at` (DateTime), `finalization_kind` (`MANUAL_FINALIZADA | MANUAL_SUSPENDIDA`). All three MUST be set together; partial writes SHALL NOT occur.

#### Scenario: Finalize records MANUAL_FINALIZADA audit

- GIVEN an `EN_PROCESO` operacion with all preconditions met
- WHEN admin `U` invokes finalize at time `T`
- THEN `finalized_by == U`, `finalized_at == T`, `finalization_kind == MANUAL_FINALIZADA`
- AND the three fields SHALL be persisted in the same transaction as the state change.

#### Scenario: Suspend records MANUAL_SUSPENDIDA audit

- GIVEN an `EN_PROCESO` operacion
- WHEN admin `U` invokes suspend at time `T`
- THEN `finalization_kind == MANUAL_SUSPENDIDA`
- AND the three audit fields SHALL be persisted atomically.

### Requirement: SUSPENDIDA Blocks New Reservations and Cuotas

While `Operacion.estado == SUSPENDIDA`, the system MUST reject creation of new `CitaMedica` and new `CuotaPlanPago` rows for that operacion. Existing rows MAY be read but MUST NOT be created.

#### Scenario: New cita rejected while SUSPENDIDA

- GIVEN an `Operacion` with `estado == SUSPENDIDA`
- WHEN a cita creation request targets that operacion
- THEN the system SHALL reject the request.

#### Scenario: New cuota rejected while SUSPENDIDA

- GIVEN an `Operacion` with `estado == SUSPENDIDA`
- WHEN a cuota creation request targets that operacion
- THEN the system SHALL reject the request.

### Requirement: Cliente Auto-State No Longer Auto-Finalizes

The `Cliente.actualizar_estado_automaticamente` rule MUST NOT transition `Operacion` from `EN_PROCESO` to `FINALIZADA` based on "no pendientes". Other auto-state transitions SHALL be preserved. `procedimiento_tiene_pendientes` MUST return `False` for both `SUSPENDIDA` and `FINALIZADA`.

#### Scenario: Regression — auto-closure no longer fires

- GIVEN an `Operacion` in `EN_PROCESO` with zero pending sesiones and zero pending cuotas
- WHEN `Cliente.actualizar_estado_automaticamente` runs
- THEN operacion state SHALL remain `EN_PROCESO`.

#### Scenario: Terminal states treated as no pendientes

- GIVEN `procedimiento_tiene_pendientes` is called for an operacion in `SUSPENDIDA` or `FINALIZADA`
- WHEN the method evaluates
- THEN it SHALL return `False`.

### Requirement: API Contract — Finalize and Suspend Endpoints

The system SHALL expose `POST /api/operaciones/<id>/finalizar/` and `POST /api/operaciones/<id>/suspender/` for admin users. Success returns HTTP 200. Failed preconditions MUST return HTTP 409 with body `{ "estado": "<current>", "preconditions": { "sesiones": {...}, "cuotas": {...}, "monto": {...} } }`. Failed source-state checks MUST return HTTP 409 with the source-state error. Non-admin callers MUST receive HTTP 403.

#### Scenario: Finalize success returns 200

- GIVEN an `EN_PROCESO` operacion with all preconditions met
- WHEN an admin POSTs to `/finalizar/`
- THEN the response SHALL be HTTP 200.

#### Scenario: Finalize precondition failure returns structured 409

- GIVEN an `EN_PROCESO` operacion with one pending cuota
- WHEN an admin POSTs to `/finalizar/`
- THEN the response SHALL be HTTP 409 with the failing precondition detail.

#### Scenario: Suspend from wrong source returns 409

- GIVEN a `FINALIZADA` operacion
- WHEN an admin POSTs to `/suspender/`
- THEN the response SHALL be HTTP 409 with a source-state error.

#### Scenario: Non-admin caller is forbidden

- GIVEN a non-admin authenticated user
- WHEN they POST to either endpoint
- THEN the response SHALL be HTTP 403.

### Requirement: Frontend Closure Actions

The operation detail page SHALL render two buttons visible only when `estado == EN_PROCESO`. "Finalizar" MUST be disabled with a tooltip naming the failing precondition whenever any precondition is unmet; a confirmation modal listing each precondition with pass/fail SHALL appear before submission. "Suspender" SHALL be enabled whenever `estado == EN_PROCESO` and SHOULD require a confirmation prompt. The disabled state and modal payload MUST mirror the server's structured precondition report.

#### Scenario: Finalizar disabled when a precondition fails

- GIVEN the operation detail page with `estado == EN_PROCESO` and one pending cuota
- WHEN the page renders
- THEN the "Finalizar" button SHALL be disabled
- AND the tooltip SHALL name the failing precondition.

#### Scenario: Finalizar confirmation modal lists preconditions

- GIVEN the admin clicks an enabled "Finalizar" button
- WHEN the modal opens
- THEN it SHALL list each precondition with a pass/fail indicator.

#### Scenario: Buttons hidden outside EN_PROCESO

- GIVEN the operation detail page with `estado` in `BORRADOR`, `FINALIZADA`, `CANCELADA`, or `SUSPENDIDA`
- WHEN the page renders
- THEN neither closure button SHALL be visible.

#### Scenario: Server 409 surfaces in the modal on race

- GIVEN the client computed all preconditions as passing
- WHEN the server returns 409 because state changed between checks
- THEN the modal SHALL re-render with the server's structured report.