# Exploration: `manage-procedure-types-catalog`

## Current State

`ProcEsteticosTipo` is a Django model (`backend/catalogs/models.py:35-43`) that inherits from `CatalogoEditableModel`. It represents the "Tipo de procedimiento" dropdown option used by `procedimientos-esteticos` catalog items. The model has one own field: `tipo = CharField(max_length=120, unique=True)`. It inherits `descripcion`, `orden`, and `activo` from `CatalogoEditableModel` (`backend/common/models.py:12-18`).

**Existing consumers (read-only):**
- `backend/config/api_views.py:1217-1218` — populates the `procedureTypeId` select dropdown for `procedimientos-esteticos` form
- `backend/config/api_views.py:1685` — used as FK (`tipo_p_estetico`) in `ProcEstetico` create/update via `_catalog_parse_payload`

**Gap:** There is NO admin catalog page to CRUD the `ProcEsteticosTipo` items themselves. The `ProcEsteticosTipo` catalog is managed only through this indirect FK relationship.

## Affected Areas

### Backend
- `backend/config/api_views.py` — two new blocks needed:
  - `_catalog_page_data` switch (around line ~1227): new `if catalog_key == "tipos-procedimiento"` block after `tipos-servicio` (line ~1278), using `ProcEsteticosTipo.objects.all()` with identical structure to `tipos-servicio` but with `tipo` field mapping and a "Procedimientos vinculados" metadata count from the `procedimientos` reverse relation
  - `_catalog_parse_payload` switch (around line ~1694): new `if catalog_key == "tipos-procedimiento"` block after `tipos-servicio` (line ~1703), mapping `name` → `tipo` and `description` → `descripcion`

### Frontend
- `frontend/aesthetic-clinic/src/types/admin.ts:446-454` — `AdminCatalogKey` union: add `'tipos-procedimiento'`
- `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx:24-73` — `catalogFallbackInfo` Record: add entry for `'tipos-procedimiento'` with title "Tipos de procedimiento", description, and createLabel "Crear tipo de procedimiento"
- `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx:552-582` — add `export function AdminProcedureTypesCatalogPage()` wrapper returning `<CatalogPage catalogKey="tipos-procedimiento" />` (no `showCreateAction` prop — dead after Phase 2 `IN_SCOPE_CATALOGS` removal)
- `frontend/aesthetic-clinic/src/App.tsx:149-156` — add `<Route path="catalogos/tipos-procedimiento" element={<AdminProcedureTypesCatalogPage />} />`
- `frontend/aesthetic-clinic/src/components/admin/AdminCatalogTabs.tsx:3-12` — add `{ to: '/cms/catalogos/tipos-procedimiento', label: 'Tipos de procedimiento' }` to the tabs array

## Verification of Locked Decisions

| Decision | Status | Evidence |
|---|---|---|
| `CatalogoEditableModel.descripcion` exists | ✓ Verified | `backend/common/models.py:13` — `descripcion = models.TextField(blank=True)` |
| `ProcEsteticosTipo.tipo` is CharField(max_length=120, unique=True) | ✓ Verified | `backend/catalogs/models.py:36` |
| `orden` and `activo` inherited | ✓ Verified | `backend/common/models.py:14-15` |
| `CatalogPage` always shows Create (Phase 2 removed IN_SCOPE_CATALOGS) | ✓ Verified | No `showCreateAction` prop accepted in `CatalogPage` function signature (`AdminCatalogsPage.tsx:369`) |
| Form fields: `tipo` (name, required), `descripcion` (textarea, optional), `orden` (number, optional, default 0) | ✓ Confirmed | Matches `tipos-servicio` pattern exactly; `orden` is a PositiveInteger inherited from abstract model, not exposed as an editable field in the `tipos-servicio` form fields — only `name` and `description` are sent as editable payload |

**Note on `orden` field:** The inherited `orden` PositiveIntegerField is NOT part of the create/edit form in the `tipos-servicio` pattern. The backend `_catalog_parse_payload` for `tipos-servicio` only sets `obj.tipo` and `obj.descripcion`. The `orden` defaults to 0 via the model field. If explicit `orden` editing is desired, it would need to be added as a third `_catalog_field` in the `_catalog_page_data` block AND in the parse block — but the user did not request this, so it stays at default 0.

## Sensible Defaults

| Behaviour | Value | Source |
|---|---|---|
| Search field | `tipo` (case-insensitive, `?q=`) | `tipos-servicio` pattern (`backend/config/api_views.py:1231`) |
| Active filter | `?active=` (`true` / `false` / `all`) | `tipos-servicio` pattern (`backend/config/api_views.py:1232-1235`) |
| Default active filter | `all` | `CatalogPage` component default (`AdminCatalogsPage.tsx:371`) |
| Search debounce | 300ms | `CatalogPage` (`AdminCatalogsPage.tsx:372`) |
| Page title | "Tipos de procedimiento" | Tab label match |
| Create label | "Crear tipo de procedimiento" | Consistent with "Crear tipo de servicio" |
| Subtitle in list | "Tipo de procedimiento estético" | Descriptive, similar to "Base comercial del servicio" |
| Sort order | `orden, tipo` | Model Meta ordering (`backend/catalogs/models.py:40`) |

## Approaches

### 1. Copy `tipos-servicio` pattern (RECOMMENDED)
Exact structural clone: same field names (`name`/`description`), same query/filter pattern, same `_catalog_entry` shape, same parse block. Only the model and slug differ.

- **Pros**: Minimal diff, proven pattern, low risk, predictable behavior
- **Cons**: None significant
- **Effort**: Low

### 2. Build from scratch with separate analysis
Custom design of fields, metadata, and payload parsing for `ProcEsteticosTipo`.

- **Pros**: Potential for cleaner design
- **Cons**: Over-engineering for a near-identical schema; more review surface; diverges from established pattern
- **Effort**: High

## Recommendation

**Approach 1 — Copy `tipos-servicio` pattern.** The `ProcEsteticosTipo` schema is nearly identical to `TipoServicio` (both have `tipo CharField + inherited descripcion/orden/activo`). The new blocks are mechanical copies with model and string literals swapped. This is a textbook small-pattern-follow-on change.

## Risks

1. **Model relationship integrity**: `ProcEsteticosTipo` is referenced as FK by `ProcEstetico.proc_estetico`. The `on_delete=models.PROTECT` means you cannot delete a `ProcEsteticosTipo` that has child `ProcEstetico` records. The catalog page's deactivate toggle is safe (FK is only on delete); but if the user deletes (future), they need to move children first.
2. **`tipos-servicio` `descripcion` was set on update**: The `_catalog_parse_payload` for `tipos-servicio` only sets `tipo` and `descripcion` — it does NOT update `orden`. This is the correct approach and should be mirrored.
3. **`tipos-procedimiento` metadata count**: The `tipos-servicio` block shows "Configuraciones activas" (from `servicios_config.filter(activo=True)`). For `ProcEsteticosTipo`, the equivalent metadata should be "Procedimientos vinculados" using `procedimientos.count()` (the `related_name` on the FK from `ProcEstetico`).

## Ready for Proposal

**Yes.** All facts verified. Locked decisions confirmed. The change is a near-clone of an existing pattern. The `proposal.md` should write the scope as: 1 new BE block in `_catalog_page_data`, 1 new BE block in `_catalog_parse_payload`, 5 FE file modifications (types, catalogFallbackInfo, page wrapper, route, tab). No new components needed. No database migration needed.
