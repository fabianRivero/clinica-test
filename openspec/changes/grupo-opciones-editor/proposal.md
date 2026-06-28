# Proposal: grupo-opciones-editor

## Intent

Enable admin users to manage `GrupoOpciones` options (child `OpcionCatalogo` entries) from the UI without touching code or Django admin. The admin catalog `grupos-opciones` already exists with basic CRUD; this change adds nested option management via a modal, solving the gap where an admin can create a MULTISELECCION field but cannot populate its options.

## Scope

### In Scope
- Backend nested REST sub-endpoints for `OpcionCatalogo` under `GrupoOpciones`
- Frontend modal in the `grupos-opciones` catalog page for option CRUD
- Bulk creation endpoint for multiple options in one request
- Toggle (soft-delete) for individual options
- Existing catalog machinery (`grupos-opciones` endpoints, UI shell) left unchanged

### Out of Scope
- Changes to `FichaCampo`, `FichaRespuestaOpcion`, or downstream serialization
- `GrupoOpciones` soft-delete bulk toggle
- Patient-facing form behavior or validation on deactivated options

## Capabilities

### New Capabilities
- `grupo-opciones-editor-modal`: Modal UI on the `grupos-opciones` catalog page listing options for a group, with filters, create form, edit per-row, and bulk selection for future bulk actions. Consumes the new `opcion-catalogo-api` endpoints.
- `opcion-catalogo-api`: Nested REST endpoints under `/api/admin/catalogos/grupos-opciones/<grupo_id>/opciones/` exposing list, create (single and bulk), update, and toggle for `OpcionCatalogo`.

### Modified Capabilities
- None — `admin-catalog-management` and `medical-form-field-editor-enhancements` are unaffected; the field editor already consumes `GrupoOpciones` via FK.

## Approach

**Backend**: Add handlers in `backend/config/api_views.py` for sub-endpoints. Nested routes registered in the API URL config. Validate `grupo_id` exists. Bulk create wrapped in `transaction.atomic()` for all-or-nothing semantics. `OpcionCatalogo.grupo` uses CASCADE — `FichaRespuestaOpcion.opcion` uses PROTECT (blocks option deletion if referenced), so soft-delete toggle is the only state-changing operation.

**Frontend**: Add "Manage options" button per row in `AdminOptionGroupsCatalogPage`. Opens a modal showing option list (filtered by `?active=true` by default), with search `?q=`, "Add option" inline form, "Edit" per row, and checkbox selection for future bulk toggle. Refetches list after every mutation.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/config/api_views.py` | Modified | Add handlers for nested `grupos-opciones/<id>/opciones/` endpoints |
| `backend/config/api_urls.py` (or equiv.) | Modified | Register new nested routes |
| `backend/catalogs/tests.py` | Modified | Add tests for new sub-endpoints |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx` | Modified | Add option modal and handlers to `grupos-opciones` catalog |
| `frontend/e2e/admin_general.spec.ts` | Modified | E2E for option modal flow |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Bulk create partial failure | Low | Use `transaction.atomic()` — whole batch rolls back on any failure |
| FK PROTECT blocking toggle | Low | Toggle sets `activo=False`; PROTECT only blocks actual DELETE |
| Line count ~450 exceeds budget | Medium | Accept `size:exception` or split frontend modal into a separate PR slice |

## Rollback Plan

1. Revert API URL registrations — remove nested routes from URL config
2. Remove option handlers from `api_views.py`
3. Revert modal changes in frontend — restore previous `AdminCatalogsPage.tsx` state
4. Revert test additions — remove new test cases from `catalogs/tests.py` and `admin_general.spec.ts`
5. No database migration needed — all models already exist; no schema changes

## Dependencies

- `grupos-opciones` catalog machinery already in place (endpoints + UI shell)
- `OpcionCatalogo` model already exists with CASCADE FK from `grupo`
- `_admin_principal_required` and `@admin_required` decorators already used in API views

## Success Criteria

- [ ] Admin can open a modal from the `grupos-opciones` list and see existing options for a group
- [ ] Admin can create a single `OpcionCatalogo` via the modal
- [ ] Admin can create multiple `OpcionCatalogo` entries in one request via bulk endpoint
- [ ] Admin can edit an existing option's name, valor, orden via the modal
- [ ] Admin can toggle an option's `activo` state (soft-delete) from the modal
- [ ] All new endpoints return correct HTTP status codes and validation errors
- [ ] New backend tests pass: list, create, create-bulk, update, toggle, uniqueness constraint
- [ ] New E2E test passes: full option management flow in modal
- [ ] Existing `grupos-opciones` catalog CRUD still works without regression
