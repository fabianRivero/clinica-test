# Tasks: manage-procedure-types-catalog

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~180–200 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |

Decision needed before apply: NO
Chained PRs recommended: NO
Chain strategy: pending
400-line budget risk: Low

---

## Phase 0: Setup

- [ ] 0.1 Create branch `feature/manage-procedure-types-catalog` from main
- [ ] 0.2 Run `cd backend && env/bin/python manage.py check` — expect clean
- [ ] 0.3 Run `cd backend && env/bin/python manage.py test backend/catalogs/tests.py -v 2` — expect 18 tests passing
- [ ] 0.4 Run `cd frontend/aesthetic-clinic && npx tsc --noEmit` — expect clean
- [ ] 0.5 Run `cd frontend/aesthetic-clinic && npx playwright test admin_general.spec.ts -g "Catalog list"` — expect 8/8 passing

## Phase 1: Backend

### 1.1 `_catalog_page_data` block
- [ ] 1.1 In `backend/config/api_views.py` (~line 1279, after `tipos-servicio` block), insert new `if catalog_key == "tipos-procedimiento":` block:
  - Model: `ProcEsteticosTipo`
  - Search field: `tipo__icontains=q`
  - Active filter: `activo=True/False`
  - Order by: `orden, tipo`
  - Entry detail fields: descripcion, procedimientos.count()
  - Metrics: `active_count = unfiltered.filter(activo=True).count()`, `total_count = unfiltered.count()`
  - Catalog meta: title "Tipos de procedimiento", createLabel "Crear tipo de procedimiento"
  - Fields: `name` (text, required), `description` (textarea, optional)

### 1.2 `_catalog_parse_payload` block
- [ ] 1.2 In `backend/config/api_views.py` (~line 1703, after `tipos-servicio` block), insert new `if catalog_key == "tipos-procedimiento":` block:
  - Map `name` → `tipo`, `description` → `descripcion`
  - Validate `tipo` is required
  - Use `ProcEsteticosTipo()` for new instances

### 1.3 Backend tests
- [ ] 1.3.1 In `backend/catalogs/tests.py`, add `"tipos-procedimiento": "/api/admin/catalogos/tipos-procedimiento/"` to `URL_TEMPLATES`
- [ ] 1.3.2 In `setUpTestData`, add fixture `cls.tipo_laser = ProcEsteticosTipo.objects.create(tipo="Laser", activo=True)` and `cls.tipo_inactivo = ProcEsteticosTipo.objects.create(tipo="Inyeccion", activo=False)` — add import if missing
- [ ] 1.3.3 Add `test_get_without_params_returns_200_for_tipos_procedimiento` (or extend existing all-catalogs test)
- [ ] 1.3.4 Add `test_search_tipos_procedimiento_filters_by_tipo`
- [ ] 1.3.5 Add `test_active_true_and_false_and_all_on_tipos_procedimiento`
- [ ] 1.3.6 Add `test_combined_q_and_active_on_tipos_procedimiento`
- [ ] 1.3.7 Add `test_invalid_active_param_returns_400_for_tipos_procedimiento`
- [ ] 1.3.8 Add `test_metrics_reflect_unfiltered_catalog_for_tipos_procedimiento`

### 1.4 Backend verification
- [ ] 1.4.1 Run `cd backend && env/bin/python manage.py test catalogs -v 2` — expect 23 tests green
- [ ] 1.4.2 Run `cd backend && env/bin/python manage.py check` — clean
- [ ] 1.4.3 Smoke: `curl /api/admin/catalogos/tipos-procedimiento/?q=laser` returns filtered list

## Phase 2: Frontend

### 2.1 AdminCatalogKey type
- [ ] 2.1 In `frontend/aesthetic-clinic/src/types/admin.ts`, add `'tipos-procedimiento'` to the `AdminCatalogKey` union

### 2.2 catalogFallbackInfo entry
- [ ] 2.2 In `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx` (~lines 23–72), add to `catalogFallbackInfo`:
  ```
  'tipos-procedimiento': { title: 'Tipos de procedimiento', description: 'Administra los tipos de procedimientos estéticos disponibles...', createLabel: 'Crear tipo de procedimiento' }
  ```

### 2.3 Page wrapper
- [ ] 2.3 In `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx` (~lines 538–568), add:
  ```
  export function AdminProcedureTypesCatalogPage() {
    return <CatalogPage catalogKey="tipos-procedimiento" />
  }
  ```

### 2.4 Route
- [ ] 2.4 In `frontend/aesthetic-clinic/src/App.tsx` (~lines 144–152), add:
  ```
  <Route path="catalogos/tipos-procedimiento" element={<AdminProcedureTypesCatalogPage />} />
  ```

### 2.5 Tab
- [ ] 2.5 In `frontend/aesthetic-clinic/src/components/admin/AdminCatalogTabs.tsx` (~lines 3–9), add to tabs array:
  ```
  { to: '/cms/catalogos/tipos-procedimiento', label: 'Tipos de procedimiento' }
  ```

### 2.6 Frontend verification
- [ ] 2.6.1 Run `cd frontend/aesthetic-clinic && npx tsc --noEmit` — clean

## Phase 3: E2E

### 3.1 Playwright E2E
- [ ] 3.1 In `frontend/aesthetic-clinic/tests/e2e/admin_general.spec.ts`, add E2E flow for `tipos-procedimiento`:
  1. Login as admin
  2. Navigate to `/cms/catalogos/tipos-procedimiento`
  3. Assert Create button visible
  4. Click Create, fill `tipo`="TestLaser${Date.now()}", submit
  5. Assert success notification and item visible in list
  6. Type substring into search input (after debounce), assert filtered list
  7. Deactivate item via toggle button
  8. Switch filter to "Inactivos" → assert item appears
  9. Switch filter to "Activos" → assert item is hidden
- [ ] 3.2 Run `cd frontend/aesthetic-clinic && npx playwright test admin_general.spec.ts -g "tipos-procedimiento"` — 1/1 green

## Phase 4: Final verification

- [ ] 4.1 `cd backend && env/bin/python manage.py test catalogs -v 2` — 23 tests green
- [ ] 4.2 `cd backend && env/bin/python manage.py check` — clean
- [ ] 4.3 `cd frontend/aesthetic-clinic && npx tsc --noEmit` — clean
- [ ] 4.4 `cd frontend/aesthetic-clinic && npx playwright test admin_general.spec.ts -g "Catalog list"` — 9/9 green (8 original + 1 new)
- [ ] 4.5 Manual smoke: open `/cms/catalogos/tipos-procedimiento` in admin, verify tab, toolbar, create/edit/toggle
- [ ] 4.6 Open PR, wait for CI, merge to main
- [ ] 4.7 Run `gentle-ai sdd-archive manage-procedure-types-catalog --cwd <repo>`

## Commit plan (single PR)

1. `feat(catalogs): add tipos-procedimiento admin catalog (backend)`
2. `feat(admin): add tipos-procedimiento route, tab, and page wrapper (frontend)`
3. `test(admin): cover tipos-procedimiento catalog list search and active filter E2E`
