# Design: Manage Procedure Types Catalog

## Technical Approach

Add a sixth admin catalog page `/cms/catalogos/tipos-procedimiento` by cloning the exact structural pattern of `tipos-servicio`. The `ProcEsteticosTipo` model (`backend/catalogs/models.py:35`) inherits `descripcion`, `orden`, and `activo` from `CatalogoEditableModel` and adds only `tipo = CharField(max_length=120, unique=True)` — identical shape to `TipoServicio`. No new components, no migrations, no model changes. Two BE blocks and five FE edits.

## Architecture Decisions

### Decision: Clone `tipos-servicio` instead of generic refactor

**Choice**: Exact mechanical clone — separate `if catalog_key == "tipos-procedimiento"` blocks in both `_catalog_page_data` and `_catalog_parse_payload`.
**Alternatives considered**: Build a shared generic helper that accepts model + field names as parameters.
**Rationale**: The existing codebase has zero generic catalog infrastructure — every catalog is a hand-rolled `if/elif` branch. Introducing generics here would be over-engineering for a single new catalog and would require changing 5 existing branches (risk of regression). The "clone and swap" approach is the established team pattern, confirmed by `proposal.md` scope and `explore.md` recommendation.

### Decision: NO new frontend components

**Choice**: Reuse `CatalogPage`, `CatalogEditorForm`, `useDebounce`, `getAdminCatalogDetail`, `useApiResource`.
**Alternatives considered**: Create a dedicated `ProcedureTypesCatalogPage` component with its own hooks.
**Rationale**: `CatalogPage` is the universal shell that drives all five existing catalogs. Phase 2 of `catalog-list-search-filter` removed the `IN_SCOPE_CATALOGS` Set, so the toolbar (Create button, search, filter) renders for all catalog keys automatically. A new wrapper function returning `<CatalogPage catalogKey="tipos-procedimiento" />` is the minimum necessary change.

### Decision: No database migration

**Choice**: No migration needed — `ProcEsteticosTipo` already has all fields it needs (`tipo`, `descripcion`, `orden`, `activo`).
**Alternatives considered**: Add an explicit `orden` editing field to the form.
**Rationale**: The `tipos-servicio` pattern does NOT expose `orden` in the create/edit form — it stays at default 0. Mirroring this exactly avoids inconsistency. The spec explicitly lists only `tipo` (required) and `descripcion` (optional) as editable fields.

### Decision: `unfiltered = ProcEsteticosTipo.objects.all()` for header counts

**Choice**: Metrics block uses the unfiltered queryset for counts (same fix as `catalog-list-search-filter` PR1).
**Alternatives considered**: Use the filtered `base_queryset` for counts.
**Rationale**: Header counts show the total catalog size (active/inactive/total) and must NOT reflect the current search/filter. Using `unfiltered` ensures counts stay stable while the list below is filtered — matching the spec and the `tipos-servicio` fix.

## Data Flow

```
Browser                 React Router           Django API View
   │                          │                        │
   ├─ GET /cms/catalogos/    │                        │
   │  tipos-procedimiento    │                        │
   │─────────────────────────> CatalogPage loads      │
   │                         ├─ GET /api/admin/        │
   │                         │  catalogos/tipos-       │
   │                         │  procedimiento/        │
   │                         │───────────────────────>+
   │                         │<───────────────────────+
   │                         │  200 + JSON payload     │
   │<───────────────────────── render item list       │
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/config/api_views.py:~1279` | Modify | Insert `tipos-procedimiento` block in `_catalog_page_data` (after `tipos-servicio`) |
| `backend/config/api_views.py:~1703` | Modify | Insert `tipos-procedimiento` block in `_catalog_parse_payload` (after `tipos-servicio`) |
| `frontend/aesthetic-clinic/src/types/admin.ts:446` | Modify | Add `'tipos-procedimiento'` to `AdminCatalogKey` union |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx:24-73` | Modify | Add entry to `catalogFallbackInfo` Record |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx:560-562` | Modify | Add `AdminProcedureTypesCatalogPage` wrapper |
| `frontend/aesthetic-clinic/src/App.tsx:~152` | Modify | Add route for `catalogos/tipos-procedimiento` |
| `frontend/aesthetic-clinic/src/components/admin/AdminCatalogTabs.tsx:3-12` | Modify | Add tab entry for `tipos-procedimiento` |
| `backend/catalogs/tests.py:17-26` | Modify | Add `"tipos-procedimiento": "/api/admin/catalogos/tipos-procedimiento/"` to `URL_TEMPLATES` + 5 test cases |
| `frontend/aesthetic-clinic/tests/e2e/admin_general.spec.ts` | Modify | Add E2E flow for `tipos-procedimiento` |

## Backend Design

### `_catalog_page_data` block (after line 1278)

```python
# AFTER line 1278 — insert this new block:
if catalog_key == "tipos-procedimiento":
    unfiltered = ProcEsteticosTipo.objects.all()
    base_queryset = unfiltered
    if q:
        base_queryset = base_queryset.filter(tipo__icontains=q)
    if active == "true":
        base_queryset = base_queryset.filter(activo=True)
    elif active == "false":
        base_queryset = base_queryset.filter(activo=False)
    queryset = base_queryset.order_by("orden", "tipo")
    items = [
        _catalog_entry(
            item.pk,
            item.tipo,
            "Tipo de procedimiento estético",
            item.activo,
            [
                {"label": "Descripción", "value": item.descripcion or "Sin descripción"},
                {
                    "label": "Procedimientos vinculados",
                    "value": str(item.procedimientos.count()),
                },
            ],
            {
                "name": item.tipo,
                "description": item.descripcion,
            },
        )
        for item in queryset
    ]
    active_count = unfiltered.filter(activo=True).count()
    total_count = unfiltered.count()
    return {
        "catalog": {
            "key": catalog_key,
            "title": "Tipos de procedimiento",
            "description": "Administra los tipos de procedimientos estéticos disponibles.",
            "createLabel": "Crear tipo de procedimiento",
        },
        "metrics": _catalog_metric_set(
            active_count,
            total_count - active_count,
            total_count,
            f"{ProcEstetico.objects.filter(activo=True).count()} procedimiento(s) activo(s)",
        ),
        "fields": [
            _catalog_field("name", "Tipo de procedimiento", "text", required=True, placeholder="Ej. Estética corporal"),
            _catalog_field("description", "Descripción", "textarea", placeholder="Notas internas del tipo de procedimiento"),
        ],
        "items": items,
    }
```

### `_catalog_parse_payload` block (after line 1703)

```python
# AFTER line 1703 — insert this new block:
if catalog_key == "tipos-procedimiento":
    name = text_value("name")
    if not name:
        errors["name"] = "El nombre del tipo de procedimiento es obligatorio."
    if errors:
        raise ValidationError(errors)
    obj = instance or ProcEsteticosTipo()
    obj.tipo = name
    obj.descripcion = text_value("description")
    return obj
```

### BEFORE/AFTER summary (high-level)

| Location | Change |
|----------|--------|
| `api_views.py:~1227` | No-op (existing `tipos-servicio` block untouched) |
| `api_views.py:~1279` | **INSERT** new `if catalog_key == "tipos-procedimiento":` block (model=ProcEsteticosTipo, field=tipo, metadata=procedimientos.count()) |
| `api_views.py:~1703` | **INSERT** new `if catalog_key == "tipos-procedimiento":` parse block (name→tipo, description→descripcion) |

## Frontend Design

### 1. `AdminCatalogKey` union (`admin.ts:446`)

```typescript
// ADD 'tipos-procedimiento' to existing union:
export type AdminCatalogKey =
  | 'todos-los-servicios'
  | 'procedimientos-esteticos'
  | 'tipos-servicio'
  | 'tipos-procedimiento'   // ← NEW
  | 'campos-ficha'
  | 'patologias-cutaneas'
  | 'especialidades'
  | 'grupos-opciones'
  | 'categorias-gasto'
```

### 2. `catalogFallbackInfo` (`AdminCatalogsPage.tsx:24-73`)

```typescript
// ADD inside the Record literal, after 'tipos-servicio' entry:
'tipos-procedimiento': {
  title: 'Tipos de procedimiento',
  description: 'Administra los tipos de procedimientos estéticos disponibles para el catálogo de procedimientos.',
  createLabel: 'Crear tipo de procedimiento',
},
```

### 3. Page wrapper (`AdminCatalogsPage.tsx:~560`)

```typescript
// ADD after AdminServiceTypesCatalogPage:
export function AdminProcedureTypesCatalogPage() {
  return <CatalogPage catalogKey="tipos-procedimiento" />
}
```

### 4. Route (`App.tsx:~152`)

```tsx
// ADD after tipos-servicio route:
<Route path="catalogos/tipos-procedimiento" element={<AdminProcedureTypesCatalogPage />} />
```

### 5. Tab (`AdminCatalogTabs.tsx:3-12`)

```tsx
// ADD to tabs array, after 'tipos-servicio':
{ to: '/cms/catalogos/tipos-procedimiento', label: 'Tipos de procedimiento' },
```

## Testing Strategy

### Backend — Django unittest (`backend/catalogs/tests.py`)

| Test | Method | Description |
|------|--------|-------------|
| `test_search_tipos_procedimiento_filters_by_tipo` | GET `?q=estét` | Returns only items matching `tipo__icontains` |
| `test_active_true_false_all_tipos_procedimiento` | GET `?active=true\|false\|all` | Correct filtering per active flag |
| `test_combined_q_and_active_tipos_procedimiento` | GET `?q=x&active=true` | Combined filters narrow results |
| `test_invalid_active_param_tipos_procedimiento` | GET `?active=maybe` | Returns 400 with validation error |
| `test_tipos_procedimiento_in_catalog_list` | GET (no params) | Returns 200 in the "all catalogs" loop |

All five tests follow the identical pattern as `tipos-servicio` tests (lines 127–179 of `tests.py`). Add `"tipos-procedimiento": "/api/admin/catalogos/tipos-procedimiento/"` to `URL_TEMPLATES` and add fixture `ProcEsteticosTipo` instances in `setUpTestData`.

### Frontend — Playwright E2E (`admin_general.spec.ts`)

| Test | Steps |
|------|-------|
| `tipos-procedimiento CRUD happy path` | 1. Authenticate → 2. Navigate to `/cms/catalogos/tipos-procedimiento` → 3. Assert Create button visible → 4. Click Create, fill `tipo`="Botox", submit → 5. Assert "Botox" in list → 6. Search "Botox", assert filtered → 7. Deactivate item → 8. Filter to "Inactivos", assert item appears |

## Sequence Diagram

```
Browser                    React                    Django
  |                          |                         |
  | [Navigate to /cms/       |                         |
  |  catalogos/tipos-       |                         |
  |  procedimiento]         |                         |
  |─────────────────────────>                         |
  |                          | [CatalogPage mounts]    |
  |                          | [useApiResource loader] |
  |                          |─────────────────────────> GET /api/admin/catalogos/
  |                          |                          tipos-procedimiento/
  |                          |                          ?active=all
  |                          |<───────────────────────── 200 OK
  |                          |  { items: [...],         |
  |                          |    metrics: {...},       |
  |                          |    fields: [...] }       |
  |<───────────────────────── render items + toolbar    |
  | [User types "lip"]       |                         |
  | [300ms debounce]         |                         |
  |                          | GET /api/admin/catalogos/|
  |                          | tipos-procedimiento/     |
  |                          | ?q=lip&active=all       |
  |                          |─────────────────────────>+
  |                          |<─────────────────────────+
  |                          |  { items: filtered }     |
  |<───────────────────────── list re-renders           |
```

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `ProcEsteticosTipo` used as FK with `on_delete=PROTECT` in `ProcEstetico` — deleting a type with linked procedures raises DB error | Low | Medium | Toggle (soft deactivate) is the safe operation; explicit delete is blocked by DB constraint |
| Metrics count uses wrong queryset (filtered instead of unfiltered) | Low | Medium | Follow exact `unfiltered = Model.objects.all()` pattern from `tipos-servicio` |
| Frontend build fails if `AdminCatalogKey` type update is incomplete | Low | High | Add `'tipos-procedimiento'` to the union; TypeScript strict mode will catch any mismatch |

## Migration / Rollout

No migration required. `ProcEsteticosTipo` model and database table already exist. No schema changes.

## Rollback Plan (from `proposal.md`)

1. Revert both BE blocks in `api_views.py` (remove the two new `if catalog_key == "tipos-procedimiento":` blocks)
2. Revert the five FE file changes (types, catalogFallbackInfo, wrapper, route, tab)
3. Run `python manage.py test` — confirm clean
4. Verify `/cms/catalogos/tipos-procedimiento` returns 404

## Open Questions

None. All decisions are locked and verified in `explore.md`.
