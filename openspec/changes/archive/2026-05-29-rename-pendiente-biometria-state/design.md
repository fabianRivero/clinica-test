# Design: Rename Pendiente Biometria State

## Technical Approach

Rename `REALIZADA_PENDIENTE_BIOMETRIA` → `REALIZADA_PENDIENTE_VERIFICACION` in the `CitaMedica.Estado` enum, add a cancel-revert endpoint, and wire the frontend cancel button. The backend enum lives in `backend/operations/models.py`, the cancel action goes in `CitasMedicasViewSet` alongside existing actions, and the frontend follows the existing patterns in `ClientAppointmentSection.tsx` and `useClientDetail.ts`.

## Architecture Decisions

### Decision: Migration strategy for enum rename

**Choice**: Data patch migration before schema alter — a two-step Django migration.

**Alternatives considered**:
- Single `AlterField` migration: fails if any row holds the old value in DB-level enum constraint
- Raw SQL migration: works but bypasses Django's migration framework

**Rationale**: The proposal already identifies this risk. Using a data migration first (`UpdateQuery` to set new value) then the schema migration is the safest path and matches what the proposal already planned. The data patch is a `RunSQL` operation that runs before the `AlterField`.

### Decision: New endpoint location

**Choice**: Add `cancelar_verificacion` as a DRF `@action` on `CitasMedicasViewSet` in `operaciones.py`, reusing the same viewset that owns `pendiente_biometria` and `confirmar_biometria`.

**Alternatives considered**:
- Separate viewset: adds URL routing complexity for a single action
- Functional view + url pattern: bypasses existing viewset conventions

**Rationale**: All three appointment action endpoints live in the same viewset (`pendiente_biometria` line 441, `confirmar_biometria` line 511). Following the same pattern keeps routing consistent and reuses existing auth/permissions.

### Decision: Frontend `canCancelFromVerification` flag

**Choice**: Add a new computed flag `canCancelFromVerification` with the same condition as `canConfirmBiometric` (i.e., appointment is in `REALIZADA_PENDIENTE_VERIFICACION`). This keeps the two actions symmetrical and lets the UI decide which buttons to show independently.

**Rationale**: The spec requires both "Confirmar huella mock" and "Cancelar" buttons to appear when the appointment is in that state. Adding a separate flag makes the UI explicit and maintainable.

## Data Flow

```
Admin UI                          Backend                     DB
   │                                │                          │
   ├─ click "Cancelar" ────────────►│                          │
   │   useConfirmDialog (confirm)   │                          │
   │                                ├─ GET /citas/:id ────────►│ verify state
   │                                │◄─ appointment object ────│
   │                                │                          │
   │                                ├─ UPDATE estado=PROGRAMADA►
   │                                │   verif_biometria=false ─►│
   │                                │◄─ saved ─────────────────│
   │◄─ reload() ─────────────────────┤                          │
   │                                │                          │
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/operations/models.py` | Modify | Rename `REALIZADA_PENDIENTE_BIOMETRIA` → `REALIZADA_PENDIENTE_VERIFICACION` in `CitaMedica.Estado` (lines 151-156) |
| `backend/config/api/viewsets/operaciones.py` | Modify | Add `cancel_verificacion` action (POST `/citas/<int:pk>/cancelar-verificacion/`), update `REALIZADA_PENDIENTE_BIOMETRIA` → `REALIZADA_PENDIENTE_VERIFICACION` in `pendiente_biometria` (line 453) and `confirmar_biometria` (line 520) |
| `backend/config/client_api_views.py` | Modify | Update `_appointment_tone` (line 162), `BLOCKING_RESERVATION_STATES` (line 34), and `_appointment_item` (line 408) to use new enum name |
| `frontend/aesthetic-clinic/src/constants/verification.ts` | Modify | Already uses `pendiente_verificacion` (lines 6, 12) — no change needed |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Modify | Add `cancelAdminAppointmentVerification(appointmentId)` function |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/useClientDetail.ts` | Modify | Add `onCancelFromVerification` handler importing `cancelAdminAppointmentVerification` |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientAppointmentSection.tsx` | Modify | Add `onCancelFromVerification` prop, render "Cancelar" button next to "Confirmar huella mock", with `useConfirmDialog` confirmation |
| `backend/operations/migrations/` | Create | Data patch migration + `AlterField` migration for the enum rename |

## Interfaces / Contracts

### Backend: `cancel_verificacion` action

```python
@action(detail=True, methods=["post"], url_path="cancelar-verificacion")
def cancelar_verificacion(self, request, pk=None):
    """
    POST /api/admin/citas/<int:appointment_id>/cancelar-verificacion/
    Revert REALIZADA_PENDIENTE_VERIFICACION -> PROGRAMADA.
    """
    appointment = self._get_appointment(pk)
    if not appointment:
        return Response({"detail": "No encontramos la cita solicitada."}, status=404)
    if appointment.estado != CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION:
        return Response({"detail": "Solo se puede cancelar la verificación de citas pendientes."}, status=400)

    appointment.estado = CitaMedica.Estado.PROGRAMADA
    appointment.verif_biometria = False
    appointment.save(update_fields=["estado", "verif_biometria", "updated_at"])

    return Response({
        "detail": "La verificación fue cancelada. La cita volvió a estado Programada.",
        "appointment": _client_appointment_item(appointment),
    })
```

### Frontend: `cancelAdminAppointmentVerification` API function

```typescript
// admin.ts — follows existing pattern (lines 168-197)
export function cancelAdminAppointmentVerification(appointmentId: number) {
  return requestJsonWithBody<{ detail: string }>(
    `/api/admin/citas/${appointmentId}/cancelar-verificacion/`,
    {},
  )
}
```

### Frontend: `canCancelFromVerification` flag (client-detail endpoint)

```typescript
// In _appointment_item or wherever the admin appointment object is built:
"canCancelFromVerification": appointment.estado == CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `cancelar_verificacion` action: valid transition, wrong state, not found | DRF APIClient test with mocked appointment |
| Unit | Enum rename: no references to old value remain after migration | Search codebase for `REALIZADA_PENDIENTE_BIOMETRIA` — zero matches |
| Integration | Full flow: admin clicks cancel → API called → state reverts → UI reloads | Selenium/admin E2E test |
| Integration | Client API `canConfirmBiometric` condition updated | Test that client dashboard no longer references old enum |

## Migration / Rollout

Two-step Django migration:

1. **Data patch** (`0002_rename_pending_biometria_data.py`): `UPDATE operations_citamedica SET estado='REALIZADA_PENDIENTE_VERIFICACION' WHERE estado='REALIZADA_PENDIENTE_BIOMETRIA'` — runs before `AlterField`
2. **Schema alter** (`0003_alter_citamedica_estado.py`): `AlterField` from `REALIZADA_PENDIENTE_BIOMETRIA` → `REALIZADA_PENDIENTE_VERIFICACION`

No downtime required with the two-step approach — the data patch commits before the constraint changes.

## Open Questions

- [ ] None — all decisions are captured above.