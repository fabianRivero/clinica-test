# Delta for admin-catalog-management

## Delta: medical-form-sector-management
## Modified Capability: admin-catalog-management

## ADDED Requirements

### Requirement: Sixth Catalog: Sectores

The system SHALL extend `admin-catalog-management` to include `sectores` as a sixth catalog accessible at `/api/admin/catalogos/sectores/`, following the identical API contract as the five existing catalogs (sucusales, ciudades, especialidades, tipos-servicio, categorias-gasto).

The `sectores` catalog title field SHALL be `nombre`. All other fields (`codigo`, `descripcion`, `activo`, `orden`) and behaviors (filtering, search, toggle, CRUD) MUST match the established catalog contract.

#### Scenario: Sectores catalog list follows same contract

- GIVEN an authenticated admin user
- WHEN they call `GET /api/admin/catalogos/sectores/`
- THEN the response structure matches the other catalogs (ordered by `orden`, includes both active and inactive)
- AND `GET /api/admin/catalogos/sectores/?active=true` returns only active sectors
- AND `GET /api/admin/catalogos/sectores/?q=dep` returns sectors where `nombre` icontains "dep"

#### Scenario: Sectores catalog create follows same contract

- GIVEN an authenticated admin user
- WHEN they call `POST /api/admin/catalogos/sectores/` with `nombre`, `codigo`, `descripcion`, `activo`, `orden`
- THEN the sector is created and persisted following the same validation rules as other catalogs

#### Scenario: Sector dropdown appears in service form

- GIVEN an authenticated admin user on the service create/edit form at `/cms/catalogos/todos-los-servicios/`
- WHEN the page loads
- THEN a sector dropdown is displayed populated with active sectors from `/api/admin/catalogos/sectores/?active=true`
- AND the dropdown allows the admin to select a sector or leave it empty (null)
