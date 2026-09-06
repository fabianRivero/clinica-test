# Tasks: prospecto-origen-heredable

## Review Workload Forecast

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

| Key | Value |
|-----|-------|
| Decision needed before apply | No |
| Chained PRs recommended | No |
| Chain strategy | pending |
| 400-line budget risk | Low |

## Suggested Work Units

Single work unit = single PR.

| Field | Value |
|-------|-------|
| Work unit ID | WU-1: prospecto-origen propagation |
| Branch | `feat/prospecto-origen-heredable` |
| Commit plan | 4 commits: (1) backend model+migration, (2) backend views, (3) frontend types+page, (4) frontend E2E + final lint/build. Follow `work-unit-commits`. |
| Test command | `python manage.py test customers.tests.test_prospecto_origen` |
| Runtime harness | Django dev server (`python manage.py runserver`) + Vite dev server (`npm run dev`) for manual smoke of the radio. |
| Rollback boundary | `python manage.py migrate customers 0015_cliente_origen` + revert frontend commits in `frontend/aesthetic-clinic/src/`. |

---

## Phase 1: Backend foundation (model + migration)

- [x] 1.1 Add `class Prospecto.Origen(models.TextChoices)` (mirroring `Cliente.Origen`) and `origen = models.CharField(max_length=32, choices=Origen.choices, default=Origen.NUEVO, db_default=Origen.NUEVO)` on `Prospecto` in `backend/customers/models.py`.
- [x] 1.2 Generate migration `backend/customers/migrations/0016_prospecto_origen.py` (deps `0015_cliente_origen`; `AddField` on `prospectos.origen` with `default="NUEVO"` + `db_default="NUEVO"`, mirroring `0015_cliente_origen.py`).
- [x] 1.3 Create `backend/customers/tests/test_prospecto_origen.py` with scenarios: existing `Prospecto` rows backfill to `NUEVO` after migration; new prospect rejects unknown `origen` with 400; `marcar_como_convertido` leaves `origen` untouched.

## Phase 2: Backend creation endpoint

- [x] 2.1 Extend `admin_crear_prospecto` in `backend/config/api_views.py` (~line 4725) to read `origen` from payload, validate against `Prospecto.Origen.choices`, default `NUEVO` when omitted, and forward into `Prospecto.objects.create(...)`.
- [x] 2.2 Extend `test_prospecto_origen.py`: `admin_crear_prospecto` with `origen=RECURRENTE_PRE_SISTEMA` persists; unknown value returns 400 with zero rows inserted.

## Phase 3: Backend conversion finalize propagation

- [x] 3.1 Modify `admin_prospect_conversion_finalize` in `backend/config/prospect_conversion_views.py` (~line 1877): inside `if draft.prospecto:` branch only, change `origen=user_data.get("origen") or Cliente.Origen.NUEVO` to `origen=draft.prospecto.origen`. Leave the `elif draft.cliente:` (reactivation) branch and the `mode='direct'` site (~line 1959) byte-identical.
- [x] 3.2 Extend `test_prospecto_origen.py`: finalizing a `RECURRENTE_PRE_SISTEMA` prospect produces `Cliente.origen=RECURRENTE_PRE_SISTEMA`; finalizing via reactivation leaves existing `Cliente.origen` unchanged.

## Phase 4: Frontend types + UI

- [x] 4.1 Extend `CreateAdminProspectPayload` in `frontend/aesthetic-clinic/src/types/admin.ts` (line 917) to include `origen?: 'NUEVO' | 'RECURRENTE_PRE_SISTEMA'`.
- [x] 4.2 Add `origen` to local form state and render a REQUIRED two-option radio as the first `<form>` child (above `primerNombre`) in `frontend/aesthetic-clinic/src/pages/admin/AdminProspectCreatePage.tsx`, mirroring `<fieldset class="field field--full origen-fieldset">` markup from the previous change's `ConversionStepUser.tsx`. Disable submit until selected; include `origen` in the `createAdminProspect` payload.
- [x] 4.3 Add Playwright spec `frontend/aesthetic-clinic/tests/e2e/admin-prospect-origen.spec.ts`: radio blocks submit; "Antiguo" persists `RECURRENTE_PRE_SISTEMA`; "Nuevo" persists `NUEVO`; converting a "Antiguo" prospect produces a `Cliente` with matching `origen`.

## Phase 5: Verification

- [x] 5.1 Run `python manage.py test customers.tests.test_prospecto_origen` — backend green.
- [x] 5.2 Run `npx playwright test admin-prospect-origen` — green (modulo pre-existing global-setup bug).
- [x] 5.3 Run `npm run build` and `npm run lint` — green (modulo pre-existing baseline).