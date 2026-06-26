# Design: catalog-list-search-filter

## Technical Approach

Add server-side title search (`?q=`) and active-state filter (`?active=`) to the existing catalog list endpoint `GET /api/admin/catalogos/<slug>/`. The backend reads query params in `admin_catalogo_detalle` and threads them through `_catalog_page_data`, applying `.filter()` on the relevant title field per catalog. The frontend adds a debounced search input and a `<select>` filter to `CatalogPage`, passing both to the API call via `getAdminCatalogDetail(catalogKey, { q, active })`. The Create button fix removes `showCreateAction={false}` from all five wrappers so the button appears by default.

## Architecture Decisions

### Decision: Server-side filter, not client-side

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Client-side (filter already-loaded array) | Zero backend changes, but filter state lost on reload, feels disconnected | Rejected |
| Server-side via `?q=` + `?active=` query params | Single source of truth in DB, filter state survives reload, consistent with REST | **Chosen** |

### Decision: Debounce 300ms

| Option | Tradeoff | Decision |
|--------|----------|----------|
| 150ms | May fire on incomplete words for fast typers | Not chosen |
| 500ms | More network-efficient but feels sluggish | Not chosen |
| **300ms** | Balances keystroke responsiveness with not flooding the API | **Chosen** |

### Decision: Reuse `CatalogEditorForm`, not a separate Create form

`CatalogEditorForm` already handles both create and edit (keyed by `editingItem ? \`edit-${id}\` : \`create-${version}\``). A second form would duplicate field definitions and validation logic. **Follow existing pattern.**

### Decision: Single shared `CatalogPage`, not per-catalog components

All five catalogs share the same API contract, same CRUD endpoints, same UI layout. One component with `catalogKey` as a prop eliminates code duplication and ensures consistent UX. **Follow existing pattern.**

## Data Flow

```
User types "botox" → useDebounce(300ms) fires
  → getAdminCatalogDetail("todos-los-servicios", { q: "botox", active: "true" })
    → GET /api/admin/catalogos/todos-los-servicios/?q=botox&active=true
      → admin_catalogo_detalle reads q + active
        → _catalog_page_data("todos-los-servicios", q="botox", active="true")
          → queryset.filter(Q(tipo_servicio__tipo__icontains="botox") | Q(proc_estetico__proceso__icontains="botox"))
          → queryset.filter(activo=True)
          → items serialized → json_response
      → React renders filtered items
    → list re-renders
```

## Backend Design

### `admin_catalogo_detalle` (BEFORE / AFTER)

```python
# BEFORE (lines 3987–3992)
def admin_catalogo_detalle(request, catalog_key):
    try:
        data = _catalog_page_data(catalog_key)
    except KeyError:
        return json_response({"detail": "El catalogo solicitado no existe."}, status=404)
    return json_response(data)

# AFTER
def admin_catalogo_detalle(request, catalog_key):
    q = request.GET.get("q", "")
    active = request.GET.get("active", "all")   # "true" | "false" | "all"
    try:
        data = _catalog_page_data(catalog_key, q=q, active=active)
    except KeyError:
        return json_response({"detail": "El catalogo solicitado no existe."}, status=404)
    return json_response(data)
```

### `_catalog_page_data` signature and filter insertions

**Signature change**: `_catalog_page_data(catalog_key)` → `_catalog_page_data(catalog_key, q="", active="all")`

#### `todos-los-servicios` — BEFORE
```python
queryset = (
    ServicioConfig.objects.select_related(...).order_by(...)
)
```
#### `todos-los-servicios` — AFTER
```python
from django.db.models import Q

queryset = ServicioConfig.objects.select_related(
    "tipo_servicio", "proc_estetico", "proc_estetico__tipo_p_estetico",
)
if q:
    queryset = queryset.filter(
        Q(tipo_servicio__tipo__icontains=q) | Q(proc_estetico__proceso__icontains=q)
    )
if active == "true":
    queryset = queryset.filter(activo=True)
elif active == "false":
    queryset = queryset.filter(activo=False)
queryset = queryset.order_by("tipo_servicio__tipo", "proc_estetico__proceso", "pk")
```

#### `procedimientos-esteticos` — filter insertion
```python
queryset = ProcEstetico.objects.select_related("tipo_p_estetico")
if q:
    queryset = queryset.filter(proceso__icontains=q)
if active == "true":
    queryset = queryset.filter(activo=True)
elif active == "false":
    queryset = queryset.filter(activo=False)
queryset = queryset.order_by("orden", "proceso")
```

#### `tipos-servicio` — filter insertion
```python
queryset = TipoServicio.objects.all()
if q:
    queryset = queryset.filter(tipo__icontains=q)
if active == "true":
    queryset = queryset.filter(activo=True)
elif active == "false":
    queryset = queryset.filter(activo=False)
queryset = queryset.order_by("orden", "tipo")
```

#### `especialidades` — filter insertion
```python
queryset = Especialidad.objects.all()
if q:
    queryset = queryset.filter(nombre__icontains=q)
if active == "true":
    queryset = queryset.filter(activo=True)
elif active == "false":
    queryset = queryset.filter(activo=False)
queryset = queryset.order_by("orden", "nombre")
```

#### `categorias-gasto` — filter insertion
```python
queryset = _expense_categories_queryset()
if q:
    queryset = queryset.filter(nombre__icontains=q)
if active == "true":
    queryset = queryset.filter(activo=True)
elif active == "false":
    queryset = queryset.filter(activo=False)
queryset = queryset.order_by("nombre")   # preserve original order
```

**Note**: `campos-ficha`, `patologias-cutaneas`, `grupos-opciones` are out of scope and receive no changes.

## Frontend Design

### `getAdminCatalogDetail` signature

```typescript
// BEFORE (admin.ts:340)
export function getAdminCatalogDetail(catalogKey: AdminCatalogKey) {
  return requestJson<AdminCatalogDetailResponse>(`/api/admin/catalogos/${catalogKey}/`)
}

// AFTER
interface CatalogListParams {
  q?: string
  active?: 'true' | 'false' | 'all'
}

export function getAdminCatalogDetail(
  catalogKey: AdminCatalogKey,
  params: CatalogListParams = {},
) {
  const qs = new URLSearchParams()
  if (params.q) qs.set("q", params.q)
  if (params.active && params.active !== "all") qs.set("active", params.active)
  const query = qs.toString()
  return requestJson<AdminCatalogDetailResponse>(
    `/api/admin/catalogos/${catalogKey}/${query ? `?${query}` : ""}`
  )
}
```

### `useDebounce` hook

No existing hook found. Create `frontend/aesthetic-clinic/src/hooks/useDebounce.ts`:

```typescript
import { useState, useEffect } from "react"

export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debouncedValue
}
```

### `CatalogPage` state shape

```typescript
function CatalogPage({ catalogKey, showCreateAction = true }: Props) {
  const [searchQuery, setSearchQuery] = useState("")
  const [activeFilter, setActiveFilter] = useState<'all' | 'true' | 'false'>('all')
  const debouncedQuery = useDebounce(searchQuery, 300)

  const loader = useMemo(
    () => () => getAdminCatalogDetail(catalogKey, {
      q: debouncedQuery,
      active: activeFilter,
    }),
    [catalogKey, debouncedQuery, activeFilter]
  )
  const { data, isLoading, error, reload } = useApiResource(loader)
  // ...
}
```

### Search + filter UI markup (inside `PageHeader` area, before the list `SectionCard`)

```tsx
<div className="catalog-admin-toolbar">
  <input
    type="search"
    placeholder="Buscar por título..."
    value={searchQuery}
    onChange={(e) => setSearchQuery(e.target.value)}
    aria-label="Buscar registros"
  />
  <select
    value={activeFilter}
    onChange={(e) => setActiveFilter(e.target.value as typeof activeFilter)}
    aria-label="Filtrar por estado"
  >
    <option value="all">Todos</option>
    <option value="true">Activos</option>
    <option value="false">Inactivos</option>
  </select>
</div>
```

### Create button visibility — wrapper changes

Remove `showCreateAction={false}` from all four wrappers. `CatalogEditorForm` is conditionally rendered when `showCreateAction || editingItem`.

```tsx
// BEFORE (4 wrappers)
export function AdminProceduresCatalogPage() {
  return <CatalogPage catalogKey="procedimientos-esteticos" showCreateAction={false} />
}

// AFTER
export function AdminProceduresCatalogPage() {
  return <CatalogPage catalogKey="procedimientos-esteticos" />
}
// (default showCreateAction=true applies)
```

## Sequence Diagram

```
User                    Frontend                   Backend                     DB
 │                         │                          │                          │
 │  types "botox"          │                          │                          │
 │────────────────────────>│                          │                          │
 │                         │  (300ms debounce fires)  │                          │
 │                         │  GET /api/admin/catalogos/│                          │
 │                         │  todos-los-servicios/    │                          │
 │                         │  ?q=botox&active=true    │                          │
 │                         │────────────────────────>│                          │
 │                         │                          │  SELECT ... WHERE          │
 │                         │                          │  (tipo_servicio__tipo     │
 │                         │                          │   ILIKE '%botox%' OR      │
 │                         │                          │   proc_estetico__proceso  │
 │                         │                          │   ILIKE '%botox%')        │
 │                         │                          │  AND activo = True        │
 │                         │                          │────────────────────────>│
 │                         │                          │<────────────────────────│
 │                         │                          │  filtered rows + counts   │
 │                         │<─────────────────────────│                          │
 │                         │  JSON { catalog, items }  │                          │
 │<────────────────────────│                          │                          │
 │  re-renders list        │                          │                          │
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/config/api_views.py` | Modify | `admin_catalogo_detalle` reads `?q=` and `?active=`; `_catalog_page_data` accepts them and applies `.filter()` per catalog |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Modify | `getAdminCatalogDetail` accepts optional `CatalogListParams`; builds query string |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx` | Modify | Add `searchQuery`/`activeFilter` state, `useDebounce`, search+filter UI; remove 4× `showCreateAction={false}` |
| `frontend/aesthetic-clinic/src/hooks/useDebounce.ts` | Create | Debounce hook for 300ms search delay |
| `backend/catalogs/tests.py` | Modify | Add 7 Django unittest cases (5 happy-path + 1 search + 1 filter) |
| `frontend/aesthetic-clinic/tests/e2e/admin_general.spec.ts` | Modify | Add 5 Playwright E2E cases (1 per catalog: create → search → deactivate → filter) |

## Testing Strategy

| Layer | What | How |
|-------|------|-----|
| Backend unit | Each catalog endpoint returns correct filtered rows | Django unittest — 1 happy-path test per catalog + 1 search test + 1 active-filter test |
| Frontend E2E | Full flow per catalog: create item → search → deactivate → filter to inactive | Playwright — 5 specs (1 per catalog) |
| Lint/Type | New hook and modified function signatures | `npm run lint` + `npx tsc --noEmit` |

## Migration / Rollback

**No database migration required.** All changes are additive:

- **Rollback (backend)**: Revert `admin_catalogo_detalle` to the original 5-line form; revert `_catalog_page_data` signature and remove the three `.filter()` blocks from each catalog branch.
- **Rollback (frontend)**: Remove `searchQuery`, `activeFilter`, `useDebounce` from `CatalogPage`; remove the search-bar markup; restore `showCreateAction={false}` on the four wrappers; revert `getAdminCatalogDetail` to the original 2-arg form.
- **Verification**: existing catalog list views resume pre-change behavior — all items returned, Create button hidden on the four wrappers.

## Open Questions

- [ ] None. All decisions are locked via the orchestrator's brief.
