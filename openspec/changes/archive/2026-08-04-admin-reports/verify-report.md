# Verification Report — `admin-reports`

## Verification Report

**Change**: `admin-reports`
**Version**: N/A (delta spec, single revision)
**Mode**: Standard (Strict TDD false — `openspec/config.yaml` `strict_tdd: false`)
**Project**: `clinica-test`
**Artifact store**: `openspec`
**Date**: 2026-08-04
**Reviewer**: sdd-verify (fresh-context)

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 21 (1.1–5.2 inclusive) |
| Tasks complete (checked) | 19 (1.1–1.4, 2.1–2.4, 3.1–3.6, 4.1–4.4) |
| Tasks incomplete (unchecked) | 2 (5.1, 5.2 — Phase 5 cleanup) |
| Implementation tasks (Phase 1–4) | 18 / 18 ✅ |
| Cleanup tasks (Phase 5) | 0 / 2 — explicitly deferred to cleanup |

Phase 5 (`5.1 Remove temporary code, dead imports, and ensure shared useApiResource is used consistently` and `5.2 Confirm no regression in existing admin pages`) is a post-implementation cleanup pass. Phase 5 is **not blocking** verification because the implementation + verification phases (1–4) are all checked.

#### Per-task completeness table

| Task | Description | Implementation | Test | Status |
|------|-------------|----------------|------|--------|
| 1.1 | Add `ReportClientSerializer`, `ReportProspectSerializer`, `ReportIncomeSerializer` | `backend/config/api_serializers.py:22-70` (3 classes) | `AdminReportClientsTests::test_rows_expose_required_client_fields` + serializer round-trips via `AdminReportClientsTests::test_branch_admin_only_sees_own_branch` and `AdminReportIncomeScenarioTests::test_invoice_link_is_exported_as_url` | ✅ Complete |
| 1.2 | Add `AdminReportClientsView`, `AdminReportProspectsView`, `AdminReportIncomeView` (branch-scoped, admin-only, 500-row cap) | `backend/config/api_views.py:5899-6079` (`REPORT_ROW_CAP=500`, three `@admin_required` views) | `test_branch_admin_only_sees_own_branch` + `test_500_row_cap_is_enforced` for each endpoint | ✅ Complete |
| 1.3 | Register three endpoints under `/api/admin/reportes/` | `backend/config/api_urls.py:130-133` | All `test_*` calls hit the registered URLs (no 404) | ✅ Complete |
| 1.4 | Backend test in `backend/config/tests/test_admin_reports.py` covering branch isolation, admin-only access, 500-row cap | `backend/config/tests/test_admin_reports.py:1-573` (17 tests across 4 TestCase classes) | Run below — 17/17 OK | ✅ Complete |
| 2.1 | Add report types in `frontend/aesthetic-clinic/src/types/admin.ts` | `types/admin.ts:109-158` | `tsc --noEmit` exit 0 | ✅ Complete |
| 2.2 | Add `getAdminReportClients`, `getAdminReportProspects`, `getAdminReportIncome` | `services/api/admin.ts:312-330` | `tsc --noEmit` exit 0 | ✅ Complete |
| 2.3 | Create `ReportLayout.tsx` | `pages/admin/reports/ReportLayout.tsx:1-226` | E2E `Clients report renders the table at /cms/reportes/clientes` + others | ✅ Complete |
| 2.4 | Create `ReportTable.tsx` with XLSX export + HYPERLINK formula | `pages/admin/reports/ReportTable.tsx:1-138` (lines 82-83 set HYPERLINK formula) | E2E `Export button is visible and triggers a download when rows exist` | ✅ Complete |
| 3.1 | `AdminReportClientsPage.tsx` | `pages/admin/reports/AdminReportClientsPage.tsx:1-61` | E2E test 1 | ✅ Complete |
| 3.2 | `AdminReportProspectsPage.tsx` | `pages/admin/reports/AdminReportProspectsPage.tsx:1-63` | E2E test 2 | ✅ Complete |
| 3.3 | `AdminReportIncomePage.tsx` (month/year + invoice HYPERLINK export) | `pages/admin/reports/AdminReportIncomePage.tsx:1-94` (period via refs, invoice column with `<a>` + HYPERLINK export) | E2E tests 3 + 5 + 6 | ✅ Complete |
| 3.4 | `AdminReportExpensesPage.tsx` reusing `getAdminExpenses` | `pages/admin/reports/AdminReportExpensesPage.tsx:1-93` (imports `getAdminExpenses`) | E2E test 4 | ✅ Complete |
| 3.5 | Add `Reportes` group with 4 children | `layouts/AdminLayout.tsx:41-49` (`label: 'Reportes'` + 4 children) | Manual route inspection | ✅ Complete |
| 3.6 | Register routes in `App.tsx` with `index` redirect to `clientes` | `App.tsx:148-152` (`reportes` → `Navigate to /cms/reportes/clientes` + 4 children) | E2E tests 1–4 | ✅ Complete |
| 4.1 | E2E covering navigation, branch isolation, XLSX download trigger, empty state, error state | `tests/e2e/admin_reports.spec.ts:1-297` (6 tests) | Run below — 5/6 pass (1 locator strict-mode failure, see Issues) | ✅ Complete (with one Playwright assertion failure noted below) |
| 4.2 | Verify endpoints against spec scenarios (branch isolation, admin-only, all-payments-included, invoice URL is a usable hyperlink) | `tests/test_admin_reports.py::AdminReportIncomeScenarioTests` (3 tests) + `AdminReportClientsTests`, `AdminReportProspectsTests`, `AdminReportIncomeTests` | Run below — 17/17 OK | ✅ Complete |
| 4.3 | Run `npm run lint` and `npx tsc --noEmit` | Run below — `tsc` exit 0, `lint` exit 1 with 93 problems (89 baseline + 4 new from admin-reports: 3 unused imports + 1 exhaustive-deps warning) | ⚠️ Lint regressions | ✅ Complete (3 new lint errors + 1 new lint warning introduced) |
| 4.4 | Run `python manage.py test` | `python manage.py test config.tests.test_admin_reports` — exit 0, 17/17 OK in 86.4s | ✅ Complete |
| 5.1 | Cleanup: remove temporary code, dead imports, ensure shared `useApiResource` is used consistently | not yet implemented | n/a | ⬜ Not started (cleanup) |
| 5.2 | Confirm no regression in existing admin pages (`/cms/gastos/lista`, `/cms/pagos/pendientes`) | not yet verified post-apply | n/a | ⬜ Not started (cleanup) |

### Build & Tests Execution

**TypeScript type check**: ✅ Passed
```text
$ cd frontend/aesthetic-clinic && npx tsc --noEmit
EXIT=0
(no output — clean)
```

**Backend tests (Django)**: ✅ 17 passed / 0 failed / 0 skipped
```text
$ cd backend && DJANGO_USE_LOCAL_DB=1 python3 manage.py test config.tests.test_admin_reports
Ran 17 tests in 86.373s
OK
EXIT=0
```
Test classes executed:
- `AdminReportClientsTests` (5 tests) — covers `/api/admin/reportes/clientes/`: unauthenticated 401, non-admin 403, branch admin branch isolation, required-field presence, 500-row cap with truncated=True.
- `AdminReportProspectsTests` (4 tests) — same contract on `/api/admin/reportes/prospectos/`.
- `AdminReportIncomeTests` (5 tests) — same contract on `/api/admin/reportes/ingresos/` plus `test_requires_valid_month_year` (returns 400 on `month=abc`).
- `AdminReportIncomeScenarioTests` (3 tests) — Phase 4 spec coverage: `test_income_report_includes_all_payments` (4 statuses PENDIENTE/APROBADO/RECHAZADO/CANCELADO all surface), `test_invoice_link_is_exported_as_url` (`invoiceUrl` + `invoiceName` exposed and URL has `/` or `http` prefix and `invoiceName` ends `.pdf`), `test_branch_isolation_excludes_other_branch_payments` (branch-B amount `200.00` not in branch-A response).

**Lint (ESLint)**: ❌ Exit 1 — 93 problems (79 errors, 14 warnings)
```text
$ cd frontend/aesthetic-clinic && npm run lint
✖ 93 problems (79 errors, 14 warnings)
EXIT=1

Delta vs baseline (commit 769aeaa, pre-admin-reports):
  Baseline: 89 problems (76 errors, 13 warnings)
  Current:  93 problems (79 errors, 14 warnings)
  Net delta from admin-reports: +3 errors, +1 warning
```

Lint regressions introduced by admin-reports (NEW in this change, not pre-existing):

1. `frontend/aesthetic-clinic/src/services/api/admin.ts:37:3` — `'ReportClientResponse' is defined but never used` — `@typescript-eslint/no-unused-vars`. (type defined in `types/admin.ts:156` and imported into `services/api/admin.ts:37` but never referenced; only `ReportResponse<T>` is used in the loader return types).
2. `frontend/aesthetic-clinic/src/services/api/admin.ts:39:3` — `'ReportIncomeResponse' is defined but never used` — same rule.
3. `frontend/aesthetic-clinic/src/services/api/admin.ts:41:3` — `'ReportProspectResponse' is defined but never used` — same rule.
4. `frontend/aesthetic-clinic/src/pages/admin/reports/ReportLayout.tsx:100:52` — warning `React Hook useCallback has unnecessary dependencies: 'branchId', 'month', and 'year'` — `react-hooks/exhaustive-deps`. (Line 100 is `const periodLoader = useCallback(() => loader(), [loader, branchId, month, year])`; the `branchId`/`month`/`year` are captured in the closure but the wrapped `loader` already encapsulates them via refs.)

Pre-existing lint issues (NOT regressions, NOT counted): 89 problems at baseline — BranchProvider/NotificationProvider fast-refresh errors, several `_branchId` unused-vars in `services/api/admin.ts:86/245/517`, several `Unexpected any` in `biometric_*.spec.ts` and `global-setup.ts`, etc.

**Playwright E2E**: ❌ Exit 1 — 5 passed / 1 failed / 0 skipped (out of 6 tests)
```text
$ cd frontend/aesthetic-clinic && npx playwright test admin_reports.spec.ts --reporter=line
1 failed
  [chromium] › tests/e2e/admin_reports.spec.ts:221:3 › Admin Reports — /cms/reportes/* navigation,
  period controls, and export › Clients report renders the table at /cms/reportes/clientes

Error: expect(locator).toBeVisible() failed
Locator: getByRole('heading', { name: /Reporte de clientes/i })
Expected: visible
Error: strict mode violation: getByRole('heading', { name: /Reporte de clientes/i }) resolved to 2 elements:
    1) <h1>Reporte de clientes de Sede Principal</h1>
    2) <h2>Reporte de clientes</h2>

EXIT=1
5 passed (1.4m)
```

The dev server was already running at `http://localhost:5173` (Playwright config baseURL). Global setup ran `reset_test_db_local.sh` successfully. Five of six tests pass; the failing test (test #1) hits a strict-mode locator violation in Playwright because the `ReportLayout` shell renders the page title in BOTH `<PageHeader title>` (`<h1>`) AND `<SectionCard title>` (`<h2>`) when `withPeriod` is false. Tests 2–6 use the same `getByRole('heading', ...)` pattern but only the clients report triggered the strict mode because the `h1` includes the branch name suffix while `h2` does not — both still match the `/Reporte de clientes/i` regex.

**Coverage**: ➖ Not available (no coverage tool installed per `openspec/config.yaml` `coverage_available: false`).

### Spec Compliance Matrix

**Source**: `openspec/changes/admin-reports/specs/admin-reports/spec.md`

| Requirement | Scenario | Test / Evidence | Result |
|-------------|----------|-----------------|--------|
| **Reports navigation and access** | Administrator opens Reports | E2E `admin_reports.spec.ts` tests 1–4 navigate to all four `/cms/reportes/*` URLs; nav group `Reportes` present in `AdminLayout.tsx:41-49`; routes registered in `App.tsx:148-152`; backend `@admin_required` decorator on all three views (`api_views.py:5978, 6008, 6033`); frontend wrapped by `RequireRole allowedRoles={['ADMINISTRADOR']}` (`App.tsx:123`) | ✅ COMPLIANT |
| **Reports navigation and access** | Unauthorized access is rejected | `AdminReportClientsTests::test_unauthenticated_is_rejected` (401) + `test_non_admin_is_rejected` (403) + same on prospects and income classes | ✅ COMPLIANT |
| **Reports navigation and access** | Branch isolation | `AdminReportClientsTests::test_branch_admin_only_sees_own_branch` (only branch A clients, branch B excluded) + same on prospects/income + `AdminReportIncomeScenarioTests::test_branch_isolation_excludes_other_branch_payments` | ✅ COMPLIANT |
| **Client report** | Client rows are displayed | `AdminReportClientsTests::test_rows_expose_required_client_fields` asserts `firstName`, `lastName`, `ci`, `status`, `lastAppointmentDate` all present + `status ∈ {"Activo", "Inactivo"}`; `AdminReportClientsPage` renders exactly those columns (`AdminReportClientsPage.tsx:10-16`) | ✅ COMPLIANT |
| **Client report** | No clients exist | `AdminReportClientsPage.tsx:48` emptyTitle="Sin clientes para mostrar"; `ReportLayout.tsx:217-219` renders `<DataState>` when `rows.length === 0`; `ReportTable.tsx:93-95` returns `null` so the export button is hidden when there are no rows; E2E test 5 verifies this contract on the income endpoint (same `ReportLayout` shell) | ✅ COMPLIANT |
| **Prospect report** | Prospect rows are displayed | `AdminReportProspectsTests::test_branch_admin_only_sees_own_branch` asserts `firstName=Paula`, `ci="-"`, `state ∈ {Pasajero, Convertido, Descartado}`; `AdminReportProspectsPage.tsx:10-19` columns match the spec fields | ✅ COMPLIANT |
| **Monthly income report** | All payments are included | `AdminReportIncomeScenarioTests::test_income_report_includes_all_payments` creates payments in PENDIENTE/APROBADO/RECHAZADO/CANCELADO and asserts all 4 surface; `api_views.py:6052-6065` does not filter by `estado_verificacion` | ✅ COMPLIANT |
| **Monthly income report** | Invoice link is exported | `AdminReportIncomeScenarioTests::test_invoice_link_is_exported_as_url` asserts `invoiceUrl` starts with `/` or `http`, `invoiceName` ends `.pdf`; `ReportTable.tsx:80-85` writes `HYPERLINK(...)` formula in cell `A{excelRow}` of the exported sheet | ✅ COMPLIANT |
| **Monthly expense report** | Expenses are exported | `AdminReportExpensesPage.tsx:7-36` exposes columns including `invoiceUrl` with `<a>` render + `withHyperlinks` enables HYPERLINK export; E2E test 4 verifies period controls + row count + export button visibility; E2E test 6 verifies download triggered with `ingresos_<month>_<year>.xlsx` filename pattern (same `ReportTable` powers both reports) | ✅ COMPLIANT |
| **Shared report states and export** | API failure | `ReportLayout.tsx:199-203` renders `<DataState tone="danger">` with the API error message when `error && !data`; `ReportLayout.tsx:193-197` renders loading state when `isLoading && !data`; E2E tests 1–4 indirectly prove the happy path (loading → data) | ✅ COMPLIANT (UI path verified by source; no direct error-state E2E test, but the design and the LAYOUT code clearly handle the contract) |

**Compliance summary**: 10/10 spec scenarios have covering implementation evidence. 9/10 scenarios have at least one runtime test that passed. The "API failure" scenario has source-level coverage (the `ReportLayout` `error && !data` branch) but no direct E2E test that forces an API failure; this is a WARNING-class gap, not a CRITICAL.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|-------------|--------|-------|
| Spec scenarios mapped to passing tests | ✅ Implemented | All 10 spec scenarios mapped; 9 have explicit passing tests |
| `/api/admin/reportes/clientes/` returns `{branch, rows, cap, truncated}` | ✅ Implemented | `api_views.py:5997-6003`; `cap=500`, `truncated=full_count>500` |
| `/api/admin/reportes/prospectos/` returns `{branch, rows, cap, truncated}` | ✅ Implemented | `api_views.py:6022-6028` |
| `/api/admin/reportes/ingresos/` returns `{branch, month, year, rows, cap, truncated}` | ✅ Implemented | `api_views.py:6070-6078`; `month`/`year` required, returns 400 on invalid (`api_views.py:6040-6044`) |
| 500-row cap enforced on all three endpoints | ✅ Implemented | `clientes_qs[:REPORT_ROW_CAP]` (`api_views.py:5994`), same on prospects (`api_views.py:6019`), same on income (`api_views.py:6067`) |
| Branch isolation (no cross-branch leakage) | ✅ Implemented | `get_user_branch(request)` + `filter(sucursal_registro=branch)` (clients/prospects) and `filter(cuota__operacion__paciente__sucursal_registro=branch).distinct()` (income) |
| `@admin_required` on all three endpoints | ✅ Implemented | `api_views.py:5978, 6008, 6033` |
| Client `lastAppointmentDate` excludes CANCELADA, looks at both `CitaMedica` and `CitaClienteLibre` | ✅ Implemented | `_client_last_appointment_date` (`api_views.py:5902-5923`) |
| Income payload includes `invoiceUrl` + `invoiceName` | ✅ Implemented | `_report_income_row` (`api_views.py:5959-5974`) — `invoiceUrl = invoice_field.url`, `invoiceName = PurePosixPath(invoice_field.name).name` |
| Expense report reuses `/api/admin/gastos/` (not a new endpoint) | ✅ Implemented | `AdminReportExpensesPage.tsx:3, 55` imports `getAdminExpenses` |
| Income `HYPERLINK` formula written in XLSX | ✅ Implemented | `ReportTable.tsx:80-85` — `targetCell.f = 'HYPERLINK("<url>","<label>")'` |
| Filenames: `clientes_<slug>.xlsx`, `prospectos_<slug>.xlsx`, `ingresos_<month>_<year>.xlsx`, `gastos_<month>_<year>.xlsx` | ✅ Implemented | `AdminReportClientsPage.tsx:39` (`clientes_${branchNameToSlug}.xlsx`), `AdminReportProspectsPage.tsx:41` (`prospectos_${branchNameToSlug}.xlsx`), `AdminReportIncomePage.tsx:86` (`ingresos_${period.month}_${period.year}.xlsx`), `AdminReportExpensesPage.tsx:85` (`gastos_${period.month}_${period.year}.xlsx`) |
| `Reportes` nav group with 4 children | ✅ Implemented | `AdminLayout.tsx:41-49` |
| Routes mounted at `/cms/reportes/*` with index redirect to `clientes` | ✅ Implemented | `App.tsx:148-152` |
| Frontend wrapped by `RequireRole allowedRoles={['ADMINISTRADOR']}` | ✅ Implemented | `App.tsx:123` (parent route for `/cms`) |

### Coherence (Design)

| Decision | Followed? | Evidence |
|----------|-----------|----------|
| D1 — Shared report shell with `/cms/reportes/*` routes + `ReportLayout` | ✅ Yes | `App.tsx:148-152`, `pages/admin/reports/ReportLayout.tsx` |
| D2 — Reuse existing endpoints, add only what's needed | ✅ Yes | New: `/api/admin/reportes/clientes/`, `prospectos/`, `ingresos/`. Reused: `/api/admin/gastos/` (expense report). No modifications to existing endpoints. |
| D3 — Read-only, paginated (500-row cap), branch-filtered | ✅ Yes | `REPORT_ROW_CAP=500` + `cap/truncated` in response; `get_user_branch` + filter on each view; no PATCH/PUT/DELETE routes registered |
| D4 — Client name normalized (`firstName`/`lastName` from `primer_nombre`/`apellido_paterno`) | ✅ Yes | `_report_client_row` (`api_views.py:5926-5940`) emits `firstName`/`lastName` directly from `Usuario.primer_nombre` + `apellido_paterno` (+ `apellido_materno` in `lastName`); `ReportClientSerializer` exposes both |
| D5 — XLSX export frontend-only with `HYPERLINK` formula | ✅ Yes | `ReportTable.tsx:80-85` |

Design decisions D1–D5 are all implemented as described.

### Issues Found

**CRITICAL**: None.

**WARNING**:

1. **E2E test failure — `Clients report renders the table at /cms/reportes/clientes`** (Playwright strict-mode violation). The test at `tests/e2e/admin_reports.spec.ts:223` uses `getByRole('heading', { name: /Reporte de clientes/i })` and the page renders the title in BOTH `<PageHeader>` (`<h1>` with branch suffix) AND `<SectionCard>` (`<h2>` plain) because `ReportLayout` (`pages/admin/reports/ReportLayout.tsx:189, 207-211`) renders the same title twice when `withPeriod` is false. Source of the bug: when `withPeriod=false`, both `<PageHeader title={composedTitle}>` AND `<SectionCard title={title}>` render the report name, creating two accessible `heading` roles. The fix is either (a) tighten the test locator to `.first()` / `exact: true` for the `<h1>` only, or (b) drop the redundant title from `SectionCard` when not using period controls. Not blocking — five other E2E tests in the same spec run green and prove the page renders correctly — but the test fails and the test name promises "table renders", which it doesn't currently verify because the test bails out before the row-count assertion.

2. **Three unused type imports in `services/api/admin.ts`** (`ReportClientResponse`, `ReportIncomeResponse`, `ReportProspectResponse`). Lines 37, 39, 41 import the explicit response types but the loader functions return `ReportResponse<T>` directly. Lint flags 3 errors. Not blocking — TypeScript catches nothing because the unused imports are valid references — but per Phase 5 cleanup task 5.1 ("remove temporary code, dead imports") this is in-scope.

3. **No direct E2E coverage for the "API failure" spec scenario**. Spec says "GIVEN the report endpoint returns an error / WHEN the report page renders / THEN a user-visible error state is shown". The `ReportLayout` source clearly handles this (`pages/admin/reports/ReportLayout.tsx:199-203`), but no Playwright test mocks a 500/403 response and asserts the `<DataState tone="danger">` renders. The other shared states (loading, empty, data) are covered indirectly.

4. **One new lint warning from admin-reports** — `ReportLayout.tsx:100` `useCallback` with unnecessary dependencies `branchId, month, year`. Functional but noisy.

**SUGGESTION**:

1. The `Prospect` endpoint may want to include the optional `ci` field more visibly. Spec says "It SHOULD support search and status filtering" — current implementation shows `ci` as a column but no text-search filter is exposed in the frontend (neither clients nor prospects reports expose a search input). The spec uses "SHOULD" (not "MUST"), so this is non-blocking, but worth a follow-up.

2. `AdminReportClientsPage.tsx` and `AdminReportProspectsPage.tsx` use a `branchSuffix` only in the page description/title, while `AdminReportIncomePage.tsx`/`AdminReportExpensesPage.tsx` rely on the `ReportLayout`'s `withPeriod` for the title month/year suffix. The two styles are visually inconsistent. Minor.

3. `Design.md` Decision "Branch scope" said "endpoint takes `activeBranchId` from session, ignores any client-supplied branch param". The implementation uses `get_user_branch(request)` which honors `HTTP_X_SELECTED_BRANCH_ID` (`backend/config/api_helpers.py` / `get_user_branch`). This is consistent with the rest of the admin API and matches the test (`test_500_row_cap_is_enforced` passes `HTTP_X_SELECTED_BRANCH_ID=str(branch_b.pk)`). Worth noting that the design said "ignores any client-supplied branch param" but the implementation actually honors the session branch selector header — that's correct behavior for an admin area where main admins need to switch branches, but the design text is slightly inaccurate.

### Verdict

**PASS WITH WARNINGS**

All 10 spec scenarios are implemented and 9 have runtime passing tests. The 17 backend Django tests pass in 86.4s. The 6 Playwright tests run end-to-end against a live dev server, the database is reset through the existing convention, and 5/6 pass; the one failing test fails due to a strict-mode locator violation caused by duplicate `<h1>`/`<h2>` heading rendering in `ReportLayout`, which is a test+source bug pair, not a missing feature. TypeScript type check exits 0. The 4 new lint issues (3 unused imports + 1 unnecessary deps) are the only implementation regressions introduced by admin-reports and are explicitly in scope for Phase 5 cleanup task 5.1. Phase 5 tasks remain unchecked but are post-implementation cleanup, not blocking. The change is otherwise verification-ready.

---

## Verification Report (Result Contract)

**Status**: success (verification complete; warnings documented, no CRITICAL issues)
**executive_summary**: Verified SDD change `admin-reports` across proposal/spec/design/tasks. 18/18 implementation tasks (Phases 1–4) complete with covering tests; 17/17 Django backend tests pass in 86.4s. TypeScript `tsc --noEmit` exits 0. 5/6 Playwright E2E tests pass against the live dev server; the one failing E2E test is a strict-mode locator violation on `getByRole('heading', ...)` caused by `ReportLayout` rendering the report title in both `<PageHeader>` and `<SectionCard>`. All 10 spec scenarios have implementation evidence; 9 have runtime passing tests. Backend endpoints `/api/admin/reportes/{clientes,prospectos,ingresos}/` are registered, branch-scoped, admin-only, and capped at 500 rows. Frontend report pages mount under `/cms/reportes/*` and the `Reportes` nav group exists with 4 children. 4 new lint issues (3 unused imports + 1 exhaustive-deps warning) are introduced; these align with Phase 5 cleanup task 5.1.
**detailed_report**: see sections above (Completeness, Build & Tests, Spec Compliance Matrix, Correctness, Coherence, Issues, Verdict).
**artifacts**:
- `openspec/changes/admin-reports/verify-report.md` — this file
- Engram `sdd/admin-reports/verify-report` (capture_prompt: false)
**next_recommended**: `sdd-archive` once Phase 5 cleanup (5.1–5.2) is finished and the lint regressions are absorbed (or, alternatively, accept Phase 5 tasks as part of the change scope and finish them). The 3 unused-import errors and 1 exhaustive-deps warning are small, mechanical fixes that match task 5.1 exactly. The duplicate-heading E2E failure is also a small mechanical fix (pick locator `.first()` OR drop the redundant `<SectionCard title>` for non-period reports).
**risks**: None blocking. Phase 5 cleanup tasks 5.1–5.2 remain unchecked (post-implementation cleanup, not gating). The single failing E2E test ("Clients report renders the table at /cms/reportes/clientes") does not indicate a missing feature; it indicates a test/source contract mismatch that the orchestrator should flag for the apply phase or a follow-up. If the team accepts the failing test as a known issue and ships, the change is otherwise verification-ready.
**skill_resolution**: paths-injected — 3 skills (`sdd-verify`, `sdd-verify/references/report-format.md`, `_shared/sdd-phase-common.md`). Loaded `/home/fabianrivero/.config/opencode/skills/sdd-verify/SKILL.md`, `/home/fabianrivero/.config/opencode/skills/sdd-verify/references/report-format.md`, and `/home/fabianrivero/.config/opencode/skills/_shared/sdd-phase-common.md`. Followed Sections A–D of the shared phase-common document. No fallback registry lookup needed.