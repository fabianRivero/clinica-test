# Medical Form Sector Management Specification

## Purpose

The medical form sector management capability allows admin users to manage `Sector` records that group medical form sections (`FichaSeccion`) independently of service identity. Sectors enable multiple services (e.g., "Depilación definitiva" and "Depilación día de la madre") to share the same medical form template without duplicating `FichaSeccion` records. A service without a sector receives no medical form, preserving backward compatibility.

## Requirements

### Requirement: Sector CRUD via Admin Catalog API

The system SHALL provide create, read, update, and toggle (activate/deactivate) operations for Sector records via `/api/admin/catalogos/sectores/`, following the same contract as the five existing admin catalogs.

#### Scenario: Admin creates a sector

- GIVEN an authenticated admin user
- WHEN they submit the create form for sectores with `nombre="Depilación"`, `codigo="DEP"`, and `activo=true`
- THEN the sector is persisted and appears in the list

#### Scenario: Admin lists active sectors

- GIVEN an authenticated admin user
- WHEN they call `GET /api/admin/catalogos/sectores/?active=true`
- THEN only sectors with `activo=true` are returned, ordered by `orden`

#### Scenario: Admin toggles sector active state

- GIVEN an authenticated admin user viewing an active sector
- WHEN they toggle it to inactive
- THEN `activo` is set to `false` and the list refreshes

### Requirement: Sector Uniqueness Constraints

The system MUST enforce unique constraints on `nombre` and `codigo` for Sector records. Duplicate creation SHALL return a validation error.

#### Scenario: Duplicate sector name rejected

- GIVEN an authenticated admin user
- WHEN they attempt to create a sector with `nombre="Depilación"` when a sector with that name already exists
- THEN a validation error is returned and no new record is created

#### Scenario: Duplicate sector code rejected

- GIVEN an authenticated admin user
- WHEN they attempt to create a sector with `codigo="DEP"` when a sector with that code already exists
- THEN a validation error is returned and no new record is created

### Requirement: Service Without Sector Shows No Medical Form

The system SHALL NOT display a medical form during prospect conversion when the service has no sector assigned.

#### Scenario: Service null sector shows no form

- GIVEN a service configured with `sector=null`
- WHEN a prospect reaches the medical form step during conversion
- THEN no medical form fields are rendered

### Requirement: Service With Sector Shows Sector-Scoped Form

The system SHALL filter `FichaSeccion` records by the service's assigned sector when rendering the medical form.

#### Scenario: Service with sector shows matching sections

- GIVEN a service configured with `sector="Depilación"`
- WHEN a prospect reaches the medical form step during conversion
- THEN only `FichaSeccion` records linked to that sector are displayed

#### Scenario: Multiple services share same sector sections

- GIVEN service A with `sector="Depilación"` and service B also with `sector="Depilación"`
- WHEN prospects for both services reach the medical form step
- THEN both see the identical set of `FichaSeccion` records

#### Scenario: New service shares existing sector form

- GIVEN a new service "Depilación día de la madre" is created with `sector="Depilación"`
- AND "Depilación definitiva" is an existing service with `sector="Depilación"`
- WHEN a prospect converts through "Depilación día de la madre"
- THEN they see the same medical form sections as "Depilación definitiva" prospects

### Requirement: Sector Dropdown in Service Form

The system SHALL display a sector dropdown in the service create/edit form at `/cms/catalogos/todos-los-servicios/`, allowing selection of a sector or leaving it empty.

#### Scenario: Sector dropdown visible with empty option

- GIVEN an authenticated admin user on the service create page
- WHEN the page loads
- THEN a sector dropdown is displayed with all active sectors as options
- AND an empty option is present to allow clearing the selection
