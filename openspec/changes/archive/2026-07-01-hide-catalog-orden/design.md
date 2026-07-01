# Design: hide-catalog-orden

## Technical Approach

Surgical removal of `orden`/`order` from the API response and payload handling for four admin catalogs (`especialidades`, `campos-ficha`, `secciones-ficha`, `sectores`). Two backend functions are modified: `_catalog_page_data` strips three `order`/`orden` artefacts from the list response, and `_catalog_parse_payload` replaces payload-driven `orden` assignment with server-side `max(orden)+1` auto-assignment on create and no-op on update. The frontend requires zero changes — `CatalogPage` renders whatever the API returns, so omitting `orden` from the response naturally hides it.

## Architecture Decisions

### Decision: Backend-only, frontend passive

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Remove `orden` from API + add `omittedFieldNames` on frontend | More explicit, but adds state and logic to frontend | Not chosen |
| Remove `orden` from API only; frontend reads from API | No frontend changes; zero new state; smaller diff | **Chosen** |

The `CatalogPage` component iterates `data.fields` at line 553 for the form and `item.metadata` at line 605 for the list card. Once the backend stops emitting `order` in those three places, the UI naturally hides it with no prop or flag needed.

### Decision: Auto-assign pattern mirrors existing `sectores` branch

`sectores` already implements the desired contract (lines 2095–2100). Replicating that exact pattern for the other three catalogs minimizes novelty and makes the code pattern consistent across all four.

## Backend Response Shape Changes

All removals are surgical — only the three `order`/`orden` artefacts per catalog are touched; no surrounding code moves.

### `especialidades` (lines 1540–1594)

| Artefact | What to remove | Line |
|----------|---------------|------|
| (a) Form field | `_catalog_field("order", "Orden", "number", ...)` | 1591 |
| (b) Per-item metadata | `{"label": "Orden", "value": str(item.orden)}` | 1557 |
| (c) Per-item values | `"order": item.orden,` | 1567 |

### `campos-ficha` (lines 1378–1489)

| Artefact | What to remove | Line |
|----------|---------------|------|
| (a) Form field | `_catalog_field("order", "Orden", "number", ...)` | 1483 |
| (b) Per-item metadata | `{"label": "Orden", "value": str(item.orden)}` | 1405 |
| (c) Per-item values | `"order": item.orden,` | 1418 |

Metadata placement (confirmed): `Orden` sits between `Grupo de opciones` (1402–1404) and `Requerido` (1406).

### `secciones-ficha` (lines 1768–1869)

| Artefact | What to remove | Line |
|----------|---------------|------|
| (a) Form field | `_catalog_field("order", "Orden", "number", ...)` | 1866 |
| (b) Per-item metadata | `{"label": "Orden", "value": str(item.orden)}` | 1804 |
| (c) Per-item values | `"order": item.orden,` | 1819 |

Metadata placement (confirmed): `Orden` sits between `Código` (1803) and `Sector` (1805–1808).

### `sectores` (lines 1708–1766)

Only (b) and (c) apply — the form `fields` array already has no `order` entry (lines 1760–1764 contain only `code`, `name`, `description`).

| Artefact | What to remove | Line |
|----------|---------------|------|
| (b) Per-item metadata | `{"label": "Orden", "value": str(item.orden)}` | 1728 |
| (c) Per-item values | `"order": item.orden,` | 1739 |

## Backend Payload Parsing Changes

`_catalog_parse_payload` is the single function to change. Three catalogs need updates.

### `especialidades` (lines 2043–2054)

```python
# BEFORE
order = int_value("order", minimum=0, allow_empty=True)
# ... validation ...
obj = instance or Especialidad()
obj.nombre = name
obj.descripcion = text_value("description")
obj.orden = order or 0          # line 2053

# AFTER
order = int_value("order", minimum=0, allow_empty=True)  # still read; ignored
# ... validation ...
obj = instance or Especialidad()
obj.nombre = name
obj.descripcion = text_value("description")
if instance is None:
    max_orden = Especialidad.objects.aggregate(Max("orden"))["orden__max"] or 0
    obj.orden = max_orden + 1   # auto-assign on create
# update branch: obj.orden untouched
```

### `campos-ficha` (lines 1986–2030)

Mirror `especialidades` pattern: keep `order = int_value(...)` for parsing but never assign it. In the create branch (`instance is None`), compute `max_orden` from `FichaCampo.objects` and assign `max_orden + 1`. The update branch assigns nothing to `obj.orden` — the existing DB value is preserved.

### `secciones-ficha` (lines 2103–2142)

Same pattern: keep `order = int_value("order", minimum=0, allow_empty=True)` read, ignore it. In create branch compute `max_orden = FichaSeccion.objects.aggregate(Max("orden"))["orden__max"] or 0` and assign `max_orden + 1`. Update branch: no assignment to `obj.orden`.

### `sectores`

No change — already correct at lines 2095–2100.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/config/api_views.py` | Modify | Strip `order`/`orden` from 4 `_catalog_page_data` branches; replace payload assignment with `max+1` auto-assign in 3 `_catalog_parse_payload` branches |
| `backend/tests/test_secciones_ficha_crud.py` | Modify | Update create assertions to `assertEqual(created.orden, baseline_max + 1)`; update `test_update_section_persists_changes` to assert `orden` unchanged when `order: 9` is sent; add explicit "PATCH with order=9 must not change orden" scenario |
| `backend/tests/test_campos_ficha_validation.py` | Review | Does not assert anything about `orden` — no changes required |
| `backend/tests/test_admin_catalog_especialidades.py` | Create | Mirror `test_admin_catalog_sectores.py` lines 187–211 (create auto-assigns) and 291–310 (update preserves) for `Especialidad` |

## Testing Strategy

| Layer | What | How |
|-------|------|-----|
| Backend unit | Create for 3 catalogs: `orden` equals `max+1` regardless of payload `order` | Django unittest — mirror sectors pattern with `aggregate(Max("orden"))` baseline |
| Backend unit | Update for 3 catalogs: `orden` unchanged when `order: 9` is sent | Django unittest — fetch existing, PATCH with `order: 9`, assert `orden` is original value |
| Backend unit | List response: no `Orden` in any `item.metadata` | Django unittest — parse response JSON, iterate items, assert no metadata entry with `label == "Orden"` |
| Backend unit | List response: no `order` in any `item.values` | Django unittest — assert `"order" not in item["values"]` |
| Backend unit | Form fields: no `order` field | Django unittest — assert no `fields` entry with `name == "order"` |

## Risks and Mitigations

### Race condition on concurrent creates

Two simultaneous `POST /crear/` requests can read the same `max(orden)` before either writes. This is a **pre-existing risk** on all four catalogs — `orden` has no `UniqueConstraint` at the model level on any of `Especialidad`, `Sector`, `FichaSeccion`, or `FichaCampo`. The DB layer is the source of truth; a collision on `orden` (e.g. both get `max+1 = 5`) does not raise a constraint error. Mitigation: the risk is pre-existing and unchanged by this change.

### Existing items with duplicate `orden` values

No migration is performed. Pre-existing duplicate `orden` rows are untouched; they remain queryable and display correctly under the unchanged `orden, nombre` ordering.

### Backward compatibility

Any client that sends `order` in the payload receives **HTTP 200/201** — the field is silently ignored, not rejected. This is the same behaviour already established by `sectores` since the auto-assign pattern was first introduced.

## Out of Scope

- Drag-to-reorder UI or any manual reorder control
- API endpoint for manual reorder
- Data migration
- Change to list ordering (remains `orden, nombre`)
- `test_campos_ficha_validation.py` — already validates `required`/`grupo_opciones` only; `orden` not asserted anywhere in it

## Open Questions

- [ ] None. The pattern is fully specified by the existing `sectores` branch and the two spec deltas.
