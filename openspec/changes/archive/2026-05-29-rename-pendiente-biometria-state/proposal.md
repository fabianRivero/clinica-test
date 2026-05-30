# Proposal: Rename Pendiente Biometria State

## Intent

Replace the misleading `REALIZADA_PENDIENTE_BIOMETRIA` label ("Realizada pendiente biometria") with `REALIZADA_PENDIENTE_VERIFICACION` ("Realizada Pendiente de Verificación") across the codebase, and add a cancel endpoint to revert this state back to `PROGRAMADA`.

## Scope

### In Scope
- Rename the `REALIZADA_PENDIENTE_BIOMETRIA` enum value to `REALIZADA_PENDIENTE_VERIFICACION` in `backend/operations/models.py`
- Rename `REALIZADA_PENDIENTE_BIOMETRIA` in frontend constants/labels used by `ClientAppointmentSection.tsx`
- Add `POST /api/admin/citas/:id/cancelar-verificacion/` endpoint that reverts `REALIZADA_PENDIENTE_VERIFICACION` → `PROGRAMADA`
- Add cancel button next to "Confirmar huella mock" in `ClientAppointmentSection.tsx` when in this state, with "¿Está seguro?" confirmation dialog

### Out of Scope
- Changing other states or the appointment state machine logic (beyond the revert path described above)
- Notification triggers related to state changes
- Any changes to biometric confirmation flow beyond the rename

## Capabilities

### New Capabilities
- `verification-cancel`: Backend endpoint to revert an appointment from `REALIZADA_PENDIENTE_VERIFICACION` to `PROGRAMADA`

### Modified Capabilities
- `appointment-states`: The `REALIZADA_PENDIENTE_BIOMETRIA` state is renamed to `REALIZADA_PENDIENTE_VERIFICACION` — label changes and revert path added

## Approach

**Backend**:
1. Rename `REALIZADA_PENDIENTE_BIOMETRIA` → `REALIZADA_PENDIENTE_VERIFICACION` in `backend/operations/models.py`
2. Add new DRF action `cancelar_verificacion` in `CitasMedicasViewSet` (or a separate viewset if appropriate), path: `citas/<int:appointment_id>/cancelar-verificacion/`
3. The action validates the appointment is in `REALIZADA_PENDIENTE_VERIFICACION`, then sets `estado = PROGRAMADA` and saves

**Frontend**:
1. In `ClientAppointmentSection.tsx`, add new button next to "Confirmar huella mock" that:
   - Shows a confirmation dialog ("¿Está seguro que desea cancelar la verificación?")
   - On confirm: calls `POST /api/admin/citas/:id/cancelar-verificacion/`
   - On success: reloads appointment data (already handled by parent via callback)
2. Update any frontend constants that reference the old state name

**Data migration**: A migration is needed to rename the enum value in the database from `REALIZADA_PENDIENTE_BIOMETRIA` to `REALIZADA_PENDIENTE_VERIFICACION`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/operations/models.py` | Modified | Rename `REALIZADA_PENDIENTE_BIOMETRIA` → `REALIZADA_PENDIENTE_VERIFICACION` enum value |
| `backend/config/api/viewsets/operaciones.py` | Modified | Add `cancelar_verificacion` action endpoint |
| `backend/config/urls.py` (or api_urls) | Modified | Register new cancel endpoint |
| `frontend/.../constants/verification.ts` (or similar) | Modified | Rename state constant and label |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientAppointmentSection.tsx` | Modified | Add cancel button with confirmation dialog |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Database migration to rename enum value may cause downtime | Medium | Use Django migration with `AlterField`; plan maintenance window or use a no-op data migration approach |
| Active appointments in `REALIZADA_PENDIENTE_BIOMETRIA` state become invalid after rename | Medium | Pre-migration data patch: update all existing rows to new value before applying schema migration |
| Cancellation called on wrong state could corrupt appointment data | Low | Endpoint validates current state is `REALIZADA_PENDIENTE_VERIFICACION` before updating |

## Rollback Plan

1. **Backend rollback**: Revert `CitaMedica.Estado` enum rename via Django migration — generate a new migration that reverts the field rename
2. **Endpoint rollback**: Remove the `cancelar_verificacion` action (code-only change, no migration needed)
3. **Frontend rollback**: Revert constant rename and remove cancel button
4. **Data rollback**: Pre-migration data patch approach means if rollback is needed, run a data patch to restore `REALIZADA_PENDIENTE_BIOMETRIA` before reverting the schema

## Dependencies

- Django 5.2.8 with DRF
- Existing `POST /citas/<int:appointment_id>/pendiente-biometria/` endpoint as reference for the new cancel endpoint

## Success Criteria

- [ ] `REALIZADA_PENDIENTE_VERIFICACION` is the new enum value in `CitaMedica.Estado`
- [ ] `POST /api/admin/citas/:id/cancelar-verificacion/` returns 200 on valid state transition and 400 otherwise
- [ ] Cancel button appears in `ClientAppointmentSection` when `canConfirmBiometric` is true
- [ ] Confirmation dialog prevents accidental cancellation
- [ ] Existing appointments in old state are migrated before schema change
- [ ] No broken references to the old enum value in codebase
