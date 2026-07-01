# Delta for medical-form-section-editor

## MODIFIED Requirements

### Requirement: REQ-7 — Section Update

The system SHALL support `PUT /api/admin/catalogos/secciones-ficha/<id>/` updating `nombre`, `codigo`, `sector`, `proc_estetico`, and `activo`. The `orden` field is NOT updatable; the server auto-assigns it on create and preserves the existing value on every update. Any `orden` or `order` field sent in the update payload is ignored.
(Previously: `orden` was listed as an updatable field)

#### Scenario: Edit section preserves orden

- GIVEN an existing section with id `5` and `orden` set to a known value
- WHEN `PUT /api/admin/catalogos/secciones-ficha/5/` is called with updated `{nombre: "Updated Name", ...}`
- THEN the response is HTTP 200 and the `orden` value is unchanged

#### Scenario: Update payload with order field is ignored

- GIVEN an existing section with id `5` and `orden` equal to `3`
- WHEN `PUT /api/admin/catalogos/secciones-ficha/5/` is called with `{nombre: "Updated", order: 999}`
- THEN the response is HTTP 200, the persisted `orden` is still `3`, and the `order` value in the payload is ignored

## REMOVED Requirements

### Requirement: REQ-11 — Reorder Sections

(Reason: Manual `orden` assignment is removed. The server auto-assigns `orden = max(orden) + 1` on every create and preserves the existing `orden` on every update. There is no longer any manual reorder path for `secciones-ficha` entries.)
(Migration: None — the behavior is replaced by automatic ordering on create.)
