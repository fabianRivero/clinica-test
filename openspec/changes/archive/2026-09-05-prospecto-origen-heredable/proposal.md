# Proposal: prospecto-origen-heredable

## Intent

The previous change `cliente-origen-recurrente` (archived) added `Cliente.origen` and a required origin radio to the `mode='direct'` conversion wizard, but it left the prospect path broken: a `Prospecto` has no `origen`, so `admin_prospect_conversion_finalize` always persists `Cliente.origen = NUEVO`, dropping the "antiguo" label for pre-system patients entering via `/cms/prospectos/nuevo`. This change closes that gap by making `Prospecto.origen` settable at creation and propagating it to `Cliente.origen` at finalize, so the prospect path preserves the same signal the direct path already records.

## Scope

### In Scope
- `Prospecto.origen` field (same `ORIGEN_CHOICES` as `Cliente`) + migration backfilling existing rows to `NUEVO`.
- Required origin radio at the top of `AdminProspectCreatePage` ("Antiguo / Nuevo"), submit-block until selected.
- Backend `admin_crear_prospecto` accepts and validates `origen`.
- Backend `admin_prospect_conversion_finalize` propagates `prospecto.origen` → `Cliente.origen` (NOT hardcoded `NUEVO`).
- Frontend `CreateAdminProspectPayload` type + `createAdminProspect` service include `origen`.

### Out of Scope
- No change to `Cliente.origen`, its serializer exposure, the badge in `/cms/clientes`, the `mode='direct'` radio, the migration `0015_cliente_origen`, or the perfil endpoint.
- No change to `CitaProspecto` model or its `clean()` invariant.
- No `ProspectoAdmin` change for the new field.
- No `origen` column in the prospect list/detail views.

## Capabilities

### New Capabilities
- `prospecto-origen`: full spec mirroring `cliente-origen` structure (field semantics, write-once, API serialization, defaults) but scoped to `Prospecto`.

### Modified Capabilities
- `cliente-origen`: delta — (a) note `Prospecto.origen` is settable on creation via `admin_crear_prospecto`; (b) note the prospect list MAY show the badge in a future change (out of scope here).
- `admin-prospect-conversion`: delta — add a requirement that `prospect` finalize propagates `Prospecto.origen` to the new `Cliente.origen`, and that `reactivation` finalize MUST NOT overwrite `Cliente.origen`.

## Approach

- Add `Prospecto.origen = models.CharField(..., choices=ORIGEN_CHOICES, default=NUEVO, null=False)`; reuse the same choices constant pattern as `Cliente`.
- Migration `0016_prospecto_origen` adds the column with `default=NUEVO` so the existing `prospectos` rows backfill atomically.
- Reuse the radio UX pattern from the previous change in `AdminProspectCreatePage`: two-option radio at the top, submit disabled until a choice is made, mirror copy "Antiguo (ya fue paciente)" / "Nuevo (primera vez)".
- In `admin_prospect_conversion_finalize`, replace the hardcoded `origen=NUEVO` with `origen=self.prospecto.origen`; the `reactivation` branch is untouched.
- Backend validates `origen` against `ORIGEN_CHOICES` in `admin_crear_prospecto`; frontend wires the new field into the payload and the wizard's draft state.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/customers/models.py` | Modified | Add `Prospecto.origen` + `ORIGEN_CHOICES` (mirror `Cliente`). |
| `backend/customers/migrations/0016_prospecto_origen.py` | New | Migration with `default=NUEVO` to backfill existing rows. |
| `backend/config/api_views.py` | Modified | `admin_crear_prospecto` (~line 4725) accepts + validates `origen`. |
| `backend/config/prospect_conversion_views.py` | Modified | `admin_prospect_conversion_finalize` reads `prospecto.origen` instead of hardcoding `NUEVO`. |
| `frontend/aesthetic-clinic/src/types/admin.ts` | Modified | `CreateAdminProspectPayload` adds `origen`. |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Modified | `createAdminProspect` signature sends `origen`. |
| `frontend/aesthetic-clinic/src/pages/admin/AdminProspectCreatePage.tsx` | Modified | Radio at top, submit-block until selected. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Migration on non-empty `prospectos` table | Low | Column has server-side `default=NUEVO`, so existing rows backfill in one statement; non-blocking ALTER. |
| UI regression on the new modal radio | Med | Mirror the radio already validated in the previous change; manual smoke of the modal. |
| Drift between Django `ORIGEN_CHOICES` and TS labels | Low | TS type uses the same literal union (`'NUEVO' \| 'RECURRENTE_PRE_SISTEMA'`); single shared label table. |
| Finalize forgetting to copy `origen` for reactivation | Med | Explicit guard: `reactivation` branch MUST NOT touch `Cliente.origen`; covered by a delta-scenario assertion. |

## Rollback Plan

Revert migration `0016_prospecto_origen` with `python manage.py migrate customers 0015_prospecto_origen` (drops the column, no row data destroyed since `Cliente.origen` remains). Revert the frontend commits. `Cliente.origen` semantics and the `mode='direct'` radio from the previous change are untouched and continue to work.

## Dependencies

- Requires `cliente-origen-recurrente` (archived) to be shipped — confirmed.

## Success Criteria

- [ ] All existing `Prospecto` rows have `origen = NUEVO` after migration applies.
- [ ] `AdminProspectCreatePage` submit is disabled until an origin radio is selected.
- [ ] Converting a `RECURRENTE_PRE_SISTEMA` `Prospecto` produces a `Cliente` with `origen = RECURRENTE_PRE_SISTEMA`.
- [ ] `reactivation` finalize leaves `Cliente.origen` unchanged (verified by delta scenario).
- [ ] Backend rejects unknown `origen` value in `admin_crear_prospecto` with 400.
