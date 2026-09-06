# Delta for admin-prospect-conversion

## MODIFIED Requirements

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
