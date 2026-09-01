# Tasks — Appointment Reservation Redesign

## Phase 0 — Bootstrap

- [ ] **0.1** Verify `Pillow` is in `backend/requirements.txt` (or add it).
- [ ] **0.2** Verify `MEDIA_URL` / `MEDIA_ROOT` in `backend/config/settings.py` (line 203-204). Add `urlpatterns += static(...)` for `DEBUG=True` if missing.

## Phase 1 — Backend models & migrations

- [ ] **1.1** Add `Maquinaria` to `backend/catalogs/models.py` (fields: nombre, marca, descripcion, cantidad_total, sucursal nullable FK, activo). Meta: `db_table="maquinaria"`, ordering by nombre.
- [ ] **1.2** Generate `catalogs/migrations/0XXX_add_maquinaria.py`.
- [ ] **1.3** Add `CitaMaquinaria` to `backend/operations/models.py` (cita FK, maquinaria FK, cantidad, planificada). UniqueConstraint `(cita, maquinaria, planificada)`.
- [ ] **1.4** Add `CitaEspecialista` to `backend/operations/models.py` (cita FK, especialista FK, planificada). UniqueConstraint `(cita, especialista, planificada)`.
- [ ] **1.5** Add 11 optional fields to `CitaMedica` (duración_estimada_minutos, descripción_general, notas_previas, notas_post, foto_antes, foto_despues, procedimiento_planificado, zona_cuerpo_planificada, hora_real_inicio, hora_real_fin, procedimiento_realizado, zona_cuerpo_realizada). All nullable/blank.
- [ ] **1.6** Generate `operations/migrations/0XXX_add_cita_planning_real_fields.py`.
- [ ] **1.7** Run `python manage.py migrate` locally and verify.

## Phase 2 — Maquinaria catalog API + UI

- [ ] **2.1** Add `"maquinaria"` to `_catalog_key_to_slug` whitelist in `backend/config/api_views.py`.
- [ ] **2.2** Add `maquinaria` case in `_catalog_page_data` with role-based filtering (`es_admin_principal` vs `es_admin_sucursal`).
- [ ] **2.3** Add `maquinaria` case in `_catalog_parse_payload` with validation: `admin_sucursal` cannot set `sucursal=null`.
- [ ] **2.4** Add `Maquinaria` to `model_map` in `_catalog_get_instance`.
- [ ] **2.5** Backend test: `test_maquinaria_catalog.py` covering list, create, update, role-scope, 403 on global edit.
- [ ] **2.6** Add "Maquinaria" tab to `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx` (reuse generic catalog UI).
- [ ] **2.7** Frontend E2E test: `admin_maquinaria_catalog.spec.ts`.

## Phase 3 — Backend helpers & conflict endpoint

- [ ] **3.1** Add `get_maquinaria_conflicts(sucursal_id, fecha, hora, duracion_minutos, items)` to `backend/operations/scheduling.py`.
- [ ] **3.2** Add `admin_check_maquinaria(request)` view in `backend/config/admin_availability_views.py` (or a new file). Permissions: admin only.
- [ ] **3.3** Wire URL in `backend/config/api_urls.py`: `disponibilidad/check-maquinaria/`.
- [ ] **3.4** Backend test: `test_maquinaria_conflicts.py` covering: no conflict, single conflict, multiple items, sum exceeding total, cita cancelada excluded.

## Phase 4 — Reservation endpoint extended

- [ ] **4.1** Extend `OperationReservationCreateSerializer` in `backend/config/api/serializers/clientes.py` with 7 optional fields.
- [ ] **4.2** Extend reservation view in `backend/config/api/viewsets/clientes.py` (line ~525) to:
  - Read optional fields from request.data.
  - Persist on `CitaMedica`.
  - Bulk-create `CitaMaquinaria(planificada=True)` rows from `maquinariaPlanificada`.
  - Bulk-create `CitaEspecialista(planificada=True)` rows from `especialistasPlanificados`.
  - Validate `duracionEstimadaMinutos` 1..480.
- [ ] **4.3** Extend the response with the new fields and `maquinaria[]` / `especialistas[]` arrays.
- [ ] **4.4** Backend test: `test_appointment_reservation_extended.py` covering: minimal payload (only branchId+dateTime), full payload, duracion>480 rejected, persistence of M2M rows.

## Phase 5 — Close endpoint extended

- [ ] **5.1** Add `AppointmentCloseSerializer` in `backend/config/api/serializers/operaciones.py` with 6 optional fields + validators (fin>inicio, inicio>=fecha_hora-1h).
- [ ] **5.2** Extend `pendiente_biometria` action in `backend/config/api/viewsets/operaciones.py` (line 589) to:
  - Read optional real-time fields.
  - Persist on `CitaMedica`.
  - Bulk-create `CitaMaquinaria(planificada=False)` rows.
  - Bulk-create `CitaEspecialista(planificada=False)` rows.
  - Update state to `REALIZADA_PENDIENTE_VERIFICACION`.
- [ ] **5.3** Backend test: `test_appointment_close_extended.py` covering: happy path, fin<=inicio rejected, persistence of M2M rows.

## Phase 6 — Notes PATCH endpoint

- [ ] **6.1** Add `AppointmentNotesPatchSerializer` in `backend/config/api/serializers/operaciones.py` with optional text fields + 2 ImageFields (max 5MB).
- [ ] **6.2** Add `admin_update_appointment_notes(request, pk)` view. Permissions: admin (any state) or assigned specialist.
- [ ] **6.3** Wire URL in `backend/config/api_urls.py`: `citas/<id>/notas/`.
- [ ] **6.4** Backend test: `test_appointment_notes.py` covering: text PATCH, photo upload, specialist auth (assigned vs non-assigned), 5MB cap.

## Phase 7 — Specialist mis-citas endpoint

- [ ] **7.1** Add `especialista_mis_citas(request)` view in a new `backend/config/specialist_views.py` (or extension of existing).
- [ ] **7.2** Filter `CitaMedica` by `CitaEspecialista__especialista=user.especialista` AND `estado__not_in=[CANCELADA, NO_ASISTIO]`. Exclude cancelled/no-show.
- [ ] **7.3** Shape response with full planning data + maquinaria list.
- [ ] **7.4** Wire URL in `backend/config/api_urls.py`: `especialista/mis-citas/`.
- [ ] **7.5** Backend test: `test_especialista_mis_citas.py` covering: assigned only, cancelled excluded, no-show excluded, ordering.

## Phase 8 — Frontend services + types

- [ ] **8.1** Add `getMaquinariaCatalog`, `checkMaquinariaConflicts`, `updateAppointmentNotes`, `getMyAppointments` to `frontend/aesthetic-clinic/src/services/api/admin.ts` (or new files).
- [ ] **8.2** Extend `createAdminClientReservation` and the close endpoint payload type.
- [ ] **8.3** Add TS types: `Maquinaria`, `MaquinariaConflict`, `AppointmentNotesPatch`, `MyAppointmentsItem` in `frontend/aesthetic-clinic/src/types/admin.ts`.

## Phase 9 — Frontend modals & integration

- [ ] **9.1** Create `frontend/aesthetic-clinic/src/pages/admin/components/ReservationModal.tsx`. Fields per spec.
- [ ] **9.2** Create `frontend/aesthetic-clinic/src/pages/admin/components/MaquinariaConflictList.tsx`.
- [ ] **9.3** Replace inline reservation block in `ClientReservationSection.tsx` and `AdminOperationDetailPage.tsx` with `<ReservationModal>` triggered by a button.
- [ ] **9.4** Create `frontend/aesthetic-clinic/src/pages/admin/components/CloseAppointmentModal.tsx`. Prepopulate from `cita`.
- [ ] **9.5** Wire `CloseAppointmentModal` in `AdminOperationDetailPage.tsx` (and any cita list actions).
- [ ] **9.6** Create `frontend/aesthetic-clinic/src/pages/admin/components/AppointmentNotesPanel.tsx` with multipart PATCH for photos + text.
- [ ] **9.7** Place `<AppointmentNotesPanel>` in `AdminOperationDetailPage.tsx` and the cita detail surfaces.
- [ ] **9.8** Frontend E2E tests: `admin_reservation_modal.spec.ts`, `admin_close_modal.spec.ts`, `admin_notes_panel.spec.ts`.

## Phase 10 — Specialist view

- [ ] **10.1** Create `frontend/aesthetic-clinic/src/pages/specialist/MyAppointmentsPage.tsx`. Read-only list using `getMyAppointments`.
- [ ] **10.2** Add route `/trabajador/mis-citas` in `App.tsx`.
- [ ] **10.3** Add "Mis citas" link in the specialist sidebar / `SpecialistPortalPage.tsx`.
- [ ] **10.4** Frontend E2E test: `specialist_mis_citas.spec.ts`.

## Phase 11 — Seed & docs

- [ ] **11.1** Seed 3-5 maquinaría items in the demo baseline so the catalog is not empty. Use `accounts/management/commands/seed_branch_test_scenarios.py` or a new seed command.
- [ ] **11.2** Add Pillow install note to the README's "Backend setup" section (if README covers it).

## Done criteria

- All tests green: `python manage.py test` (backend) and `npx playwright test` (frontend).
- Build passes: `npm run build` (frontend).
- Manual smoke: admin creates a cita via the new modal, sees a conflict warning, confirms anyway; closes the cita via the new close modal; specialist sees the cita in their Mis Citas view.

## Estimated complexity

| Phase | LOC (est.) | Risk |
| --- | --- | --- |
| 0 | ~5 | low |
| 1 | ~120 | medium (migrations) |
| 2 | ~200 | medium |
| 3 | ~150 | medium |
| 4 | ~150 | medium |
| 5 | ~120 | medium |
| 6 | ~120 | medium |
| 7 | ~80 | low |
| 8 | ~80 | low |
| 9 | ~600 | high (UI) |
| 10 | ~150 | medium |
| 11 | ~60 | low |

Total estimate: ~1,835 LOC across backend + frontend. **Strongly exceeds 400-line review budget** → applies `delivery_strategy: ask-on-risk`.

## Suggested slicing (if user picks chained PRs)

| PR | Phases | LOC | Focus |
| --- | --- | --- | --- |
| PR 1 | 0, 1, 2 | ~325 | Models, migrations, machinery catalog |
| PR 2 | 3, 4 | ~300 | Conflict detection + extended reservation |
| PR 3 | 5, 6 | ~240 | Close modal + notes PATCH |
| PR 4 | 7, 8 | ~160 | Specialist mis-citas API + frontend services/types |
| PR 5 | 9 | ~600 | Frontend modals + notes panel integration |
| PR 6 | 10, 11 | ~210 | Specialist view + seed |

Total: 6 chained PRs, stacked-to-main. All PRs ≤ 400 lines except PR 5 (~600) — PR 5 will be split further at apply time if needed: `ReservationModal + MaquinariaConflictList + ClientReservationSection swap` (~300 LOC) and `CloseAppointmentModal + AppointmentNotesPanel + AdminOperationDetailPage wiring` (~300 LOC).