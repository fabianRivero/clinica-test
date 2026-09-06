# Spec: admin-prospect-conversion

## Purpose

Define the multi-mode conversion wizard that transforms a `Prospecto`, reactivates an inactive `Cliente`, or creates a brand-new `Cliente` directly. The same five-step flow runs across all three modes; only step-1 readOnly behavior and the finalize dispatcher differ per mode.

## Requirements

### Requirement: Three Wizard Modes

The system MUST support three mutually exclusive modes selected by URL: `prospect`, `reactivation`, and `direct`. The mode MUST be derivable on backend and frontend from the URL and MUST determine step-1 behavior and finalize dispatch.

#### Scenario: Mode is derived from URL

- GIVEN an authenticated admin
- WHEN the admin visits `/cms/prospectos/{id}/convertir`, `/cms/clientes/{id}/reactivar`, or `/cms/clientes/nuevo`
- THEN the draft is created with `prospecto={id}`+`cliente=NULL`, `prospecto=NULL`+`cliente={id}`, or `prospecto=NULL`+`cliente=NULL` respectively
- AND the mode is `prospect`, `reactivation`, or `direct` respectively

### Requirement: Step 1 ReadOnly Behavior Per Mode

Step 1 MUST be editable in `prospect` and `direct` modes and readOnly in `reactivation` mode. Password fields MUST be visible in `prospect` and `direct` modes and hidden in `reactivation` mode. In `mode='direct'`, Step 1 MUST additionally present a required radio at the top asking "Ya fue cliente de la clínica?" with two choices: "Sí" (sets `origen = RECURRENTE_PRE_SISTEMA`) and "No" (sets `origen = NUEVO`). The "Siguiente" control MUST remain disabled until one of the two choices is selected. The required origin radio MUST NOT be rendered in `prospect` or `reactivation` modes.

(Previously: Step 1 was editable in `prospect` and `direct`, readOnly in `reactivation`, with no origin requirement. The `direct` branch now requires a one-time origin choice that flows into finalize.)

#### Scenario: ReadOnly and password visibility per mode

- GIVEN the wizard is in any mode
- WHEN the admin views step 1
- THEN in `prospect` and `direct` modes every input is editable and password fields are visible
- AND in `reactivation` mode every input is prefilled, readOnly, and password fields are hidden

#### Scenario: Required origin radio renders at the top of direct step 1

- GIVEN the wizard is in `mode='direct'`
- WHEN the admin views step 1
- THEN the origin radio appears at the top of the step
- AND it offers exactly two choices: "Sí, ya fue paciente" and "No, es nuevo"
- AND the "Siguiente" control is disabled until a choice is made

#### Scenario: Selecting Sí persists origen RECURRENTE_PRE_SISTEMA

- GIVEN the wizard is in `mode='direct'` at step 1
- WHEN the admin selects "Sí, ya fue paciente" and advances to step 2
- THEN the wizard draft stores `origen = RECURRENTE_PRE_SISTEMA`

#### Scenario: Selecting No persists origen NUEVO

- GIVEN the wizard is in `mode='direct'` at step 1
- WHEN the admin selects "No, es nuevo" and advances to step 2
- THEN the wizard draft stores `origen = NUEVO`

#### Scenario: Direct step 1 blocks advancing without an origin choice

- GIVEN the wizard is in `mode='direct'` at step 1
- AND the admin has not yet selected an origin radio
- WHEN the admin attempts to advance
- THEN the wizard MUST NOT advance to step 2
- AND the origin radio MUST be highlighted as the blocking field

#### Scenario: Origin radio is absent in prospect and reactivation modes

- GIVEN the wizard is in `mode='prospect'` or `mode='reactivation'`
- WHEN the admin views step 1
- THEN the required origin radio is NOT rendered
- AND the existing per-mode behavior is unchanged

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

### Requirement: Common Step Validation Across Modes

Steps 2 through 5 MUST run the same validation logic across all three modes. Only step 1's readOnly/password visibility and finalize's dispatcher differ between modes.

#### Scenario: Steps 2–5 behave identically across modes

- GIVEN a draft in any of `prospect`, `reactivation`, or `direct` mode
- WHEN the admin submits step 2, 3, 4, or 5 with valid data
- THEN the step succeeds and advances
- AND the behavior is identical across all three modes except biometric migration in step 4, which only runs in `prospect` mode

### Requirement: Cancel Works Across All Modes

The cancel action MUST be available at any wizard step in all three modes and MUST delete the draft row without creating or modifying any `Usuario`, `Cliente`, or `Prospecto` row.

#### Scenario: Cancel deletes the draft in every mode

- GIVEN a draft in `prospect`, `reactivation`, or `direct` mode at any step
- WHEN the admin cancels
- THEN the draft row is deleted
- AND the underlying `Prospecto` (if any) is unchanged
- AND the underlying `Cliente` (if any) is unchanged
- AND no `Usuario` or `Cliente` row is created
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
