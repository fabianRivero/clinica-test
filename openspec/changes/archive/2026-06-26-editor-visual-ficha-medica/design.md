# Design: Visual Medical Form Editor (`editor-visual-ficha-medica`)

## Technical Approach

Add `secciones-ficha` as a new admin catalog key in `api_views.py` following the exact 5-point integration pattern used for `sectores` and `campos-ficha`. Enhance the `campos-ficha` form with type-conditional UI rendering and add backend validation requiring `grupo_opciones` for SELECCION/MULTISELECCION fields. No changes to `_serialize_medical_config` or `_validate_medical_step`.

## Architecture Decisions

### ADR-1: `secciones-ficha` as a catalog key, not a standalone module

| Option | Tradeoff | Decision |
|--------|---------|----------|
| Standalone router + controller for `FichaSeccion` CRUD | Full control; bypasses existing catalog machinery | Rejected — introduces parallel patterns, doubles maintenance |
| New catalog key `secciones-ficha` in existing machinery | Zero new URL patterns; admin tab appears in the same UI as all other catalogs | **Chosen** |

**Rationale**: The catalog machinery already handles list/search/create/update/toggle/filter with zero extra boilerplate. Admin users expect a single "Configuración → Catálogos" experience. A standalone route would break the unified interface and require its own form renderer.

### ADR-2: At-least-one validation (sector / proc_estetico) in `_catalog_parse_payload` (backend), not frontend only

| Option | Tradeoff | Decision |
|--------|---------|----------|
| Frontend-only validation (disable Save button) | Simpler; UX catches it before submit | Rejected — API is the source of truth; direct API calls bypass the check |
| Backend only in `_catalog_parse_payload` | API enforces for all callers; works with future integrations | **Chosen** |
| Database-level CHECK constraint | Strongest guarantee | Rejected — FKs are nullable by design (for legacy); a partial constraint would require partial-index tricks |

**Rationale**: The API is the authoritative boundary. Frontend validation is UX polish; backend validation is correctness. The existing `UniqueConstraint(proc_estetico, codigo)` already lives at DB level and is sufficient for uniqueness — the at-least-one check fills the other gap.

### ADR-3: `_validate_medical_step` is not touched

| Option | Tradeoff | Decision |
|--------|---------|----------|
| Add `secciones-ficha` validation to `_validate_medical_step` | Ensures conversion step rejects incomplete configs | Rejected — out of scope per proposal; structural change, not validation change |
| Leave `_validate_medical_step` unchanged | No risk of breaking existing conversion flow | **Chosen** |

**Rationale**: The proposal explicitly excludes changes to `_serialize_medical_config` and `_validate_medical_step`. This change is structural (adding a new catalog), not a validation tightening. Integration tests cover the serialization side; if validation is needed later, it gets its own change.

## Data Flow

```
Admin creates section via UI

Admin ──fills form──► Frontend (CatalogEditorForm)
                              │
                              ▼
                    POST /api/admin/catalogos/secciones-ficha/crear/
                              │
                              ▼
              Backend: _catalog_key_to_slug("secciones-ficha") ✓
                              │
                              ▼
              Backend: _catalog_page_data("secciones-ficha", ...) [rejected — wrong method]
                              │
                              ▼
              Backend: _catalog_parse_payload("secciones-ficha", payload)
                              │
                   ┌──────────┴──────────┐
                   │  Parse sector_id   │
                   │  Parse proc_estetico_id │
                   │  Validate at-least-one │
                   │  Validate uniqueness   │
                   │  (proc_estetico, codigo)│
                   └──────────┬──────────┘
                              ▼
                    FichaSeccion.objects.create(...)  or  .save(...)
                              │
                              ▼
                    201 response → Frontend reloads list
```

## Backend Integration — 5 Points

### Point 1: `_catalog_key_to_slug` (set)

```python
def _catalog_key_to_slug(catalog_key):
    if catalog_key in {
        # ...existing keys...
        "sectores",
        "secciones-ficha",   # ← NEW
    }:
        return catalog_key
    raise KeyError(catalog_key)
```

### Point 2: `_catalog_summary_descriptor` (item)

```python
{
    "key": "secciones-ficha",
    "title": "Secciones de ficha médica",
    "description": "Agrupa campos de ficha clínica por ámbito operativo o procedimiento estético.",
},
```

### Point 3: `_catalog_page_data` (block — list/search/active/filter/order)

```python
if catalog_key == "secciones-ficha":
    unfiltered = FichaSeccion.objects.all()
    base_qs = unfiltered.select_related("sector", "proc_estetico")

    if q:
        base_qs = base_qs.filter(
            Q(codigo__icontains=q) | Q(nombre__icontains=q)
        )
    if active == "true":
        base_qs = base_qs.filter(activo=True)
    elif active == "false":
        base_qs = base_qs.filter(activo=False)
    # filter by sector: ?sector=<id>
    # filter by proc_estetico: ?proc_estetico=<id>
    queryset = base_qs.order_by("sector__nombre", "proc_estetico__proceso", "orden", "nombre")

    items = [
        _catalog_entry(pk, nombre, codigo, activo, metadata=[...], values={
            "name": nombre, "code": codigo,
            "sectorId": sector_id, "procEsteticoId": proc_estetico_id,
            "order": orden,
        })
        for item in queryset
    ]
    # fields: name(text), code(text), sectorId(select), procEsteticoId(select), order(number), active(checkbox)
```

### Point 4: `_catalog_parse_payload` (validation block)

```python
if catalog_key == "secciones-ficha":
    name = text_value("name")
    code = text_value("code")
    sector_id = int_value("sectorId", minimum=1, allow_empty=True)
    proc_estetico_id = int_value("procEsteticoId", minimum=1, allow_empty=True)
    order = int_value("order", minimum=0, allow_empty=True)

    if not code:
        errors["code"] = "El código es obligatorio."
    if not name:
        errors["name"] = "El nombre es obligatorio."
    if not sector_id and not proc_estetico_id:
        errors["_general"] = "Debes asignar al menos un sector o un procedimiento estético."
    if errors:
        raise ValidationError(errors)

    # Uniqueness check: UniqueConstraint(proc_estetico, codigo) is enforced at DB level
    # but we can catch the IntegrityError and return a friendly 400
    # by wrapping save() in try/except.

    sector = Sector.objects.filter(pk=sector_id).first() if sector_id else None
    proc = ProcEstetico.objects.filter(pk=proc_estetico_id).first() if proc_estetico_id else None

    obj = instance or FichaSeccion()
    obj.nombre = name
    obj.codigo = code
    obj.sector = sector
    obj.proc_estetico = proc
    obj.orden = order or 0
    return obj
```

### Point 5: `_catalog_get_instance` (model_map)

```python
model_map = {
    # ...existing entries...
    "sectores": Sector,
    "secciones-ficha": FichaSeccion,   # ← NEW
}
```

### Backend: `grupo_opciones` required for SELECCION/MULTISELECCION in `_catalog_parse_payload`

In the existing `campos-ficha` block, after parsing `option_group_id`:

```python
if catalog_key == "campos-ficha":
    # ...existing parsing...
    SELECTION_TYPES = {"SELECCION", "MULTISELECCION"}
    if field_type in SELECTION_TYPES and not option_group_id:
        errors["optionGroupId"] = "El grupo de opciones es obligatorio para campos de selección."
    if errors:
        raise ValidationError(errors)
    # ...rest unchanged...
```

## Frontend Changes

### Tab entry in `AdminCatalogsPage.tsx` (`catalogFallbackInfo`)

```typescript
secciones-ficha: {
  title: 'Secciones de ficha médica',
  description: 'Agrupa campos de ficha clínica por sector o procedimiento estético.',
  createLabel: 'Crear sección de ficha',
},
```

New exported page component:
```typescript
export function AdminSeccionesFichaCatalogPage() {
  return <CatalogPage catalogKey="secciones-ficha" />
}
```

### Conditional form renderer for `campos-ficha` fields

The existing `CatalogFormField` in `AdminCatalogsPage.tsx` handles generic types. A conditional renderer wraps the field selection:

```typescript
function CamposFichaConditionalFields({
  fieldType,
  formState,
  onChange,
}: {
  fieldType: string
  formState: Record<string, AdminCatalogFormValue>
  onChange: (name: string, value: AdminCatalogFormValue) => void
}) {
  // Renders es_multiple and permite_detalle only for SELECCION / MULTISELECCION
  if (fieldType === 'SELECCION' || fieldType === 'MULTISELECCION') {
    return (
      <>
        <CatalogFormField
          field={{ name: 'isMultiple', label: 'Permite múltiples respuestas',
                   inputType: 'checkbox', valueType: 'boolean' }}
          value={formState.isMultiple}
          onChange={onChange}
        />
        <CatalogFormField
          field={{ name: 'allowsDetail', label: 'Permite detalle adicional',
                   inputType: 'checkbox', valueType: 'boolean' }}
          value={formState.allowsDetail}
          onChange={onChange}
        />
      </>
    )
  }
  return null  // Hidden for TEXTO, NUMERO, FECHA, BOOLEANO
}
```

The `CatalogEditorForm` already renders `isMultiple` and `allowsDetail` as regular fields — the conditional wrapper gates their visibility by checking the current `fieldType` from form state. The `CatalogFormField` component's `inputType` map is extended so `fieldType === 'TEXTO'` renders `<textarea>`, `fieldType === 'NUMERO'` renders `<input type="number">`, `fieldType === 'FECHA'` renders `<input type="date">`, and `fieldType === 'BOOLEANO'` renders a `<select>` with Si/No options instead of a raw checkbox.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/config/api_views.py` | Modify | Add `secciones-ficha` to all 5 catalog integration points; add `grupo_opciones` required check for `campos-ficha` |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx` | Modify | Add `secciones-ficha` entry to `catalogFallbackInfo`; export `AdminSeccionesFichaCatalogPage`; add conditional field renderer for `campos-ficha` |
| `frontend/aesthetic-clinic/src/components/admin/AdminCatalogTabs.tsx` | Inspect | Add `secciones-ficha` tab if list is hardcoded |
| `backend/tests/test_secciones_ficha_crud.py` | Create | Backend unit tests: CRUD, at-least-one validation, uniqueness per proc_estetico |
| `backend/tests/test_campos_ficha_validation.py` | Create | Backend unit tests: `grupo_opciones` required for SELECCION/MULTISELECCION |
| `frontend/aesthetic-clinic/tests/e2e/cms-catalogos-secciones-ficha.spec.ts` | Create | Playwright E2E: full CRUD cycle via UI |
| `frontend/aesthetic-clinic/tests/e2e/cms-catalogos-campos-ficha-ui-by-type.spec.ts` | Create | Playwright E2E: type-conditional UI renders correctly |

## Sequence Diagram

```
Admin opens /cms/catalogos/secciones-ficha
         │
         ▼
Frontend → GET /api/admin/catalogos/secciones-ficha/?active=all
         │
         ▼
Backend: _catalog_key_to_slug("secciones-ficha") → hits block
Backend: _catalog_page_data("secciones-ficha") → returns list
         │
         ▼
Frontend renders list + create form
         │
Admin fills form and clicks "Crear sección"
         │
         ▼
Frontend → POST /api/admin/catalogos/secciones-ficha/crear/
  { name, code, sectorId, procEsteticoId, order, active }
         │
         ▼
Backend: _catalog_parse_payload("secciones-ficha", payload)
  → validates at-least-one (sectorId | procEsteticoId)
  → validates required fields
  → saves FichaSeccion
         │
         ▼
201 response → Frontend reloads list
```

## Testing Strategy

| Layer | What | How |
|-------|------|-----|
| Backend unit | `secciones-ficha` CRUD: create, list, filter by sector, filter by proc, at-least-one rejection, duplicate (proc, codigo) rejection, update, toggle activo | `test_secciones_ficha_crud.py` — Django unittest |
| Backend unit | `grupo_opciones` required for SELECCION and MULTISELECCION; allowed for all other types | `test_campos_ficha_validation.py` — Django unittest |
| Backend unit | Existing `test_medical_form_by_sector.py` still passes after integration | Django unittest runner |
| Frontend E2E | `secciones-ficha` tab: create, edit, toggle, list filters | `cms-catalogos-secciones-ficha.spec.ts` — Playwright |
| Frontend E2E | `campos-ficha` form renders correct input per `tipo_campo` | `cms-catalogos-campos-ficha-ui-by-type.spec.ts` — Playwright |

## Migration / Rollout

No schema migration required. `FichaSeccion`, `FichaCampo`, `Sector`, and `ProcEstetico` models already exist with the correct fields and constraints. The change is entirely a wiring + validation addition.

No feature flag required — `secciones-ficha` appears as a new tab only; no existing behavior changes.

## Open Questions

- [ ] Should the `secciones-ficha` tab use the generic `CatalogPage` component (via `catalogKey="secciones-ficha"`), or does it need a standalone page component with custom business logic?
  **Recommendation**: Use the generic `CatalogPage` — the backend already returns the correct fields and values shape. No custom logic needed.
- [ ] Does the `sectores` filter in `secciones-ficha` list default to showing sections with `sector IS NOT NULL` or show all?
  **Recommendation**: Show all (no default filter), let the admin explicitly filter via the dropdown.
