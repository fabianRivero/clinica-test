# Delta for admin-prospect-conversion

## MODIFIED Requirements

### Requirement: Finalize Dispatcher Per Mode

The system MUST dispatch finalize to one of three branches based on the draft state and MUST wrap every branch in a single `transaction.atomic()` block that rolls back all writes on any error. In `mode='prospect'` finalize, the new `Cliente.origen` MUST be set from the source `Prospecto.origen`; in `mode='reactivation'` finalize, the existing `Cliente.origen` MUST NOT be modified under any circumstance.

(Previously: finalize dispatched per mode inside a single atomic transaction, with no explicit `origen` propagation contract for the prospect branch.)

#### Scenario: Prospect finalize

- GIVEN a draft in `prospect` mode with all 5 steps complete
- WHEN the admin submits finalize
- THEN a new `Usuario (CLIENTE)` is created
- AND a new `Cliente` linked to that `Usuario` is created
- AND the new `Cliente.origen` equals the source `Prospecto.origen`
- AND the prospect is marked as converted
- AND prospect biometrics are migrated to the new `Cliente`

#### Scenario: Reactivation finalize

- GIVEN a draft in `reactivation` mode with all 5 steps complete
- WHEN the admin submits finalize
- THEN no new `Usuario` is created
- AND the existing `Cliente` is updated with wizard payload data
- AND the live `Cliente.origen` is unchanged regardless of what the draft carries
- AND any provided biometric is stamped onto the existing `Cliente`

#### Scenario: Direct finalize

- GIVEN a draft in `direct` mode with all 5 steps complete
- WHEN the admin submits finalize
- THEN a new `Usuario (CLIENTE)` is created
- AND a new `Cliente` linked to that `Usuario` is created
- AND the new `Cliente.origen` equals the `origen` the admin selected on step 1
- AND no prospect is marked as converted
- AND no prospect biometric migration occurs

#### Scenario: Prospect finalize propagates RECURRENTE_PRE_SISTEMA

- GIVEN a `Prospecto` with `origen = RECURRENTE_PRE_SISTEMA` and a complete `mode='prospect'` draft
- WHEN the admin submits finalize
- THEN the resulting `Cliente.origen` is `RECURRENTE_PRE_SISTEMA`
- AND the resulting `Cliente.origen` is NOT `NUEVO`

#### Scenario: Reactivation finalize never overwrites Cliente.origen

- GIVEN an existing `Cliente` with `origen = NUEVO`
- AND a reactivation draft whose draft-level `origen` differs from the live value
- WHEN the admin submits reactivation finalize
- THEN the live `Cliente.origen` remains `NUEVO`

#### Scenario: Finalize rolls back on any error

- GIVEN any draft in any mode with all 5 steps complete
- AND a persistence error is forced during finalize
- WHEN the admin submits finalize
- THEN the entire transaction rolls back
- AND no `Usuario`, `Cliente`, draft, or biometric row is modified or created

## ADDED Requirements

### Requirement: prospect origin non-overwrite contract

The `mode='prospect'` branch of finalize MUST derive `Cliente.origen` exclusively from `prospecto.origen`; it MUST NOT use the wizard draft's `origen` field as a fallback or override when the prospect was created without a draft-level origin. The `mode='reactivation'` branch MUST treat `Cliente.origen` as immutable for the duration of the reactivate flow.

#### Scenario: Prospect origin is the sole source for Cliente.origen in prospect mode

- GIVEN a `Prospecto` with `origen = RECURRENTE_PRE_SISTEMA`
- AND a `mode='prospect'` draft whose step-1 origin field is empty or differs
- WHEN finalize runs
- THEN the new `Cliente.origen` equals the `Prospecto.origen` (`RECURRENTE_PRE_SISTEMA`), not the draft field

#### Scenario: Reactivation never writes Cliente.origen

- GIVEN any `mode='reactivation'` finalize payload
- WHEN the finalize dispatcher runs the reactivation branch
- THEN no `UPDATE` statement targets the `origen` column of `Cliente`
