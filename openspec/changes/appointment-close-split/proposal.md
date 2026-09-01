# Proposal: Appointment Close Split

## Why

Today the close flow is single-step. When the admin clicks "Cerrar cita" on `/cms/operaciones/:id`, the backend endpoint `POST /api/admin/citas/<id>/pendiente-biometria/` transitions the cita from `PROGRAMADA` to `REALIZADA_PENDIENTE_VERIFICACION` AND captures the real-time fields (horaRealInicio/Fin, procedimientoRealizado, zonaCuerpoRealizada, attended staff, used machinery) at the same time.

This conflates two operations that are conceptually different:
1. "The session happened, mark it done and wait for the client to confirm."
2. "Here is what actually went on during the session."

The user noticed the asymmetry: `cms/clientes/:id` does only (1) — the button label is "Cambiar a pendiente de verificación" and it sends no body — while `cms/operaciones/:id` does both — the modal label is "Cerrar cita" and it sends the rich real-time payload. The result is inconsistent: the admin can "close" a cita in two different ways depending on which page they used.

Splitting the flow into three explicit steps (status transition, client confirmation, close with real data) restores consistency and matches the actual operational reality: the front desk marks the cita as attended when the client leaves, the client verifies later, and the practitioner fills in the close data after the verification.

## What changes

- The `pendiente-biometria` endpoint stops accepting real-time fields. Body is now ignored entirely. The endpoint becomes a pure state transition `PROGRAMADA → REALIZADA_PENDIENTE_VERIFICACION`.
- A new endpoint `POST /api/admin/citas/<id>/cerrar/` fills in the real-time fields on a `CONFIRMADA` cita. Returns 400 if the cita is not in `CONFIRMADA`.
- `AdminOperationDetailPage` renders different buttons per state:
  - `PROGRAMADA`: a simple "Marcar como pendiente" button (no modal) wired to the existing wrapper.
  - `REALIZADA_PENDIENTE_VERIFICACION`: existing "Confirmar" and "Cancelar verificación" actions.
  - `CONFIRMADA`: a "Cerrar cita" button that opens `CerrarCitaModal` (the renamed/refactored `CloseAppointmentModal`) for capturing real-time fields.
- `AdminClientDetailPage` and `ClientAppointmentSection` render "Marcar como pendiente" on `PROGRAMADA` (already there) and add a "Cerrar cita" button on `CONFIRMADA` in the same action area.
- `CloseAppointmentModal` is renamed to `CerrarCitaModal` to make the action it represents clear.

## Out of scope

- Changing the underlying state machine (`PROGRAMADA → REALIZADA_PENDIENTE_VERIFICACION → CONFIRMADA` stays the same).
- Specialist-side close capture (admin only for v1).
- Notification flows when a cita is closed.
- New views for "what changed" diff between planning and close.
- Migration of existing data — citas already in `REALIZADA_PENDIENTE_VERIFICACION` or `CONFIRMADA` keep their current state; the admin can fill missing real-time fields via the new `cerrar` endpoint later.

## User experience

### Admin flow (cms/operaciones/:id)

1. Admin opens an operation detail page. Sees the list of appointments with their state badges.
2. For a `PROGRAMADA` cita, the action row shows: **Reprogramar reserva**, **Marcar como pendiente** (new label for the existing flow, no modal), **Cancelar reserva**. The "Cerrar cita" button is gone for this state.
3. Admin clicks **Marcar como pendiente**. The existing confirm dialog asks "¿Solo se debe cambiar a este estado cuando el cliente asiste al tratamiento?". On confirm, the cita transitions to `REALIZADA_PENDIENTE_VERIFICACION` with no real-time fields touched.
4. Later (after client verification), the cita transitions to `CONFIRMADA`. The action row updates: **Cerrar cita** appears (new button). Reprogramar and Cancelar are hidden for confirmed citas.
5. Admin clicks **Cerrar cita**. The `CerrarCitaModal` opens with the same fields it had before (horaRealInicio, horaRealFin, procedimientoRealizado, zonaCuerpoRealizada, especialistas, maquinaria), prepopulated from planning data where possible.
6. Admin fills in the actual data and submits. Backend persists. Cita stays `CONFIRMADA` with the new fields populated.

### Admin flow (cms/clientes/:id)

Mirrors the operation-detail flow:
- `PROGRAMADA` → **Marcar como pendiente** (already exists; just renamed for consistency).
- `CONFIRMADA` → **Cerrar cita** (new), opens the same `CerrarCitaModal`.

### Specialist flow

Out of scope for v1.

## Affected users and permissions

- **Admin general / admin de sucursal**: full access to both step-1 (pending) and step-3 (close) actions on citas in their visible scope.
- **Specialist**: read-only on `mis-citas`. Cannot close citas. No change.
- **Cliente**: no change in this change; client-side verification (biometric or manual via `confirmar-biometria`) is unchanged.

## Risks and mitigations

- **Behavior change**: admins who today use the cms/operaciones/:id modal will see the action split. Mitigate with a brief release note and the visible state badges.
- **Idempotency**: closing a CONFIRMADA cita twice must replace the M2M rows, not duplicate them. Mirror the existing `CitaEspecialista(planificada=False) / CitaMaquinaria(planificada=False)` delete-then-bulk-create pattern from the current `pendiente-biometria` endpoint.
- **Existing tests split**: `test_appointment_close_extended.py` (12 tests) covers the merged behavior. We split it into two test classes — one for step-1 (state transition only) and one for step-3 (close with real-time data). No test is dropped; coverage is preserved.
- **Specialist close data**: out of scope for v1; will be tracked as a follow-up.
- **Time precision**: the existing close flow already validates `fin > inicio` and `inicio >= fecha_hora - 1h`. Reuse the validators.

## Rollback plan

- The new endpoint `cerrar/` is additive. Disable it in the routes file if a regression is detected.
- Reverting `pendiente-biometria` to accept real-time fields is a one-line change (remove the body-parsing block). Git revert of PR 1's first commit is the faster rollback.
- The frontend rename is purely cosmetic; revert via `git revert PR 2 commit 2`.

## Open questions

Resolved during planning:

1. **Backend name for step-3 endpoint**: `cerrar` (the Spanish verb for "to close"). Alternatives considered: `finalizar`, `completar`. `cerrar` matches the UI button label.
2. **Permissions**: admin only for v1. The endpoint lives under `/api/admin/citas/`. Specialist extension deferred.
3. **Validation of real-time fields on step-3**: same rules as the current single-step close (`fin > inicio`, `inicio >= fecha_hora - 1h`, `zonaCuerpoRealizada <= 200 chars`). Reuse the validators.

Open:

4. **Re-opening from CONFIRMADA**: should the admin be able to revert a CONFIRMADA cita back to `REALIZADA_PENDIENTE_VERIFICACION` if the close data was wrong? The current `admin_update_appointment_status` allows it. Decision: do not surface a "Reabrir" button in v1; the admin can do it via the existing generic state transition if needed.
5. **Closing with no real-time data** (admin skips everything in the modal): is the cita still considered "closed"? Decision: yes — the close endpoint accepts empty/missing fields and the cita is already CONFIRMADA. The fields just stay empty. No regression.
