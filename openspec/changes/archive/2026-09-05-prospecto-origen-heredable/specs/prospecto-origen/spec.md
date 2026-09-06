# prospecto-origen Specification

## Purpose

Tag every `Prospecto` with an `origen` recording whether the person being onboarded is brand-new (`NUEVO`) or a pre-system returning patient (`RECURRENTE_PRE_SISTEMA`). The field is the source of truth that `admin_prospect_conversion_finalize` copies to `Cliente.origen` at the end of the `mode='prospect'` wizard, so the prospect path preserves the same cobrable-eligibility signal the direct path already records.

## Requirements

### Requirement: origen field semantics

The `Prospecto` model MUST expose an `origen` field with the same closed enumeration as `Cliente.origen`: exactly `NUEVO` and `RECURRENTE_PRE_SISTEMA`. The field MUST be `NOT NULL` and MUST default to `NUEVO`. Prospect serializers used by the admin `mode='prospect'` wizard MUST expose the field.

#### Scenario: Existing Prospecto persists with the default origin after migration

- GIVEN a `Prospecto` row created before this change
- WHEN the migration applies
- THEN that row's `origen` becomes `NUEVO`
- AND the row remains queryable

#### Scenario: New Prospecto created with each value

- GIVEN an `admin_crear_prospecto` payload carrying `origen`
- WHEN the backend persists the prospect
- THEN the resulting row stores the supplied value
- AND omitting `origen` in the payload defaults it to `NUEVO`

#### Scenario: Unknown origin value rejected on creation

- GIVEN an `admin_crear_prospecto` payload with `origen = "ALGOTRO"`
- WHEN the backend persists the prospect
- THEN the response returns 400
- AND no `Prospecto` row is created

#### Scenario: origen exposed in prospect serialization

- GIVEN a `Prospecto` with `origen = RECURRENTE_PRE_SISTEMA`
- WHEN any serializer returning this `Prospecto` to the conversion wizard is invoked
- THEN the payload includes `origen = "RECURRENTE_PRE_SISTEMA"`

### Requirement: creation-time origin selection in admin UI

`AdminProspectCreatePage` MUST present a REQUIRED radio at the TOP asking "Es un cliente nuevo o antiguo?" with exactly two options: "Antiguo (ya fue paciente)" → `RECURRENTE_PRE_SISTEMA`, and "Nuevo (primera vez en el sistema)" → `NUEVO`. The submit control MUST remain disabled until one option is selected.

#### Scenario: Required origin radio blocks submit until selected

- GIVEN an admin viewing `AdminProspectCreatePage`
- WHEN no origin radio has been selected
- THEN the submit control is disabled
- AND selecting either option enables the submit control

#### Scenario: Each radio choice persists its origin value

- GIVEN the admin selects "Antiguo (ya fue paciente)" and submits
- WHEN `admin_crear_prospecto` runs
- THEN the payload sent to the backend includes `origen = RECURRENTE_PRE_SISTEMA`
- AND when the admin selects "Nuevo (primera vez en el sistema)" and submits
- THEN the payload sent to the backend includes `origen = NUEVO`

### Requirement: write-once prospect origin

`Prospecto.origen` SHALL be settable on creation only. The system MUST NOT introduce a `Prospecto` profile-edit endpoint or general-purpose PATCH view that would expose `origen` for post-creation editing.

#### Scenario: Re-saving preserves the original origin

- GIVEN a `Prospecto` with `origen = RECURRENTE_PRE_SISTEMA`
- WHEN the model instance is re-saved without an explicit `origen` argument
- THEN the stored value remains `RECURRENTE_PRE_SISTEMA`

#### Scenario: No prospect PATCH endpoint introduced

- GIVEN the system after this change
- WHEN admin API routes are inspected
- THEN no `PATCH` endpoint for `Prospecto` exposes `origen`

### Requirement: propagation at prospect finalize

`admin_prospect_conversion_finalize` MUST copy `prospecto.origen` to the newly created `Cliente.origen` when finalizing a `mode='prospect'` draft. The system MUST NOT hardcode the resulting `Cliente.origen` to `NUEVO`.

#### Scenario: Prospect origin flows into Cliente.origen

- GIVEN a complete `mode='prospect'` draft
- WHEN the admin submits finalize
- AND the source `Prospecto.origen` is `NUEVO`
- THEN the resulting `Cliente.origen` is `NUEVO`
- AND when the source `Prospecto.origen` is `RECURRENTE_PRE_SISTEMA`
- THEN the resulting `Cliente.origen` is `RECURRENTE_PRE_SISTEMA`

#### Scenario: Cobrable CitaProspecto unchanged across origins

- GIVEN a `Prospecto` in `PASAJERO` state with `origen = RECURRENTE_PRE_SISTEMA`
- WHEN the existing `CitaProspecto` cobrable flow is exercised
- THEN the same cobrable path used for `origen = NUEVO` applies
- AND no new cobrable model or branch is introduced
