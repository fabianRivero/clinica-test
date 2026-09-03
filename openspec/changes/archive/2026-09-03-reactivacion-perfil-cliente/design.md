# Design: reactivacion-perfil-cliente

## Technical Approach

Add a dedicated admin-only `PATCH /api/admin/clientes/<id>/perfil/` action on the existing `ClientesViewSet` that updates the live `Cliente` and its `Usuario` in a single `transaction.atomic()` block, dispatching each of the 13 contract fields by ownership (names/username/email/telefono → `Usuario`; ci/fechaNacimiento/nroHijos/ocupacion/direccionDomicilio/observacionesCliente → `Cliente`). Telefono syncs to both rows; fechaNacimiento writes to `Cliente.fecha_nacimiento` only. The new endpoint supersedes the modal's current path through `saveAdminClientReactivationUserStep` and is the canonical home for the 13 live profile fields.

The reactivation wizard step 1 becomes read-only for all profile fields except `observacionesCliente` (still editable, still goes through the draft). The reactivation finalize block in `prospect_conversion_views.py:1755-1778` stops overwriting live `Usuario`/`Cliente` rows from `datos_usuario`; it only writes `observacionesCliente` and the operation/medical/biometric/payment draft fields. The prospect conversion path (no `draft.cliente`) is untouched.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| Endpoint shape | PATCH on `ClientesViewSet` (`@action(detail=True, methods=["patch"], url_path="perfil")`) | New dedicated view function | Reuses existing router URL prefix and `AdminRequired` permission; consistent with `inactivar`/`migrar` patterns; one URL family per admin client resource |
| Branch authorization | Reuse `AdminRequired` + `_admin_client_queryset().filter(pk=pk)` (admin-only, no branch scoping) | Add branch scoping | Existing `_admin_client_queryset` does not scope by branch, and the spec/orchestrator notes confirm we only need admin-only access; introducing branch scoping here would diverge from `inactivar`/`migrar` without a defined branch policy |
| Serializer location | Append `AdminClientProfileWriteSerializer` to `backend/config/api/serializers/clientes.py` | New sibling module | The file already groups every client DRF serializer; co-locating keeps discoverability and avoids a one-class module |
| Password | Not accepted; serializer rejects unknown `password` field | Reuse `auth_views` password branch | Admin-driven password reset is out of scope (proposal §Out of Scope); mixing auth concerns into a profile endpoint would let admins set passwords without re-auth |
| Field ownership dispatch | Inside `serializer.update()` using `transaction.atomic` + `serializer.validated_data` lookups | Model `pre_save` signals | Explicit, traceable, and matches `auth_views.py:84-115` style; no cross-app signal coupling |
| `fechaNacimiento` ownership | Write to `Cliente.fecha_nacimiento` only | Mirror to `Usuario.fecha_nacimiento` | The orchestrator's fact sheet explicitly excludes `Usuario.fecha_nacimiento`; keeping that mirror avoided avoids surprising `_serialize_user` output |
| Frontend HTTP helper | New `patchJsonWithBody<T>(path, body)` in `apiClient.ts` that issues `method: 'PATCH'` | Add a `method` param to `requestJsonWithBody` | Existing `requestJsonWithBody` hardcodes `POST`; changing its signature is invasive and would force every caller to pass a method. A purpose-built helper is clearer and matches the `_WithBody` family pattern |
| Modal data flow | Open → `getAdminClientReactivation` already hydrates `userData`; save → `patchAdminClientProfile` | Add a separate GET for live profile | Reactivation endpoint's `userData` for `draft.cliente` is hydrated from the live snapshot via `_build_initial_client_user_data` (`prospect_conversion_views.py:198-215`) — same source of truth. A second live GET would duplicate serialization and add a roundtrip |
| Finalize policy | When `draft.cliente` exists, drop the entire `user`+`cliente` overwrite block; only apply `observacionesCliente` | Add explicit allow-list guard around each field | Removing the block is the smallest safe diff and proves "no overwrite" by absence; an allow-list inside an existing overwrite block leaves the door open to future regressions |
| Reactivation step 1 read-only enforcement | Conditional `disabled={isReactivation}` on every input except `observacionesCliente` | Hidden inputs / entirely different component | Keeps one component, one form, one submit handler; native `disabled` is supported by HTML + React, the values still POST so step-1 submit to `paso-1/` keeps working for the observation field |

## Sequence Diagram

```
User clicks "Ver perfil"
       │
       ▼
ClientProfileModal opens (isOpen=true, clientId set)
       │
       ▼
useEffect → getAdminClientReactivation(clientId)
       │
       ▼
GET /api/admin/clientes/<id>/reactivar/
       │
       ▼
Server: _serialize_draft(draft) → userData = _build_initial_client_user_data(cliente)
       │
       ▼
Modal hydrates form state from res.draft.userData (live snapshot)
       │
       ▼
User edits fields (all 13 still editable in modal)
       │
       ▼
Click "Guardar cambios" → handleSubmit
       │
       ▼
patchAdminClientProfile(clientId, form)
       │
       ▼
PATCH /api/admin/clientes/<id>/perfil/
       │
       ▼
ClientesViewSet.perfil(request, pk)
  ├─ permission check: AdminRequired (401/403)
  ├─ fetch: _admin_client_queryset().filter(pk=pk).first()
  │    └─ not found → 404
  ├─ validate: AdminClientProfileWriteSerializer(data=request.data, partial=True)
  │    └─ unknown field / ci collision / username collision → 400 with errors
  ├─ transaction.atomic:
  │    ├─ serializer.update() → dispatch fields:
  │    │    ├─ Usuario: primer_nombre, segundo_nombre, apellido_paterno,
  │    │    │          apellido_materno, username, email
  │    │    ├─ Usuario.telefono + Cliente.telefono (sync, both .save())
  │    │    └─ Cliente: fecha_nacimiento, ci, nro_hijos, direccion_domicilio,
  │    │                ocupacion, observaciones (alias observacionesCliente)
  │    └─ _build_initial_client_user_data(cliente) → response payload
  └─ 200 OK { "client": { ...13 camelCase fields + hasPassword:true... } }
       │
       ▼
Modal updates form state from response.client, closes
```

## Data Flow

```
                   ┌─────────────────────────────────────────────┐
                   │ ClientesViewSet.perfil (PATCH action)       │
                   │  ── transaction.atomic()                    │
                   │   ┌─────────────────────────────────────┐   │
                   │   │ AdminClientProfileWriteSerializer   │   │
                   │   │  .update(instance=cliente,          │   │
                   │   │           validated_data={...})     │   │
                   │   │                                     │   │
                   │   │  if "telefono" in vd:               │   │
                   │   │      user.telefono = vd["telefono"] │   │
                   │   │      cliente.telefono = vd[...]     │   │
                   │   │                                     │   │
                   │   │  user_fields = (                    │   │
                   │   │      "primerNombre","segundoNombre",│   │
                   │   │      "apellidoPaterno",             │   │
                   │   │      "apellidoMaterno",             │   │
                   │   │      "username","email")            │   │
                   │   │  cliente_fields = (                 │   │
                   │   │      "ci","fechaNacimiento",        │   │
                   │   │      "nroHijos","direccionDomicilio│   │
                   │   │      "ocupacion",                   │   │
                   │   │      "observacionesCliente")        │   │
                   │   └─────────────────────────────────────┘   │
                   └────────────┬─────────────┬─────────────────┘
                                │             │
                       Usuario.save()   Cliente.save()
                                │             │
                                └──────┬──────┘
                                       ▼
                       _build_initial_client_user_data(cliente)
                                       │
                                       ▼
                          { "client": { ...13 camelCase... } }
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/config/api/serializers/clientes.py` | Modify | Append `AdminClientProfileWriteSerializer` with 13 fields (camelCase), partial updates, `validate_username`/`validate_ci` excluding self, `validate_fechaNacimiento` required, no `password`; implement `update(cliente, validated_data)` with field-dispatch table. |
| `backend/config/api/viewsets/clientes.py` | Modify | Add `@action(detail=True, methods=["patch"], url_path="perfil")` on `ClientesViewSet`; reuse `_admin_client_queryset` + `AdminRequired`; wrap in `transaction.atomic`; return `{ "client": _build_initial_client_user_data(cliente) }`. |
| `backend/config/api_urls.py` | Modify | No change required — DRF router already exposes `ClientesViewSet` under `clientes/<pk>/`; the new action registers `clientes/<pk>/perfil/`. Verify post-registration that `clientes_router` resolves the action. |
| `backend/config/prospect_conversion_views.py` | Modify | In `admin_prospect_conversion_finalize`, lines 1755-1778: when `draft.cliente` is set, remove the entire user+cliente overwrite block; replace with a single line `cliente.observaciones = user_data.get("observacionesCliente", "")` and `cliente.save(update_fields=["observaciones", "updated_at"])`. Operation/medical/biometric/payment paths unchanged. |
| `backend/tests/suspension/test_conversion_split.py` | Modify | Add regression assertion that reactivation finalize leaves live profile data unchanged when step 1 was edited. |
| `backend/billing/tests/test_conversion_first_payment.py` | Modify | Add live-profile isolation assertion for reactivation finalize path; preserve existing payment coverage. |
| `backend/tests/test_admin_client_profile_edit.py` | Create | New test module covering happy path, partial update, telefono cascade, fechaNacimiento Cliente-only, username collision, ci collision, password rejected, unknown field rejected, non-admin 403, cross-branch (allowed today), finalize non-overwrite. |
| `frontend/aesthetic-clinic/src/services/api/apiClient.ts` | Modify | Add `patchJsonWithBody<T>(path, body)` helper that issues `method: 'PATCH'`, reuses CSRF + branch header + `parseErrorResponse`. |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Modify | Add `patchAdminClientProfile(clientId, payload)` typed client; preserve existing `saveAdminClientReactivationUserStep` for the wizard draft endpoint. |
| `frontend/aesthetic-clinic/src/types/prospectConversion.ts` | Modify | (Optional) export `AdminClientProfilePayload` type alias over `ProspectConversionUserData` without `password`. |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientProfileModal.tsx` | Modify | Replace `saveAdminClientReactivationUserStep` with `patchAdminClientProfile`; keep `getAdminClientReactivation` for hydration; on success, update local form state from `res.client` (instead of `res.draft.userData`) before closing. |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx` | Modify | Add `disabled={isReactivation}` to every profile input except `observacionesCliente` (and except the password block which is already conditional). |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts` | Modify | In the reactivation branch of the load effect (`response = initializeAdminClientReactivation(clientId)`), reset `userForm` to live snapshot via `_build_initial_client_user_data` semantics — already returned by `res.draft.userData`, so no code change is strictly required; document that step-1 PATCH keeps writing only `observacionesCliente` to the draft. |

## Interfaces / Contracts

### Backend: `PATCH /api/admin/clientes/<int:pk>/perfil/`

**Auth**: `AdminRequired` (DRF permission) — 401 unauthenticated, 403 non-admin / inactive branch.

**Request body** (all fields optional; partial update):

```json
{
  "primerNombre": "string",
  "segundoNombre": "string",
  "apellidoPaterno": "string",
  "apellidoMaterno": "string",
  "ci": "string",
  "username": "string",
  "email": "user@example.com",
  "telefono": "string",
  "fechaNacimiento": "YYYY-MM-DD",
  "nroHijos": 0,
  "ocupacion": "string",
  "direccionDomicilio": "string",
  "observacionesCliente": "string"
}
```

`password` and any field outside the 13-field whitelist are rejected with 400 (an explicit validator raises `"password is not editable through this endpoint"` for `password`).

**Response (200 OK)** — matches `_build_initial_client_user_data(cliente)` shape exactly so the modal can hydrate from one source of truth:

```json
{
  "client": {
    "primerNombre": "...",
    "segundoNombre": "...",
    "apellidoPaterno": "...",
    "apellidoMaterno": "...",
    "username": "...",
    "email": "...",
    "telefono": "...",
    "ci": "...",
    "fechaNacimiento": "YYYY-MM-DD",
    "nroHijos": 0,
    "direccionDomicilio": "...",
    "ocupacion": "...",
    "observacionesCliente": "...",
    "hasPassword": true
  }
}
```

**Error responses**:

| Status | Trigger |
|--------|---------|
| 400 | Validation error: unknown field, `password` rejected, `ci` collision, `username` collision, missing required field (e.g. malformed `fechaNacimiento`) |
| 401 | Not authenticated |
| 403 | Authenticated but not admin (or admin's branch inactive) |
| 404 | Client `pk` not found (cross-branch admins get 404 today because `_admin_client_queryset().filter(pk=pk)` returns `None` only if the row is gone — branch scoping is not enforced; this matches existing `migrar`/`inactivar` behavior) |

### Backend: `AdminClientProfileWriteSerializer.update()`

```python
def update(self, instance, validated_data):
    user = instance.usuario  # OneToOne, always present
    USER_FIELDS = {
        "primerNombre": "primer_nombre",
        "segundoNombre": "segundo_nombre",
        "apellidoPaterno": "apellido_paterno",
        "apellidoMaterno": "apellido_materno",
        "username": "username",
        "email": "email",
    }
    for camel, snake in USER_FIELDS.items():
        if camel in validated_data:
            setattr(user, snake, validated_data[camel])

    if "telefono" in validated_data:
        value = validated_data["telefono"] or ""
        user.telefono = value
        instance.telefono = value

    CLIENTE_FIELDS = {
        "ci": "ci",
        "fechaNacimiento": "fecha_nacimiento",
        "nroHijos": "nro_hijos",
        "direccionDomicilio": "direccion_domicilio",
        "ocupacion": "ocupacion",
        "observacionesCliente": "observaciones",
    }
    for camel, snake in CLIENTE_FIELDS.items():
        if camel in validated_data:
            setattr(instance, snake, validated_data[camel])

    user.save()
    instance.save()
    return instance
```

Wrapped in `transaction.atomic` at the view level. `validate_username` and `validate_ci` exclude the current row (`pk=instance.pk` / `usuario.pk`).

### Frontend: API client

```typescript
// frontend/aesthetic-clinic/src/services/api/admin.ts
export type AdminClientProfilePayload = {
  primerNombre?: string
  segundoNombre?: string
  apellidoPaterno?: string
  apellidoMaterno?: string
  ci?: string
  username?: string
  email?: string
  telefono?: string
  fechaNacimiento?: string
  nroHijos?: number
  ocupacion?: string
  direccionDomicilio?: string
  observacionesCliente?: string
}

export function patchAdminClientProfile(
  clientId: string,
  payload: AdminClientProfilePayload,
) {
  return patchJsonWithBody<{ client: AdminClientProfilePayload & { hasPassword: boolean } }>(
    `/api/admin/clientes/${clientId}/perfil/`,
    payload,
  )
}
```

```typescript
// frontend/aesthetic-clinic/src/services/api/apiClient.ts (new helper)
export async function patchJsonWithBody<T>(path: string, body: unknown): Promise<T> {
  const csrfToken = await ensureCsrfCookie()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PATCH',
    credentials: 'include',
    headers: buildHeaders({
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    }),
    body: JSON.stringify(body),
  })
  const responseBody = (await response.json().catch(() => null)) as
    | { detail?: string; errors?: Record<string, string> }
    | null
  if (!response.ok) {
    parseErrorResponse(response, path, responseBody)
  }
  return responseBody as T
}
```

### Frontend: `ClientProfileModal` (key changes)

```typescript
// On save success: hydrate from response.client, NOT response.draft.userData
const response = await patchAdminClientProfile(clientId, form)
setForm(response.client)
onClose()

// Hydration stays on getAdminClientReactivation because it returns the live
// snapshot via _build_initial_client_user_data(draft.cliente).
useEffect(() => {
  if (isOpen && clientId) {
    setIsLoading(true)
    getAdminClientReactivation(clientId)
      .then((res) => setForm(res.draft.userData))
      .catch(() => setError('No se pudieron cargar los datos del cliente'))
      .finally(() => setIsLoading(false))
  }
}, [isOpen, clientId])
```

Password field was never rendered; we do not add it. The 13 fields and 1 textarea stay as today.

### Frontend: `ConversionStepUser` (key changes)

```tsx
// Every profile input gains disabled={isReactivation}; observacionesCliente stays editable.
<label className="field">
  <span>Primer nombre <abbr title="obligatorio" className="required-mark">*</abbr></span>
  <input
    className="input"
    name="primerNombre"
    value={userForm.primerNombre}
    onChange={onUserChange}
    onBlur={onNameBlur}
    disabled={isReactivation}
  />
</label>
<label className="field field--full">
  <span>Observaciones del cliente</span>
  <textarea
    className="input textarea"
    name="observacionesCliente"
    rows={4}
    value={userForm.observacionesCliente}
    onChange={onUserChange}
    // intentionally NOT disabled — observation flows through draft + finalize
  />
</label>
```

The submit path (`onSubmit` → `saveAdminClientReactivationUserStep`) is untouched: it POSTs the entire `userForm` to the draft endpoint, but since the inputs are `disabled`, the browser still POSTs the same values (or empty strings if `userForm` was initialized from the live snapshot and never edited). `paso-1` accepts the payload and stores it in `draft.datos_usuario`; finalize will only consume `observacionesCliente` from that payload after this change.

## Defensive Finalize Diff (illustrative)

`backend/config/prospect_conversion_views.py:1755-1778` — before:

```python
else:
    # Actualizacion de cliente existente (reactivacion)
    cliente = draft.cliente
    user = cliente.usuario

    user.primer_nombre = user_data["primerNombre"]
    user.segundo_nombre = user_data.get("segundoNombre", "")
    user.apellido_paterno = user_data["apellidoPaterno"]
    user.apellido_materno = user_data.get("apellidoMaterno", "")
    user.email = user_data.get("email", "")
    if user_data.get("passwordHash"):
        user.password = user_data["passwordHash"]
    user.save()

    cliente.ci = user_data.get("ci", "")
    cliente.fecha_nacimiento = date.fromisoformat(user_data["fechaNacimiento"])
    cliente.nro_hijos = int(user_data.get("nroHijos") or 0)
    cliente.direccion_domicilio = user_data.get("direccionDomicilio", "")
    cliente.telefono = user_data.get("telefono", "")
    cliente.ocupacion = user_data.get("ocupacion", "")
    cliente.observaciones = user_data.get("observacionesCliente", "")
    cliente.save()
```

After:

```python
else:
    # Reactivacion: el perfil del cliente NO se sobrescribe desde el borrador.
    # Las ediciones de identidad se canalizan por PATCH /api/admin/clientes/<id>/perfil/.
    # Solo se aplica la anotacion clinica del procedimiento.
    cliente = draft.cliente
    if user_data.get("observacionesCliente") is not None:
        cliente.observaciones = user_data.get("observacionesCliente") or ""
        cliente.save(update_fields=["observaciones", "updated_at"])
```

The `if draft.prospecto:` branch (lines 1711-1754) is untouched — prospect conversion still creates `Usuario` and `Cliente` from `user_data` exactly as today.

## Migration / Existing Drafts

No data migration required. Pre-existing reactive drafts in the wild may still carry stale identity edits inside `ProspectoConversionBorrador.datos_usuario`; after this change, those values will no longer reach live `Usuario`/`Cliente` rows on finalize. Cleanup is an operator decision (out of scope per proposal §Out of Scope) — the safest path is to discard stale drafts via the existing `cancelar` endpoint or, for drafts in active use, leave them as drafts and ask the admin to apply any intended identity edits through the new modal/endpoint before finalizing.

## Testing Strategy

### Backend (Django TestCase, session auth via `Client`)

| Case | Description |
|------|-------------|
| Happy path — single field | Admin PATCH with `{"primerNombre": "Maria"}` updates `Usuario.primer_nombre`, leaves everything else untouched, returns 200 with full `client` payload |
| Happy path — telefono cascades | PATCH `{"telefono": "70000000"}` writes both `Usuario.telefono` and `Cliente.telefono` |
| Happy path — fechaNacimiento Cliente only | PATCH `{"fechaNacimiento": "1990-01-15"}` writes `Cliente.fecha_nacimiento`, `Usuario.fecha_nacimiento` untouched |
| Happy path — multiple fields | PATCH with names + ci + username + email updates all six in one transaction |
| Partial update preserves omitted | PATCH `{"email": "x"}` leaves `telefono`, `ci`, etc. unchanged on both rows |
| Username collision | PATCH `{"username": "taken"}` where another `Usuario` already owns it → 400, live row unchanged |
| CI collision | PATCH `{"ci": "1234567"}` where another `Cliente` already owns it → 400, live row unchanged |
| Password rejected | PATCH `{"password": "x"}` → 400 with `"password is not editable through this endpoint"`; `set_password` not invoked |
| Unknown field rejected | PATCH `{"invalid": "x"}` → 400, no row modified |
| Non-admin 403 | Authenticated `CLIENTE`/`ESPECIALISTA` user → 403 |
| Unauthenticated 401/403 | No session → 401 (or 403, matches `AdminRequired`) |
| Cross-branch admin (today allowed) | Admin from branch A PATCH on branch B's client → 200 (matches current `migrar`/`inactivar` behavior; documented in Open Questions) |
| Finalize non-overwrite (reactivation) | Wizard finalize after editing step 1 of an in-flight reactivation leaves live profile fields unchanged; only operation/medical/biometric/payment + `observacionesCliente` are applied |
| Prospect conversion finalize unchanged | Wizard finalize of a prospect conversion still creates `Usuario`+`Cliente` from `user_data` (regression guard) |

### Frontend

No unit test framework installed (only `playwright` per `package.json`). One optional Playwright e2e under `frontend/aesthetic-clinic/tests/`:

- Login as admin → `/cms/clientes/<id>/` → click "Ver perfil" → edit `telefono` and `email` → save → reload page → assert updated values are persisted via GET on the reactivation endpoint.

Manual smoke checklist documented in the change README:
- Open modal, save with no changes → 200, no DB write.
- Open modal in reactivation wizard → step 1 fields disabled; only `observacionesCliente` editable; submit still works.
- Reactivate an existing client → confirm `Usuario.primer_nombre` unchanged after finalize.

## Threat Matrix

`N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.`

This change only modifies a Django DRF endpoint, a serializer, and React UI state.

## Risks & Mitigations

(Summarized; see proposal §Risks for the full matrix.)

- **Telefono drift** between `Usuario` and `Cliente` — mitigated by single-transaction sync in `update()`.
- **Existing clients with invalid data** — PATCH is partial; only explicit validator rules reject.
- **Cross-branch authorization gap** — no branch scoping today; matches existing `migrar`/`inactivar`. Documented as Open Question below.
- **Password exposure** — serializer has no `password` field; `validate()` raises on it; regression test included.
- **Stale reactive drafts** — finalize policy neutralizes the corruption risk going forward; cleanup is operator decision (out of scope).

## Rollback

See proposal §Rollback Plan: revert `ClientesViewSet` action, `AdminClientProfileWriteSerializer`, finalize block, modal rewire, wizard `disabled` flags, and `patchJsonWithBody` helper. Step 4 of the rollback (re-enabling the live-overwrite block) re-introduces Bug A and must not be executed while in-flight reactive drafts exist.

## Open Questions

- [ ] Cross-branch authorization policy is undocumented; the spec mandates rejection but the codebase never enforced it. Proposal/spec leave this for a follow-up; design follows the existing pattern (no branch scoping) and adds a regression test that asserts today's behavior. Confirm with product before tightening.
