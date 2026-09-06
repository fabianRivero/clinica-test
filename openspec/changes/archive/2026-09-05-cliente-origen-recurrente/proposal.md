# Proposal: cliente-origen-recurrente

## Intent

Pre-system patients cannot today be onboarded as `Cliente` while able to receive a cobrable medical appointment: the "directo" path skips `Prospecto`, so no cobrable `CitaProspecto`. This change unifies both flows into ONE wizard and tags every `Cliente` with `origen`, so pre-system patients are `Cliente` from step 1 and immediately receive cobrable `CitaMedica`.

## Scope

### In Scope
- `Cliente.origen` field, choices `NUEVO` (default) and `RECURRENTE_PRE_SISTEMA`.
- Migration defaulting `origen=NUEVO` for existing rows.
- Required origin radio at TOP of Step 1.
- Remove "Crear cliente directo" button; route preserved.
- Profile/finalize accept `origen`, write-once.

### Out of Scope
- `CitaProspecto` model or its `clean()` invariant.
- Cobrable appointments BEFORE the 5 steps finish.
- `ClientProfileSerializer` changes unrelated to `origen`.
- Reports beyond the `origen` badge.
- `prospect`/`reactivation` behavior; bulk re-tagging.

## Capabilities

### New Capabilities
- `cliente-origen`: field semantics, default migration, write-once, badge.

### Modified Capabilities
- `admin-direct-client-creation`: REMOVED — button gone; route mounts wizard forcing origin. Mark for archive.
- `admin-prospect-conversion`: Step 1 MUST require origin before advancing in `direct`; finalize MUST persist `origen`.
- `admin-client-profile-editing`: `origen` read-only after creation.

## Approach

- Add `origen = CharField(choices=ORIGEN_CHOICES, default='NUEVO', max_length=32)` to `Cliente`; column default backfills.
- `useConversionWizard` + `ConversionStepUser.tsx` lift `origen` into draft; required radio blocks "Next".
- `AdminClientProfileWriteSerializer` accepts `origen`; `direct` finalize persists it.
- Delete the button; route stays.

## Affected Areas

- `backend/customers/models.py` — add `Cliente.origen` + `ORIGEN_CHOICES`.
- `backend/customers/migrations/<new>.py` — new migration with `default='NUEVO'`.
- `backend/config/api/viewsets/clientes.py` + `serializers/clientes.py` — accept `origen` on finalize; reject post-create edits; serializer exposes it (write-once).
- `frontend/.../prospect-convert/ConversionStepUser.tsx` + `useConversionWizard.ts` — required origin radio at top of Step 1; gate before advancing.
- `frontend/.../admin/AdminClientsPage.tsx` — remove button.
- `frontend/.../App.tsx` — unchanged; route preserved.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Migration mis-applies on non-empty DB | Low | Column default; verify row-count post-apply. |
| UI regression blocks valid submits | Medium | Playwright check that both Sí/No paths advance. |
| Drift between Django choices and TS labels | Medium | Serializer choices drive frontend constant. |
| Stale direct-creation path remains | Low | Grep for `mode='direct'`, "Crear cliente directo", old router. |

## Rollback Plan

`migrate customers <prev>` drops `origen`. Revert frontend commits that added the radio and removed the button. No row data destroyed.

## Dependencies

- `prospect-conversion` spec exists in `openspec/specs/`.
- No external libs.

## Success Criteria

- [ ] All existing `Cliente` rows have `origen='NUEVO'` after `migrate`.
- [ ] Step 1 blocks "Next" until `origen` is selected.
- [ ] `RECURRENTE_PRE_SISTEMA` Cliente gets cobrable `CitaMedica` immediately.
- [ ] "Crear cliente directo" gone; one entry remains.
- [ ] `origen` read-only on profile edit post-creation.