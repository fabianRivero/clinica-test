# Explore — appointment-reservation-redesign

## Context

The current reservation flow only collects tratamiento + fecha + hora and confirms inline, with a single button that moves the cita to `REALIZADA_PENDIENTE_VERIFICACION`. We are reshaping the booking flow so each reservation captures richer planning data (duración estimada, procedimiento planificado, zona del cuerpo, especialistas esperados, maquinaria esperada), and so the close modal captures the actual outcome (horas reales, procedimiento realizado, zona, especialistas que atendieron, maquinaria usada). A new `Maquinaria` catalog supports the per-appointment resource selection, with admin-general and admin-de-sucursal scopes. Specialists gain a read-only "Mis citas" view. The flow preserves existing availability-of-specialists and nearby-appointments visibility; conflicts on machinery are WARN-only (admin decides).

## Current behavior

- **Reservation from client detail** — `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientReservationSection.tsx:42-124`. Inline form with select tratamiento + date + time + "Verificar disponibilidad" + result panel + "Confirmar reserva". Hook in `useClientDetail.ts:422-447` calls `createAdminClientReservation` with `{ branchId, dateTime }`.
- **Reservation from operation detail** — `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx:829-889`. Same UX inline; `handleCheckReservation` and `handleReserve` around lines 200-260.
- **Free medical appointment** — `backend/config/api/viewsets/clientes.py:579` `FreeMedicalAppointmentViewSet` (out of scope; we only touch `OperationReservationCreateSerializer`-backed routes and `pendiente-biometria`).
- **Reservation endpoint** — `backend/config/api/viewsets/clientes.py:525-572`. `POST /api/admin/clientes/<id>/operaciones/<opId>/reservar/`. Body: `{ branchId, dateTime }`. Creates `CitaMedica` with `estado=PROGRAMADA` and a fixed `detalles_cita` string.
- **Serializer** — `backend/config/api/serializers/clientes.py:175-188` `OperationReservationCreateSerializer`.
- **Availability check** — `backend/config/admin_availability_views.py:325-382` `admin_check_concurrency`. Returns `concurrency`, `hora_inicio`, `hora_fin`, `appointments`, `presentes` (specialists in shift at that moment).
- **Concurrency helpers** — `backend/operations/scheduling.py:88-200`: `get_concurrency`, `get_concurrency_detail`, `get_specialists_present`.
- **Close / pendiente-biometria** — `backend/config/api/viewsets/operaciones.py:589-610`. Currently accepts no body. Sets `estado=REALIZADA_PENDIENTE_VERIFICACION`, `verif_biometria=False`, and a fixed `detalles_cita`.
- **Estado machine spec** — `openspec/specs/appointment-states/spec.md`. We will EXTEND this spec, not replace it; new fields/state behaviors are additive.
- **Models** — `backend/operations/models.py:132-274` `CitaMedica`. We add fields to this model. `backend/catalogs/models.py:1-287` shows the catalog patterns (`CatalogoEditableModel`, `Sucursal`, `ProcEstetico`, etc.). `backend/staff/models.py:1-67` shows `Especialista`.
- **Permissions** — `backend/biometric/permissions.py:57-62`: `is_admin_sucursal`, `is_admin_principal`. Method `user.es_admin_sucursal`/`user.es_admin_principal` on `Usuario`. These are the predicates we'll use for Maquinaria visibility.
- **Catalog registry** — `backend/config/api_views.py:1008-1023` `_catalog_key_to_slug`, `_catalog_page_data` (line 1086), `_catalog_parse_payload` (line 1874), `_catalog_get_instance` (line 2162-2177). Adding `maquinaria` to all four dispatches plugs the new catalog into the existing CRUD endpoints.
- **Media storage** — `backend/config/settings.py:203-204`: `MEDIA_URL="/media/"`, `MEDIA_ROOT=BASE_DIR/"media"`. No `ImageField` is currently used in this codebase, so we are introducing a new pattern (must add Pillow to requirements and wire `urlpatterns += static(...)` if missing).
- **Specialist interface** — `frontend/aesthetic-clinic/src/pages/specialist/`. We need to inspect during the design phase to confirm routing/nav, but the directory exists and is where `MyAppointmentsPage.tsx` will live.

## Files that will change

| File | Current role | Change reason |
| --- | --- | --- |
| `backend/operations/models.py` | Defines `CitaMedica` and related models | Add 11 new fields to `CitaMedica`; add `CitaMaquinaria`, `CitaEspecialista` |
| `backend/operations/migrations/0XXX_*.py` | New migration generated from model changes | Will be auto-generated; needs review |
| `backend/catalogs/models.py` | Defines catalogs (ProcEstetico, ServicioConfig, Sucursal, ...) | Add `Maquinaria` |
| `backend/catalogs/migrations/0XXX_*.py` | Migration for `Maquinaria` | Auto-generated |
| `backend/config/api/serializers/clientes.py` | `OperationReservationCreateSerializer`, `OperationReservationAvailabilitySerializer` | Extend payload with optional planning fields; expose Maquinaria in availability response if useful |
| `backend/config/api/serializers/operaciones.py` | `AppointmentStatusUpdateSerializer`, `AppointmentRescheduleSerializer`, `AppointmentBiometricConfirmSerializer` | Extend with optional real-time fields; add `AppointmentNotesUpdateSerializer` |
| `backend/config/api/viewsets/clientes.py` | Reservation endpoint at line 525 | Accept new planning fields; persist them and the M2M items |
| `backend/config/api/viewsets/operaciones.py` | `pendiente-biometria` at line 589, plus `actualizar`, `confirmar-biometria` | Accept new real fields on close; new `notes` PATCH action |
| `backend/config/api_views.py` | `_catalog_key_to_slug`, `_catalog_page_data`, `_catalog_parse_payload`, `_catalog_get_instance` | Register `maquinaria` slug; pagination + role-scoped filtering |
| `backend/operations/scheduling.py` | `get_concurrency`, `get_concurrency_detail`, `get_specialists_present` | Add `get_maquinaria_conflicts(sucursal_id, fecha, hora_inicio, duracion_minutos, maquinaria_items)` returning list of conflicts per machinery item |
| `backend/config/api_urls.py` | URL routing | Register new endpoints (`check-maquinaria`, specialist `mis-citas`, catalog dispatch already covers CRUD) |
| `backend/accounts/models.py` (or biometric/permissions.py) | Permission predicates | Add `user.puede_ver_toda_maquinaria` / `puede_crear_maquinaria_global` shortcuts if helpful; otherwise inline `user.es_admin_principal` checks |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | `createAdminClientReservation`, `getAdminClientReservationAvailability`, etc. | Extend payload types; add `getMaquinariaCatalog`, `checkMaquinariaConflicts`, `updateAppointmentNotes` |
| `frontend/aesthetic-clinic/src/types/admin.ts` | TS types | Add new types (`Maquinaria`, `MaquinariaConflict`, `AppointmentNotesPatch`, `MyAppointmentsItem`) |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientReservationSection.tsx` | Inline reservation form | Replace with a button that opens `<ReservationModal>` |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/AdminClientDetailPage.tsx` | Hosts `ClientReservationSection` | Pass required props; render modal |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/useClientDetail.ts` | `handleReserve` | Submit extended payload |
| `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` | Hosts inline reservation form and `pendiente-biometria` button | Replace inline form with `<ReservationModal>`; wire `<CloseAppointmentModal>` + `<AppointmentNotesPanel>` |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx` | Catalog tabs | Add "Maquinaria" tab using existing catalog dispatch |
| `frontend/aesthetic-clinic/src/App.tsx` | Router | Add `/especialista/mis-citas` route |
| `frontend/aesthetic-clinic/src/pages/specialist/SpecialistHomePage.tsx` (or sidebar) | Specialist nav | Add link to "Mis citas" |
| `frontend/aesthetic-clinic/src/pages/admin/AdminClientsPage.tsx` (or detail) | Clients list | May show cita media thumbnails if useful (out of scope for v1) |

## Files that will be created

| File | Purpose |
| --- | --- |
| `frontend/.../pages/admin/components/ReservationModal.tsx` | Modal that captures full planning fields + shows availability + machinery conflicts |
| `frontend/.../pages/admin/components/CloseAppointmentModal.tsx` | Modal that captures real times + real performed work + actual staff + actual machinery |
| `frontend/.../pages/admin/components/AppointmentNotesPanel.tsx` | Editable panel for `descripcion_general`, `notas_previas`, `notas_post`, `foto_antes`, `foto_despues` |
| `frontend/.../pages/admin/components/MaquinariaConflictList.tsx` | Reusable list of conflicting citas for a given machinery (used inside ReservationModal) |
| `frontend/.../pages/specialist/MyAppointmentsPage.tsx` | Read-only list of citas assigned to the authenticated specialist |
| `frontend/.../services/api/maquinaria.ts` | Typed wrapper for the machinery catalog + conflict-check endpoints |
| `frontend/.../services/api/specialistAppointments.ts` | Typed wrapper for `/api/especialista/mis-citas/` |
| `backend/config/api_views.py` (new view functions) | `admin_check_maquinaria`, `especialista_mis_citas`, `admin_update_appointment_notes` |
| `backend/tests/test_appointment_reservation_redesign.py` | Backend tests covering: machinery conflict detection, optional fields omitted, role scoping for catalog, real-time close, notes PATCH |
| `frontend/.../tests/admin_appointment_reservation_redesign.spec.ts` | Playwright E2E covering the modal flows |

## Backend contracts to extend

| Endpoint | Method | Current body | New payload (fields added) |
| --- | --- | --- | --- |
| `/api/admin/clientes/<id>/operaciones/<opId>/reservar/` | POST | `{ branchId, dateTime }` | + `duracionEstimadaMinutos` (int? ≤480), `descripcionGeneral` (str?), `notasPrevias` (str?), `procedimientoPlanificado` (str?), `zonaCuerpoPlanificada` (str?), `especialistasPlanificados` (int[]?), `maquinariaPlanificada` ({maquinariaId:int, cantidad:int}[]?). All optional. |
| `/api/admin/disponibilidad/concurrencia/` | GET | `{ sucursalId, fecha, hora }` | Response now ALSO includes `maquinariaEnUso` (list of `{maquinariaId, nombre, cantidad, citaId, fechaHora}`) for the 1h± window. Not blocking. |
| `/api/admin/citas/<id>/pendiente-biometria/` | POST | `{}` | + `horaRealInicio`, `horaRealFin`, `procedimientoRealizado`, `zonaCuerpoRealizada`, `especialistasAtendieron`, `maquinariaUtilizada`. All optional. Validates fin > inicio and horaRealInicio >= fecha_hora - 1h. |
| `/api/admin/citas/<id>/notas/` (new PATCH) | PATCH | — | `{ descripcionGeneral?, notasPrevias?, notasPost?, fotoAntes? (multipart), fotoDespues? (multipart) }` |
| `/api/admin/catalogos/<slug>/` | GET | — | Adds `maquinaria` slug (admin general sees all; admin sucursal sees globales + own). |

## Backend contracts to add

| Endpoint | Method | Purpose | Payload |
| --- | --- | --- | --- |
| `/api/admin/disponibilidad/check-maquinaria/` | GET | Detect overlapping reservations for a set of maquinaria at a given time block | Query: `sucursalId`, `fecha`, `hora`, `duracionMinutos`, `maquinariaIds=12,13`. Response: `{ conflictos: [{ maquinariaId, nombre, cantidadSolicitada, cantidadDisponible, citasQueLaUsan: [{citaId, cliente, fecha, horaInicio, horaFin}] }] }`. |
| `/api/especialista/mis-citas/` | GET | Specialist read-only view of all citas they are assigned to | Response: `{ citas: [{ id, cliente, fecha, horaInicio, duracionEstimadaMinutos, procedimientoPlanificado, zonaCuerpoPlanificada, descripcionGeneral, notasPrevias, sucursal, estado, maquinaria: [{nombre, cantidad}] }] }` |
| `/api/admin/citas/<id>/notas/` | PATCH | Edit cita notes & photos (multipart) | See above |

## Patterns to follow

- **Catalog CRUD**: plug `maquinaria` into `_catalog_key_to_slug`, `_catalog_page_data`, `_catalog_parse_payload`, `_catalog_get_instance` in `backend/config/api_views.py`. Reuses the entire `AdminCatalogsPage` UI on the frontend.
- **`CatalogoEditableModel`** (`backend/common/models.py`): provides `activo` flag and standard fields. Use it for `Maquinaria` if we want a soft-delete; otherwise inherit directly from `TimeStampedModel` so we have full FK control over `sucursal`.
- **Permission predicates**: `user.es_admin_principal` for full catalog visibility; `user.es_admin_sucursal and user.sucursal_id` for branch-scoped.
- **M2M with payload pattern**: copy `CitaMaquinaria` and `CitaEspecialista` from any existing M2M-through model in the codebase (e.g. `GrupoOpciones`/`OpcionCatalogo` for catalog M2M, or `AgendaHabitualEspecialista.dias` for M2M with extra data).
- **Appointment item serializer**: `_client_appointment_item` is the canonical shape returned by reservation/close endpoints; we extend it to include `duracionEstimadaMinutos`, `procedimientoPlanificado`, `zonaCuerpoPlanificada`, `maquinaria`, `especialistas` for new responses, but KEEP the existing fields for backward compatibility.
- **State machine**: extend `openspec/specs/appointment-states/spec.md` with new requirements for the close modal and notes panel; do not break the existing scenarios.
- **Frontend modal pattern**: use the same Dialog/Modal component already used by `RescheduleModal.tsx` and `ClientProfileModal.tsx` for consistency.

## Open questions

1. **Photo upload UI scope**: Should `foto_antes`/`foto_despues` be inlined in the notes panel (always editable), or only surfaced at the close modal? Plan currently says: notes panel always editable; close modal does NOT edit photos.
2. **`maquinaria_items` write API**: do we accept them as part of the reservation POST body OR expose a separate endpoint to attach them after reservation? Plan says: single body in reservation POST (simpler, transactional).
3. **Close modal — re-edit**: if the admin already passed a cita to `REALIZADA_PENDIENTE_VERIFICACION` and needs to fix the hora_real_fin or the staff, can they re-open the modal? Plan says: YES, but only the editable fields (not estado). Need a small endpoint for it.
4. **Specialist view pagination/scope**: list ALL assigned citas, or only future ones? Plan says: ALL (history + future), but exclude CANCELADA. Needs spec confirmation.

## Risks

- **Image upload introduces Pillow dependency and MEDIA serving**: `requirements.txt` change + `urlpatterns += static(...)` wiring may be needed.
- **M2M cascades**: deleting a `Maquinaria` must NOT cascade-delete `CitaMaquinaria`; we use `on_delete=PROTECT`.
- **Conflict visibility vs privacy — citas of other clients**: the conflict-list endpoint will expose that "cliente X has cita Y with machine Z at time T" to any admin in the same sucursal. Acceptable per current trust model (admins see other admins' work).
- **Specialist view auth**: must verify the endpoint rejects non-specialists; reuse the existing auth pattern.
- **Catalog role-scope UI**: AdminCatalogsPage needs to know the role to disable the "Todas las sucursales" option for admin_sucursal.
- **Optional fields & DB schema**: every new CitaMedica field is null/blank-safe; existing rows keep working.