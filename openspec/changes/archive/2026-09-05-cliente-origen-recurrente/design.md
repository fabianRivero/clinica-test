# Design: cliente-origen-recurrente

## Technical Approach

- Add `Cliente.origen` in `backend/customers/models.py` as a non-null `CharField` backed by `TextChoices`; the next customers migration uses `default='NUEVO'`, backfilling existing rows safely.
- Extend the shared direct-mode draft user data with optional `origen`; `useConversionWizard` hydrates it from initialization, requires it before Step 1 advances, and sends it through the existing finalize payload.
- Render the origin radio only when `mode='direct'` by threading `isDirect` through `AdminProspectConvertPage` to `ConversionStepUser`; prospect and reactivation behavior remains unchanged.
- Extend direct finalize in `backend/config/prospect_conversion_views.py` to validate and pass `origen` when constructing `Cliente`; existing atomic creation and regular cobrable `CitaMedica` paths remain unchanged.
- Keep `origen` out of `AdminClientProfileWriteSerializer` fields so its existing unknown-field guard returns 400 for all profile PATCH attempts; serializers that expose clients include the model field for read visibility.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Field type & choices | `CharField(max_length=32, choices=Cliente.Origen)` with nested `TextChoices` | `PositiveSmallIntegerField`; bare enum | Values are API/reporting strings, readable in SQL and stable across clients; Django choices provide validation and labels. |
| Write-once enforcement | Omit from profile serializer fields | Add field and reject PATCH explicitly | Existing `validate()` rejects unknown keys loudly, preserves the exact 13-field contract, and requires no update-path special case. |
| Wizard data shape | Extend `ProspectConversionUserData` with optional `origen` | Parallel direct-only type | One draft/user payload and existing handlers remain aligned; optionality preserves prospect/reactivation payload compatibility. |
| Radio rendering | Thread `isDirect` to `ConversionStepUser` | Render whenever not reactivation | Explicit mode expresses the spec, prevents accidental rendering if another editable mode is added, and keeps presentation semantics clear. |
| Button removal | Remove the PageHeader JSX action linking to `/cms/clientes/nuevo` in `frontend/aesthetic-clinic/src/pages/admin/AdminClientsPage.tsx` | Hide it conditionally; remove route | Removes the duplicate entry while preserving the required deep-link route and unified wizard. |
| Reporting visibility | In scope now for admin listing badge/filter; broader reports are Phase 2 | Defer all reporting; modify every report now | The capability requires `/cms/clientes` visibility; avoid expanding unrelated report contracts. |

## Data Flow

```text
Admin /cms/clientes
  -> single remaining creation entry
  -> /cms/clientes/nuevo (existing App.tsx route)
  -> initializeDirectClientConversion
  -> draft.userData.origen + Step 1 radio (required)
  -> select Sí => RECURRENTE_PRE_SISTEMA
  -> five steps complete / finalize
  -> atomic Usuario + Cliente(origen)
  -> existing appointment UI creates cobrable CitaMedica(precio)
```

## File Changes

| File | Action | Description |
|---|---|---|
| `backend/customers/models.py` | Modify | Add `Cliente.Origen` and non-null `origen`. |
| `backend/customers/migrations/<next>.py` | Create | Add column with `default='NUEVO'`, depending on `0008_split_prospecto_name_fields`. |
| `backend/customers/admin.py` | Modify | Add `origen` to client admin `list_filter`/`list_display`. |
| `backend/config/api/viewsets/clientes.py` | No change | Preserve perfil endpoint and read response contract. |
| `backend/config/api/serializers/clientes.py` | Modify | Leave `origen` absent from write serializer; ensure read serializers expose it where applicable. |
| `backend/config/prospect_conversion_views.py` | Modify | Validate and persist `origen` in direct finalize only; reactivation never rewrites it. |
| `frontend/aesthetic-clinic/src/types/prospectConversion.ts` | Modify | Add optional `origen` union. |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx` | Modify | Render required direct-mode radio at the top. |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts` | Modify | Lift, validate, hydrate, and submit `origen`. |
| `frontend/aesthetic-clinic/src/pages/admin/AdminClientsPage.tsx` | Modify | Remove exact standalone PageHeader link/button to `/cms/clientes/nuevo`. |
| `frontend/aesthetic-clinic/src/App.tsx` | No change | Existing route already mounts direct wizard. |

## Interfaces / Contracts

```python
class Origen(models.TextChoices):
    NUEVO = "NUEVO", "Nuevo"
    RECURRENTE_PRE_SISTEMA = "RECURRENTE_PRE_SISTEMA", "Recurrente pre-sistema"

origen = models.CharField(max_length=32, choices=Origen.choices,
                          default=Origen.NUEVO)
```

Profile write contract intentionally omits `origen`:

```python
def validate(self, attrs):
    declared = set(self.fields.keys())
    for key in self.initial_data:
        if key not in declared and key not in {"hasPassword"}:
            raise serializers.ValidationError(
                {key: f"Unknown field '{key}'. Only the 13 declared profile fields are editable."}
            )
    return attrs
```

```ts
export type ProspectConversionUserData = {
  // existing fields...
  origen?: 'NUEVO' | 'RECURRENTE_PRE_SISTEMA'
}
```

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Backend unit | Migration applies, perfil rejects `origen`, direct finalize persists and validates it | Django `TestCase`; run `python manage.py test`. |
| Frontend E2E | Radio required blocks advance; Sí and No paths persist correct values | Playwright spec under `frontend/aesthetic-clinic/e2e/`; run `npx playwright test`. |

## Threat Matrix

N/A — this change does not touch routing, shell commands, subprocesses, VCS/PR automation, executable-file classification, or process integration.

## Migration / Rollout

Migration applies to production with existing `Cliente` rows; the column default `NUEVO` backfills all rows. Rollback via `migrate customers <prev>` drops the column; no data is lost from unrelated fields. No feature flag is needed because the default is harmless.

## Open Questions

None.
