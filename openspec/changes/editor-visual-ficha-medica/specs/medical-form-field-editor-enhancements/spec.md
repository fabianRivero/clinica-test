# Medical Form Field Editor Enhancements Specification

## Purpose

Enhance the `campos-ficha` form with type-conditional UI and backend validation, ensuring `grupo_opciones` is required for selection-type fields and the frontend renders the appropriate input widget per `tipo_campo`.

## Requirements

### Requirement: REQ-1 — Tipo TEXTO Does Not Require GrupoOpciones

The system SHALL allow creating a `FichaCampo` with `tipo_campo=TEXTO` without providing `grupo_opciones`. The backend MUST accept the payload and the frontend form MUST render a textarea widget.

### Requirement: REQ-2 — Tipo NUMERO Does Not Require GrupoOpciones

The system SHALL allow creating a `FichaCampo` with `tipo_campo=NUMERO` without `grupo_opciones`. The frontend form MUST render a number input widget.

### Requirement: REQ-3 — Tipo FECHA Does Not Require GrupoOpciones

The system SHALL allow creating a `FichaCampo` with `tipo_campo=FECHA` without `grupo_opciones`. The frontend form MUST render a date picker widget.

### Requirement: REQ-4 — Tipo BOOLEANO Does Not Require GrupoOpciones

The system SHALL allow creating a `FichaCampo` with `tipo_campo=BOOLEANO` without `grupo_opciones`. The frontend form MUST render a checkbox widget.

### Requirement: REQ-5 — Tipo SELECCION Requires GrupoOpciones

The system SHALL reject creation of a `FichaCampo` with `tipo_campo=SELECCION` when `grupo_opciones` is null, returning HTTP 400 with an error message indicating `grupo_opciones` is required for selection fields.

### Requirement: REQ-6 — Tipo MULTISELECCION Requires GrupoOpciones

The system SHALL reject creation of a `FichaCampo` with `tipo_campo=MULTISELECCION` when `grupo_opciones` is null, returning HTTP 400.

### Requirement: REQ-7 — Tipo SELECCION Accepts GrupoOpciones

The system SHALL allow creating a `FichaCampo` with `tipo_campo=SELECCION` when `grupo_opciones` is provided. The frontend form MUST render a dropdown widget populated from the associated `GrupoOpciones`.

### Requirement: REQ-8 — Tipo MULTISELECCION Accepts GrupoOpciones

The system SHALL allow creating a `FichaCampo` with `tipo_campo=MULTISELECCION` when `grupo_opciones` is provided. The frontend form MUST render a multi-select widget populated from the associated `GrupoOpciones`.

### Requirement: REQ-9 — Conditional Fields for SELECCION/MULTISELECCION

The frontend form SHALL display `es_multiple` and `permite_detalle` fields only when `tipo_campo` is `SELECCION` or `MULTISELECCION`. These fields MUST be hidden for `TEXTO`, `NUMERO`, `FECHA`, and `BOOLEANO`.

### Requirement: REQ-10 — Edit Preserves Values with Type Warning

When editing a `FichaCampo` and changing its `tipo_campo` to an incompatible type (e.g., from `TEXTO` to `SELECCION`), the system SHOULD display a warning if existing saved values may become incompatible with the new type.

## Scenarios

### Scenario: Create TEXTO field without grupo_opciones

- GIVEN `tipo_campo` is `TEXTO` and `grupo_opciones` is not provided
- WHEN `POST /api/admin/catalogos/campos-ficha/` is called with valid payload
- THEN the response is HTTP 201 and the field is created

### Scenario: Create NUMERO field without grupo_opciones

- GIVEN `tipo_campo` is `NUMERO` and `grupo_opciones` is not provided
- WHEN POST is called
- THEN the response is HTTP 201

### Scenario: Create FECHA field without grupo_opciones

- GIVEN `tipo_campo` is `FECHA` and `grupo_opciones` is not provided
- WHEN POST is called
- THEN the response is HTTP 201

### Scenario: Create BOOLEANO field without grupo_opciones

- GIVEN `tipo_campo` is `BOOLEANO` and `grupo_opciones` is not provided
- WHEN POST is called
- THEN the response is HTTP 201

### Scenario: Create SELECCION field without grupo_opciones

- GIVEN `tipo_campo` is `SELECCION` and `grupo_opciones` is null
- WHEN POST is called
- THEN the response is HTTP 400 with error indicating grupo_opciones is required

### Scenario: Create MULTISELECCION field without grupo_opciones

- GIVEN `tipo_campo` is `MULTISELECCION` and `grupo_opciones` is null
- WHEN POST is called
- THEN the response is HTTP 400

### Scenario: Create SELECCION field with grupo_opciones

- GIVEN `tipo_campo` is `SELECCION` and `grupo_opciones` references a valid group
- WHEN POST is called
- THEN the response is HTTP 201

### Scenario: Create MULTISELECCION field with grupo_opciones

- GIVEN `tipo_campo` is `MULTISELECCION` and `grupo_opciones` references a valid group
- WHEN POST is called
- THEN the response is HTTP 201

### Scenario: Frontend renders textarea for TEXTO

- GIVEN a `FichaCampo` with `tipo_campo=TEXTO` is displayed in the form
- WHEN the form is rendered
- THEN a `<textarea>` element is shown for this field

### Scenario: Frontend renders number input for NUMERO

- GIVEN a `FichaCampo` with `tipo_campo=NUMERO` is displayed
- WHEN the form is rendered
- THEN an `<input type="number">` element is shown

### Scenario: Frontend renders date picker for FECHA

- GIVEN a `FichaCampo` with `tipo_campo=FECHA` is displayed
- WHEN the form is rendered
- THEN a date picker widget is shown

### Scenario: Frontend renders checkbox for BOOLEANO

- GIVEN a `FichaCampo` with `tipo_campo=BOOLEANO` is displayed
- WHEN the form is rendered
- THEN a checkbox input is shown

### Scenario: Frontend renders dropdown for SELECCION

- GIVEN a `FichaCampo` with `tipo_campo=SELECCION` and valid `grupo_opciones` is displayed
- WHEN the form is rendered
- THEN a dropdown (single select) populated from `GrupoOpciones` options is shown

### Scenario: Frontend renders multi-select for MULTISELECCION

- GIVEN a `FichaCampo` with `tipo_campo=MULTISELECCION` and valid `grupo_opciones` is displayed
- WHEN the form is rendered
- THEN a multi-select checkbox group populated from `GrupoOpciones` options is shown

### Scenario: es_multiple and permite_detalle hidden for non-selection types

- GIVEN a `FichaCampo` with `tipo_campo=TEXTO` is displayed
- WHEN the form is rendered
- THEN `es_multiple` and `permite_detalle` fields are NOT visible

### Scenario: Edit preserves values with incompatibility warning

- GIVEN a `FichaCampo` with `tipo_campo=TEXTO` and value "some text" exists
- WHEN the user changes `tipo_campo` to `SELECCION` in the edit form
- THEN a warning is displayed indicating existing values may become incompatible