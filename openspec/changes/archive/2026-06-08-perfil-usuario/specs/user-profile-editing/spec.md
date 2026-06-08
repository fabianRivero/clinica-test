# Delta for user-profile-editing

## ADDED Requirements

### Requirement: Profile Edit Access

The system MUST allow authenticated users to edit their own profile data via PATCH to `/api/auth/me`.

#### Scenario: Edit username

- GIVEN an authenticated user
- WHEN they send `PATCH /api/auth/me` with `{"username": "newname"}`
- THEN username is updated and returns 200 with updated profile

#### Scenario: Username collision

- GIVEN an authenticated user
- WHEN they send `PATCH /api/auth/me` with `{"username": "taken"}`
- AND username "taken" already exists
- THEN returns 400 with validation error

### Requirement: Editable Fields

The system SHALL accept partial updates to `username`, `email`, `telefono`, and `password` fields. Unsupported fields MUST be rejected.

#### Scenario: Change password

- GIVEN an authenticated user
- WHEN they send `PATCH /api/auth/me` with `{"password": "newpass123"}`
- THEN password is updated and returns 200

#### Scenario: Invalid field rejected

- GIVEN an authenticated user
- WHEN they send `PATCH /api/auth/me` with `{"invalid_field": "value"}`
- THEN returns 400 with validation error

### Requirement: Telefono Synchronization

The system MUST synchronize `Usuario.telefono` changes to related `Cliente.telefono` or `Especialista.telefono` records within the same transaction.

#### Scenario: Update telefono for Cliente

- GIVEN an authenticated Cliente user
- WHEN they send `PATCH /api/auth/me` with `{"telefono": "1234567890"}`
- THEN both `Usuario.telefono` and `Cliente.telefono` are updated

#### Scenario: Update telefono for Especialista

- GIVEN an authenticated Especialista user
- WHEN they send `PATCH /api/auth/me` with `{"telefono": "1234567890"}`
- THEN both `Usuario.telefono` and `Especialista.telefono` are updated

### Requirement: Role Equality

The system MUST grant `ADMIN_SUCURSAL` the same profile editing capabilities as `Cliente` and `Especialista` roles.

#### Scenario: Admin Sucursal edits profile

- GIVEN an authenticated ADMIN_SUCURSAL user
- WHEN they send `PATCH /api/auth/me` with `{"email": "admin@clinic.com"}`
- THEN email is updated and returns 200