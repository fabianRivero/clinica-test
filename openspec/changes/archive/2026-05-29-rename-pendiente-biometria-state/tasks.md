# Tasks: Rename Pendiente Biometria State

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~120–150 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Full implementation | PR 1 | All backend + frontend changes in one PR |

## Phase 1: Backend — Enum Rename + Migration

- [x] 1.1 Create data migration `000X_rename_pending_biometria_data.py` in `backend/operations/migrations/` that runs `UpdateQuery` to set all rows with `estado='REALIZADA_PENDIENTE_BIOMETRIA'` → `'REALIZADA_PENDIENTE_VERIFICACION'` before the schema alter
- [x] 1.2 Create schema migration `000X_alter_citamedica_estado.py` using `AlterField` to rename the enum value in the DB
- [x] 1.3 In `backend/operations/models.py` line 151-156: rename `REALIZADA_PENDIENTE_BIOMETRIA` → `REALIZADA_PENDIENTE_VERIFICACION` and update display label from "Realizada pendiente biometria" → "Realizada Pendiente de Verificación"
- [x] 1.4 In `backend/operations/models.py` line 69: update `sesiones_pendientes_confirmacion` filter to use `REALIZADA_PENDIENTE_VERIFICACION`
- [x] 1.5 In `backend/operations/models.py` lines 215, 221, 245: update all `REALIZADA_PENDIENTE_BIOMETRIA` references in `CitaMedica.clean()` and `CitaMedica.save()`

## Phase 2: Backend — Cancel Endpoint + Updated References

- [x] 2.1 In `backend/config/api/viewsets/operaciones.py` line 453: update `pendiente_biometria` action to set `estado = CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION`
- [x] 2.2 In `backend/config/api/viewsets/operaciones.py` line 520: update `confirmar_biometria` action condition from `REALIZADA_PENDIENTE_BIOMETRIA` → `REALIZADA_PENDIENTE_VERIFICACION`
- [x] 2.3 In `backend/config/api/viewsets/operaciones.py` line 701: update `resolver_conflicto` condition from `REALIZADA_PENDIENTE_BIOMETRIA` → `REALIZADA_PENDIENTE_VERIFICACION`
- [x] 2.4 In `backend/config/api/viewsets/operaciones.py`: add new `cancelar_verificacion` DRF action (POST `/citas/<int:pk>/cancelar-verificacion/`) that validates state is `REALIZADA_PENDIENTE_VERIFICACION`, then sets `estado=PROGRAMADA` and `verif_biometria=False`, returns 200 with `{"detail": ..., "appointment": ...}`; return 400 if state mismatch, 404 if not found
- [x] 2.5 In `backend/config/client_api_views.py` line 34: update `BLOCKING_RESERVATION_STATES` set to use `REALIZADA_PENDIENTE_VERIFICACION`
- [x] 2.6 In `backend/config/client_api_views.py` line 162: update `_appointment_tone` warning condition to use `REALIZADA_PENDIENTE_VERIFICACION`
- [x] 2.7 In `backend/config/client_api_views.py` line 408: update `canConfirmBiometric` condition to use `REALIZADA_PENDIENTE_VERIFICACION`
- [x] 2.8 In `backend/config/client_api_views.py` lines 594, 821, 849, 856, 1009: update all `REALIZADA_PENDIENTE_BIOMETRIA` references to `REALIZADA_PENDIENTE_VERIFICACION`

## Phase 3: Frontend — API Function + Handler

- [x] 3.1 In `frontend/aesthetic-clinic/src/services/api/admin.ts`: add `cancelAdminAppointmentVerification(appointmentId: number)` function that calls `POST /api/admin/citas/${appointmentId}/cancelar-verificacion/` using `requestJsonWithBody<{detail: string}>` (follow pattern from `cancelAdminAppointment` lines 168-173)
- [x] 3.2 In `frontend/aesthetic-clinic/src/pages/admin/client-detail/useClientDetail.ts`: import `cancelAdminAppointmentVerification`, add `handleCancelFromVerification(appointmentId: number)` async handler with confirmation dialog ("¿Está seguro que desea cancelar la verificación?") and success reload
- [x] 3.3 In `frontend/aesthetic-clinic/src/pages/admin/client-detail/useClientDetail.ts`: export `onCancelFromVerification` in return object

## Phase 4: Frontend — UI Button + Integration

- [x] 4.1 In `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientAppointmentSection.tsx`: add `onCancelFromVerification: (id: number) => void` prop
- [x] 4.2 In `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientAppointmentSection.tsx`: add "Cancelar" button next to "Confirmar huella mock" button (lines 99-108), guarded by `appointment.canCancelFromVerification`, with click handler calling `onCancelFromVerification(appointment.rawId)`
- [x] 4.3 In `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientAppointmentSection.tsx`: add `canCancelFromVerification` to the conditional at line 109 so it shows alongside `canConfirmBiometric`

## Phase 5: Verification

- [ ] 5.1 Run Django migrations to verify the enum rename works in DB
- [ ] 5.2 Verify no remaining references to `REALIZADA_PENDIENTE_BIOMETRIA` in the codebase (search)
- [ ] 5.3 Test: `POST /api/admin/citas/:id/cancelar-verificacion/` on an appointment in `REALIZADA_PENDIENTE_VERIFICACION` → returns 200, state reverts to `PROGRAMADA`
- [ ] 5.4 Test: `POST /api/admin/citas/:id/cancelar-verificacion/` on an appointment in `PROGRAMADA` → returns 400
- [ ] 5.5 Test: Cancel button appears in `ClientAppointmentSection` for appointments in the renamed state
- [ ] 5.6 Test: Confirmation dialog appears before API call; cancelling dismisses without API call

## File Summary

| File | Phase | Change |
|------|-------|--------|
| `backend/operations/migrations/0022_rename_pending_biometria_data.py` | 1 | Data patch: rename all rows before schema alter |
| `backend/operations/migrations/0023_alter_citamedica_estado.py` | 1 | Schema alter: rename enum value |
| `backend/operations/models.py` | 1, 2 | Rename enum + update all internal references |
| `backend/config/api/viewsets/operaciones.py` | 2 | Update actions + add `cancelar_verificacion` action |
| `backend/config/client_api_views.py` | 2 | Update all `REALIZADA_PENDIENTE_BIOMETRIA` → `REALIZADA_PENDIENTE_VERIFICACION` |
| `backend/config/api_views.py` | 2 | Additional references updated (canConfirmBiometric condition) |
| `backend/config/api/helpers_operations.py` | 2 | Helper functions updated |
| `backend/config/api/serializers/operaciones.py` | 2 | Serializer choice updated |
| `backend/operations/scheduling.py` | 2 | BLOCKING_RESERVATION_STATES updated |
| `backend/config/api/viewsets/dashboard.py` | 2 | Dashboard queries updated |
| `backend/config/api/viewsets/staff.py` | 2 | Staff queries updated |
| `backend/tests/test_appointment_confirmation_flows.py` | - | Test fixtures updated |
| `backend/operations/tests.py` | - | Test fixtures updated |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | 3 | Add `cancelAdminAppointmentVerification` |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/useClientDetail.ts` | 3, 4 | Add `handleCancelFromVerification`, export handler |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientAppointmentSection.tsx` | 4 | Add Cancel button with prop wiring |
| `frontend/aesthetic-clinic/src/types/common.ts` | 4 | Add `canCancelFromVerification` type |
| `frontend/aesthetic-clinic/src/types/admin.ts` | 4 | Add `canCancelFromVerification` to OperationDetailAppointment |
