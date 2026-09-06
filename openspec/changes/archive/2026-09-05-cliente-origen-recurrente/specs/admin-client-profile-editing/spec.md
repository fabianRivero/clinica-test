# Delta for admin-client-profile-editing

## MODIFIED Requirements

### Requirement: Editable Fields

The system SHALL accept partial updates on exactly these 13 fields: `primerNombre`, `segundoNombre`, `apellidoPaterno`, `apellidoMaterno`, `ci`, `username`, `email`, `telefono`, `fechaNacimiento`, `nroHijos`, `ocupacion`, `direccionDomicilio`, `observacionesCliente`. The endpoint MUST reject any field outside that list, MUST NOT accept `password`, and MUST preserve the current value of any omitted field. The `origen` field is part of the `Cliente` payload but MUST be treated as read-only through this endpoint: any PATCH that includes `origen` MUST return 400, and any PATCH that omits `origen` MUST leave the stored value untouched.

(Previously: the 13-field whitelist was the only constraint on the perfil endpoint; `origen` is now added to the read-only list and any attempt to write it returns 400.)

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

#### Scenario: PATCH attempting to change origen returns 400

- GIVEN an authenticated admin
- AND a live `Cliente` with `origen = NUEVO`
- WHEN they send `PATCH /api/admin/clientes/{id}/perfil/` with `{"origen": "RECURRENTE_PRE_SISTEMA"}`
- THEN the response returns 400 with a validation error
- AND the live row's `origen` remains `NUEVO`

#### Scenario: PATCH omitting origen preserves the stored value

- GIVEN a live `Cliente` with `origen = RECURRENTE_PRE_SISTEMA`
- WHEN admin sends `PATCH /api/admin/clientes/{id}/perfil/` with `{"telefono": "70000000"}`
- THEN `telefono` updates
- AND `origen` remains `RECURRENTE_PRE_SISTEMA`
