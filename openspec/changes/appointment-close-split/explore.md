# Explore: appointment-close-split

## Context

The appointment close flow today is single-step. When the admin clicks "Cerrar cita" (or "Cambiar a pendiente de verificación"), the backend endpoint `POST /api/admin/citas/<id>/pendiente-biometria/` transitions the cita from `PROGRAMADA` to `REALIZADA_PENDIENTE_VERIFICACION` AND captures the real-time fields (horas, procedimiento, zona, staff, maquinaria) at the same time.

The user wants to split this into a multi-step flow:

1. **Step 1 (no data)**: PROGRAMADA → REALIZADA_PENDIENTE_VERIFICACION. The admin marks the cita as "done, awaiting client verification". No real-time fields.
2. **Step 2 (client side or manual)**: REALIZADA_PENDIENTE_VERIFICACION → CONFIRMADA. Existing biometric + manual confirmation flows handle this.
3. **Step 3 (data)**: CONFIRMADA → CONFIRMADA with the real-time fields populated. New endpoint. Captures the same fields that were captured at step 1 before.

Today there is an asymmetry the user noticed: the cms/clientes/:id page calls the no-data version of the endpoint, while cms/operaciones/:id opens a heavy modal that does capture the data. After this change, both pages should be consistent — the close-with-data modal only appears when the cita is `CONFIRMADA`.

## Current behavior

- **Backend close endpoint** — `backend/config/api_views.py:3748-3902` (`admin_mark_appointment_pending_biometric`). Accepts optional `horaRealInicio`, `horaRealFin`, `procedimientoRealizado`, `zonaCuerpoRealizada`, `especialistasAtendieron`, `maquinariaUtilizada`. Transitions to `REALIZADA_PENDIENTE_VERIFICACION` and persists whatever was sent. Idempotent re-close replaces `planificada=False` rows.
- **Backend status update endpoint** — `backend/config/api_views.py:3908-3951` (`admin_update_appointment_status`). Generic state transition. When `CONFIRMADA` is the target, sets `metodo_confirmacion=MANUAL` and creates an `EventoConfirmacionCita`. Useful for the "skip biometric, mark confirmed manually" path.
- **Backend biometric confirm** — `backend/config/api/viewsets/operaciones.py:670-` (`confirmar_biometria` action). Requires `REALIZADA_PENDIENTE_VERIFICACION`, transitions to `CONFIRMADA`, sets `metodo_confirmacion=BIOMETRICO`. Suspended if `BIOMETRIC_SUSPENDED` env is set.
- **Client detail page** — `frontend/aesthetic-clinic/src/pages/admin/client-detail/AdminClientDetailPage.tsx:325-334`. Calls `markAdminAppointmentPendingBiometric` (no body) via `handleMarkPendingBiometric` (in `useClientDetail.ts:226`). Wrapped in a `confirm()` modal that asks "¿Solo cuando el cliente asiste?".
- **Operation detail page** — `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx:866-873` opens `CloseAppointmentModal` (`./components/CloseAppointmentModal.tsx`) which captures the same fields and calls `markAppointmentPendingBiometricExtended`. This is the inconsistency: the two pages do the same state transition but with different payload shapes.
- **Serializers** — `backend/config/api/serializers/operaciones.py` defines `AppointmentStatusUpdateSerializer`, `AppointmentRescheduleSerializer`, `AppointmentBiometricConfirmSerializer`. There is no dedicated serializer for the close payload; the endpoint parses manually.
- **Appointment states** — `backend/operations/models.py:149-157`. `PROGRAMADA | REALIZADA_PENDIENTE_VERIFICACION | CONFIRMADA | CANCELADA | NO_ASISTIO`. The spec at `openspec/specs/appointment-states/spec.md` documents the current machine which we will amend.

## Files that will change

| File | Current role | Change reason |
| --- | --- | --- |
| `backend/config/api_views.py` | Defines `admin_mark_appointment_pending_biometric` (the heavy endpoint) | Strip real-time-field parsing from this endpoint. It becomes a pure state transition. |
| `backend/config/api_urls.py` | Routes `pendiente-biometria` and `actualizar` | Register new `cerrar` endpoint for step 3. |
| `backend/tests/test_appointment_close_extended.py` | Covers the existing single-step close with real-time fields | Split into two test classes: one for step-1 transition (no data), one for step-3 close (with data). Existing 12 tests will move accordingly. |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Has `markAppointmentPendingBiometricExtended` and the simpler `markAdminAppointmentPendingBiometric` | Add new `closeAppointmentWithRealTimeData(appointmentId, payload)` that hits the new `cerrar` endpoint. Keep the simple wrapper as-is for the step-1 call. |
| `frontend/aesthetic-clinic/src/pages/admin/components/CloseAppointmentModal.tsx` | Captures real-time fields + transitions to PENDIENTE | Rename to `CerrarCitaModal` (semantically clearer). Update its `onSuccess` payload type. |
| `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` | Renders the "Cerrar cita" button on PROGRAMADA appointments, opens `CloseAppointmentModal` | Show the new modal only on CONFIRMADA appointments. PROGRAMADA appointments get a simple "Marcar como pendiente" button (no modal) wired to the existing wrapper. |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/AdminClientDetailPage.tsx` | Already has the simple "Cambiar a pendiente de verificación" button on `canMarkPendingBiometric` appointments | Add a "Cerrar cita" button on CONFIRMADA appointments in the same place. |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientAppointmentSection.tsx` | Same pattern as AdminClientDetailPage | Add the same "Cerrar cita" button on CONFIRMADA sessions. |
| `frontend/aesthetic-clinic/src/types/admin.ts` | Defines `AdminCloseExtendedPayload` and `_appointment_item` | Add `estado` (or status field) to the appointment payload so the UI can render the right button per state. |

## Files that will be created

| File | Purpose |
| --- | --- |
| `frontend/aesthetic-clinic/src/pages/admin/components/CerrarCitaModal.tsx` | Renamed and refactored `CloseAppointmentModal`. Same fields (horas, procedimiento, zona, staff, maquinaria) but calls the new `cerrar` endpoint instead of `pendiente-biometria`. |

## Backend contracts to extend

| Endpoint | Current payload | New payload |
| --- | --- | --- |
| `POST /api/admin/citas/<id>/pendiente-biometria/` | Optional real-time fields | Empty body (or none). All real-time fields are silently ignored. Error 400 if the cita is not in `PROGRAMADA`. |

## Backend contracts to add

| Endpoint | Purpose | Payload |
| --- | --- | --- |
| `POST /api/admin/citas/<id>/cerrar/` | Step 3. Fills in the real-time fields on a CONFIRMADA cita. Requires `estado=CONFIRMADA`. | `horaRealInicio`, `horaRealFin` (ISO datetimes; fin > inicio; inicio >= fecha_hora - 1h tolerance), `procedimientoRealizado`, `zonaCuerpoRealizada`, `especialistasAtendieron` (int list), `maquinariaUtilizada` ([{maquinariaId, cantidad}]). Returns 400 if cita is not CONFIRMADA. |

## Patterns to follow

- Use `BLOCKING_RESERVATION_STATES` from `operations/scheduling.py` to determine which `estado` values count as "open".
- Mirror the `CitaEspecialista(planificada=False)` / `CitaMaquinaria(planificada=False)` idempotency pattern from `admin_mark_appointment_pending_biometric` — delete prior rows, bulk_create the new ones.
- Reuse `AppointmentBiometricConfirmSerializer` style (manual JSON parse, response shape `{detail, appointment, operation}`).
- For the frontend, mirror `CloseAppointmentModal`'s `data-testid` and label conventions so the new modal is a drop-in replacement.

## Open questions

1. **Re-opening from CONFIRMADA**: can the admin reopen a CONFIRMADA cita back to REALIZADA_PENDIENTE_VERIFICACION if they need to fix the close data? The current `admin_update_appointment_status` allows any transition, so yes. Should we surface this in the UI?
2. **Re-opening PROGRAMADA**: what happens if the admin mistakenly marks a cita as pendiente and wants to undo? Today there's no "revert to PROGRAMADA" endpoint (just `cancelar-verificacion`). Confirm whether we keep it.
3. **Migration of in-flight citas**: today there are citas already in `REALIZADA_PENDIENTE_VERIFICACION` and `CONFIRMADA` (with or without real-time fields). The new flow lets admins fill missing fields via `cerrar` regardless. No migration needed in the DB — the field is nullable/empty by default.

## Risks

- **Behavior change for current admins**: anyone using the cms/operaciones/:id modal today to set real-time fields will see the modal split into two steps. Document the change in the user-facing release notes.
- **Existing tests need split + rename**: `test_appointment_close_extended.py` was designed around the merged endpoint. We need to carefully move assertions to the new test files without breaking coverage.
- **Permission scope**: the new `cerrar` endpoint should be `admin_required` like the others. Specialist-side: should specialists assigned to the cita also be able to fill in close data? Probably yes, via a dedicated endpoint or by extending the existing specialist API. Out of scope for v1 — admin only.
- **Data loss risk**: if an admin accidentally clicks "Marcar como pendiente" twice in a row, the second click is a no-op (PROGRAMADA → REALIZADA_PENDIENTE_VERIFICACION already done). No risk. Same for cerrar (CONFIRMADA → CONFIRMADA idempotent).
