# Design — Appointment Reservation Redesign

## Overview

This document is the technical architecture for the `appointment-reservation-redesign` change. It complements the proposal and the delta spec by spelling out HOW the spec is implemented: data models, migrations, endpoints, files touched, decisions taken, and sequence flows.

## Architecture decisions

| # | Decision | Rationale |
| --- | --- | --- |
| AD1 | All new CitaMedica fields are nullable or have safe defaults | Existing rows must continue to work without backfill |
| AD2 | `Maquinaria` lives in `catalogs` app | It is a catalog with branch scoping, the same domain as ProcEstetico/Sector |
| AD3 | `CitaMaquinaria` and `CitaEspecialista` are explicit through-models (FK to both sides + extras), not Django M2M `through=` | Matches the `AgendaHabitualDia` pattern already used in `operations/models.py:515-534` |
| AD4 | On the reservation POST we accept the planning data inline (not a separate endpoint) | One transaction, simpler for the admin, fewer round-trips |
| AD5 | Conflict visibility = WARN only, never block | Explicit user requirement; admin decides |
| AD6 | Conflict-check is a separate GET endpoint, called after the user selects maquinaria | Keeps the existing concurrency-check endpoint lean and unchanged in shape |
| AD7 | Notes panel uses multipart PATCH so photo upload shares one endpoint with text fields | Avoids two endpoints per cita, simpler frontend |
| AD8 | Image upload uses Django's default `FileSystemStorage` to `MEDIA_ROOT/citas/<id>/{antes,despues}/` | Standard Django pattern, no S3 dependency |
| AD9 | Pillow is added to `requirements.txt` (or `requirements-dev.txt` if separation exists) | Required by `ImageField` |
| AD10 | Media serving is wired only when `settings.DEBUG` is true | Standard Django production guidance; no production secret exposure |
| AD11 | Specialist view is read-only and exposes only citas where they appear in `CitaEspecialista` (any `planificada`) | Privacy + accuracy |
| AD12 | Specialist view uses the same cita serializer shape used elsewhere (`_client_appointment_item`-like) with `procedimiento_planificado`, `maquinaria`, etc. | Consistency + reuse |
| AD13 | Machinery catalog plugs into the existing `_catalog_*` dispatch in `config/api_views.py` | No new CRUD endpoints; UI tab reuses AdminCatalogsPage |
| AD14 | Branch-scoped filtering of `Maquinaria` happens at the API layer using `user.es_admin_sucursal` / `user.es_admin_principal` | Matches the existing pattern in `ticket_views.py:44,80,248-249` |
| AD15 | Permission to write global maquinaría is restricted to admin principal only | Spec scenario "Admin de sucursal cannot edit global maquinaría" |

## Data model

### New model `catalogs.Maquinaria`

```python
class Maquinaria(TimeStampedModel):
    nombre = models.CharField(max_length=120)
    marca = models.CharField(max_length=120, blank=True)
    descripcion = models.TextField(blank=True)
    cantidad_total = models.PositiveIntegerField(default=1)
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.PROTECT,
        related_name="maquinaria",
        null=True,
        blank=True,
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "maquinaria"
        ordering = ("nombre",)

    def __str__(self):
        return f"{self.nombre} ({self.marca})" if self.marca else self.nombre
```

### New model `operations.CitaMaquinaria`

```python
class CitaMaquinaria(TimeStampedModel):
    cita = models.ForeignKey("CitaMedica", on_delete=models.CASCADE, related_name="maquinaria_items")
    maquinaria = models.ForeignKey("catalogs.Maquinaria", on_delete=models.PROTECT, related_name="citas_items")
    cantidad = models.PositiveIntegerField(default=1)
    planificada = models.BooleanField(default=True)

    class Meta:
        db_table = "citas_maquinaria"
        constraints = [
            models.UniqueConstraint(
                fields=("cita", "maquinaria", "planificada"),
                name="uniq_cita_maquinaria_planificada",
            )
        ]
```

### New model `operations.CitaEspecialista`

```python
class CitaEspecialista(TimeStampedModel):
    cita = models.ForeignKey("CitaMedica", on_delete=models.CASCADE, related_name="especialistas_items")
    especialista = models.ForeignKey("staff.Especialista", on_delete=models.PROTECT, related_name="citas_items")
    planificada = models.BooleanField(default=True)

    class Meta:
        db_table = "citas_especialistas"
        constraints = [
            models.UniqueConstraint(
                fields=("cita", "especialista", "planificada"),
                name="uniq_cita_especialista_planificada",
            )
        ]
```

### Fields added to `operations.CitaMedica`

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `duracion_estimada_minutos` | PositiveIntegerField | `null=True` | validators 1..480 |
| `descripcion_general` | TextField | `""` | |
| `notas_previas` | TextField | `""` | |
| `notas_post` | TextField | `""` | |
| `foto_antes` | ImageField | `null=True` | `upload_to="citas/%Y/%m/%d/antes/"` |
| `foto_despues` | ImageField | `null=True` | `upload_to="citas/%Y/%m/%d/despues/"` |
| `procedimiento_planificado` | TextField | `""` | |
| `zona_cuerpo_planificada` | CharField(max_length=200) | `""` | |
| `hora_real_inicio` | DateTimeField | `null=True` | |
| `hora_real_fin` | DateTimeField | `null=True` | |
| `procedimiento_realizado` | TextField | `""` | |
| `zona_cuerpo_realizada` | CharField(max_length=200) | `""` | |

All fields are nullable/blank → existing rows keep working. The migration is generated with `python manage.py makemigrations`.

## API surface

### New endpoints

| Method + Path | Purpose | Payload | Returns |
| --- | --- | --- | --- |
| `GET /api/admin/disponibilidad/check-maquinaria/` | Detect machinery overlap | Query: `sucursalId`, `fecha`, `hora`, `duracionMinutos`, `maquinariaIds=12,13` | `{ conflictos: [...] }` |
| `PATCH /api/admin/citas/<id>/notas/` | Edit notes & photos (multipart) | multipart: any of `descripcionGeneral`, `notasPrevias`, `notasPost`, `fotoAntes`, `fotoDespues` | `{ cita: {...}, photos: {...} }` |
| `GET /api/especialista/mis-citas/` | Specialist read-only list | — | `{ citas: [...] }` |

### Extended endpoints

| Endpoint | Change |
| --- | --- |
| `POST /api/admin/clientes/<id>/operaciones/<opId>/reservar/` | Accept 7 new optional fields + persist `CitaMaquinaria(planificada=true)` + `CitaEspecialista(planificada=true)` |
| `POST /api/admin/citas/<id>/pendiente-biometria/` | Accept 6 new optional fields + persist `CitaMaquinaria(planificada=false)` + `CitaEspecialista(planificada=false)` |
| `GET /api/admin/disponibilidad/concurrencia/` | Response MAY include `maquinariaEnUso` (additive, existing fields unchanged) |
| `GET /api/admin/catalogos/<slug>/` for `maquinaria` | Plugged into the existing catalog dispatch; filter by `user.es_admin_*` |

### Catalog dispatch updates

`backend/config/api_views.py`:

- Add `"maquinaria"` to `_catalog_key_to_slug` whitelist.
- In `_catalog_page_data`: handle `catalog_key == "maquinaria"`. Items shaped as `{ id, nombre, marca, descripcion, cantidadTotal, sucursalId, sucursalNombre, activo }`. Filter:
  - `user.es_admin_principal` → no filter.
  - `user.es_admin_sucursal and user.sucursal_id` → `Q(sucursal__isnull=True) | Q(sucursal_id=user.sucursal_id)`.
- In `_catalog_parse_payload`: parse `{ nombre, marca?, descripcion?, cantidadTotal, sucursalId?, activo? }`. If `sucursalId` is provided and user is `admin_sucursal`, reject (force `sucursalId=user.sucursal_id`).
- In `_catalog_get_instance`: add `Maquinaria` to `model_map`.

### Permissions matrix

| Role | Catalog Maquinaria | Create reservation | Close cita | Edit notes | Mis citas |
| --- | --- | --- | --- | --- | --- |
| Admin principal | Full CRUD (any sucursal or global) | Yes | Yes | Yes | n/a |
| Admin sucursal | Read globales + own; CRUD only own | Yes (own sucursal) | Yes (own sucursal) | Yes (own sucursal) | n/a |
| Specialist | No | No | No | Only citas assigned to them | Yes |

## Helper functions

### `operations/scheduling.py`

Add:

```python
def get_maquinaria_conflicts(sucursal_id, fecha, hora, duracion_minutos, maquinaria_items):
    """
    For each (maquinaria_id, cantidad) in maquinaria_items, return any overlapping
    reservations whose sum of cantidad exceeds (cantidad_total - cantidad_solicitada).
    Returns list of {maquinariaId, nombre, cantidadSolicitada, cantidadDisponible,
                      citasQueLaUsan: [{citaId, cliente, fecha, horaInicio, horaFin}]}.
    """
```

Algorithm:
1. Compute window: `[fecha+hora, fecha+hora+duracion_minutos]` as aware datetimes.
2. For each `(maquinaria_id, cantidad_solicitada)`:
   - Query `CitaMaquinaria.objects.filter(maquinaria_id=maquinaria_id, planificada=True).select_related("maquinaria", "cita")`.
   - Filter to those whose `cita.fecha_hora` is in the window AND `cita.estado in {PROGRAMADA, REALIZADA_PENDIENTE_VERIFICACION}`.
   - Sum `cantidad`. If `cantidad_solicitada + suma > maquinaria.cantidad_total` → conflict.
   - For each conflict cita, include `citaId`, `cliente` (concat first_name + last_pat), `fecha`, `horaInicio` (HH:MM), `horaFin = fecha + duracion_minutos`.
3. Return list. Items with no conflict are NOT in the output.

### `operations/views_citas.py` (new file or extension of existing)

Add views:

- `admin_check_maquinaria(request)` — GET handler for `check-maquinaria/`. Permissions: admin only.
- `admin_update_appointment_notes(request, pk)` — PATCH handler. Multipart. Permissions: admin or assigned specialist.
- `especialista_mis_citas(request)` — GET handler. Permissions: specialist with `Especialista` profile.

### Serializers

`backend/config/api/serializers/clientes.py`:

- Extend `OperationReservationCreateSerializer` with all 7 optional fields, all `required=False`.

`backend/config/api/serializers/operaciones.py`:

- Add `AppointmentCloseSerializer` (input for `pendiente-biometria`) with optional real-time fields.
- Add `AppointmentNotesPatchSerializer` with `descripcionGeneral`, `notasPrevias`, `notasPost` (CharField, required=False), `fotoAntes`, `fotoDespues` (ImageField, required=False).

`backend/config/api/serializers/citas_medicas.py` (new):

- `MaquinariaItemSerializer` for `CitaMaquinaria`.
- `EspecialistaItemSerializer` for `CitaEspecialista`.
- Extend `_client_appointment_item` (or its replacement) to include `duracionEstimadaMinutos`, `procedimientoPlanificado`, `zonaCuerpoPlanificada`, `maquinaria: [...]`, `especialistas: [...]`.

## Frontend files

### New components

| File | Purpose |
| --- | --- |
| `frontend/aesthetic-clinic/src/pages/admin/components/ReservationModal.tsx` | The reservation modal |
| `frontend/aesthetic-clinic/src/pages/admin/components/CloseAppointmentModal.tsx` | The close modal |
| `frontend/aesthetic-clinic/src/pages/admin/components/AppointmentNotesPanel.tsx` | Notes + photo editor |
| `frontend/aesthetic-clinic/src/pages/admin/components/MaquinariaConflictList.tsx` | Conflict list (used in ReservationModal) |
| `frontend/aesthetic-clinic/src/pages/specialist/MyAppointmentsPage.tsx` | Specialist read-only list |

### Modified files

| File | Change |
| --- | --- |
| `pages/admin/client-detail/ClientReservationSection.tsx` | Remove inline form; show a button that opens `ReservationModal` |
| `pages/admin/client-detail/AdminClientDetailPage.tsx` | Render `<ReservationModal>` |
| `pages/admin/client-detail/useClientDetail.ts` | Extend `handleReserve` payload |
| `pages/admin/AdminOperationDetailPage.tsx` | Replace inline form with `<ReservationModal>`; wire `<CloseAppointmentModal>`; add `<AppointmentNotesPanel>` |
| `pages/admin/AdminCatalogsPage.tsx` | Add "Maquinaria" tab using the generic catalog dispatch |
| `App.tsx` | Add `/trabajador/mis-citas` route |
| `pages/specialist/SpecialistPortalPage.tsx` (or sidebar component) | Add link to "Mis citas" |
| `services/api/admin.ts` | Extend `createAdminClientReservation` and the close endpoint payload; add `getMaquinariaCatalog`, `checkMaquinariaConflicts`, `updateAppointmentNotes`, `getMyAppointments` |
| `types/admin.ts` | Add types `Maquinaria`, `MaquinariaConflict`, `AppointmentNotesPatch`, `MyAppointmentsItem` |
| `pages/specialist/SpecialistPortalPage.tsx` (or sidebar) | Add "Mis citas" nav entry |

### Modal pattern reference

The existing `RescheduleModal.tsx` (client-detail) and `ClientProfileModal.tsx` define the modal patterns. `ReservationModal` and `CloseAppointmentModal` follow them with bigger bodies. Use the project's standard `<dialog>` / `<Modal>` pattern.

## Sequence flows

### Reservation (happy path with conflict warning)

```
User → ReservationModal
  → Verificar disponibilidad
    → GET /admin/disponibilidad/concurrencia/ (existing)
    → GET /admin/disponibilidad/check-maquinaria/ (new)
  ← { concurrency, appointments, presentes, conflictos: [...] }
  → Confirmar reserva
    → POST /admin/clientes/<id>/operaciones/<opId>/reservar/ (extended body)
      → backend creates CitaMedica + CitaMaquinaria(planificada=true) + CitaEspecialista(planificada=true)
    ← 201 { appointment }
```

### Close (happy path)

```
User → Cita detail → "Cambiar a pendiente de verificación"
  → CloseAppointmentModal opens (prepopulated)
  → User edits horas reales, procedimiento, zona, staff, maquinaria
  → User submits
    → POST /admin/citas/<id>/pendiente-biometria/ (extended body)
      → backend transitions estado, persists CitaMaquinaria(planificada=false) + CitaEspecialista(planificada=false)
    ← 200 { appointment, detail }
```

### Notes edit

```
User → Cita detail → Notes panel → Editar
  → User uploads new fotoAntes / edits notasPrevias
  → User submits
    → PATCH /admin/citas/<id>/notas/ (multipart)
      → backend updates CitaMedica + saves image to MEDIA_ROOT/citas/<id>/antes/<filename>
    ← 200 { cita: {...} }
```

### Specialist mis-citas

```
Specialist → /trabajador/mis-citas
  → GET /especialista/mis-citas/
    → backend filters CitaMedica where CitaEspecialista(especialista=self) exists and estado not in {CANCELADA, NO_ASISTIO}
  ← { citas: [...] }
```

## Migrations

Two migrations:

1. `catalogs/migrations/0XXX_add_maquinaria.py` — create `Maquinaria` table.
2. `operations/migrations/0XXX_add_cita_planning_real_fields.py` — add 11 fields to `CitaMedica` + create `CitaMaquinaria` and `CitaEspecialista`.

Run `python manage.py makemigrations catalogs operations` to generate. Review for:
- Default values consistent with this design.
- Indexes: `db_index=True` on `cita_id`, `maquinaria_id`, `especialista_id` in the new through-models for query performance.
- `MEDIA_ROOT` exists; if not, create it via migration step or documentation.

## Settings & dependencies

- `backend/requirements.txt` — add `Pillow>=10.0` if not present.
- `backend/config/settings.py` — confirm `MEDIA_ROOT` and `MEDIA_URL` already configured (they are at line 203-204).
- `backend/config/urls.py` — add `urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)` only when `DEBUG=True` (typical pattern).

## Tests

### Backend (Django unittest)

| File | Coverage |
| --- | --- |
| `backend/tests/test_maquinaria_catalog.py` | Catalog CRUD, role-scoped visibility, create global restricted to admin_principal |
| `backend/tests/test_appointment_reservation_extended.py` | Reservation with optional fields null, with duracion >480, with staff + machinery; persists CitaEspecialista + CitaMaquinaria |
| `backend/tests/test_maquinaria_conflicts.py` | `get_maquinaria_conflicts` returns correct conflicts; no false positives when window is empty |
| `backend/tests/test_appointment_close_extended.py` | Close with real hours + attended staff + used machinery; rejects fin<=inicio |
| `backend/tests/test_appointment_notes.py` | PATCH /notas/ with text + multipart; specialist assigned allowed; non-assigned denied |
| `backend/tests/test_especialista_mis_citas.py` | Lists only assigned citas; excludes CANCELADA and NO_ASISTIO |

### Frontend (Playwright)

| File | Coverage |
| --- | --- |
| `frontend/aesthetic-clinic/tests/admin_reservation_modal.spec.ts` | Open modal, fill all fields, conflict panel appears, confirm succeeds |
| `frontend/aesthetic-clinic/tests/admin_close_modal.spec.ts` | Close modal prepopulates; rejects fin<=inicio; submits successfully |
| `frontend/aesthetic-clinic/tests/admin_notes_panel.spec.ts` | Edit text + upload photo; persist + re-render |
| `frontend/aesthetic-clinic/tests/admin_maquinaria_catalog.spec.ts` | CRUD; admin_sucursal cannot edit global |
| `frontend/aesthetic-clinic/tests/specialist_mis_citas.spec.ts` | Lists assigned citas; no action buttons visible |

## Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Image upload fills disk | 5 MB cap in serializer; document clean-up policy |
| Conflict visibility leaks client names across branches | Endpoint filters by `sucursal_id` |
| Concurrent reservations of same maquinaría | Acceptable per spec; admin warned, not blocked |
| Migration on large CitaMedica table takes time | Run during low-traffic window; fields are all null/blank so no rewrites |
| Specialist auth misconfigured | Test `test_especialista_mis_citas.py` covers auth + scope |
| Pillow version conflict | Pin in `requirements.txt`; CI installs fresh env to catch it |

## Out of scope (explicit)

- Real-time websockets for conflict updates (we keep HTTP request/response).
- Slot-level machinery reservation lock.
- Editing global maquinaría from a non-admin principal user.
- iCal/export integration.
- Cross-sucursal specialist assignments (specialist is assigned to one sucursal).