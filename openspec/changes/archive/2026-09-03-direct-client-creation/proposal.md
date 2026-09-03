# Proposal: direct-client-creation

## Intent

The `/cms/clientes` listing has no admin-driven way to create a brand-new `Cliente` + `Usuario` pair. Today, new clients can only enter the system as prospects. Admins sometimes need to register a walk-in or legacy client (with no prospect history) directly, and that case is currently impossible. This change adds a third wizard mode — **direct client creation** — that runs the same 5-step flow as prospect→client but starts from a `(prospecto=NULL, cliente=NULL)` draft and, on finalize, creates a new `Usuario (CLIENTE)` + `Cliente` in one transaction without ever touching a prospect.

## Scope

### In Scope

- New backend endpoint family under `/api/admin/clientes/directo/<step>/` (initialize, detail, user, operation, medical, biometric, payment, finalize, cancel) reusing the existing step views.
- `_get_draft_convertible` accepts a new `direct_id` (draft PK) path and creates `ProspectoConversionBorrador(prospecto=None, cliente=None)` when neither FK is present.
- `admin_prospect_conversion_finalize` gains a third branch: when neither FK is set, it creates `Usuario` + `Cliente` (same code path as the prospect branch) but skips `prospecto.marcar_como_convertido()` and skips prospect biometric migration.
- `_admin_conversion_detail` payload already tolerates `prospect=None`; the `client` block returns `null` for direct mode (frontend already typed `client?: ... | null`).
- Frontend: new route `clientes/nuevo` rendering `AdminProspectConvertPage` with `mode='direct'`; new `PageHeader` action "Crear cliente directo" on `AdminClientsPage`; new service `initializeDirectClientConversion` in `services/api/admin.ts`.
- CI/username uniqueness enforcement on step 1 (reuses `_validate_user_step`); duplicate CI → 400 with a clear Spanish error message.
- No DB migration: `ProspectoConversionBorrador.prospecto` and `.cliente` are already nullable; `(null, null)` is a conceptual-only state change.

### Out of Scope

- Editing existing client profile (already covered by `admin-client-profile-editing`).
- Bulk import, CSV, cross-branch client creation.
- Username auto-generation strategies beyond reusing `_validate_user_step`.
- Phantom-draft garbage collection beyond extending `admin_prospect_conversion_cancel` (which already deletes a draft by PK, regardless of FK state).
- A pre-created stub `Cliente` (Approach 3 in exploration) — rejected because it dirties `/cms/clientes` before the wizard completes and breaks the wizard-time uniqueness UX.

## Capabilities

### New Capabilities

- **`admin-direct-client-creation`**: Admins can create a brand-new `Cliente` + `Usuario (CLIENTE)` pair from `/cms/clientes` via a 5-step wizard. The new client never had a prospect or prior reactivation. CI and username uniqueness are enforced during the wizard; duplicate CI blocks finalize and rolls back the transaction cleanly.

### Modified Capabilities

- **`admin-prospect-conversion`** (the implicit capability covering `prospect_conversion_views.py` and `AdminProspectConvertPage.tsx`): the wizard now operates in three modes — `prospect`, `reactivation`, `direct` — instead of the current two. The finalize dispatcher grows a third branch; `_get_draft_convertible` grows a third resolution path; `AdminProspectConvertPage` renders summary cards conditionally on `data.prospect`. No existing requirement text in any archived spec is invalidated; the capability is being **extended** rather than redefined.

## Approach

**Backend:** add `admin_direct_client_initialize` that creates an empty `ProspectoConversionBorrador(prospecto=None, cliente=None, iniciado_por=request.user)` and returns its detail payload. Reuse `admin_prospect_conversion_detail`, `..._user_step`, `..._operation_step`, `..._medical_step`, `..._biometric_step`, `..._payment_step`, `..._cancel` by routing all of them through a new `_get_draft_convertible(direct_id=...)` path. `_validate_user_step` keeps its current logic — when neither FK is set, the "self" exclusion is a no-op, so a duplicate CI simply fails the global `Cliente.objects.filter(ci=ci).exists()` check at line 830-837. Finalize branches:

```
if draft.prospecto:       # prospect → client (unchanged)
    create user + cliente; marcar_como_convertido
elif draft.cliente:       # reactivation (unchanged, profile-data non-overwrite already enforced)
    update observaciones + biometric/payment
else:                     # NEW: direct creation
    create user + cliente; stamp biometric from wizard payload (or skip)
    # NO marcar_como_convertido (no prospect); NO prospect biometric migration
```

All writes inside `transaction.atomic()`; on any error, no DB row is created.

**Frontend:** `AdminProspectConvertPage` replaces the boolean `isReactivation` with a `mode: 'prospect' | 'reactivation' | 'direct'` enum derived from URL (`prospectId` → prospect; `clientId` → reactivation; neither → direct). The summary card block (lines 150-166) skips rendering when `data.prospect == null`. `useConversionWizard` initializes from a new `initializeDirectClientConversion()` service call. `AdminClientsPage` PageHeader gains a primary `actions={[{ label: 'Crear cliente directo', onClick: () => navigate('/cms/clientes/nuevo') }]}`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/config/prospect_conversion_views.py:714-747` | Modified | `_get_draft_convertible` accepts `direct_id=...`; creates a `(null, null)` draft when called from the direct entry point. |
| `backend/config/prospect_conversion_views.py:1676-2020` | Modified | `admin_prospect_conversion_finalize` adds a third branch for `draft.prospecto is None and draft.cliente is None`: create `Usuario` + `Cliente`, stamp biometric from wizard payload, skip prospect-only side effects. |
| `backend/config/prospect_conversion_views.py:1271-1299` | Modified (defensive) | `_admin_conversion_detail` already guards `prospect`/`client` blocks with `if ... else None`; no structural change, just verified for `client=null` payload. |
| `backend/config/prospect_conversion_views.py:806-864` | Reused | `_validate_user_step` — duplicate CI/username check fires correctly without the "self" exclusion. |
| `backend/config/api_urls.py:200-293` | Modified | Add `clientes/directo/<step>/` URL family. |
| `backend/customers/models.py:87-133` | Read-only | No model change. |
| `frontend/aesthetic-clinic/src/App.tsx:133-137` | Modified | New route `path="clientes/nuevo"` rendering `<AdminProspectConvertPage />` (no params → `mode='direct'`). |
| `frontend/aesthetic-clinic/src/pages/admin/AdminClientsPage.tsx:177-181` | Modified | PageHeader gains primary `actions` slot with "Crear cliente directo". |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/AdminProspectConvertPage.tsx:16-20,115-166` | Modified | `mode` enum replaces `isReactivation`; summary card hidden when `data.prospect == null`; back-link routes to `/cms/clientes`. |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts` | Modified | When `mode='direct'`, call `initializeDirectClientConversion()` instead of `getAdminProspectConversionDetail`. |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Modified | Add `initializeDirectClientConversion` typed client. |
| `frontend/aesthetic-clinic/src/types/prospectConversion.ts` | Reused | `ProspectConversionResponse.prospect: ProspectLead \| null` and `client?: ... \| null` already permit direct mode. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Phantom `(null, null)` drafts if admin abandons the wizard | Medium | `admin_prospect_conversion_cancel` already deletes a draft by PK regardless of FK state; verify it works for `(null, null)`. Add a periodic cleanup task or document manual cleanup as operator decision. |
| Username/CI race between two concurrent direct-creation wizards | Low | Same TOCTOU window that exists today for prospect conversion. `_validate_user_step` runs at step 1; the final uniqueness check at `Usuario.objects.filter(username=...).exists()` (line 1717) catches the rest. Acceptable. |
| `AdminProspectConvertPage.tsx:150-166` summary cards crash on null `data.prospect` | Medium | Conditionally render the summary card block; show a "Nuevo cliente directo — paso 1 de 5" stub instead. Verified at spec time. |
| Backend finalize creates partial state on error | Low | All branches wrap in `transaction.atomic()` (existing pattern at `prospect_conversion_views.py:1714-1754`). The new branch reuses the same atomic block. |
| URL family `/clientes/directo/<step>/` collides with future `/clientes/<int:id>/directo/...` routes | Low | Confirm URL ordering: `int:id` converter will not match `directo` (it parses as integer); routing precedence is safe. |
| Reactivation flow regresses because finalize branching is touched | Low | Existing `elif draft.cliente` branch is unchanged; existing prospect branch unchanged. New branch only fires when both FKs are null. Regression tests on both existing branches. |

## Rollback Plan

1. Revert `backend/config/api_urls.py` to remove the `clientes/directo/<step>/` route family.
2. Revert `backend/config/prospect_conversion_views.py` to drop the `direct_id` parameter in `_get_draft_convertible` and the third `else` branch in `admin_prospect_conversion_finalize`.
3. Revert `frontend/aesthetic-clinic/src/App.tsx` to drop the `clientes/nuevo` route.
4. Revert `frontend/aesthetic-clinic/src/pages/admin/AdminClientsPage.tsx` to remove the "Crear cliente directo" PageHeader action.
5. Revert `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/AdminProspectConvertPage.tsx` and `useConversionWizard.ts` to remove the `mode='direct'` branch.
6. Revert `frontend/aesthetic-clinic/src/services/api/admin.ts` to drop `initializeDirectClientConversion`.
7. **No DB migration to revert** — no schema change was made.
8. Any `(null, null)` `ProspectoConversionBorrador` rows left behind are safe to leave or to delete via a one-off `DELETE WHERE prospecto_id IS NULL AND cliente_id IS NULL` after the rollback lands.

## Dependencies

- Existing `ProspectoConversionBorrador` model (no migration).
- Existing `_validate_user_step`, `_admin_conversion_detail`, step views, and `admin_prospect_conversion_cancel` (all reused).
- Existing admin branch scoping via `_get_branch_for_scope_check`.
- No new third-party packages.

## Success Criteria

- [ ] Admin clicks "Crear cliente directo" in `/cms/clientes` PageHeader and lands on a 5-step wizard with mode `direct`.
- [ ] All 5 steps (user, operation, medical, biometric, payment) run identically to the prospect→client flow, except biometric is stamped from the wizard payload (no prospect to migrate from).
- [ ] Finalize creates a new `Usuario (CLIENTE)` + `Cliente` in one `transaction.atomic()` block; on any validation error, no rows are persisted.
- [ ] A duplicate CI entered at step 1 returns a clear Spanish 400 message ("Ya existe un cliente con este CI.") and the wizard blocks forward navigation.
- [ ] The new client appears in `/cms/clientes` after finalize with a valid `cliente_codigo`.
- [ ] Cancel at any step deletes the `(null, null)` draft cleanly.
- [ ] Existing prospect→client and reactivation flows are byte-for-byte unaffected (regression test passes for both branches).
- [ ] No DB migration is required; `ProspectoConversionBorrador` schema is unchanged.