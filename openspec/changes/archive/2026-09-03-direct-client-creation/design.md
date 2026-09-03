# Design: direct-client-creation

## Threat Matrix

| Threat Row | Status | Reason |
|---|---|---|
| Shell command / subprocess execution | N/A | Change touches Django URL routing and React Router only. No shell/subprocess usage introduced. |
| VCS / PR automation | N/A | No GitHub Actions, gh CLI, or git automation added. |
| Executable-file classification | N/A | No new executables, hooks, or scripts. |
| Django URL routing | Touched (mitigated) | New literal route `clientes/directo/<step>/` cannot collide with `<int:id>` converter; ordering verified in `api_urls.py:200-293`. |
| React Router routing | Touched (mitigated) | New path `clientes/nuevo` is a literal segment; no params. |

**Threat Matrix is N/A on all risk rows.** All rows touching this change are explicitly covered by the routing-precedence decision below.

## Architecture Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | URL family for direct mode | Dedicated `clientes/directo/<step>/` | Rejected `/prospectos/<id>/<step>/` (requires fake prospect). Rejected `/clientes/<id>/reactivar/<step>/` (overloads reactivation semantics — "reactivate" implies existing client). Dedicated family maps cleanly to proposal §Approach 1 and spec §Direct Client Entry Point. |
| 2 | Wizard mode enum | `mode: 'prospect' \| 'reactivation' \| 'direct'` | Replaces `isReactivation: boolean`. Open-closed extension: existing prospect/reactivation call sites unchanged, third value additive. Derived on frontend from URL params; on backend from draft FK state. |
| 3 | Finalize dispatch order | `if draft.prospecto → elif draft.cliente → else (direct)` | Preserves byte-for-byte existing branches. Direct branch is a strict superset of the prospect branch (create user+cliente) with two side-effects skipped (`marcar_como_convertido`, prospect biometric migration). Ordering chosen so the more-specific reactivation branch keeps its existing `elif` position and is not re-tested by the new branch. |
| 4 | URL routing precedence | `<int:id>` converter vs literal `directo` | Django URL resolution: `<int:id>` requires integer match; literal `directo` never matches `int`. Place `clientes/directo/<step>/` BEFORE `clientes/<int:id>/reactivar/<step>/` to ensure deterministic resolution and future-proof against a hypothetical `/clientes/<int:id>/directo/...` route. |
| 5 | Frontend mode detection | Derived from URL params (`useParams`) | `prospectId` → `prospect`; `clientId` → `reactivation`; neither → `direct`. Single source of truth (URL), no extra state, no query string overloading. React Router provides all three params natively. |
| 6 | Admin scope branch resolution for direct mode | `_get_branch_for_scope_check(request) or get_user_branch(request)` | Direct mode has no `prospecto.sucursal_registro` to fall back to. The design originally specified `_get_branch_for_scope_check(request)` alone, but that helper returns `None` for principal admins, breaking the entire finalize flow. Implementation now chains the existing `get_user_branch(request)` fallback (mirroring the same pattern the prospect branch uses) so principal admins resolve via session/scope branch. Documented inline at the call site. |

## Data Flow

```
Admin               AdminClientsPage        useConversionWizard        Backend (Django)            DB
  |                       |                        |                          |                        |
  | click "Crear cliente   |                        |                          |                        |
  | directo"              |                        |                          |                        |
  |---------------------->|                        |                          |                        |
  |                       | navigate /cms/clientes/nuevo                       |                        |
  |                       |----------------------->|                          |                        |
  |                       |                        | mount, mode='direct'      |                        |
  |                       |                        | initializeDirectClient   |                        |
  |                       |                        | Conversion()             |                        |
  |                       |                        |------------------------->|                        |
  |                       |                        |                          | POST /api/admin/clientes|
  |                       |                        |                          |   /directo/initialize/  |
  |                       |                        |                          | create ProspectoConver- |
  |                       |                        |                          | sionBorrador(null,null, |
  |                       |                        |                          | iniciado_por=admin)     |
  |                       |                        |                          |----------------------->|
  |                       |                        |                          |                        | INSERT (null,null)
  |                       |                        |                          |<-----------------------|
  |                       |                        |                          | _admin_conversion_detail|
  |                       |                        |                          |   (prospect=null,       |
  |                       |                        |                          |    client=null)         |
  |                       |                        |<-------------------------|                        |
  |                       |                        | { draftId, prospect:null,|                        |
  |                       |                        |   client:null }          |                        |
  |                       |<-----------------------|                          |                        |
  | <-- render wizard ----|                        |                          |                        |
  |                       |                        |                          |                        |
  | step 1 (user) PATCH draft        ────────────────────────────────────────>| PATCH /directo/<id>/user/
  |                       |                        |                          | _validate_user_step    |
  |                       |                        |                          |   (CI/username unique) |
  |                       |                        |                          |----------------------->|
  |                       |                        |                          |<-----------------------|
  |                       |                        |<-------------------------|                        |
  |                       |                        |                          |                        |
  | step 2-5 PATCH ... (operation, medical, biometric, payment) — identical to prospect flow
  |                       |                        |                          |                        |
  | click Finalizar       |                        |                          |                        |
  |---------------------->|---------------------->|                          |                        |
  |                       |                        | finalize()               |                        |
  |                       |                        |------------------------->|                        |
  |                       |                        |                          | POST finalize           |
  |                       |                        |                          | BEGIN TRANSACTION       |
  |                       |                        |                          | if draft.prospecto: ... |
  |                       |                        |                          | elif draft.cliente: ... |
  |                       |                        |                          | else:  # DIRECT          |
  |                       |                        |                          |   create Usuario        |
  |                       |                        |                          |   create Cliente        |
  |                       |                        |                          |   stamp biometric       |
  |                       |                        |                          |   (no marcar_como_      |
  |                       |                        |                          |    convertido)          |
  |                       |                        |                          |----------------------->|
  |                       |                        |                          |<-----------------------|
  |                       |                        |<-------------------------| { cliente_codigo }      |
  |                       |                        | navigate /cms/clientes   | COMMIT                  |
  | <-- see new row -------|                        |                          |                        |
```

## File Changes

| File | Action | Purpose |
|---|---|---|
| `backend/config/prospect_conversion_views.py` | Modify | `_get_draft_convertible(direct_id=...)`; third `else` branch in `admin_prospect_conversion_finalize`; new `admin_direct_client_initialize` view. |
| `backend/config/api_urls.py` | Modify | Add `clientes/directo/<step>/` URL family BEFORE `clientes/<int:id>/reactivar/<step>/`. |
| `frontend/aesthetic-clinic/src/App.tsx` | Modify | New route `path="clientes/nuevo"` → `<AdminProspectConvertPage />`. |
| `frontend/aesthetic-clinic/src/pages/admin/AdminClientsPage.tsx` | Modify | `PageHeader.actions`: primary `Crear cliente directo` → `navigate('/cms/clientes/nuevo')`. |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/AdminProspectConvertPage.tsx` | Modify | `mode` enum replaces `isReactivation`; summary card hidden when `data.prospect == null`. |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts` | Modify | `mode='direct'` branch calls `initializeDirectClientConversion()`. |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Modify | Add `initializeDirectClientConversion(): Promise<ProspectConversionResponse>`. |

## Interfaces / Contracts

```python
# backend/config/prospect_conversion_views.py

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_direct_client_initialize(request):
    """Create empty ProspectoConversionBorrador(prospecto=None, cliente=None)
    and return _admin_conversion_detail payload."""

def _get_draft_convertible(request, prospecto_id=None, cliente_id=None, direct_id=None):
    """Extended signature: direct_id creates a (null,null) draft when called
    from the direct entry point. Existing two-arg callsites unchanged."""

# Branch added to admin_prospect_conversion_finalize (after elif draft.cliente):
else:
    # Direct creation: create Usuario + Cliente (same as prospect branch)
    # but skip marcar_como_convertido and prospect biometric migration.
    usuario = Usuario.objects.create_user(
        username=..., password=..., rol='CLIENTE', is_active=True,
        primer_nombre=..., apellido_paterno=...,
    )
    cliente = Cliente.objects.create(
        usuario=usuario,
        sucursal_origen=_get_branch_for_scope_check(request),
        fecha_nacimiento=...,
    )
    # biometric stamping from wizard payload (same as reactivation else-branch)
```

```typescript
// frontend/aesthetic-clinic/src/services/api/admin.ts

export async function initializeDirectClientConversion(): Promise<ProspectConversionResponse> {
  const { data } = await apiClient.post('/api/admin/clientes/directo/initialize/');
  return data;
}

// Response shape (same as ProspectConversionResponse):
{
  draftId: number;
  prospect: ProspectLead | null;   // always null for direct mode
  client:  ClienteDetail | null;  // always null until finalize
  draft:   { step: 1..5, ... };
}
```

```typescript
// frontend/aesthetic-clinic/src/pages/admin/prospect-convert/AdminProspectConvertPage.tsx
type WizardMode = 'prospect' | 'reactivation' | 'direct';
const mode: WizardMode = prospectId ? 'prospect' : clientId ? 'reactivation' : 'direct';
```

No new TS types required — `ProspectConversionResponse.prospect: ProspectLead | null` and `client?: ... | null` already permit direct mode.

## Testing Strategy

| Layer | Tool | Cases |
|---|---|---|
| Backend unit | `python manage.py test` | CI uniqueness on step 1, duplicate username rejected, draft created with both FKs null, finalize atomic rollback on forced DB error, finalize happy path returns `cliente_codigo`, cancel deletes `(null,null)` draft. |
| Backend regression | `python manage.py test` | Prospect→client finalize still calls `marcar_como_convertido` (branch 1); reactivation finalize still updates existing cliente only (branch 2). |
| Backend latent-bug fix | `python manage.py test` | Defensive `bytes(template)` coercion when persisting `template_biometrico` (BinaryField) from JSON-string wizard payloads. Fixes 7 pre-existing broken tests that relied on the UPDATE path but never exercised INSERT. Applied to both prospect-fallback and reactivation finalize paths. |
| Frontend E2E | `npx playwright test` | Happy path 5 steps → new client appears in `/cms/clientes`; duplicate CI blocks step 1 with Spanish 400; cancel cleans up; "Crear cliente directo" button visible on `/cms/clientes` PageHeader. |
| Build gate | `npm run build` | TypeScript strict mode passes; React Router resolves `clientes/nuevo` without colliding with `clientes/<int:id>/...`. |

## Migration / Rollout

**No migration required. No data backfill. Safe to deploy in a single PR.**

- `ProspectoConversionBorrador.prospecto` and `.cliente` are already nullable `OneToOneField`s; `(null, null)` is a conceptual-only state.
- No new packages, no settings changes, no fixture changes.
- Rollback = revert the PR. Any orphan `(null, null)` drafts can be deleted by `DELETE WHERE prospecto_id IS NULL AND cliente_id IS NULL` post-rollback.

## Open Questions

None — the proposal resolved all open questions (URL naming, view sharing vs duplication, summary card rendering, cleanup story).

## Decisions captured (with rationale)

| Decision | Rationale |
|---|---|
| `clientes/directo/<step>/` (not `conversion-directa` or `nuevo/<step>/`) | Mirrors `<int:id>/reactivar/<step>/` shape; "directo" is a literal route segment that cannot collide with `<int:id>` (an integer converter will not match a non-numeric string). |
| Mode enum over boolean | Open-closed extension; avoids three-valued boolean confusion; matches spec §Three Wizard Modes. |
| Branch order `prospect → reactivation → direct` | Preserves byte-for-byte existing branches; direct branch is the strict superset of prospect-branch minus two side-effects. No regression risk on existing tests. |
| URL routes ordered: literal `directo` BEFORE `<int:id>` | Defensive; even though `<int:id>` cannot match `directo`, ordering makes intent explicit and future-proofs against future `/clientes/<int:id>/directo/...` routes. |
| Mode derived from URL params, not state | URL is the single source of truth; React Router gives all three params natively; no extra state, no query string. |
| Branch resolution = `_get_branch_for_scope_check(request)` | No `prospecto.sucursal_registro` to fall back to in direct mode; admin's scope branch is the only sensible default and matches reactivation behavior. |