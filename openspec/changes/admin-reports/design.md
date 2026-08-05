# Design: Admin Reports

## Technical Approach

Build a brand-new read-only Reports section inside the admin SPA, anchored on four dedicated routes sharing one shell and a single set of period/loading/empty/export primitives. The shell reuses the existing `BranchProvider` context and the `xlsx` package already in the bundle. Each report reuses the closest existing admin API endpoint wherever the payload already carries the required fields and branch isolation; otherwise it calls a new, narrowly-scoped report endpoint. Backend additions are minimal: only the income report needs a new endpoint family because the existing `/api/admin/pagos/` aggregator does not return `invoiceUrl`/`invoiceName` or `lastAppointmentDate` per client. Clients, prospects, and expenses reuse existing endpoints.

## Architecture Decisions

### Decision: Shared report shell with feature pages

| Option | Tradeoff | Decision |
|---|---|---|
| One mega page with all four tables | Simple nav, but state and unload cost grow | Rejected |
| New `/cms/reportes/*` routes with a `ReportLayout` shell | Clean URLs, lazy per-report state, mirrors existing admin patterns | **Chosen** |

**Rationale**: Matches the existing top-level groupings (`Gastos`, `Pagos y cuotas`) and keeps each report's filtering/period state independent.

### Decision: Reuse existing endpoints, add only the minimum new ones

| Endpoint | Action | Reason |
|---|---|---|
| `/api/admin/prospectos` GET | **Reuse** | Already returns `ProspectLead[]` with `state`, `interest`, `phone`, `createdAt`, `branchId`. |
| `/api/admin/pagos/` GET | **New family**: `/api/admin/reportes/ingresos/?month=&year=` | The existing endpoint is filtered for the actionable payments UI and does not expose `invoiceUrl`/`invoiceName` per row. |
| `/api/admin/reportes/clientes/?branchId=` | **New** | `/api/admin/prospectos` returns both prospects and clients mixed for the conversion UI; we need clients-only with `lastAppointmentDate`. |
| `/api/admin/gastos/` GET | **Reuse** | Already month/year, branch-scoped, returns `invoiceUrl`. |

**Rationale**: Avoid changing API surface that already works for the conversion flow; add only what the report needs.

### Decision: Report endpoints are read-only and return paginated, branch-filtered payloads

| Concern | Approach |
|---|---|
| Branch isolation | `IsAdminBranchMember` reused; endpoint takes `activeBranchId` from session, ignores any client-supplied branch param to avoid tampering. |
| Pagination | Hard cap of 500 rows per report; ETag-based revalidation handled by the shared `useApiResource` hook. |
| Invoice URL | Same field name (`invoiceUrl`) as expenses; no rewriting. |
| `lastAppointmentDate` | New column on the client serializer; sourced from the most recent `Cita` (excluding `CANCELADA`) on the client's branch. |

### Decision: Client report columns are normalized splits of name

Frontend splits `name` into `firstName` (token before the first space) and `lastName` (token after the first space) only when the backend payload exposes `primerNombre`/`apellidoPaterno`. Otherwise (legacy clients) it falls back to a space split of `name`. The `ClientSnapshot` serializer on the new endpoint emits `firstName` and `lastName` explicitly so the report never re-splits strings.

### Decision: XLSX export is frontend-only, links only

`xlsx` already in bundle. Workbook generated with `XLSX.utils.json_to_sheet` + `XLSX.writeFile`. Invoice URLs are written as a `HYPERLINK` formula so Excel renders a clickable link. Filenames: `clientes_<branchSlug>.xlsx`, `prospectos_<branchSlug>.xlsx`, `ingresos_<month>_<year>.xlsx`, `gastos_<month>_<year>.xlsx`.

## Data Flow

```
AdminNavbar
  └── /cms/reportes/*  (RequireRole: ADMINISTRADOR)
        └── ReportLayout
              ├── useApiResource(report-loader)
              ├── ReportState: loading | error | empty | data
              └── ReportTable
                    ├── PeriodControls (month/year only for income/expenses)
                    ├── ExportXlsxButton (disabled when no rows)
                    └── Table view (sorted + filtered subset of dataset)
```

```
PeriodControls → month/year state
ExportXlsxButton → derives XLSX rows from the current data subset
Backend (only new endpoints):
  Branch middleware → activeBranchId resolution → queryset filter
  → Response builder wraps {month, year, branch, metrics, rows[]}
```

## File Changes

| File | Action | Description |
|---|---|---|
| `frontend/aesthetic-clinic/src/layouts/AdminLayout.tsx` | Modify | Add `Reportes` group with 4 children. |
| `frontend/aesthetic-clinic/src/App.tsx` | Modify | Add `/cms/reportes/*` routes (index → `clientes`, then `prospectos`, `ingresos`, `gastos`). |
| `frontend/aesthetic-clinic/src/pages/admin/reports/ReportLayout.tsx` | New | Shared shell: header, period controls, empty/error/loading wrappers. |
| `frontend/aesthetic-clinic/src/pages/admin/reports/ReportTable.tsx` | New | Generic table component with `columns[]` and export. |
| `frontend/aesthetic-clinic/src/pages/admin/reports/AdminReportClientsPage.tsx` | New | Client report. |
| `frontend/aesthetic-clinic/src/pages/admin/reports/AdminReportProspectsPage.tsx` | New | Prospect report. |
| `frontend/aesthetic-clinic/src/pages/admin/reports/AdminReportIncomePage.tsx` | New | Income report (month/year + XLSX). |
| `frontend/aesthetic-clinic/src/pages/admin/reports/AdminReportExpensesPage.tsx` | New | Expenses report (reuses monthly logic; XLSX). |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Modify | Add `getAdminReportClients`, `getAdminReportProspects`, `getAdminReportIncome`. |
| `frontend/aesthetic-clinic/src/types/admin.ts` | Modify | Add `ReportClient`, `ReportProspect`, `ReportIncomeItem`, `ReportClientResponse`, `ReportProspectResponse`, `ReportIncomeResponse`. |
| `backend/config/api_views.py` | Modify | Add `AdminReportClientsView`, `AdminReportProspectsView`, `AdminReportIncomeView`; branch-scoped, read-only. |
| `backend/config/api_urls.py` | Modify | Register the three new endpoints under `/api/admin/reportes/`. |
| `backend/config/api_serializers.py` | Modify | Add `ReportClientSerializer`, `ReportProspectSerializer`, `ReportIncomeSerializer`. |
| `frontend/aesthetic-clinic/tests/e2e/admin_reports.spec.ts` | New | E2E covering navigation, branch isolation, XLSX download trigger, and empty/error states. |

## Interfaces / Contracts

```ts
export type ReportClient = {
  firstName: string
  lastName: string
  ci: string
  status: string
  lastAppointmentDate: string | null
}

export type ReportProspect = {
  firstName: string
  lastName: string
  phone: string
  ci: string | null
  interest: string
  state: string
  createdAt: string
  registeredBy: string
}

export type ReportIncomeItem = {
  paymentId: number
  date: string
  time: string
  amount: string
  clientName: string
  serviceName: string
  status: string
  invoiceUrl: string | null
  invoiceName: string | null
}
```

Backend endpoints:

| Method | Path | Query |
|---|---|---|
| GET | `/api/admin/reportes/clientes/` | none (active branch) |
| GET | `/api/admin/reportes/prospectos/` | none (active branch) |
| GET | `/api/admin/reportes/ingresos/` | `month`, `year` (required) |

Response shape:

```json
{
  "branch": { "id": 1, "name": "Sucursal Principal" },
  "month": 8,
  "year": 2026,
  "rows": [ /* ReportClient[] | ReportProspect[] | ReportIncomeItem[] */ ]
}
```

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | `ReportLayout` period/loading/empty reducers, name splitter | vitest if available; otherwise manual smoke |
| Integration | `getAdminReport*` serializers branch-scope, query filter, pagination cap | Django `TestCase` against `/api/admin/reportes/*` |
| E2E | Nav, table render, XLSX download, branch isolation, empty state | Playwright `admin_reports.spec.ts` |

## Migration / Rollout

No data migration. New endpoints run side-by-side with existing ones. Reports are gated behind the existing admin role check. To roll back, remove the routes and the new files; no existing functional path is affected.

## Open Questions

- Should the prospect report include the optional `ci` column or omit it when null? Default: always render, leave a dash when null.
- For the income report, do we want a monthly summary card (total approved vs total recorded) or just the table? Default: table only for now; add summary in a follow-up if requested.
- Branch scope: main admin has access to all branches; non-main admin only sees their active branch. Confirm whether main admin should keep the active-branch selector or get a global view. **Default**: keep the selector; main admin already uses it.
