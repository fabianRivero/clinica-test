# Delta for admin-catalog-management (manage-procedure-types-catalog)

## MODIFIED Requirements

### Title Field Per Catalog

The system uses a different title field per catalog. The following table extends the canonical spec's 5-entry table to 6 entries:

| Catalog | Title Field |
|---------|-------------|
| `todos-los-servicios` | `tipo_servicio__tipo` OR `proc_estetico__proceso` (composite, OR) |
| `procedimientos-esteticos` | `proceso` |
| `tipos-servicio` | `tipo` |
| `especialidades` | `nombre` |
| `categorias-gasto` | `nombre` |
| `tipos-procedimiento` | `tipo` |

(Previously: 5-entry table without `tipos-procedimiento`)

## ADDED Requirements

### Requirement: `tipos-procedimiento` — List with No Filter

The system MUST return all `tipos-procedimiento` catalog items (active and inactive) ordered by `orden, tipo` when no search or active filter is applied.

#### Scenario: Default load shows all procedure types

- GIVEN an authenticated admin user
- WHEN they navigate to `/cms/catalogos/tipos-procedimiento/`
- THEN the list loads all `ProcEsteticosTipo` entries with no filter applied
- AND items are ordered by `orden` ascending, then `tipo` ascending

### Requirement: `tipos-procedimiento` — Search by `tipo`

The system MUST filter `tipos-procedimiento` items by `tipo` when `?q=<text>` is provided, using case-insensitive `icontains` matching.

#### Scenario: Search by partial `tipo` text

- GIVEN an authenticated admin user on the `tipos-procedimiento` catalog page
- WHEN they type "lip" in the search input and the 300ms debounce elapses
- THEN the API is called with `?q=lip`
- AND only items whose `tipo` contains "lip" (case-insensitive) are returned

#### Scenario: Search combined with active filter

- GIVEN an authenticated admin user on the `tipos-procedimiento` catalog page with active filter set to "Activos"
- WHEN they type "botox" in the search input and the 300ms debounce elapses
- THEN the API is called with `?q=botox&active=true`
- AND only active items whose `tipo` contains "botox" are returned

### Requirement: `tipos-procedimiento` — Active State Filter

The system MUST accept `?active=<true|false|all>` on `GET /api/admin/catalogos/tipos-procedimiento/`. Default MUST be `all`.

#### Scenario: Filter to active items only

- GIVEN an authenticated admin user on the `tipos-procedimiento` catalog page
- WHEN they select "Activos" from the active filter
- THEN the API is called with `?active=true`
- AND only items with `activo=true` are returned

#### Scenario: Filter to inactive items only

- GIVEN an authenticated admin user on the `tipos-procedimiento` catalog page
- WHEN they select "Inactivos" from the active filter
- THEN the API is called with `?active=false`
- AND only items with `activo=false` are returned

#### Scenario: Combined search and filter

- GIVEN an authenticated admin user on the `tipos-procedimiento` catalog page with active filter set to "Activos"
- WHEN they type "botox" in the search input and the 300ms debounce elapses
- THEN the API is called with `?q=botox&active=true`
- AND only active items whose `tipo` contains "botox" are returned

### Requirement: `tipos-procedimiento` — Create New Procedure Type

The system MUST allow creating a new `ProcEsteticosTipo` entry via the Create button, sending `name` (mapped to `tipo`) and `description` (mapped to `descripcion`) to `admin_catalogo_crear`.

#### Scenario: Create button visible in header

- GIVEN an authenticated admin user on the `tipos-procedimiento` catalog page with items present
- WHEN the page loads
- THEN the Create button is visible in the header

#### Scenario: Create button visible in empty state

- GIVEN an authenticated admin user on the `tipos-procedimiento` catalog page with no items
- WHEN the page loads
- THEN the Create button is visible in the empty state

#### Scenario: Submit create form with valid data

- GIVEN an authenticated admin user on the `tipos-procedimiento` catalog page
- WHEN they fill in `tipo` (required) and optionally `descripcion`, then submit
- THEN the `ProcEsteticosTipo` entry is created with `tipo` and `descripcion` set
- AND the list refreshes to show the new entry
- AND `orden` defaults to 0

### Requirement: `tipos-procedimiento` — Edit Existing Procedure Type

The system MUST allow editing the `tipo` and `descripcion` fields of an existing `ProcEsteticosTipo` entry via the inline edit action, sending updates to `admin_catalogo_actualizar`.

#### Scenario: Edit `tipo` field

- GIVEN an authenticated admin user viewing an existing `tipos-procedimiento` item
- WHEN they update the `tipo` field and save
- THEN the `tipo` field is persisted to `ProcEsteticosTipo`
- AND the list refreshes to show the updated value

#### Scenario: Edit `descripcion` field

- GIVEN an authenticated admin user viewing an existing `tipos-procedimiento` item
- WHEN they update the `descripcion` field and save
- THEN the `descripcion` field is persisted to `ProcEsteticosTipo`

### Requirement: `tipos-procedimiento` — Toggle Active State

The system MUST allow toggling the `activo` state of a `tipos-procedimiento` entry via the toggle action, sending the update to `admin_catalogo_estado`.

#### Scenario: Toggle active to inactive

- GIVEN an authenticated admin user viewing an active `tipos-procedimiento` item
- WHEN they toggle it to inactive
- THEN `activo=false` is persisted to `ProcEsteticosTipo`
- AND the list refreshes to reflect the new state

#### Scenario: Toggle inactive to active

- GIVEN an authenticated admin user viewing an inactive `tipos-procedimiento` item
- WHEN they toggle it to active
- THEN `activo=true` is persisted to `ProcEsteticosTipo`
- AND the list refreshes to reflect the new state

### Requirement: `tipos-procedimiento` — Empty State

The system MUST display "Sin registros" when the `tipos-procedimiento` list has no items to display.

#### Scenario: Empty unfiltered state

- GIVEN an authenticated admin user on the `tipos-procedimiento` catalog page with no items
- WHEN the page loads with no search or filter
- THEN the empty state shows "Sin registros"

#### Scenario: Empty filtered state

- GIVEN an authenticated admin user on the `tipos-procedimiento` catalog page
- WHEN they apply a search or filter that returns zero items
- THEN the empty state shows "Sin registros"
