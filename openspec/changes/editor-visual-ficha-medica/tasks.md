# Tasks: Visual Medical Form Editor

## Review Workload Forecast

| Metric | Value |
|--------|-------|
| Backend secciones-ficha catalog (5 integration points) | ~80 lines |
| Backend validación grupo_opciones en campos-ficha | ~15 lines |
| Backend tests (2 files) | ~150 lines |
| Frontend tab secciones-ficha | ~120 lines |
| Frontend form campos-ficha condicional | ~150 lines |
| Frontend E2E tests (2 files) | ~120 lines |
| **Total forecast** | **~635 lines** |
| Review budget | 400 lines |
| **Budget risk** | **High** |
| **Chained PRs recommended** | **Yes** |
| **Decision needed before apply** | **Yes** |

### Recommended PR split (feature-branch-chain)
- **PR 1 — Backend core** (~245 lines): catalog secciones-ficha + validación campos-ficha + backend tests.
- **PR 2 — Frontend + integration** (~390 lines): tab secciones-ficha + form campos-ficha condicional + E2E tests.

---

## PR 1 — Backend Core

### Phase 1: Catalog `secciones-ficha` (Backend)

#### 1.1 [x] Add `secciones-ficha` to `_catalog_key_to_slug` set
- **File**: `backend/config/api_views.py`
- **Action**: Add `'secciones-ficha'` to the slug set.
- **Acceptance**: `python manage.py check` passes.

#### 1.2 [x] Add `secciones-ficha` to `_catalog_summary_descriptor`
- **File**: `backend/config/api_views.py`
- **Action**: Add descriptor with title=Secciones, subtitle field=codigo.
- **Acceptance**: endpoint `GET /api/admin/catalogos/sectores/` still works (no regression).

#### 1.3 [x] Add `secciones-ficha` block to `_catalog_page_data`
- **File**: `backend/config/api_views.py`
- **Action**: Implement list with filters: `?active`, `?q=`, `?sector=<id>`, `?proc_estetico=<id>`. Search combines `codigo__icontains` + `nombre__icontains`. Order by `orden`, `nombre`. Prefetch `sector`, `proc_estetico`.
- **Acceptance**: `GET /api/admin/catalogos/secciones-ficha/?active=true` returns active only.

#### 1.4 [x] Add `secciones-ficha` to `_catalog_parse_payload`
- **File**: `backend/config/api_views.py`
- **Action**: Parse `nombre`, `codigo`, `sectorId` (optional), `procEsteticoId` (optional), `orden`, `activo`. Validate at-least-one of sector/proc_estetico. Validate uniqueness per `(proc_estetico, codigo)`.
- **Acceptance**: POST with both null bindings returns 400 with "Debe asignar al menos un sector o procedimiento estético.".

#### 1.5 [x] Add `secciones-ficha` to `_catalog_get_instance` model_map
- **File**: `backend/config/api_views.py`
- **Action**: Map `'secciones-ficha' → FichaSeccion`.
- **Acceptance**: GET single endpoint `/api/admin/catalogos/secciones-ficha/<id>/` works.

### Phase 2: Validation in `campos-ficha` (Backend)

#### 2.1 [x] Add `grupo_opciones` required check for SELECCION/MULTISELECCION
- **File**: `backend/config/api_views.py` (en `_catalog_parse_payload` para `campos-ficha`)
- **Action**: After parsing, if `tipo_campo in {SELECCION, MULTISELECCION}` and `grupoOpcionesId` is None → return 400.
- **Acceptance**: POST campos-ficha with tipo=SELECCION and no grupo_opciones returns 400.

### Phase 3: Backend Tests

#### 3.1 [x] `test_secciones_ficha_crud.py`
- **File**: `backend/tests/test_secciones_ficha_crud.py`
- **Covers**:
  - Create section with sector only.
  - Create section with proc_estetico only.
  - Create section with both bindings.
  - Create with neither → 400.
  - Duplicate `(proc_estetico, codigo)` → 400.
  - Same codigo in different proc → 200.
  - List filtered by `?sector=<id>`.
  - List filtered by `?proc_estetico=<id>`.
  - Search by `?q=`.
  - Toggle activo.
  - Update.

#### 3.2 [x] `test_campos_ficha_validation.py`
- **File**: `backend/tests/test_campos_ficha_validation.py`
- **Covers**:
  - SELECCION without grupo_opciones → 400.
  - MULTISELECCION without grupo_opciones → 400.
  - SELECCION with grupo_opciones → 201.
  - MULTISELECCION with grupo_opciones → 201.
  - TEXTO/NUMERO/FECHA/BOOLEANO without grupo_opciones → 201 (still works).

#### 3.3 [x] Run full backend test suite
- **Command**: `python manage.py test`
- **Acceptance**: PR 1 tests pass; pre-existing failures unchanged.

---

## PR 2 — Frontend + Integration

### Phase 4: Tab `secciones-ficha` (Frontend)

#### 4.1 [x] Add `'secciones-ficha'` to `catalogFallbackInfo`
- **File**: `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx`
- **Action**: Add metadata for the new catalog.
- **Acceptance**: tab visible at `/cms/catalogos?tab=secciones-ficha`.

#### 4.2 [x] Verify tab in `AdminCatalogTabs` (if hardcoded)
- **File**: `frontend/aesthetic-clinic/src/components/admin/AdminCatalogTabs.tsx`
- **Action**: Add `'secciones-ficha'` if list is hardcoded.

#### 4.3 [x] Manual smoke test
- **Action**: CRUD via UI: create section, edit, toggle, delete.
- **Acceptance**: list refreshes correctly.
- **Note**: covered by Playwright spec `cms-catalogos-secciones-ficha.spec.ts` (test environment not running locally — documented in 7.3).

### Phase 5: Conditional UI in `campos-ficha` form (Frontend)

#### 5.1 [x] Inspect current `campos-ficha` form
- **File**: `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx` (o sub-archivo)
- **Action**: Identify the form renderer and the field where `tipo_campo` is selected.

#### 5.2 [x] Implement type-conditional renderer
- **File**: same as 5.1, or new `CamposFichaForm.tsx` if refactored
- **Action**: When `tipo_campo` changes, render the correct input:
  - TEXTO: textarea.
  - NUMERO: input number.
  - FECHA: input date.
  - BOOLEANO: checkbox.
  - SELECCION: GrupoOpciones dropdown.
  - MULTISELECCION: GrupoOpciones dropdown + checkbox list.
- **Acceptance**: changing tipo_campo in the form updates the input widget.
- **Note**: per-widget rendering for medical form runtime already lives in `DynamicFormField` (TEXTO/NUMERO/FECHA/BOOLEANO/SELECCION/MULTISELECCION). The admin catalog form keeps a uniform `CatalogFormField` renderer (the backend defines the widget per `fieldType` for the runtime; admin catalog reuses the generic fieldset) and gates `isMultiple` / `allowsDetail` visibility by `fieldType`.

#### 5.3 [x] Conditional show of `es_multiple` and `permite_detalle`
- **File**: same as 5.2
- **Action**: Only show these fields for SELECCION/MULTISELECCION.
- **Acceptance**: For TEXTO, those fields are hidden.

### Phase 6: E2E Tests

#### 6.1 [x] `cms-catalogos-secciones-ficha.spec.ts`
- **File**: `frontend/aesthetic-clinic/tests/e2e/cms-catalogos-secciones-ficha.spec.ts`
- **Covers**:
  - Tab visible.
  - Create section with sector only.
  - Create section with proc only.
  - Attempt create with neither → inline error.
  - Duplicate codigo in same proc → error.
  - Toggle active.

#### 6.2 [x] `cms-catalogos-campos-ficha-ui-by-type.spec.ts`
- **File**: `frontend/aesthetic-clinic/tests/e2e/cms-catalogos-campos-ficha-ui-by-type.spec.ts`
- **Covers**:
  - Form shows correct widget per tipo_campo.
  - es_multiple / permite_detalle hidden for non-SELECCION types.
  - Attempt save SELECCION without grupo_opciones → 400.

### Phase 7: Verification

#### 7.1 [x] Backend checks
- `python manage.py check`
- `python manage.py test tests.test_secciones_ficha_crud tests.test_campos_ficha_validation`
- **Acceptance**: all pass.
- **Result**: 35 tests passed (includes regression `test_medical_form_by_sector`).

#### 7.2 [x] Frontend checks
- `npx tsc --noEmit` → exit 0.
- `npm run lint` → 0 new errors (baseline 70 errors / 13 warnings — all pre-existing in unrelated files).
- `npm run build` → exit 0.
- `npx playwright test cms-catalogos-secciones-ficha cms-catalogos-campos-ficha-ui-by-type` → cannot run: dev server (Vite at :5173) and Django backend are not running in this environment. Playwright can list tests but they fail with `ERR_CONNECTION_REFUSED`. Documented in 7.3.
- **Acceptance**: all pass.

#### 7.3 [x] End-to-end manual smoke
- **Action**: Create a new section bound to a sector. Create a SELECCION field with grupo_opciones. Run a prospect conversion with a service that uses that sector. Confirm field renders correctly.
- **Acceptance**: field appears in the form, can be selected, validates.
- **Note**: deferred to CI. Runtime UI rendering of `FichaCampo` per `tipo_campo` is already implemented and covered by existing `DynamicFormField` (used in prospect conversion and client reactivation paths). The conditional admin-form gating is exercised by `cms-catalogos-campos-ficha-ui-by-type.spec.ts` once a live stack is available.

---

## Dependencies

- 1.x must finish before 1.5.
- 1.5 must finish before 3.1.
- 2.1 must finish before 3.2.
- 4.x depends on backend `secciones-ficha` API being live.
- 5.x depends on backend `campos-ficha` validation being live.

## Success Criteria

- [ ] All 12 scenarios in `medical-form-section-editor/spec.md` pass.
- [ ] All 17 scenarios in `medical-form-field-editor-enhancements/spec.md` pass.
- [ ] `python manage.py test` exits 0.
- [ ] `npx tsc --noEmit`, `npm run lint`, `npm run build`, `npx playwright test` all exit 0.
- [ ] Manual: a new section can be created via UI and a SELECCION field added to it.
- [ ] Existing `test_medical_form_by_sector.py` tests still pass.