# Delta for admin-catalog-management (catalog-list-search-filter)

## ADDED Requirements

### Requirement: Title Search via icontains

The system MUST filter catalog items by title when `?q=<text>` is provided on `GET /api/admin/catalogos/<slug:catalog_key>/`, using case-insensitive `icontains` matching on each catalog's designated title field.

#### Scenario: Search filters list by title

- GIVEN an authenticated admin user on a catalog list page
- WHEN they type "lip" in the search input and the 300ms debounce elapses
- THEN the API is called with `?q=lip`
- AND only items whose title contains "lip" (case-insensitive) are returned

#### Scenario: Search uses OR logic for todos-los-servicios

- GIVEN an authenticated admin user on the `todos-los-servicios` catalog page
- WHEN they search for "botox"
- THEN the API uses `Q(tipo_servicio__tipo__icontains=q) | Q(proc_estetico__proceso__icontains=q)`
- AND items matching either field are returned

### Requirement: Active State Filter Query Param

The system MUST accept `?active=<true|false|all>` on `GET /api/admin/catalogos/<slug:catalog_key>/`. Default MUST be `all` (show all items including inactive).

#### Scenario: Filter to active items

- GIVEN an authenticated admin user on a catalog list page
- WHEN they select "Activos" from the active filter
- THEN the API is called with `?active=true`
- AND only items with `activo=true` are returned

#### Scenario: Filter to inactive items

- GIVEN an authenticated admin user on a catalog list page
- WHEN they select "Inactivos" from the active filter
- THEN the API is called with `?active=false`
- AND only items with `activo=false` are returned

#### Scenario: Combined search and filter

- GIVEN an authenticated admin user on a catalog list page with active filter set to "Activos"
- WHEN they type "botox" in the search input and the 300ms debounce elapses
- THEN the API is called with `?q=botox&active=true`
- AND only active items whose title contains "botox" are returned

### Requirement: Create Button Visible on All Five Catalog Pages

The system MUST display the Create button in the page header and in the empty state for all five catalog pages. Previously, `showCreateAction={false}` was set on four of five page wrappers, hiding the button.

#### Scenario: Create button visible in header

- GIVEN an authenticated admin user on any of the five catalog pages
- WHEN the page loads
- THEN the Create button is visible in the header

#### Scenario: Create button visible in empty state

- GIVEN an authenticated admin user on any of the five catalog pages with no items
- WHEN the page loads
- THEN the Create button is visible in the empty state

### Requirement: Empty State Copy is "Sin registros"

The system MUST display "Sin registros" for both the unfiltered-empty and the filtered-empty states.

#### Scenario: Unfiltered empty state

- GIVEN an authenticated admin user on a catalog list page with no items
- WHEN the page loads
- THEN the empty state shows "Sin registros"

#### Scenario: Filtered empty state

- GIVEN an authenticated admin user on a catalog list page
- WHEN they apply a search or filter that returns zero items
- THEN the empty state shows "Sin registros"

### Requirement: Search Debounce

The system MUST debounce search input by 300ms before issuing the API request, preventing a request on every keystroke.

#### Scenario: Debounce waits 300ms

- GIVEN an authenticated admin user on a catalog list page
- WHEN they type a query in the search input
- THEN no request is made until 300ms have elapsed without additional typing
- AND only one request is made with the final query