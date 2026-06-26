# Exploration: catalog-list-search-filter

## Current State

### Backend — `api_views.py` (actual production code)

The catalog detail endpoint is at:
- **View function**: `admin_catalogo_detalle` at `backend/config/api_views.py:3987`
- **Helper**: `_catalog_page_data` at `backend/config/api_views.py:1056`
- **URL**: `GET /api/admin/catalogos/<slug:catalog_key>/` (`api_urls.py:331`)
- **Query params**: **NONE currently** — returns full unfiltered list

Each catalog branch in `_catalog_page_data` uses an `order_by()` queryset with no `filter()` for search or active state:
- `todos-los-servicios`: `ServicioConfig.objects.select_related(...).order_by(...)`
- `procedimientos-esteticos`: `ProcEstetico.objects.select_related(...).order_by(...)`
- `tipos-servicio`: `TipoServicio.objects.order_by(...)`
- `especialidades`: `Especialidad.objects.order_by(...)`
- `categorias-gasto`: `CategoriaGasto.objects.order_by(...)`

The search target (title field) per catalog:
| Catalog key | Title field | Model |
|---|---|---|
| `todos-los-servicios` | `str(item)` = derived from FKs | `ServicioConfig` |
| `procedimientos-esteticos` | `item.proceso` | `ProcEstetico` |
| `tipos-servicio` | `item.tipo` | `TipoServicio` |
| `especialidades` | `item.nombre` | `Especialidad` |
| `categorias-gasto` | `item.nombre` | `CategoriaGasto` |

Create/Update/Toggle endpoints already exist and work:
- `admin_catalogo_crear` at line 3997
- `admin_catalogo_actualizar` at line 4025
- `admin_catalogo_estado` at line 4056

Note: `backend/config/api/viewsets/catalogs.py` is a DRF ViewSet that mirrors the FBVs — **it is not wired into production URLs** (`api_urls.py` uses FBVs only). It references an undefined `GastoSucursal` at line 475 (import missing), but this doesn't affect production since the ViewSet isn't routed.

### Frontend — `AdminCatalogsPage.tsx` (line 368–536)

The `CatalogPage` component:
- Calls `getAdminCatalogDetail(catalogKey)` on mount (no query params)
- Renders items via `data.items.map(...)` — no search input, no active/inactive filter
- The `CatalogEditorForm` (line 237–366) already handles both create and edit (keyed by `editingItem ? \`edit-${id}\` : \`create-${version}\``)
- The 5 in-scope page wrappers all set `showCreateAction={false}`:
  - Line 539: `AdminProceduresCatalogPage` (`procedimientos-esteticos`)
  - Line 543: `AdminAllServicesCatalogPage` (`todos-los-servicios`)
  - Line 547: `AdminServiceTypesCatalogPage` (`tipos-servicio`)
  - Line 559: `AdminSpecialtiesCatalogPage` (`especialidades`)
  - Line 563: `AdminExpenseCategoriesCatalogPage` (`categorias-gasto`)

### Affected Areas

| File | Lines | Why affected |
|---|---|---|
| `backend/config/api_views.py` | 3987–3992 (`admin_catalogo_detalle`), 1056–~1400 (`_catalog_page_data`) | Need to read `?q=` and `?active=` query params and apply them as filters |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx` | 368–536 (`CatalogPage`), 538–568 (wrappers) | Need search input, active/inactive filter, and `showCreateAction=true` |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | 340–342 (`getAdminCatalogDetail`) | Need to accept and forward query params |
| `frontend/aesthetic-clinic/src/types/admin.ts` | 492–502 (`AdminCatalogDetailResponse`) | Types already support the response shape; no change needed |
| `backend/catalogs/tests.py` | 1–3 | Empty — needs catalog endpoint tests |
| `frontend/aesthetic-clinic/tests/e2e/admin_general.spec.ts` | 1–122 | No catalog tests; E2E coverage needed |

## Approaches

### 1. Server-side filter via query params (Recommended)

**Backend**: Modify `admin_catalogo_detalle` to read `request.GET.get('q')` and `request.GET.get('active')` and pass them into `_catalog_page_data`. Each catalog branch in `_catalog_page_data` applies `.filter()` before `order_by()`.

**Frontend**: Add `useState` for `searchQuery` and `activeFilter` to `CatalogPage`. Compute derived filtered list client-side (no extra API call), OR pass them as query params and refetch. Decision: **derive client-side** since the list is paginated only in the backend's order (not offset/limit) — the catalog detail returns ALL items with no pagination.

- Pros: Simple, no backend pagination needed, consistent with the existing pattern (list is already fully loaded)
- Cons: All items always fetched regardless of filter — acceptable for catalogs with hundreds of rows, not thousands
- Effort: **Low**

### 2. Client-side only filter (Rejected)

Filter the already-loaded `data.items` array without any backend changes. Search and filter UI added to frontend, but no backend changes.

- Pros: Zero backend changes
- Cons: Search/filter state doesn't survive page reload; UX feels disconnected from the data
- Effort: Very low

### 3. Debounced server-side search with pagination (Overkill)

- Pros: Scales for large catalogs
- Cons: Requires pagination UI, backend changes, and is premature for the current data volume
- Effort: **High**

## Recommendation

**Approach 1 (server-side via query params) — backend returns the FILTERED list.** Add `?q=<text>&active=<true|false|all>` to the `getAdminCatalogDetail` call. The backend applies `.filter()` on the queryset before serializing items. The frontend passes the current search/filter state to the API and renders whatever the API returns. The frontend does NOT re-filter from a fully-loaded array. Enable `showCreateAction` on all 5 wrappers.

For search, the `title` field of each `AdminCatalogEntry` (line 482–490 in `admin.ts`) is the searchable string — it maps to the primary human-readable name in each catalog (e.g., `item.proceso`, `item.tipo`, `item.nombre`).

For the active filter, apply `.filter(activo=<bool>)` on the backend before building the items list. The `active` field on `AdminCatalogEntry` is already present.

## Risks

1. **GastoSucursal undefined in DRF ViewSet** — `catalogs.py:475` references `GastoSucursal` without importing it. If the ViewSet is ever wired up, it will crash on `categorias-gasto`. Not in production path but should be fixed as part of this change.
2. **Missing backend tests** — `catalogs/tests.py` is empty. Adding search/filter without tests means regression risk. The existing FBVs have no test coverage.
3. **Large catalog lists** — no pagination currently; if any catalog grows to thousands of items, the filter UX degrades. Scope creep risk to add pagination if not bounded now.

## Clarifications (sensible defaults made — do not block proposal)

| Question | Default assumption |
|---|---|
| Should the search be case-insensitive? | Yes, use `icontains` |
| Should `active` filter default to `all` (show both active and inactive)? | Yes, default `?active=all` |
| Should the search be debounced? | No — derive from loaded items client-side, no debounce needed |
| Should we add pagination? | Not in scope for this change; catalog items are typically < 500 |
| Should inactive items be shown at the bottom or filtered out by default? | Show all with active filter toggle, matching current behavior |
