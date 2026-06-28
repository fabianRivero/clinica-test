# grupo-opciones-editor-modal Specification

## Purpose

Modal UI on the `grupos-opciones` catalog page enabling admins to view, create, edit, and toggle `OpcionCatalogo` entries. Closes the gap where an admin defines a `MULTISELECCION` field but has no UI to populate its options.

## Requirements

### Requirement: REQ-1 — Modal Trigger and Header

The system SHALL display an "Administrar opciones" button on each `grupos-opciones` catalog row. Clicking opens a modal with the `GrupoOpciones.nombre` in the header.

#### Scenario: Button visible on each row

- GIVEN the admin is on the `grupos-opciones` catalog list
- THEN each row displays an "Administrar opciones" button for that `grupo_id`

#### Scenario: Modal header shows group name

- GIVEN a group named "Tipo de Vacuna"
- WHEN its "Administrar opciones" button is clicked
- THEN the modal header displays "Tipo de Vacuna"

### Requirement: REQ-2 — Option List Display

The modal SHALL display options showing `codigo`, `nombre`, `valor`, `orden`, `activo`. Active options shown by default. Empty groups display "Sin opciones".

#### Scenario: Active options shown by default

- GIVEN a group with 3 active and 2 inactive options
- WHEN the modal opens
- THEN only the 3 active options are displayed

#### Scenario: Empty state

- GIVEN a group with no options
- WHEN the modal opens
- THEN "Sin opciones" is displayed

### Requirement: REQ-3 — Filter and Search

The modal SHALL provide an `activo` filter (all / active / inactive) and a search input filtering by `codigo`, `nombre`, `valor`.

#### Scenario: Filter to inactive options

- GIVEN a group with active and inactive options
- WHEN the admin selects "Inactivas"
- THEN only inactive options are displayed

#### Scenario: Search narrows results

- GIVEN a group with an option `nombre` "Gripe"
- WHEN the admin types "Gripe" in search
- THEN only matching options are displayed

### Requirement: REQ-4 — Create Option

The modal SHALL provide an "Agregar opción" button revealing an inline form with `codigo`, `nombre`, `valor`, optional `orden`. On success the list refreshes automatically.

#### Scenario: Create successfully

- GIVEN a group (ID `1`)
- WHEN the admin fills `codigo` "D", `nombre` "NuevaOp", `valor` "d" and submits
- THEN the option appears in the list and the form clears

#### Scenario: Validation error on missing required field

- GIVEN the "Agregar opción" form is open
- WHEN the admin submits without `codigo`
- THEN a validation error is shown inline and no request is sent

### Requirement: REQ-5 — Edit Option

Each option row SHALL have an "Editar" button opening the inline form pre-filled with current values. Submitting calls `PATCH`. On success the list refreshes.

#### Scenario: Edit pre-fills and updates

- GIVEN a group option with `nombre` "OldName"
- WHEN the admin clicks "Editar" and changes `nombre` to "NewName"
- THEN the list refreshes showing "NewName"

### Requirement: REQ-6 — Toggle Active State

Each option row SHALL have a toggle/button to change `activo`. Clicking calls the toggle endpoint. On success the list refreshes.

#### Scenario: Toggle to inactive

- GIVEN a group option with `activo` true
- WHEN the admin clicks the toggle
- THEN `activo` becomes false and the list refreshes

### Requirement: REQ-7 — Multi-Select Checkboxes

Each option row SHALL have a checkbox. These are for future bulk actions and have no effect in this version.

#### Scenario: Checkboxes present but non-functional

- GIVEN the modal is open
- THEN each row has a checkbox
- AND checking boxes has no immediate effect

### Requirement: REQ-8 — Modal Dismissal and Accessibility

The modal SHALL close via X button, backdrop click, or Escape, and SHALL be fully keyboard-navigable with focus trapped inside.

#### Scenario: Close via backdrop or Escape; Tab navigation

- GIVEN the modal is open
- WHEN the admin clicks the backdrop or presses Escape
- THEN the modal closes
- WHEN the admin presses Tab
- THEN focus moves through all interactive elements without leaving the modal
