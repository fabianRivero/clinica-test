# cliente-origen Specification

## Purpose

Tag every `Cliente` with an `origen` that records how they entered the system: `NUEVO` (newly acquired) or `RECURRENTE_PRE_SISTEMA` (returning patient known to the clinic before this system). The field is the source of truth for cobrable-appointment eligibility and admin reporting.

## Requirements

### Requirement: origen field semantics

The `Cliente` model MUST expose an `origen` field with a closed enumeration of exactly two values: `NUEVO` and `RECURRENTE_PRE_SISTEMA`. The field MUST be `NOT NULL` and MUST default to `NUEVO`. Every API serializer returning a `Cliente` MUST expose the field.

#### Scenario: Existing Cliente persists with the default origin

- GIVEN a `Cliente` row created before this change
- WHEN the migration applies
- THEN that row's `origen` is set to `NUEVO`
- AND the row remains queryable

#### Scenario: New Cliente created with each value

- GIVEN a wizard finalize with `origen` in the payload
- WHEN finalize completes
- THEN the resulting row stores the supplied value
- AND omitting `origen` in the payload defaults it to `NUEVO`

#### Scenario: Unknown origin value rejected on creation

- GIVEN a creation payload with `origen = "ALGOTRO"`
- WHEN the wizard finalize runs
- THEN the response returns 400
- AND no `Cliente` or `Usuario` row is created

#### Scenario: origin values exposed in API serialization

- GIVEN a `Cliente` with `origen = RECURRENTE_PRE_SISTEMA`
- WHEN any serializer returning this `Cliente` is invoked
- THEN the payload includes the field with the exact string `RECURRENTE_PRE_SISTEMA`

### Requirement: write-once origin

`origen` SHALL be settable on creation only. After creation it SHALL be immutable through every admin profile-edit endpoint: any PATCH that sets, changes, or clears `origen` MUST return 400, and any PATCH that omits `origen` MUST leave the stored value untouched.

#### Scenario: PATCH attempting to change origen returns 400

- GIVEN a `Cliente` with `origen = NUEVO`
- WHEN admin sends `PATCH /api/admin/clientes/{id}/perfil/` with `{"origen": "RECURRENTE_PRE_SISTEMA"}`
- THEN the response returns 400
- AND the live row's `origen` remains `NUEVO`

#### Scenario: PATCH omitting origen preserves the stored value

- GIVEN a `Cliente` with `origen = RECURRENTE_PRE_SISTEMA`
- WHEN admin sends `PATCH /api/admin/clientes/{id}/perfil/` with `{"telefono": "70000000"}`
- THEN `telefono` updates
- AND `origen` remains `RECURRENTE_PRE_SISTEMA`

#### Scenario: Reactivation finalize does not rewrite origen

- GIVEN a reactivation draft whose stored `origen` differs from the live `Cliente.origen`
- WHEN admin finalizes the reactivation
- THEN the live `Cliente.origen` is unchanged

### Requirement: cobrable appointment reuse

A `Cliente` with `origen = RECURRENTE_PRE_SISTEMA` SHALL receive cobrable appointments through the existing `CitaMedica` (which already accepts `precio`). The system MUST NOT introduce a new appointment model, a new cobrable path, or any special-cased flow for pre-system patients.

#### Scenario: Recurring pre-system client books a cobrable CitaMedica

- GIVEN a `Cliente` with `origen = RECURRENTE_PRE_SISTEMA`
- WHEN admin records a medical appointment with a non-null `precio`
- THEN the appointment is persisted as a `CitaMedica`
- AND it is rendered as cobrable

#### Scenario: No new cobrable model introduced

- GIVEN the system after this change
- WHEN appointment creation paths are inspected
- THEN only `CitaMedica` is offered for cobrable appointments
- AND no cobrable-special path is required for `RECURRENTE_PRE_SISTEMA` clients

### Requirement: reporting visibility

The `origen` value SHALL be exposed as a visible badge or category in every admin listing and report that renders a `Cliente`. The two values MUST be visually distinguishable.

#### Scenario: Admin listing shows the origen badge

- GIVEN two clients: `origen = NUEVO` and `origen = RECURRENTE_PRE_SISTEMA`
- WHEN the admin opens `/cms/clientes`
- THEN each row displays the corresponding badge
