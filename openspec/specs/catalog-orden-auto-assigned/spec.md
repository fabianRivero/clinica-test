# Catalog Orden Auto-Assigned Specification

## Purpose

The `orden` field on four admin catalogs (`especialidades`, `campos-ficha`, `secciones-ficha`, `sectores`) is fully server-managed. The server auto-assigns `orden = max(orden) + 1` on every create and preserves the existing value on every update. `orden` MUST NOT appear in list response metadata, per-item values, or form field definitions. List ordering remains by `orden, nombre`.

## Requirements

### Requirement: Auto-Assign Orden on Create

The system MUST ignore any `order` field in the create payload for `especialidades`, `campos-ficha`, `secciones-ficha`, and `sectores` catalogs. On create, the server MUST assign `orden` equal to `max(existing orden) + 1`, regardless of any `order` value sent in the payload.

#### Scenario: Create without order field assigns max+1

- GIVEN N existing items in the catalog with the highest `orden` equal to N
- WHEN `POST /api/admin/catalogos/{catalog_key}/crear/` is called with a valid payload that does NOT include an `order` field
- THEN the response is HTTP 201 and the created item's `orden` equals `N + 1`

#### Scenario: Create with explicit order field ignores the value

- GIVEN N existing items in the catalog with the highest `orden` equal to N
- WHEN `POST /api/admin/catalogos/{catalog_key}/crear/` is called with a valid payload that includes `order: 999`
- THEN the response is HTTP 201 and the created item's `orden` equals `N + 1`, not `999`

### Requirement: Preserve Orden on Update

The system MUST ignore any `order` field in the update payload for `especialidades`, `campos-ficha`, `secciones-ficha`, and `sectores` catalogs. On update, the server MUST preserve the existing `orden` value without modification.

#### Scenario: Update with order field preserves existing orden

- GIVEN an existing catalog item with `orden` set to a known value (e.g., `3`)
- WHEN `POST /api/admin/catalogos/{catalog_key}/<id>/actualizar/` is called with an updated payload that includes `order: 999`
- THEN the response is HTTP 200 and the persisted `orden` is still `3`

### Requirement: Orden Hidden in List Metadata

The system MUST NOT include an `Orden` entry in the `metadata` array of any item returned by `GET /api/admin/catalogos/{catalog_key}/` for `especialidades`, `campos-ficha`, `secciones-ficha`, or `sectores`.

#### Scenario: List response has no Orden metadata entry

- GIVEN existing catalog items
- WHEN `GET /api/admin/catalogos/{catalog_key}/` is called
- THEN for every item in `items`, no metadata entry has `label` equal to `"Orden"`

### Requirement: Orden Hidden in List Values

The system MUST NOT include an `order` field in the per-item `values` object returned by `GET /api/admin/catalogos/{catalog_key}/` for `especialidades`, `campos-ficha`, `secciones-ficha`, or `sectores`.

#### Scenario: List values have no order field

- GIVEN existing catalog items
- WHEN `GET /api/admin/catalogos/{catalog_key}/` is called
- THEN for every item in `items`, the `values` object does not contain an `order` key

### Requirement: Orden Hidden in Form Fields

The system MUST NOT include an `order` field definition in the top-level `fields` array returned by `GET /api/admin/catalogos/{catalog_key}/` for `especialidades`, `campos-ficha`, `secciones-ficha`, or `sectores`.

#### Scenario: Form fields array has no order entry

- GIVEN existing catalog items
- WHEN `GET /api/admin/catalogos/{catalog_key}/` is called
- THEN the `fields` array contains no entry with `name` equal to `"order"`

### Requirement: List Ordering Unchanged

The system MUST return catalog items ordered by `orden, nombre` (or the catalog's natural ordering field) on `GET /api/admin/catalogos/{catalog_key}/` for `especialidades`, `campos-ficha`, `secciones-ficha`, and `sectores`. This behavior is unchanged; this requirement locks the existing ordering contract.

#### Scenario: Items returned ordered by orden then nombre

- GIVEN catalog items with `orden` values `1`, `2`, and `3`
- WHEN `GET /api/admin/catalogos/{catalog_key}/` is called with no ordering query parameter
- THEN items appear in the response in ascending `orden` order
