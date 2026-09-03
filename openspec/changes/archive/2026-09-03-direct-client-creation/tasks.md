# Tasks: Direct Client Creation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 350–450 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | 2 stacked PRs to main: PR 1 backend (~250 lines), PR 2 frontend (~150 lines) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Backend direct-creation plumbing: new `admin_direct_client_initialize` view, extended `_get_draft_convertible(direct_id=...)`, third branch in `admin_prospect_conversion_finalize`, URL family, backend tests | PR 1 | `python manage.py test tests.test_direct_client_conversion` | `curl -X POST -b admin_cookie /api/admin/clientes/directo/initialize/` then PATCH through 5 steps then POST finalize | Revert `prospect_conversion_views.py` + `api_urls.py`; no migration |
| 2 | Frontend wizard integration: PageHeader action, App route, mode enum, wizard branch, service call, E2E test | PR 2 | `npx playwright test e2e/admin/direct-client-creation.spec.ts` | Browser: `/cms/clientes` → click "Crear cliente directo" → complete 5 steps → verify row in `/cms/clientes` | Revert `App.tsx` + `AdminClientsPage.tsx` + `AdminProspectConvertPage.tsx` + `useConversionWizard.ts` + `services/api/admin.ts` |

## Phase 1: Backend Foundation

- [x] 1.1 Add `admin_direct_client_initialize` view in `backend/config/prospect_conversion_views.py` — POST creates `ProspectoConversionBorrador(prospecto=None, cliente=None, iniciado_por=request.user)` and returns `_admin_conversion_detail` payload; admin-only (`IsAdminUser`).
- [x] 1.2 Extend `_get_draft_convertible(request, prospecto_id=None, cliente_id=None, direct_id=None)` — new `direct_id` kwarg resolves a draft by PK and creates a fresh `(null, null)` row when called from the direct entry; existing two-arg callsites unchanged.
- [x] 1.3 Wire `clientes/directo/<step>/` URL family in `backend/config/api_urls.py` BEFORE `clientes/<int:id>/reactivar/<step>/` — `initialize`, `detail`, `user`, `operation`, `medical`, `biometric`, `payment`, `finalize`, `cancel`.

## Phase 2: Backend Finalize Third Branch

- [x] 2.1 Add `else` branch in `admin_prospect_conversion_finalize` (`prospect_conversion_views.py:1768+`) — when `draft.prospecto is None and draft.cliente is None`: create `Usuario (CLIENTE, is_active=True)` + `Cliente` (with `sucursal_origen=_get_branch_for_scope_check(request)`) inside the existing `transaction.atomic()`; stamp biometric from wizard payload (reuse reactivation path); skip `marcar_como_convertido`; delete draft.
- [x] 2.2 Verify `_validate_user_step` rejects duplicate CI/username in direct mode — no code change expected (line 826-837 already enforces global uniqueness; "self" exclusion is a no-op when neither FK is set).

## Phase 3: Backend Tests

- [x] 3.1 Test: `POST /api/admin/clientes/directo/initialize/` creates draft with `prospecto=NULL, cliente=NULL` and returns detail payload.
- [x] 3.2 Test: step 1 in direct mode returns 400 with Spanish "Ya existe un cliente con este CI." on duplicate CI.
- [x] 3.3 Test: step 1 in direct mode returns 400 on duplicate `username`.
- [x] 3.4 Test: finalize happy path creates `Usuario (CLIENTE)` + `Cliente`, returns `cliente_codigo`, deletes draft.
- [x] 3.5 Test: finalize rolls back on forced DB error — no `Usuario`, no `Cliente`, draft preserved, 500 returned.
- [x] 3.6 Test: cancel at any step deletes the `(null, null)` draft and creates no `Usuario`/`Cliente`.
- [x] 3.7 Regression: prospect→client finalize still calls `marcar_como_convertido` and migrates prospect biometric.
- [x] 3.8 Regression: reactivation finalize still updates existing `Cliente` only (no new `Usuario`).
- [x] 3.9 Test: non-admin gets 403 on `initialize`; no draft row created.

## Phase 4: Frontend Types and Service

- [x] 4.1 Add `initializeDirectClientConversion(): Promise<ProspectConversionResponse>` to `frontend/aesthetic-clinic/src/services/api/admin.ts` — POSTs `/api/admin/clientes/directo/initialize/`. Also added direct-mode step endpoints (paso-1..paso-4), `cancelAdminDirectClientConversion`, and `finalizeAdminDirectClientCreation` so the wizard can dispatch the full flow.
- [x] 4.2 Verify `frontend/aesthetic-clinic/src/types/prospectConversion.ts` already permits `prospect: ProspectLead | null` and `client?: ... | null` (no change expected). Confirmed — no edit required.

## Phase 5: Frontend Wizard Integration

- [x] 5.1 Replace `isReactivation: boolean` with `mode: 'prospect' | 'reactivation' | 'direct'` enum in `AdminProspectConvertPage.tsx` (lines 16-20) — derived from URL: `prospectId ? 'prospect' : clientId ? 'reactivation' : 'direct'`.
- [x] 5.2 Conditionally render the summary card block (lines 150-166) only when `data.prospect != null`; show a "Nuevo cliente directo — paso 1 de 5" stub otherwise.
- [x] 5.3 Update wizard `wizardTitle` / `wizardSubject` / back-link ternary (lines 115-137) to use the new `mode` enum; back-link in direct mode routes to `/cms/clientes`.
- [x] 5.4 Add `mode='direct'` branch in `useConversionWizard.ts` — calls `initializeDirectClientConversion()` instead of `getAdminProspectConversionDetail`. Also wired `paso-1..paso-4`, `finalizeAdminDirectClientCreation`, and `cancelAdminDirectClientConversion` for direct mode.
- [x] 5.5 Add route `path="clientes/nuevo"` → `<AdminProspectConvertPage />` in `App.tsx` (before `clientes/:clientId/reactivar`).

## Phase 6: Frontend Entry Point

- [x] 6.1 Add primary `actions={[{ label: 'Crear cliente directo', to: '/cms/clientes/nuevo' }]}` to `PageHeader` in `AdminClientsPage.tsx` (around line 177).

## Phase 7: Frontend Tests

- [x] 7.1 E2E `e2e/admin/direct-client-creation.spec.ts` — happy path: open `/cms/clientes`, click button, complete 5 steps, verify new row appears with valid `cliente_codigo`.
- [x] 7.2 E2E: duplicate CI on step 1 returns Spanish 400 and blocks navigation.
- [x] 7.3 E2E: cancel at step 3 returns to `/cms/clientes` with no orphan row.

## Phase 8: Build and Review

- [ ] 8.1 `python manage.py test` — full backend suite green (new tests + regressions).
- [ ] 8.2 `npm run build` — TypeScript strict mode passes; no route-resolution warnings.
- [ ] 8.3 Visual review: `/cms/clientes` PageHeader shows new button; wizard renders cleanly in direct mode; summary card absent.
- [ ] 8.4 Visual review: `/cms/prospectos/:id/convertir` and `/cms/clientes/:id/reactivar` unchanged (regression check).