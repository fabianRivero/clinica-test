# Proposal: catalog-list-search-filter

## Intent

Enable admin users to discover and filter catalog entries by title and active state across all five admin catalog pages at `/cms/catalogos/`. Fix a latent bug where the Create button is hidden on four of five catalog pages.

## Scope

### In Scope
- **Search**: case-insensitive title search (`?q=`) via `icontains` per catalog's title field on `GET /api/admin/catalogos/<slug:catalog_key>/`
- **Filter**: active state filter (`?active=true|false|all`, default `all`) applied server-side on the queryset
- **Create button**: remove `showCreateAction={false}` from all 5 page wrappers so Create is visible in header and empty state
- **Empty state copy**: "Sin registros" for both unfiltered-empty and filtered-empty cases

### Out of Scope
- Pagination (catalogs expected < 500 rows)
- `campos-ficha`, `patologias-cutaneas`, `grupos-opciones` catalogs
- `GastoSucursal` undefined import in `backend/config/api/viewsets/catalogs.py:475` (ViewSet not wired to production URLs)

## Capabilities

### New Capabilities
- `admin-catalog-management`: CRUD, title search, and active-state filtering across the five admin catalogs (`todos-los-servicios`, `procedimientos-esteticos`, `tipos-servicio`, `especialidades`, `categorias-gasto`)

### Modified Capabilities
- None

## Approach

**Backend** — modify `admin_catalogo_detalle` (`api_views.py:3987`) to read `request.GET.get('q')` and `request.GET.get('active')` and pass them into `_catalog_page_data` (`:1056`). Each catalog branch applies `.filter()` before `order_by()`: `.filter(titulo__icontains=q)` + `.filter(activo=<bool>)` where applicable. Title field per catalog: `str(item)` (servicios), `item.proceso` (proc. estéticos), `item.tipo` (tipos-servicio), `item.nombre` (especialidades, categorias-gasto).

**Frontend** — `getAdminCatalogDetail` (`admin.ts:340`) forwards `?q=` and `?active=` to the API. `CatalogPage` (`AdminCatalogsPage.tsx:368`) adds `searchQuery` and `activeFilter` state. The search input is debounced 300ms; the active filter is a `<select>` (Todos/Activos/Inactivos) that refetches on change. Both combine in the request.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/config/api_views.py:1056` | Modified | `_catalog_page_data`: add `.filter(titulo__icontains=q)` and `.filter(activo=<bool>)` per catalog branch |
| `backend/config/api_views.py:3987` | Modified | `admin_catalogo_detalle`: read and forward `?q=` and `?active=` query params |
| `frontend/aesthetic-clinic/src/services/api/admin.ts:340` | Modified | `getAdminCatalogDetail`: accept and forward query params |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx:368–536` | Modified | `CatalogPage`: add search input, active filter `<select>`, debounce |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx:539,543,547,559,563` | Modified | Remove `showCreateAction={false}` from 5 page wrappers |
| `backend/catalogs/tests.py:1` | New | Add 1 happy-path + 1 filter test for catalog endpoint |
| `frontend/aesthetic-clinic/tests/e2e/admin_general.spec.ts:1` | Modified | Add catalog E2E: create → search → deactivate → filter to inactive |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| No backend test coverage for catalog FBVs | Med | Add 1 happy-path + 1 filter test before apply phase |
| `GastoSucursal` undefined import if ViewSet is ever wired | Low | Document as tech debt; not in production URL path |
| Large catalog list (hundreds of rows) with no pagination | Low | Scope excludes pagination; revisit if > 500 items |

## Rollback Plan

- **Backend**: revert `api_views.py` — remove `request.GET` reads and `.filter()` calls; `_catalog_page_data` returns full unfiltered queryset. No database migration needed.
- **Frontend**: remove search input and active filter `<select>` from `CatalogPage`; restore `showCreateAction={false}` on the 5 wrappers.
- **Verification**: existing catalog list views resume pre-change behavior.

## Dependencies

- None (self-contained backend + frontend co-change)

## Success Criteria

- [ ] Create button visible on all 5 catalog pages (header + empty state)
- [ ] Search: typing filters list to items whose title contains query (case-insensitive)
- [ ] Active filter: `Todos` shows all, `Activos` shows `activo=true`, `Inactivos` shows `activo=false`
- [ ] Search and active filter combine correctly in a single request
- [ ] `python manage.py test backend/catalogs/tests.py` passes (happy-path + filter)
- [ ] Playwright E2E passes: create item → search by title → deactivate → filter to Inactivos shows the item
