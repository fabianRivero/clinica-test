# Admin Catalog Management Specification

## Purpose

The admin catalog management capability enables admin users to list, search, filter by active state, create, update, and toggle entries across five admin catalogs at `/cms/catalogos/`. The five in-scope catalogs share the same API contract and UI pattern; only the title field name differs per catalog.

## Title Field Per Catalog

| Catalog | Title Field |
|---------|-------------|
| `todos-los-servicios` | `tipo_servicio__tipo` OR `proc_estetico__proceso` (composite, OR) |
| `procedimientos-esteticos` | `proceso` |
| `tipos-servicio` | `tipo` |
| `especialidades` | `nombre` |
| `categorias-gasto` | `nombre` |

## Requirements

### Requirement: Catalog List Returns Filtered Items

The system MUST return catalog items from `GET /api/admin/catalogos/<slug:catalog_key>/` ordered by the catalog's natural order field, including both active and inactive items by default.

#### Scenario: Default load shows all items

- GIVEN an authenticated admin user
- WHEN they navigate to a catalog page at `/cms/catalogos/{catalog_key}/`
- THEN the list loads all items (active and inactive) with no filter applied
- AND items are ordered by the catalog's natural ordering

### Requirement: Title Search Filters by icontains

The system MUST filter catalog items by title when `?q=<text>` is provided, using case-insensitive `icontains` matching on the catalog's title field. For `todos-los-servicios`, the search MUST use an OR query across both `tipo_servicio__tipo` and `proc_estetico__proceso`.

#### Scenario: Search by exact title term

- GIVEN an authenticated admin user on a catalog list page
- WHEN they type "lip" in the search input
- THEN only items whose title contains "lip" (case-insensitive) are returned

#### Scenario: Search combined with active filter

- GIVEN an authenticated admin user on a catalog list page with active filter set to "Activos"
- WHEN they type "botox" in the search input
- THEN only active items whose title contains "botox" are returned

### Requirement: Active State Filter

The system MUST accept `?active=<true|false|all>` on `GET /api/admin/catalogos/<slug:catalog_key>/`. When `active=all` (default), all items are returned. When `active=true`, only items with `activo=true` are returned. When `active=false`, only items with `activo=false` are returned.

#### Scenario: Filter to active items only

- GIVEN an authenticated admin user on a catalog list page
- WHEN they select "Activos" from the active filter
- THEN only items with `activo=true` are displayed

#### Scenario: Filter to inactive items only

- GIVEN an authenticated admin user on a catalog list page
- WHEN they select "Inactivos" from the active filter
- THEN only items with `activo=false` are displayed

#### Scenario: Reset to show all

- GIVEN an authenticated admin user on a catalog list page with a filter active
- WHEN they select "Todos" from the active filter
- THEN all items (active and inactive) are displayed

### Requirement: Search Input Debounce

The system MUST debounce search input by 300ms before issuing the API request, so that rapid typing does not trigger excessive requests.

#### Scenario: Debounce prevents early request

- GIVEN an authenticated admin user on a catalog list page
- WHEN they type a 5-character search string rapidly
- THEN only one API request is made after the 300ms debounce period
- AND the request contains the full typed query

### Requirement: Create Button Visibility

The system MUST display the Create button in the page header and in the empty state for all five catalog pages.

#### Scenario: Create button visible in header

- GIVEN an authenticated admin user on a catalog list page with items present
- WHEN the page loads
- THEN the Create button is visible in the header

#### Scenario: Create button visible in empty state

- GIVEN an authenticated admin user on an empty catalog list page
- WHEN the page loads
- THEN the Create button is visible in the empty state

### Requirement: Empty State Copy

The system MUST display "Sin registros" when a catalog list has no items to display, regardless of whether a filter is active.

#### Scenario: Empty unfiltered state

- GIVEN an authenticated admin user on a catalog list page with no items
- WHEN the page loads with no search or filter
- THEN the empty state shows "Sin registros"

#### Scenario: Empty filtered state

- GIVEN an authenticated admin user on a catalog list page
- WHEN they apply a search or filter that returns no items
- THEN the empty state shows "Sin registros"

### Requirement: Create, Update, Toggle Endpoints Unchanged

The system MUST leave the existing create (`admin_catalogo_crear`), update (`admin_catalogo_actualizar`), and toggle (`admin_catalogo_estado`) endpoints unchanged by this change.

#### Scenario: Create endpoint still works

- GIVEN an authenticated admin user on a catalog list page
- WHEN they submit the create form with valid data
- THEN the item is created and the list refreshes to show it

#### Scenario: Toggle endpoint still works

- GIVEN an authenticated admin user viewing an active catalog item
- WHEN they toggle it to inactive
- THEN the item's `activo` state is updated and the list refreshes