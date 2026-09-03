# Spec: admin-client-profile-editing

## Purpose

Define the admin-only endpoint and frontend behavior that lets an admin edit a single live client's profile without contaminating reactivation drafts, and prevent reactivation finalize from silently overwriting live identity fields.

## Requirements

### Requirement: Live Profile Endpoint

The system MUST expose `PATCH /api/admin/clientes/{id}/perfil/` as an admin-only endpoint that updates the live `Cliente` and its `Usuario` in a single transaction. The endpoint MUST reject any `password` field, MUST accept partial updates, and MUST return the updated profile in camelCase matching the 13 contract fields.

#### Scenario: Update single field (primerNombre)

- GIVEN an authenticated admin
- WHEN they send `PATCH /api/admin/clientes/{id}/perfil/` with `{"primerNombre": "Maria"}`
- THEN the live `Usuario.primer_nombre` is updated
- AND the response returns 200 with the updated profile

#### Scenario: Username collision

- GIVEN an authenticated admin
- AND a different `Usuario` already has `username` "taken"
- WHEN they send `PATCH /api/admin/clientes/{id}/perfil/` with `{"username": "taken"}`
- THEN the response returns 400 with a validation error
- AND the live row is unchanged

#### Scenario: CI collision

- GIVEN an authenticated admin
- AND a different `Cliente` already has `ci` "1234567"
- WHEN they send `PATCH /api/admin/clientes/{id}/perfil/` with `{"ci": "1234567"}`
- THEN the response returns 400 with a validation error
- AND the live row is unchanged

### Requirement: Editable Fields

The system SHALL accept partial updates on exactly these 13 fields: `primerNombre`, `segundoNombre`, `apellidoPaterno`, `apellidoMaterno`, `ci`, `username`, `email`, `telefono`, `fechaNacimiento`, `nroHijos`, `ocupacion`, `direccionDomicilio`, `observacionesCliente`. The endpoint MUST reject any field outside that list, MUST NOT accept `password`, and MUST preserve the current value of any omitted field.

#### Scenario: Password rejected

- GIVEN an authenticated admin
- WHEN they send `PATCH /api/admin/clientes/{id}/perfil/` with `{"password": "newpass"}`
- THEN the response returns 400 with the error "password is not editable through this endpoint"
- AND the live `Usuario.set_password` is NOT invoked

#### Scenario: Unknown field rejected

- GIVEN an authenticated admin
- WHEN they send `PATCH /api/admin/clientes/{id}/perfil/` with `{"invalid": "x"}`
- THEN the response returns 400 with a validation error
- AND no live row is modified

#### Scenario: Partial update preserves omitted fields

- GIVEN a `Cliente` with `telefono` "111"
- WHEN admin sends `PATCH /api/admin/clientes/{id}/perfil/` with `{"email": "a@b.com"}`
- THEN `email` is updated
- AND `telefono` remains "111" on both `Usuario.telefono` and `Cliente.telefono`

### Requirement: Telefono Synchronization

The system MUST synchronize a `telefono` change to BOTH `Usuario.telefono` and `Cliente.telefono` inside the same transaction. If either write fails, both MUST roll back.

#### Scenario: Telefono updates both rows

- GIVEN an authenticated admin
- WHEN they send `PATCH /api/admin/clientes/{id}/perfil/` with `{"telefono": "70000000"}`
- THEN `Usuario.telefono` is set to "70000000"
- AND `Cliente.telefono` is set to "70000000"
- AND the response returns 200

### Requirement: FechaNacimiento Ownership

The system MUST persist `fechaNacimiento` to `Cliente.fecha_nacimiento` ONLY and MUST NOT modify `Usuario.fecha_nacimiento`.

#### Scenario: FechaNacimiento writes to Cliente only

- GIVEN an authenticated admin
- WHEN they send `PATCH /api/admin/clientes/{id}/perfil/` with `{"fechaNacimiento": "1990-01-15"}`
- THEN `Cliente.fecha_nacimiento` is set to "1990-01-15"
- AND `Usuario.fecha_nacimiento` is unchanged

### Requirement: Authorization

The system MUST restrict `PATCH /api/admin/clientes/{id}/perfil/` to authenticated admin users. Unauthenticated and non-admin callers MUST be rejected. Cross-branch admin access follows the existing pattern established by the `inactivar` and `migrar` endpoints: branch scoping is NOT enforced by this endpoint, so an authenticated admin from any branch can edit any client's profile (200 OK).

> **Note — cross-branch policy**: Branch scoping is intentionally NOT enforced here to match the existing admin client ViewSet behavior (see `inactivar`/`migrar` actions on the same ViewSet, both of which lack branch scoping). If product decides that branch isolation is required, file a new change that tightens authorization across ALL admin client actions, not just this one.

#### Scenario: Non-admin rejected

- GIVEN an authenticated non-admin user (e.g. `Cliente` or `Especialista`)
- WHEN they send `PATCH /api/admin/clientes/{id}/perfil/`
- THEN the response returns 403

#### Scenario: Unauthenticated rejected

- GIVEN an unauthenticated request
- WHEN they send `PATCH /api/admin/clientes/{id}/perfil/`
- THEN the response returns 401 or 403

#### Scenario: Cross-branch admin allowed (matches existing pattern)

- GIVEN an authenticated admin from branch A
- AND the target client belongs to branch B
- WHEN they send `PATCH /api/admin/clientes/{id}/perfil/`
- THEN the response returns 200 (admin-only authorization succeeds; no branch scoping is enforced)
- AND the live row is updated

### Requirement: Read-Only Wizard Step 1

The reactivation/new-procedure wizard step 1 MUST render every profile field except `observacionesCliente` as read-only/disabled. The prospect conversion flow (no existing `clienteId`) MUST keep all inputs editable as today.

#### Scenario: Reactivation step 1 is read-only

- GIVEN a reactivation/new-procedure wizard session for an existing client
- WHEN step 1 renders
- THEN `primerNombre`, `segundoNombre`, `apellidoPaterno`, `apellidoMaterno`, `ci`, `username`, `email`, `telefono`, `fechaNacimiento`, `nroHijos`, `ocupacion`, and `direccionDomicilio` are all readOnly/disabled
- AND `observacionesCliente` remains editable

#### Scenario: Prospect conversion step 1 is editable

- GIVEN a prospect conversion wizard session (no existing client)
- WHEN step 1 renders
- THEN all 13 profile inputs are editable (existing behavior)

### Requirement: Defensive Finalize

When finalizing a reactivation draft (`draft.cliente` exists), the system MUST NOT overwrite live `Usuario` or `Cliente` profile fields from `draft.datos_usuario`. Only operation, medical, biometric, and payment fields from the draft, plus `observacionesCliente` as the procedure annotation, SHALL be applied to live rows.

#### Scenario: Reactivation finalize does not touch live profile

- GIVEN a reactivation draft whose `datos_usuario` differs from the live `Cliente`/`Usuario`
- WHEN admin finalizes the wizard
- THEN live `Usuario.primer_nombre`, `Usuario.segundo_nombre`, `Usuario.apellido_paterno`, `Usuario.apellido_materno`, `Usuario.username`, `Usuario.email`, `Usuario.telefono`, `Cliente.telefono`, `Cliente.fecha_nacimiento`, `Cliente.ci`, `Cliente.nro_hijos`, `Cliente.direccion_domicilio`, and `Cliente.ocupacion` all remain unchanged
- AND only operation, medical, biometric, payment fields (and `observacionesCliente` as the annotation) are finalized onto live rows

#### Scenario: Prospect conversion finalize still writes profile fields

- GIVEN a prospect conversion draft (no existing `draft.cliente`)
- WHEN admin finalizes the wizard
- THEN profile fields from `datos_usuario` are written to the newly created `Usuario` and `Cliente` (existing behavior preserved)
