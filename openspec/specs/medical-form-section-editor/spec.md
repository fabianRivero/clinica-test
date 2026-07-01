# Medical Form Section Editor Specification

## Purpose

Enable clinic admins to visually manage medical form sections (`FichaSeccion`) via the admin catalog API, with dual binding to `Sector` and/or `ProcEstetico`, and full CRUD operations including soft-delete. The `orden` field is server-managed: auto-assigned as `max(orden)+1` on create, preserved on update, and hidden from admin visibility.

## Requirements

### Requirement: REQ-1 — Section Creation with Sector Binding

The system SHALL allow creating a `FichaSeccion` with `sector` assigned and `proc_estetico` null. The API endpoint `POST /api/admin/catalogos/secciones-ficha/` MUST accept `{nombre, codigo, sector, activo}` and persist the section scoped to the sector. The `orden` field is auto-assigned as `max(orden)+1` regardless of any `order` field in the payload.

### Requirement: REQ-2 — Section Creation with ProcEstetico Binding

The system SHALL allow creating a `FichaSeccion` with `proc_estetico` assigned and `sector` null. The API MUST accept `{nombre, codigo, proc_estetico, activo}` and persist the section scoped to the procedure. The `orden` field is auto-assigned as `max(orden)+1` regardless of any `order` field in the payload.

### Requirement: REQ-3 — Section Creation with Dual Binding

The system SHALL allow creating a `FichaSeccion` with both `sector` and `proc_estetico` assigned simultaneously. Both bindings MUST be persisted. The `orden` field is auto-assigned as `max(orden)+1` regardless of any `order` field in the payload.

### Requirement: REQ-4 — At Least One Binding Required

The system SHALL reject creation of a `FichaSeccion` with both `sector` and `proc_estetico` null, returning HTTP 400 with an error message indicating at least one binding is required.

### Requirement: REQ-5 — Unique Codigo Per ProcEstetico

The system SHALL enforce `UniqueConstraint(proc_estetico, codigo)` at the database level. Creating a section with a `codigo` already used within the same `proc_estetico` MUST return HTTP 400. The same `codigo` MAY be reused across different `proc_estetico` values.

### Requirement: REQ-6 — List Sections Filtered by Sector

The system SHALL support `GET /api/admin/catalogos/secciones-ficha/?sector=<id>` returning only sections bound to that sector.

### Requirement: REQ-7 — List Sections Filtered by ProcEstetico

The system SHALL support `GET /api/admin/catalogos/secciones-ficha/?proc_estetico=<id>` returning only sections bound to that procedure.

### Requirement: REQ-8 — Text Search on Codigo and Nombre

The system SHALL support `GET /api/admin/catalogos/secciones-ficha/?q=<term>` filtering sections where `codigo` OR `nombre` contains the search term (case-insensitive).

### Requirement: REQ-9 — Section Update

The system SHALL support `PUT /api/admin/catalogos/secciones-ficha/<id>/` updating `nombre`, `codigo`, `sector`, `proc_estetico`, and `activo`. The `orden` field is NOT updatable; the server preserves the existing value. Any `orden` or `order` field sent in the update payload is ignored.

### Requirement: REQ-10 — Toggle Active (Soft Delete)

The system SHALL support toggling `activo` via PATCH `activo` field, performing a soft-delete without removing the record.

## Scenarios

### Scenario: Create section with sector only

- GIVEN a valid `Sector` with id `1` exists and no `proc_estetico` is provided
- WHEN `POST /api/admin/catalogos/secciones-ficha/` is called with `{nombre: "History", codigo: "HIST", sector: 1, activo: true}`
- THEN the response is HTTP 201 with `sector` set to `1` and `proc_estetico` null
- AND the `orden` field is auto-assigned as `max(existing orden) + 1`

### Scenario: Create section with proc_estetico only

- GIVEN a valid `ProcEstetico` with id `2` exists and no `sector` is provided
- WHEN the same POST request is made with `{nombre: "Consent", codigo: "CONS", proc_estetico: 2, activo: true}`
- THEN the response is HTTP 201 with `proc_estetico` set to `2` and `sector` null
- AND the `orden` field is auto-assigned as `max(existing orden) + 1`

### Scenario: Create section with both bindings

- GIVEN `Sector` id `1` and `ProcEstetico` id `2` both exist
- WHEN POST is called with both `sector: 1` and `proc_estetico: 2`
- THEN the response is HTTP 201 with both bindings persisted
- AND the `orden` field is auto-assigned as `max(existing orden) + 1`

### Scenario: Create section without any binding

- GIVEN no `sector` and no `proc_estetico` are provided
- WHEN POST is called with `{nombre: "Orphan", codigo: "ORPH", activo: true}`
- THEN the response is HTTP 400 with error indicating at least one binding is required

### Scenario: Create section with duplicate codigo within same proc_estetico

- GIVEN `ProcEstetico` id `2` already has a section with `codigo: "HIST"`
- WHEN POST is called with `{nombre: "History 2", codigo: "HIST", proc_estetico: 2, activo: true}`
- THEN the response is HTTP 400 with uniqueness constraint error

### Scenario: Create section with codigo that exists in another proc_estetico

- GIVEN `ProcEstetico` id `2` has `codigo: "HIST"` and `ProcEstetico` id `3` has no such codigo
- WHEN POST is called with `{codigo: "HIST", proc_estetico: 3, ...}`
- THEN the response is HTTP 201 — codigo may repeat across different procedures

### Scenario: Create section with explicit order field is ignored

- GIVEN N existing sections with the highest `orden` equal to N
- WHEN POST is called with `{..., order: 999}`
- THEN the response is HTTP 201 and the created item's `orden` equals `N + 1`, not `999`

### Scenario: List sections filtered by sector

- GIVEN sections bound to `sector: 1` and `sector: 2` exist
- WHEN `GET /api/admin/catalogos/secciones-ficha/?sector=1`
- THEN only sections with `sector=1` are returned

### Scenario: List sections filtered by proc_estetico

- GIVEN sections bound to `proc_estetico: 2` and `proc_estetico: 3` exist
- WHEN `GET /api/admin/catalogos/secciones-ficha/?proc_estetico=2`
- THEN only sections with `proc_estetico=2` are returned

### Scenario: Search sections by codigo or nombre

- GIVEN sections with `codigo: "HIST", nombre: "Patient History"` and `codigo: "CONS", nombre: "Consent Form"` exist
- WHEN `GET /api/admin/catalogos/secciones-ficha/?q=history`
- THEN the section with `codigo: "HIST"` is returned (match on nombre)

### Scenario: Edit section preserves orden

- GIVEN an existing section with id `5` and `orden` set to a known value
- WHEN `PUT /api/admin/catalogos/secciones-ficha/5/` is called with updated `{nombre: "Updated Name", ...}`
- THEN the response is HTTP 200 and the `orden` value is unchanged

### Scenario: Update payload with order field is ignored

- GIVEN an existing section with id `5` and `orden` equal to `3`
- WHEN `PUT /api/admin/catalogos/secciones-ficha/5/` is called with `{nombre: "Updated", order: 999}`
- THEN the response is HTTP 200, the persisted `orden` is still `3`, and the `order` value in the payload is ignored

### Scenario: Toggle activo

- GIVEN a section with `activo: true`
- WHEN `PATCH /api/admin/catalogos/secciones-ficha/5/` with `{activo: false}` is called
- THEN the response is HTTP 200 and `activo` is `false`
