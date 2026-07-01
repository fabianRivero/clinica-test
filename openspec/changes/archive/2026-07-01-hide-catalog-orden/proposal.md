# Proposal: hide-catalog-orden

## Intent

Eliminate manual `orden` management from four admin catalog pages (`especialidades`, `secciones-ficha`, `campos-ficha`, `sectores`). Admins should never see or touch an ordering number — the server assigns `orden = max(orden) + 1` on every create and preserves the existing value on every update. The `orden` field is dropped from the list metadata and the create/edit form entirely.

## Why

The admin UI currently exposes `orden` as a visible metadata label on list cards and as a number input on the form. Admins must manually pick a number when creating entries, creating friction and gaps (e.g., two items with `orden=3`). The solution is to make ordering fully automatic: auto-increment on create, immutable on update, hidden everywhere. The `sectores` catalog already implements this pattern (lines 2095–2100 of `api_views.py`); we extend it to the other three.

## What Changes

### Backend — `api_views.py`
- **`_catalog_page_data`** — 4 catalogs: strip `{"label": "Orden", "value": str(item.orden)}` from each item's `metadata` list. Strip the `_catalog_field("order", ...)` field definition from the form `fields` array.
- **`_catalog_parse_payload`** — 3 catalogs (`especialidades`, `secciones-ficha`, `campos-ficha`): on create, compute `max(orden)+1` and assign it instead of the payload value; on update, do not assign `orden` at all (leave the existing DB value untouched). The `sectores` branch already does this.

### Spec delta
- **`openspec/specs/medical-form-section-editor/spec.md`** — REQ-11 (manual reorder via PATCH `{orden: N}`) is removed/rewritten to reflect auto-assignment.

### Tests
- **`backend/tests/test_secciones_ficha_crud.py`** — Update create tests to assert `orden = max(orden)+1` regardless of payload `order`. Update `test_update_section_persists_changes` to assert `orden` is preserved (not overwritten to `9`). Remove `order` from payloads or assert the server-ignored value is not persisted.
- **`backend/tests/test_admin_catalog_sectores.py`** — Already aligned; no changes needed.

### Frontend
- None. `CatalogPage` renders `metadata` dynamically; omitting `orden` from the response naturally hides it. The `fields` array drives the form; removing `order` from there removes it from the create/edit UI.

### Data
- No migration. Existing `orden` values are untouched.

## Impact

| Area | Impact | Description |
|------|--------|-------------|
| `openspec/specs/medical-form-section-editor/spec.md` | Modified | REQ-11 removed/rewritten — auto-assign replaces manual reorder |
| `backend/config/api_views.py` | Modified | Response shape + payload parsing for 3–4 catalogs |
| `backend/tests/test_secciones_ficha_crud.py` | Modified | Align create/update tests to auto-assign contract |
| `backend/tests/test_admin_catalog_sectores.py` | None | Already asserts the desired behavior |

## Non-Goals

- Drag-to-reorder UI or any manual reorder control
- Per-catalog ordering rules (e.g., alphabetical fallback)
- Bulk reorder endpoint or batch operations
- Exposing `orden` in any public API
- Changing the default list ordering (still `orden, nombre`)

## Affected Files

| File | Change |
|------|--------|
| `backend/config/api_views.py` | Strip `orden` from response metadata and form fields; auto-assign `max(orden)+1` on create for 3 catalogs; preserve on update |
| `openspec/specs/medical-form-section-editor/spec.md` | Delta REQ-11 (manual reorder → auto-assign) |
| `backend/tests/test_secciones_ficha_crud.py` | Update create/update tests to match auto-assign contract |
| `backend/tests/test_admin_catalog_sectores.py` | No change needed |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `test_secciones_ficha_crud.py` assertion drift after apply | Low | Reference `test_admin_catalog_sectores.py` lines 187–212 and 367–385 for the exact assertion pattern |
| Backend payload branch for `campos-ficha` needs `Max` import | Low | Add `from django.db.models import Max` if not already present |

## Rollback Plan

Revert `api_views.py` changes: restore `orden` to each item's `metadata` list, restore `order` to each form `fields` array, and in the three payload branches restore `obj.orden = order or 0` (create) and `obj.orden = order or 0` (update). No database migration reversal needed.

## Dependencies

- None (self-contained backend change; `test_admin_catalog_sectores.py` is the reference test pattern)

## Success Criteria

- [ ] `especialidades`, `secciones-ficha`, `campos-ficha` list response has no `orden` metadata label
- [ ] `sectores` list response has no `orden` metadata label (already true by coincidence; spec confirms it)
- [ ] Create for all 4 catalogs: `orden` in DB equals `max(orden)+1` regardless of payload `order`
- [ ] Update for all 4 catalogs: `orden` in DB unchanged after update call
- [ ] `python manage.py test backend/tests/test_admin_catalog_sectores.py` passes (already passing — confirms contract)
- [ ] `python manage.py test backend/tests/test_secciones_ficha_crud.py` passes with updated assertions
- [ ] `medical-form-section-editor` spec delta replaces REQ-11 with auto-assign requirement
