# Archive Report: appointment-reservation-redesign

## Final state

**Change**: `appointment-reservation-redesign`
**Status**: ✅ Archived — fully implemented, verified, and ready to merge to remote.
**Total commits on main**: 27 (all since `8906adc`).
**Total LOC**: +4,617 / −228 across 33 files.

## Commit inventory (since main `8906adc`)

### PR 1 — bootstrap + models + Maquinaria catalog
- `14b394d` chore(deps): add Pillow dependency for cita photo fields
- `a1c15da` feat(catalogs): add Maquinaria model with branch-scoped visibility
- `0b3d252` feat(operations): add planning and real-time fields to CitaMedica
- `43c38ad` feat(api): register Maquinaria in generic catalog dispatch
- `cfe8ac2` test(catalog): cover Maquinaria CRUD and role-scoped visibility
- `41fa75a` fix(catalog): wire Maquinaria in model_map and register dedicated URLs first

### PR 2 — conflict detection + reservation extended
- `d1858f6` feat(scheduling): add get_maquinaria_conflicts helper
- `02d9379` feat(api): add admin_check_maquinaria endpoint
- `d3fb858` feat(reservation): accept optional planning fields and persist M2M rows
- `104c2eb` feat(reservation): wire real view to serializer + persist planning fields

### PR 3 — close modal + notes PATCH
- `7801ae5` feat(close): extend pendiente-biometria with real-time fields
- `3e6cf14` feat(api): add PATCH /citas/<id>/notas/ for editable notes and photos
- `9382987` feat(api+tests): extend pendiente-biometria with real-time fields and add PATCH /notas/

### PR 4 — specialist API + frontend services/types
- `013f185` feat(api): add GET /especialista/mis-citas/ for specialist read-only view
- `1fa60bf` feat(api+tests): wire especialista-mis-citas at /api/especialista/
- `4c3e749` feat(frontend): add API wrappers and types for appointment reservation redesign

### PR 5a — ReservationModal + ClientReservationSection swap
- `0533d02` feat(frontend): add MaquinariaConflictList component
- `12fb529` feat(frontend): add ReservationModal component with rich planning fields
- `d6cafc9` refactor(client-detail): replace inline reservation form with ReservationModal
- `0a27142` refactor(operation-detail): replace inline reservation form with ReservationModal

### PR 5b — CloseAppointmentModal + NotesPanel + wiring
- `ae86b4f` feat(frontend): add CloseAppointmentModal with real-time fields
- `eb89bfd` feat(frontend): add AppointmentNotesPanel with editable notes and photos
- `de12a71` refactor(operation-detail): wire CloseAppointmentModal + NotesPanel

### PR 6 — specialist Mis Citas view + seed
- `05f3a80` feat(specialist): add MyAppointmentsPage read-only view
- `0bfce9a` feat(routing): wire /trabajador/mis-citas route + sidebar link
- `8e58d0b` chore(seed): add Maquinaria items to baseline seed

### Verify-pass fix
- `f70d1ab` fix(api): add cliente name to especialista-mis-citas response

## Test coverage achieved

| Suite | Passing | Total |
| --- | --- | --- |
| `test_maquinaria_catalog` | 10 | 10 |
| `test_maquinaria_conflicts` | 11 | 11 |
| `test_appointment_reservation_extended` | 6 | 6 |
| `test_appointment_close_extended` | 12 | 12 |
| `test_especialista_mis_citas` | 10 | 10 |
| `test_admin_catalog_sectores` (regression) | 18 | 18 |
| `test_admin_catalog_especialidades_orden` (regression) | 8 | 8 |
| **Total backend** | **75** | **75** |

**Frontend typecheck**: 0 new errors (1 pre-existing unrelated error in `AdminOperationDetailPage.tsx:174` remains, out of scope).

## Migrations applied

1. `catalogs/0010_maquinaria.py` — creates `Maquinaria` table.
2. `operations/0026_citamedica_descripcion_general_and_more.py` — adds 11 fields to `CitaMedica` + creates `CitaMaquinaria` and `CitaEspecialista` tables.

## Spec coverage

All scenarios from `openspec/specs/appointment-reservation-redesign/spec.md` are satisfied:

- **Maquinaria catalog**: model + scope + dedicated endpoints + 10 catalog tests.
- **CitaMedica planning fields**: 8 fields, all optional, 6 reservation tests.
- **CitaMedica real-time fields**: 4 fields, close endpoint extended, 12 close tests.
- **CitaMaquinaria / CitaEspecialista**: through-models with `planificada` flag for planned vs used.
- **Conflict visibility (warn, no block)**: 11 conflict tests + `MaquinariaConflictList` UI.
- **Reservation optional fields**: explicit "minimal payload" test passes.
- **Close idempotency**: re-closing replaces M2M rows; test passes.
- **Notes PATCH (any state)**: tests for PROGRAMADA + REALIZADA_PENDIENTE_VERIFICACION + 404.
- **Specialist read-only view**: 10 tests for scope, auth, planning data, maquinaría list, action-flag stripping.
- **Maquinaria scope (admin_sucursal)**: explicit 403 tests for global edit and cross-branch edit.

## Findings summary

- **CRITICAL**: None. (One missing field — `cliente` on the specialist API response — was found and fixed in commit `f70d1ab`.)
- **WARNING** (4 items, recorded in `verify-report.md`):
  1. Production deploy should smoke-test `/api/especialista/mis-citas/` for the new `cliente` field.
  2. PR 5a exceeded 400-LOC budget (1014 net, single 602-LOC modal — accepted by user).
  3. PR 5b exceeded 500-LOC budget (762 — accepted by user).
  4. Every PR's LOC budget was exceeded; user approved each via runtime reset. Future SDD runs for this repo should set the budget closer to 800 LOC per work unit.
- **SUGGESTION** (6 items, recorded in `verify-report.md`): notes endpoint dual-method (POST/PATCH), dead action in `viewsets/operaciones.py`, Playwright E2E coverage gap, DRF `IntegerField(min_value/max_value)` keyword form, seed runs only in dev/test, doc strings on the close modal.

## Decisions recorded

These decisions were taken during planning with the user and recorded in Engram observation #544 and #545. They drove the implementation:

1. **Conflict visibility = WARN, never block**. Conflicting citas are listed; the admin decides.
2. **Specialists and machinery assignments are optional**. Reservations succeed even with all-empty selectors. Default placeholder "No seleccionado".
3. **Maquinaria scope**: admin general sees all and creates global; admin de sucursal sees globales + own, can CRUD only own.
4. **Photo storage**: Django default File storage. `MEDIA_ROOT`/`MEDIA_URL` already configured.
5. **Notes always editable** by admin or assigned specialist. Reachable regardless of cita state.
6. **Real-time capture uses `hora_real_inicio` + `hora_real_fin`** with minute precision, `fin > inicio`, with 1h tolerance before scheduled time.
7. **Performed-work capture**: free-text `procedimiento_realizado` + `zona_cuerpo_realizada` (zona del cuerpo, free text).
8. **Specialist "Mis citas" view**: read-only list. No action buttons.
9. **Maquinaria catalog endpoints**: dedicated `/api/admin/catalogos/maquinaria/crear/` and `/actualizar/` with `@admin_required` + scope-check (NOT touched the generic dispatch which uses `@_admin_principal_required`).
10. **Notes endpoint accepts both POST and PATCH** (Django's WSGIRequest only auto-parses multipart for POST).

## Final commit on main

`f70d1ab` — fix(api): add cliente name to especialista-mis-citas response

## Post-archive recommendations

1. **Push the branch and open the PR** to remote (`git push origin main` after the user reviews). All 27 commits are local-only at this point.
3. **Review the 4 WARNINGs** in `verify-report.md` before merge — none are blockers.
4. **Smoke-test in dev**:
   - `python manage.py seed_pdf_baseline` to load the 5 Maquinaria items.
   - Log in as admin → catalog → Maquinaria tab → verify list/edit/create.
   - Log in as specialist → /trabajador/mis-citas → verify list with cliente + planning data.
   - Create a cita via the new modal, verify the conflict warning panel appears when applicable.
   - Close a cita via the new modal, verify all real-time fields persist.
   - Edit notes (text + photo) on any cita, verify persistence.

5. **Add Playwright E2E tests** as a follow-up change (out of scope for this one).

## No outstanding blockers

The change is complete. Archive is final. Ready for review and merge.