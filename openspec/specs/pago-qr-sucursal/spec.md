# Pago QR por Sucursal — Specification

## Purpose

Each branch (sucursal) has its own QR payment configuration. The client API returns the QR associated with the authenticated user's branch. Admins manage QR configurations per branch.

## Requirements

### Requirement: QR Configurable por Sucursal

The system MUST support assigning a unique QR payment configuration to each branch (Sucursal). The `ConfiguracionPagoQR` model MUST have a foreign key to `Sucursal` with `unique=True`.

#### Scenario: QR de Sucursal A es independiente de Sucursal B

- GIVEN two branches exist: Sucursal A and Sucursal B, each with its own QR configuration
- WHEN an admin updates the QR configuration for Sucursal A
- THEN the QR configuration for Sucursal B remains unchanged

### Requirement: Cliente Obtiene QR de su Sucursal

The system MUST return the QR payment configuration for the authenticated user's assigned branch. The endpoint `GET /cliente/pagos/` MUST filter by `request.user.sucursal`.

#### Scenario: Cliente con sucursal asignada obtiene su QR

- GIVEN a client user is authenticated with `sucursal = Sucursal A`
- AND Sucursal A has an active QR configuration
- WHEN the client calls `GET /cliente/pagos/`
- THEN the response includes the QR configuration for Sucursal A

#### Scenario: Cliente sin sucursal asignada recibe 404

- GIVEN a client user is authenticated with `sucursal = null`
- WHEN the client calls `GET /cliente/pagos/`
- THEN the response is HTTP 404 with an error message indicating no branch assigned

### Requirement: Admin Gestiona QR por Sucursal

The Django Admin MUST expose the `sucursal` field for `ConfiguracionPagoQR`. Admin users MUST only see and edit QR configurations for their own branch (horizontal filtering).

#### Scenario: Admin edita QR de Sucursal A sin afectar Sucursal B

- GIVEN an admin user is logged in for Sucursal A
- WHEN the admin modifies the QR configuration for Sucursal A
- THEN no changes are made to any other branch's QR configuration

#### Scenario: Admin ve solo QR de su sucursal

- GIVEN an admin user is authenticated for Sucursal A
- WHEN the admin navigates to the QR configuration list
- THEN only QR configurations for Sucursal A are visible

### Requirement: Migración de QR Existente

A data migration MUST assign the existing global QR configuration to the principal branch (`es_principal=True`) or set it to null if no principal branch exists.

#### Scenario: QR existente migra a sucursal principal

- GIVEN a global QR configuration exists before the FK is added
- WHEN the data migration runs
- THEN the QR is assigned to the branch where `es_principal=True`
- AND if no principal branch exists, the QR is set to null

## Data Model

| Field | Type | Constraints |
|-------|------|-------------|
| sucursal | FK(Sucursal) | `null=True, unique=True` |
| qr_image | ImageField | Required |
| qr_alias | CharField | Optional, max 100 chars |
| is_active | BooleanField | Default True |
| updated_at | DateTimeField | Auto-updated |

## API Contract

### GET /cliente/pagos/

**Response 200** (client has branch):
```json
{
  "qr_image": "https://...",
  "qr_alias": "Pagos Sucursal A",
  "sucursal": 1
}
```

**Response 404** (client has no branch):
```json
{
  "error": "No branch assigned to user"
}
```

## Success Criteria

- [ ] `ConfiguracionPagoQR` has FK `sucursal` with `unique=True`
- [ ] `GET /cliente/pagos/` filters by authenticated user's branch
- [ ] Admin exposes `sucursal` field with horizontal filtering
- [ ] Data migration preserves existing QR data
- [ ] Client of Branch A cannot see QR of Branch B