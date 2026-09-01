# Tasks: Appointment Close Split

## Phase 0 — Bootstrap

No work in this phase. The branch already exists with the `appointment-reservation-redesign` changes merged. Pillow is installed. MEDIA serving is wired.

## Phase 1 — Backend split (PR 1)

### Phase 1.1 — Strip pendiente-biometria

- [ ] **1.1.1** Strip the body-parsing block (real-time fields, M2M replace) from `admin_mark_appointment_pending_biometric` in `backend/config/api_views.py`. The handler now reads no body, validates `estado==PROGRAMADA`, sets estado, and returns. ~30 LOC.
- [ ] **1.1.2** Keep the response shape unchanged: `{detail, appointment, operation}`. The `appointment` continues to use `_client_appointment_item`.

### Phase 1.2 — New cerrar endpoint

- [ ] **1.2.1** Add `admin_cerrar_cita(request, appointment_id)` in `backend/config/api_views.py`. Decorators: `@require_POST`, `@admin_required`, `@transaction.atomic`.
- [ ] **1.2.2** Validate: cita exists (else 404), `estado == CONFIRMADA` (else 400), `horaRealFin > horaRealInicio` if both set, `horaRealInicio >= fecha_hora - 1h`, `zonaCuerpoRealizada` length <= 200, `maquinariaUtilizada[*].cantidad >= 1`. Reuse the validation helpers / patterns from the stripped pendiente-biometria.
- [ ] **1.2.3** Persist real-time fields only if sent (preserve existing values when omitted). Mirror the delete-then-bulk_create pattern for `CitaEspecialista(planificada=False)` and `CitaMaquinaria(planificada=False)`.
- [ ] **1.2.4** Return shape: `{detail: "La cita quedo cerrada con los datos reales.", appointment: _client_appointment_item(cita), operation: _operation_detail(cita.operacion)}`. Status 200.

### Phase 1.3 — URL routing

- [ ] **1.3.1** In `backend/config/api_urls.py`, add `path("citas/<int:appointment_id>/cerrar/", admin_cerrar_cita, name="admin-appointment-cerrar-api")` next to the existing pendiente-biometria path.
- [ ] **1.3.2** Add `admin_cerrar_cita` to the `from config.api_views import (...)` block.

### Phase 1.4 — Tests

- [ ] **1.4.1** Create `backend/tests/test_appointment_close_split.py` with two `TestCase` classes: `PendienteBiometriaSplitTests` (5 tests) and `CerrarCitaTests` (7 tests). Each test gets the cita + operacion + sucursal + admin fixtures it needs via `setUp`.
- [ ] **1.4.2** Delete `backend/tests/test_appointment_close_extended.py`. The 12 tests there are migrated to the new file. No scenario is dropped.
- [ ] **1.4.3** Run `python manage.py test tests.test_appointment_close_split tests.test_maquinaria_conflicts tests.test_maquinaria_catalog tests.test_appointment_reservation_extended tests.test_especialista_mis_citas -v 2`. All 12 + 31 existing tests must pass.

### Phase 1.5 — Commit strategy

PR 1 must consist of:

1. `refactor(api): strip real-time field capture from pendiente-biometria`
2. `feat(api): add POST /api/admin/citas/<id>/cerrar/ for real-time capture`
3. `test(close): split close tests into pendiente + cerrar suites`

Each commit scoped and reviewable.

## Phase 2 — Frontend split (PR 2)

### Phase 2.1 — Service wrapper

- [ ] **2.1.1** In `frontend/aesthetic-clinic/src/services/api/admin.ts`, add `closeAppointmentWithRealTimeData(appointmentId, payload)` that POSTs to `/api/admin/citas/<id>/cerrar/`.
- [ ] **2.1.2** Keep `markAdminAppointmentPendingBiometric` (no body) as the canonical wrapper for step-1. Mark `markAppointmentPendingBiometricExtended` (with body) as deprecated; it is no longer called by the frontend after this change. Optionally delete the wrapper to keep the API surface clean.

### Phase 2.2 — Modal rename

- [ ] **2.2.1** Create `frontend/aesthetic-clinic/src/pages/admin/components/CerrarCitaModal.tsx` by copying `CloseAppointmentModal.tsx` and renaming:
  - `export function CloseAppointmentModal` → `export function CerrarCitaModal`
  - `export interface CloseAppointmentCita` → `export interface CerrarCitaPayload`
  - `onSubmit` prop → `onClose` (rename for clarity)
  - Internal call switches from `markAppointmentPendingBiometricExtended` → `closeAppointmentWithRealTimeData`
- [ ] **2.2.2** Delete `frontend/aesthetic-clinic/src/pages/admin/components/CloseAppointmentModal.tsx` in the same commit so imports are unambiguous.

### Phase 2.3 — Wire buttons per state (AdminOperationDetailPage)

- [ ] **2.3.1** Replace the current ternary that renders "Cerrar cita" button on `PROGRAMADA` with a `switch(appointment.estado)` that returns:
  - `PROGRAMADA`: Reprogramar reserva | Marcar como pendiente (no modal) | Cancelar reserva
  - `REALIZADA_PENDIENTE_VERIFICACION`: Confirmar | Cancelar verificación
  - `CONFIRMADA`: Cerrar cita (opens `CerrarCitaModal`)
- [ ] **2.3.2** Add `closingAppointmentId` state. The "Marcar como pendiente" button calls `markAdminAppointmentPendingBiometric(appointment.rawId)` directly (no modal).
- [ ] **2.3.3** Mount `<CerrarCitaModal>` only when `closingAppointmentId !== null` and the corresponding cita is `CONFIRMADA`. The modal receives the full cita payload (planning data prepopulates the form fields).

### Phase 2.4 — Wire buttons per state (AdminClientDetailPage and ClientAppointmentSection)

- [ ] **2.4.1** In both pages, add a "Cerrar cita" button next to "Cancelar reserva" when the cita is in `CONFIRMADA`. The button calls the same handler as `handleMarkPendingBiometric` but with a different endpoint — or we factor out a `handleCloseAppointment(citaId)` that opens a separate modal. To keep the change scoped, mount `<CerrarCitaModal>` in each page (similar to how `<CloseAppointmentModal>` was never used here).
- [ ] **2.4.2** Update the action row condition to also handle `canCloseAppointment` (or `status === 'Confirmada'`).

### Phase 2.5 — Smoke test

- [ ] **2.5.1** Run `cd frontend/aesthetic-clinic && npx tsc -b --noEmit`. Expect no new errors (the pre-existing `AdminOperationDetailPage.tsx:174` error remains).
- [ ] **2.5.2** Manual smoke: log in as admin, open an operation detail, observe the new button matrix:
  - Confirmada cita shows "Cerrar cita" → opens CerrarCitaModal with planning prepopulated → submit succeeds.
  - Programada cita shows "Marcar como pendiente" → click transitions state without modal.
  - Real-time pendiente cita shows "Confirmar" / "Cancelar verificación".

### Phase 2.6 — Commit strategy

PR 2 must consist of:

1. `feat(frontend): add closeAppointmentWithRealTimeData service wrapper`
2. `refactor(frontend): rename CloseAppointmentModal to CerrarCitaModal and switch endpoint`
3. `feat(frontend): wire per-state action buttons in operation + client detail pages`

Each commit scoped and reviewable.

## Done criteria

- All tests green: 12 backend tests in `test_appointment_close_split.py` plus the 31 existing tests across catalog / conflicts / reservation / specialist APIs.
- TypeScript build clean (only the pre-existing unrelated error).
- Manual smoke test of the new flow on a real cita: Programada → Marcar como pendiente → (separate flow) Confirmar → Cerrar cita → modal persists data.

## Estimated complexity

| Phase | LOC (est.) | Risk |
| --- | --- | --- |
| 1.1 | ~ -80 (strip) | low |
| 1.2 | ~ +110 | low |
| 1.3 | ~ +5 | low |
| 1.4 | ~ +250 | medium |
| 2.1 | ~ +20 | low |
| 2.2 | ~ +0 (rename + body change) | low |
| 2.3 | ~ +30 | medium |
| 2.4 | ~ +30 | medium |

Total estimate: +365 LOC. Within 400-LOC budget per PR when split correctly.

## Suggested slicing (within the 400-LOC budget)

| PR | Commits | LOC | Focus |
| --- | --- | --- | --- |
| PR 1 | 3 | ~ +285 | Backend split + tests |
| PR 2 | 3 | ~ +80 | Frontend rename + button matrix |

Both PRs fit within the standard 400-LOC budget. PR 1 might exceed slightly because the new test class is large (~250 LOC); if so, split into PR 1a (backend code) and PR 1b (tests). No `size:exception` required at the current estimates.
