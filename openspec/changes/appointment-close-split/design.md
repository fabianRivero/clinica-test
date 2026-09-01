# Design: Appointment Close Split

## Overview

This document is the technical architecture for splitting the appointment close flow into a no-data state transition and a separate real-data close. It complements the proposal and the spec by spelling out HOW the spec is implemented: backend endpoint split, frontend wiring, sequence flows, and edge cases.

## Architecture decisions

| # | Decision | Rationale |
| --- | --- | --- |
| AD1 | `pendiente-biometria` keeps the same URL and name but stops parsing the body. Existing callers that send a body silently get their fields ignored. No new endpoint-versioning needed. | The spec calls the step "Cambiar a pendiente de verificación" which matches the existing endpoint name. Reusing the URL preserves the contract with current FE wrappers. |
| AD2 | New endpoint URL is `/api/admin/citas/<int:appointment_id>/cerrar/`. Verb matches the UI button label ("Cerrar cita"). | Clear semantic mapping between action and endpoint. |
| AD3 | `cerrar` requires `estado=CONFIRMADA`. The transition `CONFIRMADA → CONFIRMADA` is a no-op state-wise; the endpoint only persists the close data. | The state transition `REALIZADA_PENDIENTE_VERIFICACION → CONFIRMADA` is owned by the existing biometric / manual confirmation flows. This change does not touch them. |
| AD4 | Reuse the idempotency pattern from `admin_mark_appointment_pending_biometric`: delete prior `CitaEspecialista(planificada=False)` and `CitaMaquinaria(planificada=False)` rows for the cita, then `bulk_create` the new ones. | Avoids duplicate rows on repeated close. Mirrors the existing close semantics. |
| AD5 | No data migration. Existing citas in `REALIZADA_PENDIENTE_VERIFICACION` or `CONFIRMADA` keep whatever state they have. The admin can backfill missing real-time fields via `cerrar` later. | Minimum disruption. The fields are nullable / empty by default. |
| AD6 | The frontend modal is renamed from `CloseAppointmentModal` to `CerrarCitaModal` and moves its mount point from `PROGRAMADA` (current) to `CONFIRMADA` (new). The old "Cerrar cita" button on `PROGRAMADA` is replaced by a simple in-place button that calls the no-body wrapper (no modal). | Clearer mental model. The button label and the modal title reflect the same action. |
| AD7 | Buttons per state are rendered declaratively from `appointment.estado`. No imperative "what does this button do" branching in the page. | Easier to extend later (e.g. NO_ASISTIO close flow). |
| AD8 | All close-with-data logic stays server-side; the frontend only validates `cantidad > cantidadTotal` for inline UX (matches the existing stock check from `appointment-reservation-redesign`). | Server-side enforcement is canonical; frontend checks are advisory only. |

## Data model

No changes to `CitaMedica` itself. The 11 fields added by `appointment-reservation-redesign` stay:

| Field | When populated |
| --- | --- |
| `procedimiento_planificado`, `zona_cuerpo_planificada`, `duracion_estimada_minutos` | At reservation (planning). |
| `hora_real_inicio`, `hora_real_fin`, `procedimiento_realizado`, `zona_cuerpo_realizada` | At `cerrar` (step 3). |
| `descripcion_general`, `notas_previas`, `notas_post`, `foto_antes`, `foto_despues` | Any time via PATCH `/citas/<id>/notas/`. |

`CitaEspecialista(planificada=True)` rows are created at reservation (planning). `CitaEspecialista(planificada=False)` rows are created at `cerrar` (real attendance).

`CitaMaquinaria(planificada=True)` rows are created at reservation (planning). `CitaMaquinaria(planificada=False)` rows are created at `cerrar` (real usage).

## API surface

### Endpoint changes

| Method + Path | Current state | New state |
| --- | --- | --- |
| `POST /api/admin/citas/<id>/pendiente-biometria/` | Accepts real-time fields and transitions state | Same URL, but **body is ignored**. Only transitions `PROGRAMADA → REALIZADA_PENDIENTE_VERIFICACION`. |
| `POST /api/admin/citas/<id>/cerrar/` | (does not exist) | **New endpoint**. Persists real-time fields and M2M rows on `CONFIRMADA` citas. Does NOT change state. |
| `POST /api/admin/citas/<id>/confirmar-biometria/` | Unchanged | Unchanged (out of scope). |
| `PATCH /api/admin/citas/<id>/notas/` | Unchanged | Unchanged (out of scope). |

### New endpoint: `admin_cerrar_cita`

```python
@require_POST
@admin_required
@transaction.atomic
def admin_cerrar_cita(request, appointment_id):
    cita = CitaMedica.objects.select_related(
        "operacion__paciente__usuario",
        ...
    ).filter(pk=appointment_id).first()

    if not cita:
        return json_response({"detail": "No encontramos la cita solicitada."}, status=404)

    if cita.estado != CitaMedica.Estado.CONFIRMADA:
        return json_response(
            {"detail": "Solo se pueden cerrar citas confirmadas."}, status=400
        )

    payload = parse_json_or_form(request)
    errors = {}

    # ... (parse + validate horaRealInicio/Fin, procedimientoRealizado,
    #      zonaCuerpoRealizada, especialistasAtendieron, maquinariaUtilizada)
    #      Same validators as the old single-step close: fin > inicio,
    #      inicio >= fecha_hora - 1h, zona <= 200 chars, cantidad >= 1.

    if errors:
        return json_response({"detail": "Datos invalidos.", "errors": errors}, status=400)

    # Persist text fields (only if sent, so we don't overwrite absent fields).
    if hora_real_inicio:
        cita.hora_real_inicio = hora_real_inicio
    if hora_real_fin:
        cita.hora_real_fin = hora_real_fin
    if procedimiento_realizado:
        cita.procedimiento_realizado = procedimiento_realizado
    if zona_cuerpo_realizada:
        cita.zona_cuerpo_realizada = zona_cuerpo_realizada
    cita.save()

    # Replace M2M rows (idempotent re-close).
    CitaEspecialista.objects.filter(cita=cita, planificada=False).delete()
    if especialistas_atendieron:
        CitaEspecialista.objects.bulk_create([
            CitaEspecialista(cita=cita, especialista_id=esp_id, planificada=False)
            for esp_id in especialistas_atendieron
        ])
    CitaMaquinaria.objects.filter(cita=cita, planificada=False).delete()
    if maquinaria_utilizada_raw:
        CitaMaquinaria.objects.bulk_create([
            CitaMaquinaria(
                cita=cita,
                maquinaria_id=item["maquinariaId"],
                cantidad=int(item.get("cantidad", 1)),
                planificada=False,
            ) for item in maquinaria_utilizada_raw
        ])

    return json_response({
        "detail": "La cita quedo cerrada con los datos reales.",
        "appointment": _client_appointment_item(cita),
        "operation": _operation_detail(cita.operacion),
    })
```

### Updated endpoint: `admin_mark_appointment_pending_biometric`

Strips the body-parsing block. The body is still read for backward compat (so a caller that sends `{}` works), but every real-time field is ignored. The handler is reduced to ~30 lines: select cita, validate state, set state to `REALIZADA_PENDIENTE_VERIFICACION`, save, return.

### URL routing

`backend/config/api_urls.py`: add a new line inside the existing `citas/<int:appointment_id>/...` URL group:

```python
path(
    "citas/<int:appointment_id>/cerrar/",
    admin_cerrar_cita,
    name="admin-appointment-cerrar-api",
),
```

The path is registered AFTER the existing `pendiente-biometria/` path so Django's resolver picks the more specific match first. (Actually order does not matter here since the slugs are different — Django matches literal segments exactly.)

### Permission model

| Role | pendiente-biometria | cerrar |
| --- | --- | --- |
| Admin principal | Yes | Yes |
| Admin de sucursal | Yes (own branch scope) | Yes (own branch scope) |
| Specialist | No | No |
| Cliente (biometric) | No | No (only `confirmar-biometria`) |

Closure rule: `cerrar` requires the cita to be in `CONFIRMADA`. That state is reachable only via the existing biometric / manual confirmation flows, which have their own permission scopes. So the role surface for `cerrar` is the same as `confirmar-biometria`: admins only.

## Frontend changes

### Service layer

`frontend/aesthetic-clinic/src/services/api/admin.ts`: add a new wrapper alongside `markAppointmentPendingBiometricExtended`:

```ts
export function closeAppointmentWithRealTimeData(
  appointmentId: number,
  payload: AdminCloseExtendedPayload,
) {
  return requestJsonWithBody<unknown>(
    `/api/admin/citas/${appointmentId}/cerrar/`,
    payload,
  )
}
```

The existing `markAppointmentPendingBiometric` (simple, no body) and `markAppointmentPendingBiometricExtended` (with body) stay unchanged. We mark the latter as deprecated; the new `closeAppointmentWithRealTimeData` is the canonical way to send the real-time payload going forward. The frontend still uses the simple wrapper for the "Marcar como pendiente" button on `PROGRAMADA` citas.

### Component rename and behavior split

`CloseAppointmentModal.tsx` → `CerrarCitaModal.tsx` (new file, same code path, updated prop names):

- Rename the component export `CloseAppointmentModal` → `CerrarCitaModal`.
- Rename the prop type `CloseAppointmentCita` → `CerrarCitaPayload`.
- Update the `onSubmit` callback name to `onClose` (avoids confusion with the cita-close action).
- Keep all existing validation (cantidad > stock, duration mismatch warning).

The new file is created by copy-paste from the old one. The old `CloseAppointmentModal.tsx` is deleted in the same commit so imports are unambiguous.

### Button matrix in `AdminOperationDetailPage`

Currently the page renders:

```
[PROGRAMADA]: Reprogramar reserva | Cerrar cita (modal) | Cancelar reserva
```

After this change:

```
[PROGRAMADA]: Reprogramar reserva | Marcar como pendiente (no modal) | Cancelar reserva
[REALIZADA_PENDIENTE_VERIFICACION]: Confirmar | Cancelar verificación
[CONFIRMADA]: Cerrar cita (CerrarCitaModal)
```

Implementation: a single `switch(appointment.estado)` returns the JSX for each state. Replace the current `appointment.canManage && appointment.status?.toLowerCase?.() === 'programada'` ternary with the switch.

The state badges that already render (`<StatusBadge tone={appointment.statusTone}>`) stay unchanged.

### Button matrix in `AdminClientDetailPage` and `ClientAppointmentSection`

Currently both pages render only the "Cambiar a pendiente de verificación" button (when `canMarkPendingBiometric`). Add a second button "Cerrar cita" for `CONFIRMADA` citas.

The conditional is currently `appointment.canMarkPendingBiometric` (a flag from the backend response). We add a parallel flag `canCloseAppointment` (or compute it from `status === 'Confirmada'`). The detail page already receives `session` objects from the backend; we add the close button gated on `status === 'Confirmada' && canManage` (or similar).

## Sequence flows

### Step 1: Mark as pending (cms/clientes/:id and cms/operaciones/:id)

```
Admin clicks "Marcar como pendiente"
  → confirm() modal: "¿Solo cuando el cliente asiste?"
    → markAdminAppointmentPendingBiometric(citaId)        # body = {}
      → POST /api/admin/citas/<id>/pendiente-biometria/
        → backend: transition to REALIZADA_PENDIENTE_VERIFICACION
      ← 200 { detail, appointment{estado: "Realizada..."} }
    ← reload() → UI re-renders with new state badge
```

### Step 2: Client confirms (separate flow, out of scope)

```
Client uses biometric flow OR admin clicks "Confirmar" (manual):
  → existing flow: REALIZADA_PENDIENTE_VERIFICACION → CONFIRMADA
  → existing flow: creates EventoConfirmacionCita
```

### Step 3: Close with real data (cms/operaciones/:id)

```
Admin opens operation detail. Cita is CONFIRMADA.
  → Admin clicks "Cerrar cita"
    → CerrarCitaModal opens with planning-data prepopulation
      → Admin edits horaRealInicio, horaRealFin, procedimiento, zona, staff, maquinaria
      → Admin submits
        → closeAppointmentWithRealTimeData(citaId, payload)
          → POST /api/admin/citas/<id>/cerrar/
            → backend: persists real-time fields + M2M rows
              → backend: cita stays CONFIRMADA
          ← 200 { detail, appointment{estado: "Confirmada"}, operation }
        ← UI re-renders with the new fields populated
```

### Idempotent re-close

```
Admin clicks "Cerrar cita" again with different staff/maquinaria
  → CerrarCitaModal opens prepopulated with the LAST close data (admin can see what was previously entered)
    → Admin changes staff from [3] to [3, 7]
      → Admin submits
        → backend: CitaEspecialista(planificada=False) for [3] is DELETED, [3, 7] is CREATED
        → backend: CitaMaquinaria(planificada=False) old rows DELETED, new ones CREATED
      ← 200
```

## Migrations

None. The 11 real-time fields already exist on `CitaMedica`. The CitaEspecialista / CitaMaquinaria tables already exist. No schema change.

## Settings & dependencies

No new dependencies. No settings change. No `MEDIA_ROOT` change.

## Tests

### Backend (Django unittest)

| File | Coverage |
| --- | --- |
| `backend/tests/test_appointment_close_split.py` (NEW) | Replaces/splits the 12 tests in `test_appointment_close_extended.py`. |
| `backend/tests/test_appointment_close_extended.py` (DELETE) | All 12 tests move to the new file. We delete the old file because the merged endpoint no longer exists. |

The new test file is split into two `TestCase` classes:

#### `PendienteBiometriaSplitTests` (step 1, no data)

| Test | Verifies |
| --- | --- |
| `test_empty_body_transitions_to_pendiente` | cita moves to REALIZADA_PENDIENTE_VERIFICACION with empty real-time fields |
| `test_body_with_real_time_data_is_ignored` | Fields in body are NOT persisted; cita transitions |
| `test_wrong_state_returns_400` | cita already in CONFIRMADA returns 400 |
| `test_missing_cita_returns_404` | unknown id returns 404 |
| `test_preserves_existing_real_time_data_when_called_again` | Re-call preserves any previously-persisted real-time data (we no longer overwrite) |

#### `CerrarCitaTests` (step 3, with data)

| Test | Verifies |
| --- | --- |
| `test_close_confirmada_persists_all_fields` | Full payload persists everything |
| `test_close_empty_body_accepted` | Empty body does not overwrite existing data |
| `test_close_wrong_state_returns_400` | PROGRAMADA / PENDIENTE / CANCELADA all return 400 |
| `test_close_missing_cita_returns_404` | unknown id returns 404 |
| `test_close_is_idempotent` | Re-close replaces M2M rows |
| `test_invalid_hour_range_returns_400` | fin <= inicio rejected |
| `test_inicio_before_scheduled_minus_one_hour_returns_400` | inicio < fecha_hora - 1h rejected |

Combined coverage: the 12 existing scenarios plus the split + close paths preserved.

### Frontend

No new Playwright tests added in this change. Existing `test_appointment_reservation_extended.py` (Playwright) does not exercise close flow. Out of scope to add E2E here — manual smoke test per the change risk.

## Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Existing call sites to `pendiente-biometria` that send real-time data silently lose those fields | Document in the proposal and the archive report. Admins can backfill via `cerrar`. |
| CitaMedica.save() in `cerrar` re-runs the validation in `CitaMedica.clean()`. With new fields set, it might trip the `metodo_confirmacion` check if estado is wrong. | We guard with `estado == CONFIRMADA` upfront, so the validation is no-op. |
| Specialists see the close button on the mis-citas page (they shouldn't) | Confirm via spec review that the specialist view is read-only. The new "Cerrar cita" button is only added to admin pages, not the mis-citas page. |
| Re-opening CONFIRMADA → REALIZADA_PENDIENTE_VERIFICACION is needed to fix wrong close data | Out of scope for v1. The admin can use `admin_update_appointment_status` directly if needed. |
| The new endpoint's `cerrar` URL name collides with any future "cerrar caja" or similar endpoint | Use the specific URL `citas/<id>/cerrar/` to scope. |
| Tests folder organization: deleting `test_appointment_close_extended.py` and creating `test_appointment_close_split.py` | Acceptable since the merged behavior is gone. Document in the commit message. |

## Out of scope (explicit)

- Specialist-side close capture (would need a new specialist endpoint + UI).
- New permissions on `cerrar` for assigned specialists.
- Closing citas in `REALIZADA_PENDIENTE_VERIFICACION` directly (would skip the confirmation step). The new flow enforces the confirmation-first contract.
- Closing multiple citas at once (bulk close).
- Audit log entry for the close event (the existing `CitaMedica.save()` does not emit one).
- iCal / email notifications when a cita is closed.
