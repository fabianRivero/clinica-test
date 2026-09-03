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

Step 1 MUST be editable in `prospect` and `direct` modes and readOnly in `reactivation` mode. Password fields MUST be visible in `prospect` and `direct` modes and hidden in `reactivation` mode.

#### Scenario: ReadOnly and password visibility per mode

- GIVEN the wizard is in any mode
- WHEN the admin views step 1
- THEN in `prospect` and `direct` modes every input is editable and password fields are visible
- AND in `reactivation` mode every input is prefilled, readOnly, and password fields are hidden

### Requirement: Finalize Dispatcher Per Mode

The system MUST dispatch finalize to one of three branches based on the draft state and MUST wrap every branch in a single `transaction.atomic()` block that rolls back all writes on any error.

#### Scenario: Prospect finalize

- GIVEN a draft in `prospect` mode with all 5 steps complete
- WHEN the admin submits finalize
- THEN a new `Usuario (CLIENTE)` is created
- AND a new `Cliente` linked to that `Usuario` is created
- AND the prospect is marked as converted
- AND prospect biometrics are migrated to the new `Cliente`

#### Scenario: Reactivation finalize

- GIVEN a draft in `reactivation` mode with all 5 steps complete
- WHEN the admin submits finalize
- THEN no new `Usuario` is created
- AND the existing `Cliente` is updated with wizard payload data
- AND any provided biometric is stamped onto the existing `Cliente`

#### Scenario: Direct finalize

- GIVEN a draft in `direct` mode with all 5 steps complete
- WHEN the admin submits finalize
- THEN a new `Usuario (CLIENTE)` is created
- AND a new `Cliente` linked to that `Usuario` is created
- AND no prospect is marked as converted
- AND no prospect biometric migration occurs

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