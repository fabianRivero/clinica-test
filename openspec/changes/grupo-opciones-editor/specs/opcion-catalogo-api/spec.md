# opcion-catalogo-api Specification

## Purpose

Nested REST sub-endpoints under `/api/admin/catalogos/grupos-opciones/<grupo_id>/opciones/` for CRUD and soft-delete toggle of `OpcionCatalogo`. Powers the option management modal.

## Requirements

### Requirement: REQ-1 — Nested Option List

The system SHALL list `OpcionCatalogo` entries for a group via `GET`. The endpoint SHALL accept `?active=true|false` to filter by `activo` and `?q=<term>` to search `codigo`, `nombre`, `valor`. Response is JSON ordered by `orden` ascending.

#### Scenario: List active options by default

- GIVEN a group (ID `1`) with 3 active and 2 inactive options
- WHEN admin requests `GET /api/admin/catalogos/grupos-opciones/1/opciones/`
- THEN only the 3 active options are returned

#### Scenario: Filter and search

- GIVEN a group with active and inactive options including `nombre` "vacuna"
- WHEN the request includes `?active=false&q=vacuna`
- THEN only inactive options matching "vacuna" are returned

#### Scenario: Group not found returns 404

- GIVEN no group with ID `9999` exists
- WHEN admin requests `GET /api/admin/catalogos/grupos-opciones/9999/opciones/`
- THEN HTTP 404 is returned

### Requirement: REQ-2 — Create Single Option

The system SHALL create a single `OpcionCatalogo` via `POST`. Request body SHALL contain `codigo`, `nombre`, `valor`; `orden` is optional and auto-increments if omitted. `codigo` SHALL be unique within the same `grupo`.

#### Scenario: Create with required fields

- GIVEN a group (ID `1`) exists
- WHEN admin sends `POST` with `{"codigo":"A","nombre":"Opcion A","valor":"a"}`
- THEN HTTP 201 is returned with the created option and auto-assigned `orden`

#### Scenario: Duplicate codigo or missing field returns 400

- GIVEN a group already has `codigo` "A"
- WHEN admin sends `POST` with `{"codigo":"A","nombre":"Dup","valor":"dup"}`
- THEN HTTP 400 with a validation error on `codigo`

- GIVEN a group (ID `1`) exists
- WHEN admin sends `POST` with `{"codigo":"X","valor":"x"}` (missing `nombre`)
- THEN HTTP 400 with a validation error on `nombre`

#### Scenario: Non-existent grupo returns 404

- GIVEN no group with ID `9999` exists
- WHEN admin sends `POST` to that group
- THEN HTTP 404 is returned

### Requirement: REQ-3 — Bulk Create Options

The system SHALL create multiple `OpcionCatalogo` via `POST` with array body `{"opciones":[...]}`, wrapped in `transaction.atomic()`. Any failure rolls back the entire batch.

#### Scenario: Bulk create succeeds

- GIVEN a group (ID `1`) exists
- WHEN admin sends `POST` with two valid options
- THEN HTTP 201 with both created options, no partial state

#### Scenario: Partial failure rolls back all

- GIVEN a group (ID `1`) exists
- WHEN admin sends a batch containing a duplicate `codigo`
- THEN HTTP 400 and no options are created

### Requirement: REQ-4 — Update Option

The system SHALL update an existing `OpcionCatalogo` via `PATCH`. Request body MAY contain `nombre`, `valor`, `orden`, `activo`.

#### Scenario: Update fields

- GIVEN a group (ID `1`) has an option (ID `5`)
- WHEN admin sends `PATCH` with `{"nombre":"NewName"}`
- THEN HTTP 200 with the updated option

#### Scenario: Update non-existent returns 404

- GIVEN a group (ID `1`) has no option (ID `9999`)
- WHEN admin sends `PATCH` to that option
- THEN HTTP 404 is returned

### Requirement: REQ-5 — Toggle Active State

The system SHALL toggle `activo` via `POST /<grupo_id>/opciones/<opcion_id>/toggle/`. Toggling to `activo=false` is soft-delete. Inactive options SHALL NOT appear in `FichaCampo` serializations.

#### Scenario: Toggle to inactive

- GIVEN a group option (ID `5`) is active
- WHEN admin sends `POST` to the toggle endpoint
- THEN HTTP 200 with `{"activo":false}` and the option disappears from the default list

#### Scenario: Toggle non-existent returns 404

- GIVEN a group with no option (ID `9999`)
- WHEN admin sends toggle request
- THEN HTTP 404 is returned

### Requirement: REQ-6 — Authorization

All endpoints SHALL require an authenticated admin session. Unauthenticated requests return HTTP 401; non-admin users receive HTTP 403.

#### Scenario: Auth required

- GIVEN no authenticated admin session exists
- WHEN any request is sent to the endpoint
- THEN HTTP 401 is returned if unauthenticated, HTTP 403 if non-admin
