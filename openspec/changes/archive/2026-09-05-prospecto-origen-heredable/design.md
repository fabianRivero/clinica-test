# Design: prospecto-origen-heredable

## Technical Approach

- `Prospecto.origen` lives on `Prospecto` in `backend/customers/models.py` as `CharField(max_length=32, choices=Prospecto.Origen.choices, default=NUEVO, db_default="NUEVO")`. Migration `0016_prospecto_origen.py` adds the column; existing rows backfill atomically.
- `AdminProspectCreatePage` lifts `origen` into local state with a two-option required radio as the first `<form>` child (above `primerNombre`); submit stays disabled until chosen. `createAdminProspect` already passes the payload through.
- `admin_crear_prospecto` reads `origen` from JSON, validates against `Prospecto.Origen.choices`, forwards into `Prospecto.objects.create(...)`. Unknown → 400; the "reject unknown fields" guard is preserved.
- `admin_prospect_conversion_finalize` changes ONLY inside `if draft.prospecto:` at the `Cliente.objects.create(...)` call site: line 1877 becomes `origen=draft.prospecto.origen`. The `elif draft.cliente:` branch stays byte-identical.
- `CitaProspecto` cobrable path untouched: the field is metadata, not a state-machine input.

## Architecture Decisions

| # | Decision | Choice | Alternatives | Rationale |
|---|---|---|---|---|
| 1 | Where `Origen` choices live | Separate `Prospecto.Origen(TextChoices)` mirroring `Cliente.Origen` | Import `Cliente.Origen` | Each model self-describing; future divergence stays local. Importing couples across the `cliente-origen` boundary. |
| 2 | Radio placement | Top of form (above `primerNombre`) | Grouped near `Estado inicial` | Spec copy is the gating decision; conversion wizard already places it on top — same UX. |
| 3 | Reuse radio pattern from `ConversionStepUser.tsx` | Mirror `<fieldset class="field field--full origen-fieldset">` verbatim | Build bespoke | Previous change validated markup + selectors; reusing shrinks review surface. |
| 4 | Finalize propagation point | Read `draft.prospecto.origen` at the `Cliente.objects.create(...)` call site inside `if draft.prospecto:` | (a) read once at top, (b) inside branch only | Inside the branch is minimal blast radius: reactivation and direct untouched. Top read forces later `if`; global line tempts leak into reactivation. |
| 5 | Reactivation non-overwrite | `elif draft.cliente:` keeps no reference to `origen`; only `observaciones` is persisted | Add `if False:` guard | Absence is the contract; explicit guard is dead code a contributor might delete. Branch byte-identical; spec satisfied by structure. |

## Data Flow (Prospect Path, Happy)

```
Admin -> /cms/prospectos/nuevo
   v
AdminProspectCreatePage  (origen radio required, submit blocked)
   | POST /api/admin/prospectos/crear/  {"origen": "RECURRENTE_PRE_SISTEMA", ...}
   v
admin_crear_prospecto  -- validates against Prospecto.Origen.choices
   v
Prospecto(origen=RECURRENTE_PRE_SISTEMA, estado=PASAJERO)       [NEW]
   v  (unchanged)
Admin schedules CitaProspecto (cobrable works for any PASAJERO prospect)
   v
AdminProspectConvertPage mode='prospect'  -- step 1 has NO origin radio
   | POST /api/admin/prospectos/{id}/conversion/finalize/
   v
admin_prospect_conversion_finalize
   | if draft.prospecto:                       (prospect branch ONLY)
   |    Cliente.objects.create( ..., origen=draft.prospecto.origen )   [CHANGED]
   v
Cliente(origen=RECURRENTE_PRE_SISTEMA)
```

Reactivation branch untouched: only `observaciones` is written. Direct branch keeps `user_data.get("origen") or Cliente.Origen.NUEVO`.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/customers/models.py` | Modify | Add `Prospecto.Origen(TextChoices)` + `origen` CharField. |
| `backend/customers/migrations/0016_prospecto_origen.py` | Create | Mirror `0015_cliente_origen.py`: deps `0015`, `AddField` on `prospectos.origen`. |
| `backend/config/api_views.py` | Modify | `admin_crear_prospecto` (~line 4725): read `origen`, validate, forward into `Prospecto.objects.create`. |
| `backend/config/prospect_conversion_views.py` | Modify | Line 1877 inside `if draft.prospecto:` becomes `origen=draft.prospecto.origen`. Reactivation (1879–1898) and direct (1959) untouched. |
| `frontend/aesthetic-clinic/src/types/admin.ts` | Modify | `CreateAdminProspectPayload` (line 917) adds `origen?: 'NUEVO' \| 'RECURRENTE_PRE_SISTEMA'`. |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | No-op | `createAdminProspect` already passes payload through. |
| `frontend/aesthetic-clinic/src/pages/admin/AdminProspectCreatePage.tsx` | Modify | Add `origen` to `initialForm`, required radio fieldset as first `<form>` child, gate submit, include in payload. |
| `openspec/specs/cliente-origen/spec.md` | No-op | Delta lives in change folder; archive syncs. |
| `openspec/specs/admin-prospect-conversion/spec.md` | No-op | Same. |

## Interfaces / Contracts

```python
class Prospecto(TimeStampedModel):
    class Origen(models.TextChoices):
        NUEVO = "NUEVO", "Nuevo"
        RECURRENTE_PRE_SISTEMA = "RECURRENTE_PRE_SISTEMA", "Recurrente pre-sistema"
    # ... existing fields ...
    origen = models.CharField(max_length=32, choices=Origen.choices,
                              default=Origen.NUEVO, db_default=Origen.NUEVO)

# migration 0016_prospecto_origen.py — mirrors 0015
class Migration(migrations.Migration):
    dependencies = [("customers", "0015_cliente_origen")]
    operations = [migrations.AddField(
        model_name="prospecto", name="origen",
        field=models.CharField(max_length=32,
            choices=[("NUEVO","Nuevo"),("RECURRENTE_PRE_SISTEMA","Recurrente pre-sistema")],
            default="NUEVO", db_default="NUEVO"),
    )]

# admin_prospect_conversion_finalize — ONE-LINE change inside prospect branch:
cliente = Cliente.objects.create(
    usuario=user, sucursal_origen=target_branch,
    ci=user_data.get("ci",""),
    fecha_nacimiento=date.fromisoformat(user_data["fechaNacimiento"]),
    nro_hijos=int(user_data.get("nroHijos") or 0),
    direccion_domicilio=user_data.get("direccionDomicilio",""),
    telefono=user_data.get("telefono",""),
    ocupacion=user_data.get("ocupacion",""),
    observaciones=user_data.get("observacionesCliente",""),
    origen=draft.prospecto.origen,   # CHANGED: was user_data.get("origen") or NUEVO
)
```

```ts
export type CreateAdminProspectPayload = {
  primerNombre: string; segundoNombre: string
  apellidoPaterno: string; apellidoMaterno: string
  telefono: string
  estado: 'PASAJERO' | 'DESCARTADO'
  observaciones: string
  origen?: 'NUEVO' | 'RECURRENTE_PRE_SISTEMA'   // NEW
}
```

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Backend unit | Migration backfills to `NUEVO`; `admin_crear_prospecto` accepts each value, defaults to `NUEVO` when omitted, rejects unknown with 400; finalize copies `prospecto.origen` into new `Cliente.origen`; reactivation leaves `Cliente.origen` byte-identical (assert via `update_fields`); cobrable `CitaProspecto` unaffected | `python manage.py test` |
| Frontend E2E | Radio blocks submit until chosen; each option persists expected `origen`; conversion produces `Cliente` matching the radio; step 1 stays free of origin radio in `mode='prospect'` | `npx playwright test` |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary touched. The change is a model column, a migration, a view payload field, and a form radio.

## Migration / Rollout

- Migration applies on production DB with existing `prospectos` rows. `db_default="NUEVO"` + `default="NUEVO"` backfills every row in a single non-blocking `ALTER TABLE ... ADD COLUMN ... DEFAULT 'NUEVO' NOT NULL`.
- Rollback: `python manage.py migrate customers 0015_cliente_origen` drops the column. No row data is lost. Frontend revert: drop the radio and the `origen` TS field; `createAdminProspect` keeps working because the backend rejects unknown payload fields (same approach the previous change adopted for `AdminClientProfileWriteSerializer`).
- Feature flag: NOT needed. Migration is reversible and the field is non-breaking (omitting defaults to `NUEVO`).

## Open Questions

None — decisions are locked. `mode='reactivation'` non-overwrite is guaranteed by leaving the branch byte-identical; `mode='direct'` continues to read `user_data.get("origen")`.