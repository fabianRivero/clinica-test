# Tasks: Specialized Sectors for Medical Forms

## Review Workload Forecast

| Metric | Value |
|--------|-------|
| Backend model + FKs | ~60 lines |
| Backend API integration | ~30 lines |
| Backend filter logic | ~20 lines |
| Backend migrations (schema + data) | ~40 lines |
| Backend seed updates | ~30 lines |
| Backend tests (3 files) | ~150 lines |
| Frontend catalog UI + dropdown | ~80 lines |
| Frontend E2E tests | ~80 lines |
| **Total forecast** | **~490 lines** |
| Review budget | 400 lines |
| **Budget risk** | **High** |
| **Chained PRs recommended** | **Yes** |
| **Decision needed before apply** | **Yes** |

### Recommended PR split
- **PR 1 — Backend core** (~300 lines): model + migrations + filter logic + backend tests.
- **PR 2 — Frontend + integration** (~190 lines): admin catalog tab + service form dropdown + E2E tests.

---

## PR 1 — Backend Core

### Phase 1: Models

#### 1.1 [x] Create `Sector` model
- **Files**: `backend/catalogs/models.py`
- **Action**: Add `Sector(CatalogoEditableModel)` with `codigo` (max 20), `nombre` (max 120), unique constraints case-insensitive on both, `db_table = "catalogs_sector"`.
- **Acceptance**: `python manage.py check` passes; model registered; admin shows it.

#### 1.2 [x] Add nullable `sector` FK to `ServicioConfig`
- **Files**: `backend/catalogs/models.py`
- **Action**: Add `sector = models.ForeignKey(Sector, null=True, blank=True, on_delete=SET_NULL)`.
- **Acceptance**: existing services unaffected (nullable).

#### 1.3 [x] Add nullable `sector` FK to `FichaSeccion` (preserve `proc_estetico`)
- **Files**: `backend/clinical/models.py`
- **Action**: Add `sector = models.ForeignKey("catalogs.Sector", null=True, blank=True, on_delete=SET_NULL)`. Keep existing `proc_estetico` FK.
- **Acceptance**: no migration error; both FKs coexist.

#### 1.4 [x] Register `Sector` in Django admin
- **Files**: `backend/catalogs/admin.py`
- **Action**: `admin.site.register(Sector, SectorAdmin)` with `list_display = ("nombre", "codigo", "activo", "orden")` and search on `nombre`/`codigo`.
- **Acceptance**: sector appears at `/admin/catalogs/sector/`.

### Phase 2: Migrations

#### 2.1 [x] Schema migration
- **Command**: `python manage.py makemigrations catalogs clinical`
- **Files**: `backend/catalogs/migrations/00XX_add_sector_models.py`, `backend/clinical/migrations/00XX_add_sector_fk.py`
- **Acceptance**: `python manage.py migrate --plan` shows the new migration; applying it on a copy of the prod DB succeeds without data loss.

#### 2.2 [x] Data migration: create Sector seeds and reassign FichaSeccion
- **Files**: new migration `backend/catalogs/migrations/00XY_seed_sectores.py` or extend `seed_pdf_baseline.py` (pick one and justify).
- **Action**: Create 3 records:
  - `codigo="DEP"`, `nombre="Depilación"`
  - `codigo="MAN"`, `nombre="Manchas"`
  - `codigo="TAT"`, `nombre="Tatuajes"`
- **Action**: For each `FichaSeccion` whose `proc_estetico.codigo` is `PUNTO_D` (depilación definitiva or tratamiento de manchas per A3), set `sector=DEP`. For `PUNTO_E` (borrado tatuajes), set `sector=TAT`.
- **Acceptance**: post-migration query returns 3 Sectores and correct reassignment.

#### 2.3 [x] Update `seed_pdf_baseline.py` for new installs (modification applied locally; file is gitignored by repo convention — see Risks)
- **Files**: `backend/accounts/management/commands/seed_pdf_baseline.py`
- **Action**: Same Sector creation + FichaSeccion reassignment so fresh seeds work without needing the data migration.
- **Acceptance**: Running `python manage.py seed_pdf_baseline` on an empty DB produces 3 Sectores and correctly assigned FichaSeccion records.

### Phase 3: Filter Logic

#### 3.1 [x] Branch `_serialize_medical_config` on sector (also updated `_validate_medical_step` field-validity lookup for consistency)
- **Files**: `backend/config/prospect_conversion_views.py` (~line 490)
- **Action**: If `service_config.sector_id` is not None → filter `FichaSeccion.objects.filter(sector=..., activo=True)`. Else if `proc_estetico_id` is not None → legacy filter. Else → empty list.
- **Acceptance**: existing tests pass; manual test: prospect for "Depilación día de la madre" with sector=DEP sees same form as "Depilación definitiva".

### Phase 4: Backend Tests

#### 4.1 [x] `test_sector_crud.py`
- **Files**: `backend/tests/test_sector_crud.py`
- **Covers**: create, list (with `?active=true`), update, toggle; duplicate nombre rejected; duplicate codigo rejected (case-insensitive).

#### 4.2 [x] `test_medical_form_by_sector.py` (star test)
- **Files**: `backend/tests/test_medical_form_by_sector.py`
- **Covers**: 
  - Two `ServicioConfig` instances both with `sector=DEP` → `_serialize_medical_config` returns same section set.
  - New `ServicioConfig` named "Depilación día de la madre" with `sector=DEP` returns identical sections to existing "Depilación definitiva".

#### 4.3 [x] Extend `test_prospect_conversion.py` (file did not exist — created new)
- **Files**: `backend/tests/test_prospect_conversion.py`
- **Covers**: service with `sector=null` and `proc_estetico=null` (e.g., Cita médica) returns empty sections in step 3.

#### 4.4 [x] Run full backend test suite (29 tests run; 4 pre-existing failures in `operations.AppointmentNoShowSyncTests` unrelated to this change — see Risks)
- **Command**: `python manage.py test`
- **Acceptance**: all tests pass including new ones; coverage of new files >80% (informational, no enforced threshold).

---

## PR 2 — Frontend + Integration

### Phase 5: Admin Catalog Tab

#### 5.1 Add `'sectores'` to `catalogFallbackInfo`
- **Files**: `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx`
- **Action**: Register fallback metadata for the sixth catalog (`title`, `subtitle`, `emptyMessage`, `columns`).

#### 5.2 Verify tab appears in `AdminCatalogsPage`
- **Acceptance**: visiting `/admin/catalogos?tab=sectores` shows the CRUD interface with create form (codigo, nombre, descripcion, activo, orden).

#### 5.3 Verify CRUD operations work end-to-end
- **Acceptance**: creating a Sector via UI persists; toggling active works; list reflects changes.

### Phase 6: Service Form Dropdown

#### 6.1 Add sector dropdown to ServicioConfig create/edit form
- **Files**: `frontend/aesthetic-clinic/src/pages/cms/catalogos/todos-los-servicios/` (or wherever the service form lives — locate via grep)
- **Action**: Fetch `GET /api/admin/catalogos/sectores/?active=true`; render dropdown with empty option; persist on submit.
- **Acceptance**: selecting a sector and saving persists `ServicioConfig.sector_id`.

#### 6.2 Smoke test: create "Depilación día de la madre" with sector DEP
- **Acceptance**: new service visible in list with sector assigned; prospect conversion step 3 for that service shows same sections as "Depilación definitiva".

### Phase 7: E2E Tests

#### 7.1 `cms-catalogos-sectores.spec.ts`
- **Files**: `frontend/tests/e2e/cms-catalogos-sectores.spec.ts`
- **Covers**: tab visible at `/admin/catalogos?tab=sectores`; create a sector; toggle active; delete (if supported by the pattern).

#### 7.2 `cms-servicios-sector-dropdown.spec.ts`
- **Files**: `frontend/tests/e2e/cms-servicios-sector-dropdown.spec.ts`
- **Covers**: dropdown visible in service create/edit form; can select a sector; can save with sector=null.

### Phase 8: Verification

#### 8.1 Backend checks
- **Commands**: `python manage.py check`, `python manage.py test`, `python manage.py makemigrations --check --dry-run`.
- **Acceptance**: all pass.

#### 8.2 Frontend checks
- **Commands**: `npx tsc --noEmit`, `npm run lint`, `npm run build`, `npx playwright test`.
- **Acceptance**: all pass.

#### 8.3 End-to-end manual smoke
- **Action**: Reset DB, run migrations + seed, log in as admin, create "Depilación día de la madre" with sector DEP, run prospect conversion flow up to step 3, confirm form matches "Depilación definitiva".
- **Acceptance**: form fields identical.

---

## Dependencies

- 1.x must finish before 2.1.
- 2.1 must finish before 2.2.
- 1.x and 2.2 must finish before 3.1.
- 3.1 must finish before 4.2 / 4.3.
- 5.x depends on backend `sectores` API being live.
- 6.x depends on 5.x and backend `ServicioConfig.sector` field being exposed.

## Success Criteria

- [ ] All 9 scenarios in `medical-form-sector-management/spec.md` pass.
- [ ] All 3 scenarios in delta `admin-catalog-management/spec.md` pass.
- [ ] New service "Depilación día de la madre" with sector=DEP shows identical form sections to "Depilación definitiva".
- [ ] Service with `sector=null` shows no medical form in conversion step 3.
- [ ] `python manage.py test` exits 0.
- [ ] `npx tsc --noEmit`, `npm run lint`, `npm run build`, `npx playwright test` all exit 0.
- [ ] All commits grouped per `work-unit-commits` skill (schema, model, migrations, filter, UI, tests).
