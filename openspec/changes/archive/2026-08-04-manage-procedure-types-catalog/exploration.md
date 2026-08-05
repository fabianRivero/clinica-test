# Exploration: `manage-procedure-types-catalog`

> **Status note**: This exploration was refreshed after the change was implemented. All findings reflect the **current state of the codebase** (post-merge on `main`). The earlier `explore.md` in this folder captured pre-implementation analysis; this file supersedes it and is the canonical exploration artifact for the change.

## Current State

`ProcEsteticosTipo` is a Django model (`backend/catalogs/models.py:62-70`) that inherits from `CatalogoEditableModel` (`backend/common/models.py:12-18`). It represents the "Tipo de procedimiento" dropdown option used by `procedimientos-esteticos` catalog items. The model has one own field — `tipo = CharField(max_length=120, unique=True)` — and inherits `descripcion`, `orden`, `activo`, plus `created_at` / `updated_at` from the abstract base.

The change has been implemented and merged to `main`. There are now **nine** admin catalogs reachable from `/cms/catalogos/`, including the new `tipos-procedimiento`.

### Verified post-implementation facts

| Fact | Source |
|------|--------|
| `_catalog_page_data` has a `tipos-procedimiento` block | `backend/config/api_views.py:1328+` |
| `_catalog_get_instance` model map includes `tipos-procedimiento` → `ProcEsteticosTipo` | `backend/config/api_views.py:2161` |
| `_catalog_key_to_slug` slug set includes `tipos-procedimiento` | `backend/config/api_views.py` slug set |
| `AdminCatalogKey` union includes `'tipos-procedimiento'` | `frontend/aesthetic-clinic/src/types/admin.ts:450` |
| `catalogFallbackInfo` entry present | `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx:56` |
| `AdminProcedureTypesCatalogPage` wrapper present | `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx:659` |
| Route registered | `frontend/aesthetic-clinic/src/App.tsx:155` |
| Tab entry registered | `frontend/aesthetic-clinic/src/components/admin/AdminCatalogTabs.tsx:9` and `frontend/aesthetic-clinic/src/layouts/AdminLayout.tsx:81` |
| Playwright E2E covers the flow | `frontend/aesthetic-clinic/tests/e2e/admin_general.spec.ts:309` |
| Auto-assignment of `orden` on create | commit `ad4151a` — `orden` no longer editable in form |

## Affected Areas (final, post-implementation)

### Backend

- `backend/config/api_views.py:1328-1380` — `_catalog_page_data` block for `tipos-procedimiento` (uses `ProcEsteticosTipo.objects.all()` as `unfiltered`, search on `tipo__icontains=q`, active filter on `activo`, order `orden, tipo`, metadata `procedimientos.count()`).
- `backend/config/api_views.py:~1990` — `_catalog_parse_payload` block for `tipos-procedimiento` (maps `name` → `tipo`, `description` → `descripcion`).
- `backend/config/api_views.py:2161` — `_catalog_get_instance` model map entry.
- `backend/catalogs/tests.py` — fixtures and 5 test cases for `tipos-procedimiento` (search, active true/false/all, combined, invalid param).

### Frontend

- `frontend/aesthetic-clinic/src/types/admin.ts:450` — `AdminCatalogKey` union entry.
- `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx:56` — `catalogFallbackInfo` entry.
- `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx:659` — `AdminProcedureTypesCatalogPage` wrapper returning `<CatalogPage catalogKey="tipos-procedimiento" />`.
- `frontend/aesthetic-clinic/src/App.tsx:155` — route `catalogos/tipos-procedimiento`.
- `frontend/aesthetic-clinic/src/components/admin/AdminCatalogTabs.tsx:9` — tab entry.
- `frontend/aesthetic-clinic/src/layouts/AdminLayout.tsx:81` — admin layout tab entry.
- `frontend/aesthetic-clinic/tests/e2e/admin_general.spec.ts:309` — E2E flow.

### Specs

- `openspec/specs/admin-catalog-management/spec.md` — capability now lists `tipos-procedimiento` as one of the in-scope catalogs; title field is `tipo`.

## Approaches (analysis, kept for historical record)

### 1. Clone `tipos-servicio` pattern — CHOSEN
Exact structural clone: same field names (`name`/`description`), same query/filter pattern, same `_catalog_entry` shape, same parse block. Only the model and slug differ.

- **Pros**: Minimal diff, proven pattern, low risk, predictable behavior
- **Cons**: None significant
- **Effort**: Low

### 2. Build from scratch with separate analysis
Custom design of fields, metadata, and payload parsing for `ProcEsteticosTipo`.

- **Pros**: Potential for cleaner design
- **Cons**: Over-engineering for a near-identical schema; diverges from established pattern
- **Effort**: High

## Recommendation

**Approach 1 — Copy `tipos-servicio` pattern.** The `ProcEsteticosTipo` schema is nearly identical to `TipoServicio` (both have `tipo CharField + inherited descripcion/orden/activo`). This is exactly what was implemented. The pattern is mechanical, low-risk, and matches every other in-scope catalog.

## Risks (final)

1. **`on_delete=PROTECT` on `ProcEstetico.tipo_p_estetico`**: deleting a `ProcEsteticosTipo` with linked procedures raises DB error. Mitigated by soft-deactivate only; toggle is the safe operation.
2. **`orden` not user-editable**: form only exposes `name` and `description`. `orden` is auto-assigned on create (commit `ad4151a`) and never editable. Consistent with `tipos-servicio` post-PR1.
3. **Header counts must use unfiltered queryset**: `unfiltered = ProcEsteticosTipo.objects.all()` — same fix as `catalog-list-search-filter` PR1.

## Ready for Proposal

**Already past proposal.** Proposal, design, tasks, delta spec, implementation, and E2E coverage are all in place on `main`. Next recommended step is **archive** — sync the delta spec into `openspec/specs/admin-catalog-management/spec.md` and move the change folder to `openspec/changes/archive/2026-08-04-manage-procedure-types-catalog/`.

## Verification commands

```bash
# Backend
cd backend && env/bin/python manage.py test catalogs -v 2

# Frontend type check
cd frontend/aesthetic-clinic && npx tsc --noEmit

# E2E
cd frontend/aesthetic-clinic && npx playwright test admin_general.spec.ts -g "tipos-procedimiento"
```
