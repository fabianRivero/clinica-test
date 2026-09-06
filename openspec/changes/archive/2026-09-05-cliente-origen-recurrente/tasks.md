# Tasks: cliente-origen-recurrente

## Review Workload Forecast

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium

| Signal | Value |
|---|---|
| Files touched | ~9 source + 2 test |
| Backend LOC | ~80-130 |
| Frontend LOC | ~60-120 |
| Test LOC | ~80-150 |
| Total estimate | ~220-400 (upper edge) |
| Single PR plausible | Yes |
| Chained PRs | No by default; only if actual diff > 400 |
| Risk | Medium (forecast near cap) |

## Suggested Work Units

Single work unit = single PR. Backend foundation and frontend changes are tightly coupled (radio drives finalize payload), so splitting risks a non-runnable intermediate state.

| Work unit | PR scope | Test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|
| `wu-origen-recurrente` | Backend model + migration + admin + finalize persistence + frontend types/wizard/UI + tests | `python manage.py test` + `npx playwright test` | Django dev server + Vite dev server | `python manage.py migrate customers 0014_cliente_cliente_codigo` + revert frontend commits |

## Phase 1 — Backend foundation (model + migration)

- [x] 1.1 Add `Cliente.origen` field and nested `Origen(TextChoices)` in `backend/customers/models.py`; non-null with default `NUEVO`.
- [x] 1.2 Generate migration `0015_cliente_origen` in `backend/customers/migrations/` (depends on `0014_cliente_cliente_codigo`); uses column default `NUEVO`.
- [x] 1.3 Add `origen` to `list_filter` and `list_display` in `backend/customers/admin.py` so admins can audit existing rows.
- [x] 1.4 Backend tests in `backend/customers/tests/test_origen_field.py` (Django `TestCase`): migration backfills `NUEVO`, `full_clean()` rejects unknown choices, perfil endpoint PATCH with `origen` returns 400.

## Phase 2 — Backend finalize persistence

- [x] 2.1 Extend `admin_prospect_conversion_finalize` in `backend/config/prospect_conversion_views.py` to validate and persist `origen` on the new `Cliente` only when `mode == 'direct'`; reactivation path unchanged.
- [x] 2.2 Backend test in `backend/config/tests/test_prospect_conversion_direct.py`: finalize with `origen='RECURRENTE_PRE_SISTEMA'` persists; finalize without `origen` defaults to `NUEVO`.

## Phase 3 — Frontend types + wizard state

- [x] 3.1 Extend `ProspectConversionUserData` in `frontend/aesthetic-clinic/src/types/prospectConversion.ts` with optional `origen?: 'NUEVO' | 'RECURRENTE_PRE_SISTEMA'`.
- [x] 3.2 Lift `origen` into `useConversionWizard` state in `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts`; hydrate on init and send through finalize payload (direct only).
- [x] 3.3 Thread `isDirect` to `ConversionStepUser`; add `origen` to the step's local state and props in `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx`.

## Phase 4 — Frontend UI

- [x] 4.1 Render required radio at TOP of `ConversionStepUser.tsx` only when `isDirect === true`; block "Next" until a value is selected.
- [x] 4.2 Remove the PageHeader `Crear cliente directo` button (and its label string) from `frontend/aesthetic-clinic/src/pages/admin/AdminClientsPage.tsx`; route `/cms/clientes/nuevo` stays intact.
- [x] 4.3 Playwright spec `frontend/aesthetic-clinic/tests/e2e/admin-direct-client-origen.spec.ts`: clicking the remaining entry opens the wizard, "Sí"/"No" paths persist correctly, advancing is blocked without a selection.

## Phase 5 — Verification

- [x] 5.1 Run `python manage.py test` — backend green (covers Phase 1.4, 2.2, and existing suites).
- [x] 5.2 Run `npx playwright test` covering `admin_general.spec.ts`, `admin_branch.spec.ts`, and the new `admin-direct-client-origen.spec.ts` — green.
- [x] 5.3 Run `npm run build`, `npm run lint`, and `npx tsc --noEmit` — green.

## Phase 6 — Archive prep

- [x] 6.1 Verify the proposal marks `admin-direct-client-creation` for archive; no code action in this PR (archive sync happens post-verify in `sdd-archive`).

## Phase 7 — Remediation (verify-found CRITICAL)

- [x] 7.1 Add `origen` to `ClientSearchSerializer` in `backend/config/api/serializers/clientes.py`.
- [x] 7.2 Add `origen` to the cliente detail response builder (`_admin_client_detail` in `backend/config/api/api_views.py` and any dedicated detail serializer).
- [x] 7.3 Add `origen` to `_client_item()` helpers (both copies referenced by verify: `backend/config/api/api_views.py` and `backend/config/api/viewsets/clientes.py`).
- [x] 7.4 Add `origen` to `_build_initial_client_user_data()` so the perfil endpoint response envelope surfaces it.
- [x] 7.5 Add `origen` to `AdminClientProfileWriteSerializer.update()`'s response builder and any other Cliente return path in the viewsets.
- [x] 7.6 Add `origen` badge/column to `frontend/aesthetic-clinic/src/pages/admin/AdminClientsPage.tsx` clients table.
- [x] 7.7 Backend test: `ClientSearchSerializer` (or the relevant search endpoint) returns `origen`.
- [x] 7.8 Frontend type extension + Playwright spec assertion: `/cms/clientes` renders the origen badge.
- [x] 7.9 Run scoped backend tests + `npx tsc --noEmit` + `npm run build` and confirm green.