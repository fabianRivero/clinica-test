# Tasks: Admin Reports

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 700-900 (frontend + backend + tests) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Frontend shell + clients/prospects (PR 1) → Income endpoint + page (PR 2) → Expenses read-only mirror + E2E (PR 3) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Reports shell + clients and prospects reports | PR 1 | Base: `feature/admin-reports`. Adds shell, table component, two pages, frontend types, two new endpoints. |
| 2 | Income report | PR 2 | Base: `feature/admin-reports-pr1`. Adds income endpoint, income page, joins `Pago` + `Cliente` + service + invoice. |
| 3 | Expenses read-only mirror + E2E coverage | PR 3 | Base: `feature/admin-reports-pr2`. Adds expenses page, e2e tests covering nav, isolation, exports, empty states. |

### Override: single-PR `size:exception`

The team has approved `size:exception`, so the work will be delivered as a single PR against `main`, but the stacked PRs above still describe the implementation order. The reviewer burden is absorbed by the existing 400-line review budget exception.

## Phase 1: Foundation (Backend contract)

- [x] 1.1 Add `ReportClientSerializer`, `ReportProspectSerializer`, `ReportIncomeSerializer` in `backend/config/api_serializers.py` with `firstName`, `lastName`, `ci`, `status`, `lastAppointmentDate` for clients.
- [x] 1.2 Add `AdminReportClientsView`, `AdminReportProspectsView`, `AdminReportIncomeView` in `backend/config/api_views.py`; branch-scoped, admin-only, 500-row cap.
- [x] 1.3 Register the three endpoints under `/api/admin/reportes/` in `backend/config/api_urls.py`.
- [x] 1.4 Add backend test in `backend/config/tests/test_admin_reports.py` covering branch isolation, admin-only access, and 500-row cap.

## Phase 2: Frontend shell and shared primitives

- [x] 2.1 Add `ReportClient`, `ReportProspect`, `ReportIncomeItem`, `ReportResponse` in `frontend/aesthetic-clinic/src/types/admin.ts`.
- [x] 2.2 Add `getAdminReportClients`, `getAdminReportProspects`, `getAdminReportIncome` in `frontend/aesthetic-clinic/src/services/api/admin.ts`.
- [x] 2.3 Create `ReportLayout.tsx` in `pages/admin/reports/` with branch header, loading/error/empty wrappers, and month/year controls.
- [x] 2.4 Create `ReportTable.tsx` in `pages/admin/reports/` with `columns[]` slot and XLSX export button using `xlsx` and `HYPERLINK` formulas for invoice URLs.

## Phase 3: Report pages and navigation

- [ ] 3.1 Create `AdminReportClientsPage.tsx` rendering `firstName`, `lastName`, `ci`, `status`, `lastAppointmentDate` and the export button.
- [ ] 3.2 Create `AdminReportProspectsPage.tsx` rendering `firstName`, `lastName`, `phone`, `ci`, `interest`, `state`, `createdAt`, `registeredBy`.
- [ ] 3.3 Create `AdminReportIncomePage.tsx` with month/year controls, income rows, invoice `HYPERLINK` export.
- [ ] 3.4 Create `AdminReportExpensesPage.tsx` reusing `getAdminExpenses` and the existing month/year UX; export mirrors `AdminExpenseListPage`.
- [ ] 3.5 Add `Reportes` group in `layouts/AdminLayout.tsx` with 4 children (`/cms/reportes/clientes`, `prospectos`, `ingresos`, `gastos`).
- [ ] 3.6 Register routes in `App.tsx` and add `index` redirect to `clientes`.

## Phase 4: Testing and verification

- [ ] 4.1 Add `tests/e2e/admin_reports.spec.ts` covering: navigation, branch isolation, XLSX download trigger, empty state, and error state.
- [ ] 4.2 Verify the new endpoints against the spec scenarios: branch isolation, admin-only, all-payments included, invoice URL is a usable hyperlink.
- [ ] 4.3 Run `npm run lint` and `npx tsc --noEmit` in `frontend/aesthetic-clinic/`.
- [ ] 4.4 Run `python manage.py test` in `backend/`.

## Phase 5: Cleanup

- [ ] 5.1 Remove temporary code, dead imports, and ensure shared `useApiResource` is used consistently.
- [ ] 5.2 Confirm no regression in existing admin pages (`/cms/gastos/lista`, `/cms/pagos/pendientes`).
