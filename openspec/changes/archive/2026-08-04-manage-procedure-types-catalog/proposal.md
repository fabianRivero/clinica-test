# Proposal: Manage Procedure Types Catalog

## Intent

Add a dedicated admin catalog page at `/cms/catalogos/tipos-procedimiento` so staff can CRUD `ProcEsteticosTipo` entries. Currently these procedure types only appear as a read-only dropdown inside the `procedimientos-esteticos` form — there is no way to create, edit, or deactivate them independently.

## Scope

### In Scope
- BE: `_catalog_page_data` + `_catalog_parse_payload` blocks (clone of `tipos-servicio` pattern)
- FE: `AdminCatalogKey` type, `catalogFallbackInfo` entry, `AdminProcedureTypesCatalogPage` wrapper, route, tab
- Tests: Django unit tests, Playwright E2E flow

### Out of Scope
Pagination, bulk ops, drag-drop, model changes, changes to `procedimientos-esteticos` catalog.

## Capabilities

### New Capabilities
None

### Modified Capabilities
- `admin-catalog-management` (delta spec): Extend existing capability to add `tipos-procedimiento` as the sixth in-scope catalog. Title field is `tipo`; all existing list/search/filter/create/edit/toggle requirements from `openspec/specs/admin-catalog-management/spec.md` apply unchanged.

## Approach

Exact structural clone of `tipos-servicio`. Two BE blocks with model + literals swapped. Five FE file edits, zero new components. Reuse `CatalogPage`, `CatalogEditorForm`, `useDebounce`, `getAdminCatalogDetail`, `useApiResource`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/config/api_views.py:~1227` | Modified | `_catalog_page_data` block |
| `backend/config/api_views.py:~1625` | Modified | `_catalog_parse_payload` block |
| `frontend/aesthetic-clinic/src/types/admin.ts:446` | Modified | `AdminCatalogKey` union |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx:24-73` | Modified | `catalogFallbackInfo` |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx:552-582` | Modified | Page wrapper |
| `frontend/aesthetic-clinic/src/App.tsx:149-156` | Modified | Route |
| `frontend/aesthetic-clinic/src/components/admin/AdminCatalogTabs.tsx:3-12` | Modified | Tab |
| `backend/catalogs/tests.py` | Modified | Unit tests |
| `frontend/aesthetic-clinic/tests/e2e/admin_general.spec.ts` | Modified | E2E flow |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `on_delete=PROTECT` blocks deletion when procedures reference the type | Low | Toggle (not delete) is the safe operation |
| Header counts show filtered instead of unfiltered total | Low | Use `unfiltered = ProcEsteticosTipo.objects.all()` per PR1 fix |
| `orden` not editable — stays at default 0 | Low | Mirrors `tipos-servicio`; out of scope for this change |

## Rollback Plan

1. Revert both BE blocks in `api_views.py`
2. Revert the five FE file changes
3. Run `python manage.py test` — confirm clean
4. Verify `/cms/catalogos/tipos-procedimiento` returns 404

## Dependencies

`tipos-servicio` catalog pattern must remain intact.

## Success Criteria

- [ ] `GET /api/admin/catalogos/tipos-procedimiento/` returns 200
- [ ] `?q=<text>` filters `tipo` case-insensitively
- [ ] `?active=<true|false|all>` works (default `all`)
- [ ] Combined `?q=` + `?active=` works
- [ ] Create, edit, toggle operations all persist correctly
- [ ] Django unit tests pass; Playwright E2E passes
- [ ] No regression on existing five catalogs
