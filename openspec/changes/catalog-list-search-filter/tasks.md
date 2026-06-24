# Tasks: catalog-list-search-filter

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~500 (backend ~240 + frontend ~260) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | 2-PR chain: PR1 (backend+tests) → PR2 (frontend+E2E) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Backend filter + Django unittest coverage | PR 1 | Base = main; independent, merges alone |
| 2 | Frontend search/filter UI + debounce + create-button fix + Playwright E2E | PR 2 | Base = main (after PR1); depends on API contract |

---

## Phase 0: Setup
- [x] 0.1 Create branch `feature/catalog-list-search-filter-pr1-backend` from main
- [x] 0.2 Run `python manage.py check` (baseline clean)
- [x] 0.3 Run `python manage.py test backend/catalogs/tests.py` (0 tests, file is empty)

## Phase 1: PR1 — Backend (filter + tests)

### 1.1 Param reading in `admin_catalogo_detalle`
- [x] 1.1.1 In `admin_catalogo_detalle` (`api_views.py:3987`), read `request.GET.get('q', '')` and `request.GET.get('active', 'all')`. Pass both to `_catalog_page_data` as `q=` and `active=` kwargs.
- [x] 1.1.2 Validate `active` is one of `'true'`, `'false'`, `'all'`; return 400 for unknown values.

### 1.2 Update `_catalog_page_data` signature
- [x] 1.2.1 Change `_catalog_page_data(catalog_key)` → `_catalog_page_data(catalog_key, q='', active='all')` at `api_views.py:1056`.

### 1.3 Apply filters per catalog branch (before `order_by`)
- [x] 1.3.1 `todos-los-servicios` (`api_views.py:1060`): after `select_related()`, chain `.filter(Q(tipo_servicio__tipo__icontains=q) | Q(proc_estetico__proceso__icontains=q))` when `q`, plus `.filter(activo=True)` or `.filter(activo=False)` when `active != 'all'`.
- [x] 1.3.2 `procedimientos-esteticos` (`api_views.py:1153`): chain `.filter(proceso__icontains=q)` when `q`, plus active-state filter.
- [x] 1.3.3 `tipos-servicio` (`api_views.py:1209`): chain `.filter(tipo__icontains=q)` when `q`, plus active-state filter.
- [x] 1.3.4 `especialidades` (`api_views.py:1396`): chain `.filter(nombre__icontains=q)` when `q`, plus active-state filter.
- [x] 1.3.5 `categorias-gasto` (`api_views.py:1487`): chain `.filter(nombre__icontains=q)` when `q`, plus active-state filter.
- [x] 1.3.6 Skip `.filter()` calls when `q` is empty and `active == 'all'` (no-op path preserved).

### 1.4 Backend tests (Django unittest, NOT pytest)
- [x] 1.4.1 Add `from django.test import TestCase` and `from django.db.models import Q` to `backend/catalogs/tests.py`.
- [x] 1.4.2 Add `CatalogDetailFilterTests(TestCase)`: test GET without params returns all items (sanity).
- [x] 1.4.3 Test: `?q=foo` returns only items whose searchable field contains "foo" (case-insensitive).
- [x] 1.4.4 Test: `?active=true` returns only items where `activo=True`.
- [x] 1.4.5 Test: `?active=false` returns only items where `activo=False`.
- [x] 1.4.6 Test: `?active=all` returns all items regardless of active state.
- [x] 1.4.7 Test: `?q=foo&active=true` combines both filters.
- [x] 1.4.8 Test: `?active=invalid` returns HTTP 400.
- [x] 1.4.9 Test: for `todos-los-servicios`, search matches `tipo_servicio__tipo` OR `proc_estetico__proceso`.

### 1.5 PR1 verification
- [x] 1.5.1 `python manage.py test backend/catalogs/tests.py` — all green.
- [x] 1.5.2 `python manage.py check` — clean.
- [x] 1.5.3 `python manage.py test` — no new failures (pre-existing `AppointmentNoShowSyncTests` errors unchanged).
- [ ] 1.5.4 Smoke: `GET /api/admin/catalogos/tipos-servicio/?q=est` returns filtered list.
- [ ] 1.5.5 Open PR1, wait for CI, merge to main.

## Phase 2: PR2 — Frontend (UI + debounce + create button + E2E)

### 2.0 Setup
- [x] 2.0.1 Create branch `feature/catalog-list-search-filter-pr2-frontend` from main (after PR1 merged).
- [x] 2.0.2 `npm run lint` and `npx tsc --noEmit` — baseline clean.

### 2.1 Service signature
- [x] 2.1.1 In `frontend/aesthetic-clinic/src/services/api/admin.ts:340`, change `getAdminCatalogDetail(catalogKey)` to accept optional `params?: { q?: string; active?: 'true'|'false'|'all' }`. Build `URLSearchParams` and append `?q=` and `?active=` when set.

### 2.2 useDebounce hook
- [x] 2.2.1 Create `frontend/aesthetic-clinic/src/hooks/useDebounce.ts` with generic `useDebounce<T>(value: T, delay: number): T` using `useState` + `setTimeout`/`clearTimeout` in `useEffect`.

### 2.3 CatalogPage state + UI
- [x] 2.3.1 In `CatalogPage` (`AdminCatalogsPage.tsx:368`), add state: `searchQuery` (string), `activeFilter` (`'all'|'true'|'false'`), `debouncedQuery` via `useDebounce(searchQuery, 300)`.
- [x] 2.3.2 Add `useEffect` that calls `reload()` when `debouncedQuery` or `activeFilter` change. Build `loader` with `getAdminCatalogDetail(catalogKey, { q: debouncedQuery, active: activeFilter })`.
- [x] 2.3.3 Add search `<input type="search">` and active-filter `<select>` (Todos/Activos/Inactivos) above `.catalog-admin-list`, inside the `SectionCard` that wraps the list.
- [x] 2.3.4 Change `showCreateAction` default from `false` to `true` in `CatalogPage` props. Remove `showCreateAction={false}` from all 5 wrappers at lines 539, 543, 547, 559, 563.

### 2.4 Playwright E2E
- [x] 2.4.1 Add E2E to `frontend/aesthetic-clinic/tests/e2e/admin_general.spec.ts`: parameterized flow over the 5 in-scope catalog keys — navigate → create item → search by title → assert filtered → deactivate → switch to "Inactivos" → assert item visible → switch to "Activos" → assert item hidden.

### 2.5 PR2 verification
- [x] 2.5.1 `npm run lint` — clean (no new errors).
- [x] 2.5.2 `npx tsc --noEmit` — clean.
- [x] 2.5.3 `npx playwright test admin_general.spec.ts` — all green (5/5 catalog tests passing in 23.1s).
- [ ] 2.5.4 Manual smoke: open `/cms/catalogos/tipos-servicio`, search "est", filter to Inactivos, verify UI.
- [ ] 2.5.5 Open PR2, wait for CI, merge to main.

## Phase 3: Archive (after both PRs merged)
- [ ] 3.1 Run `gentle-ai sdd-archive catalog-list-search-filter --cwd /media/fabianrivero/disco-d/proyecto C` per orchestrator instructions.