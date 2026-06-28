# Design: grupo-opciones-editor

## Technical Approach

Add nested REST sub-endpoints for `OpcionCatalogo` under `GrupoOpciones` (`/catalogos/grupos-opciones/<grupo_id>/opciones/`), and a modal in `AdminOptionGroupsCatalogPage` for full option lifecycle management. The API follows the existing catalog machinery patterns (decorators, `json_response`, validation). The frontend reuses the existing `CatalogPage` shell, adding only the modal and new API calls. No changes to `FichaCampo`, `FichaRespuestaOpcion`, or `_serialize_medical_config`.

## Architecture Decisions

### ADR-1: Nested sub-endpoints under `grupos-opciones` vs. a separate catalog key

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Standalone `opciones-catalogo` catalog key with its own CRUD | Reuses catalog machinery; admin tab appears in sidebar | Rejected — options are always scoped to a group; exposing them as a flat list with a group selector adds unnecessary UI and API complexity |
| Nested `/grupos-opciones/<id>/opciones/` sub-endpoints | URL reflects the parent-child relationship; group context is always implicit; fits naturally in the "Administrar opciones" modal | **Chosen** |

**Rationale**: An `OpcionCatalogo` cannot exist without a `GrupoOpciones` parent — the FK is CASCADE. Treating it as a standalone resource with a required `grupo_id` parameter in every request is worse than encoding that in the URL hierarchy. The modal UX already has group context (it is opened from a specific group row), so the URL nesting is natural.

### ADR-2: `transaction.atomic()` on the bulk create endpoint

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Partial creation (accept failures per item, continue with valid ones) | More resilient; admin doesn't lose valid options if one entry is bad | Rejected — creates inconsistent state that is hard to recover from without a bulk-delete; the admin intended to create all or nothing |
| All-or-nothing with `transaction.atomic()` | If any option fails validation or a duplicate codigo, the entire batch rolls back; admin must correct and resubmit | **Chosen** |

**Rationale**: The admin's intent when using bulk create is to populate a group in one shot. Partial success creates the question "which ones succeeded?" with no easy answer inside the modal. Atomic rollback keeps the invariant: the modal list always reflects what the backend has.

### ADR-3: Checkboxes in the option list are visible but non-functional

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Include bulk toggle/delete actions in this change | More value earlier; but expands scope and makes the review harder | Rejected — out of scope per proposal |
| Add checkboxes now, wire them later | Checkbox column is a trivial addition; future bulk actions only need the handler + API call | **Chosen** |

**Rationale**: The spec explicitly calls out checkboxes as a UI element for future bulk actions. Skipping the checkbox entirely would require touching the UI again when bulk actions are requested. Adding the column now costs one afternoon and one column in the row render.

## Data Flow

```
Admin opens grupos-opciones catalog
         │
         ▼
Admin clicks "Administrar opciones" on a group row
         │
         ▼
Frontend opens OptionGroupModal(grupoId, grupoNombre)
         │
         ├─► GET /api/admin/catalogos/grupos-opciones/{id}/opciones/
         │          │
         │          ▼
         │   Backend: admin_grupo_opciones_opciones_list
         │   → validates grupo exists → 404 if not
         │   → filters by ?active= (defaults to true)
         │   → searches ?q= in codigo/nombre/valor
         │   → returns ordered list of opciones
         │
         ▼
Admin adds/Edits/Toggles options
         │
         ├─► POST ...opciones/crear/
         │   Backend: validates codigo unique in group (SELECT before INSERT)
         │   → 201 + created option in "item"
         │
         ├─► POST ...opciones/crear-multiples/  (bulk)
         │   Backend: transaction.atomic() wraps all creates
         │   → 201 + array of created options
         │
         ├─► PATCH ...opciones/{id}/actualizar/
         │   Backend: updates nombre/valor/orden/activo
         │   → 200 + updated option in "item"
         │
         └─► POST ...opciones/{id}/estado/
             Backend: flips activo boolean
             → 200 + updated option in "item"

Each mutation → frontend refetches list (GET) → modal stays open
```

## Sequence Diagram

```
Admin clicks "Administrar opciones" on "Tipo Vacuna" group
     │
     │  GET /api/admin/catalogos/grupos-opciones/5/opciones/?active=true
     ▼
Backend: grupo 5 exists → fetch opciones → 200
     │
     ▼
Modal renders option list + filter toggle + search input
     │
     ▼
Admin clicks "Agregar opción"
     │
     ▼
Inline sub-form appears: codigo / nombre / valor / orden / activo
     │
     ▼
Admin fills: codigo="A", nombre="Opcion A", valor="a" → submits
     │
     │  POST /api/admin/catalogos/grupos-opciones/5/opciones/crear/
     │  { codigo:"A", nombre:"Opcion A", valor:"a" }
     ▼
Backend: SELECT WHERE grupo=5 AND codigo='A' → no row
         → OpcionCatalogo.objects.create(grupo_id=5, codigo="A", ...)
         → 201 { item: { id:10, codigo:"A", ... } }
     │
     ▼
Frontend: appends item to list → sub-form clears
     │
     ▼
Admin closes modal with X / ESC / backdrop
```

## Backend Changes

### New URL routes in `api_urls.py`

```python
# Nested option endpoints under grupos-opciones
path(
    "catalogos/grupos-opciones/<int:grupo_id>/opciones/",
    admin_grupo_opciones_opciones_list,
    name="admin-grupo-opciones-opciones-list-api",
),
path(
    "catalogos/grupos-opciones/<int:grupo_id>/opciones/crear/",
    admin_grupo_opciones_opciones_crear,
    name="admin-grupo-opciones-opciones-crear-api",
),
path(
    "catalogos/grupos-opciones/<int:grupo_id>/opciones/crear-multiples/",
    admin_grupo_opciones_opciones_crear_multiples,
    name="admin-grupo-opciones-opciones-crear-multiples-api",
),
path(
    "catalogos/grupos-opciones/<int:grupo_id>/opciones/<int:opcion_id>/actualizar/",
    admin_grupo_opciones_opciones_actualizar,
    name="admin-grupo-opciones-opciones-actualizar-api",
),
path(
    "catalogos/grupos-opciones/<int:grupo_id>/opciones/<int:opcion_id>/estado/",
    admin_grupo_opciones_opciones_estado,
    name="admin-grupo-opciones-opciones-estado-api",
),
```

### New handlers in `api_views.py`

**`admin_grupo_opciones_opciones_list`** — `@require_GET` `@admin_required`
```python
# Validates grupo_id exists → 404 if not
# Reads ?active=true|false|all (default: "true")
# Reads ?q= → filters codigo/nombre/valor__icontains
# Returns: { items: [{ id, codigo, nombre, valor, orden, activo, grupoId }] }
```

**`admin_grupo_opciones_opciones_crear`** — `@require_POST` `@_admin_principal_required`
```python
# Validates grupo_id exists → 404 if not
# Parses { codigo, nombre, valor, orden?, activo? }
# Pre-validate: SELECT WHERE grupo=grupo_id AND codigo=codigo → 400 if duplicate
# Auto-assigns orden = (max orden for group) + 1 if not provided
# OpcionCatalogo.objects.create(...)
# Returns 201: { item: { id, codigo, nombre, valor, orden, activo } }
```

**`admin_grupo_opciones_opciones_crear_multiples`** — `@require_POST` `@_admin_principal_required`
```python
# Wrapped in transaction.atomic()
# Validates grupo_id exists → 404 if not
# Iterates options array; pre-validates all codigos unique within group
# If any validation fails → IntegrityError → rollback entire transaction
# bulk_creates all options
# Returns 201: { items: [...] }
```

**`admin_grupo_opciones_opciones_actualizar`** — `@require_POST` `@_admin_principal_required`
```python
# Validates grupo and opcion exist → 404 if either not found
# Parses { nombre?, valor?, orden?, activo? } (partial update)
# Validates codigo uniqueness only if codigo would change (SELECT)
# Updates + save()
# Returns 200: { item: { id, codigo, nombre, valor, orden, activo } }
```

**`admin_grupo_opciones_opciones_estado`** — `@require_POST` `@_admin_principal_required`
```python
# Validates grupo and opcion exist → 404 if either not found
# Reads { active: bool } from body
# Sets instance.activo = active; saves
# Returns 200: { item: { id, codigo, nombre, valor, orden, activo } }
```

## Frontend Changes

### New API functions in `admin.ts`

```typescript
// GET /api/admin/catalogos/grupos-opciones/{grupoId}/opciones/?active=...&q=...
export function getGroupOptions(
  grupoId: number,
  params: { active?: 'true' | 'false' | 'all'; q?: string } = {},
) { ... }

// POST /api/admin/catalogos/grupos-opciones/{grupoId}/opciones/crear/
export function createGroupOption(grupoId: number, payload: GroupOptionPayload) { ... }

// POST /api/admin/catalogos/grupos-opciones/{grupoId}/opciones/crear-multiples/
export function createGroupOptionsBulk(grupoId: number, payloads: GroupOptionPayload[]) { ... }

// POST /api/admin/catalogos/grupos-opciones/{grupoId}/opciones/{opcionId}/actualizar/
export function updateGroupOption(grupoId: number, opcionId: number, payload: Partial<GroupOptionPayload>) { ... }

// POST /api/admin/catalogos/grupos-opciones/{grupoId}/opciones/{opcionId}/estado/
export function toggleGroupOptionState(grupoId: number, opcionId: number, active: boolean) { ... }
```

### OptionGroupModal component

The modal is added to `AdminCatalogsPage.tsx` as a local sub-component or extracted to `OptionGroupModal.tsx`. It is rendered inside `AdminOptionGroupsCatalogPage` only.

**Modal state:**
```typescript
interface OptionGroupModalState {
  isOpen: boolean
  grupoId: number | null
  grupoNombre: string
  // List
  options: OptionRow[]
  listLoading: boolean
  // Filters
  activeFilter: 'true' | 'false' | 'all'
  searchQuery: string
  // Sub-form mode
  subFormMode: 'closed' | 'create' | 'edit'
  editingOption: OptionRow | null
  formLoading: boolean
}
```

**Structure (JSX fragment):**
```tsx
<dialog open={isOpen} aria-label={`Opciones de ${grupoNombre}`}
        onClose={() => closeModal()}>
  {/* Header: grupoNombre + X close */}
  <header>
    <h2>{grupoNombre}</h2>
    <button onClick={closeModal} aria-label="Cerrar">✕</button>
  </header>

  {/* Filters */}
  <div className="option-modal-filters">
    <select value={activeFilter} onChange={...}
            aria-label="Filtrar por estado">
      <option value="true">Solo activas</option>
      <option value="false">Solo inactivas</option>
      <option value="all">Todas</option>
    </select>
    <input aria-label="Buscar opciones" value={searchQuery}
           onChange={...} placeholder="Buscar..." />
  </div>

  {/* Option list */}
  <ul role="list">
    {options.map(opt => (
      <li key={opt.id} className="option-row">
        <input type="checkbox" aria-label={`Seleccionar opción ${opt.nombre}`}
               disabled />
        <span>{opt.codigo}</span>
        <span>{opt.nombre}</span>
        <span>{opt.valor}</span>
        <StatusBadge tone={opt.activo ? 'success' : 'neutral'}>
          {opt.activo ? 'Activa' : 'Inactiva'}
        </StatusBadge>
        <button onClick={() => openEdit(opt)}>Editar</button>
        <button onClick={() => void toggleOption(opt)}>
          {opt.activo ? 'Desactivar' : 'Activar'}
        </button>
      </li>
    ))}
  </ul>

  {/* Sub-form (create or edit) */}
  {subFormMode !== 'closed' && (
    <form onSubmit={handleSubFormSubmit}>
      <input name="codigo" required disabled={subFormMode === 'edit'} />
      <input name="nombre" required />
      <input name="valor" required />
      <input name="orden" type="number" />
      <label><input name="activo" type="checkbox" /> Activo</label>
      <button type="submit">Guardar</button>
      <button type="button" onClick={closeSubForm}>Cancelar</button>
    </form>
  )}

  {/* Footer */}
  {subFormMode === 'closed' && (
    <button onClick={openCreate}>Agregar opción</button>
  )}
</dialog>
```

**Accessibility:** Focus is trapped inside the modal (using `useFocusTrap` or a library like `react-aria`). ESC and backdrop click call `closeModal()`. Every interactive element has an `aria-label`.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/config/api_views.py` | Modify | Add 5 new handlers for nested option endpoints; follow existing decorator + `json_response` patterns |
| `backend/config/api_urls.py` | Modify | Register 5 new URL paths under `catalogos/grupos-opciones/<grupo_id>/opciones/` |
| `backend/catalogs/tests.py` (or new) | Create | `test_grupo_opciones_opciones_api.py` — list/filters, create, bulk-create with rollback, update, toggle, 404s, auth |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Modify | Add 5 new API functions: `getGroupOptions`, `createGroupOption`, `createGroupOptionsBulk`, `updateGroupOption`, `toggleGroupOptionState` |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx` | Modify | `AdminOptionGroupsCatalogPage` renders `OptionGroupModal`; rows in the list get a third "Administrar opciones" button |
| `frontend/aesthetic-clinic/src/components/admin/OptionGroupModal.tsx` | Create | Modal component with option list, filter/search, inline sub-form, toggle, checkboxes (prepared) |
| `frontend/aesthetic-clinic/tests/e2e/admin_general.spec.ts` | Modify | Add E2E test: open modal, create option, edit, toggle, bulk-create, close |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Backend unit | `admin_grupo_opciones_opciones_list`: 404 if grupo missing, filter by active, search by q, ordered by orden | Django unittest in `test_grupo_opciones_opciones_api.py` |
| Backend unit | `admin_grupo_opciones_opciones_crear`: required fields, codigo unique per group (SELECT before save), auto-orden, 404 grupo missing | Django unittest |
| Backend unit | `admin_grupo_opciones_opciones_crear_multiples`: all succeed / atomic rollback on one bad item | Django unittest with `assertRaises` on transaction rollback |
| Backend unit | `admin_grupo_opciones_opciones_actualizar`: partial update, codigo change uniqueness check, 404s | Django unittest |
| Backend unit | `admin_grupo_opciones_opciones_estado`: flips activo, 404s | Django unittest |
| Backend unit | Auth: unauthenticated → 401, non-admin → 403 on all 5 endpoints | Django unittest with `@override_settings` |
| Backend unit | `_serialize_medical_config` integration: inactive option does NOT appear in ficha medical config | Extend existing test in `test_prospect_conversion.py` |
| Frontend E2E | Modal: open from grupos-opciones row, list renders, search narrows, create option, edit option, toggle option, close modal | Playwright `admin_general.spec.ts` |

## Migration / Rollout

No database migration required. `OpcionCatalogo` model already exists with all required fields. No schema changes, no data migrations, no feature flags. The new endpoints return 404 for non-existent `grupo_id` which is correct behavior.

The frontend modal is additive and only visible when an admin clicks "Administrar opciones" on a group row — no existing behavior changes.

## Open Questions

- [ ] Should the bulk-create endpoint accept a `codigo` prefix parameter so admin can create numbered options quickly (e.g., `codigo_prefix="VACUNA"` → creates `VACUNA-1`, `VACUNA-2`, ...)?
  **Recommendation**: Defer — adds parsing complexity; admin can paste a list if needed in a follow-up.
- [ ] Should the modal support keyboard navigation through the option list (↑↓ to move focus between rows)?
  **Recommendation**: Defer — the modal is primarily mouse-driven; Tab navigation through controls is sufficient for v1.
