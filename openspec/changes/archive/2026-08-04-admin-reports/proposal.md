# Proposal: Admin Reports

## Intent

Give administrators a branch-scoped reporting area where they can review and export client, prospect, monthly income, and monthly expense data without reconstructing reports from operational screens.

## Scope

### In Scope
- Add a Reports navigation group with client, prospect, income, and expense report routes.
- Provide read-only tables with search/filter states and XLSX export.
- Provide month/year controls for income and expenses, matching the current expense-list interaction.
- Enforce active-branch scope server-side and expose dedicated report data where existing endpoints lack required fields.

### Out of Scope
- Editing clients, prospects, payments, or expenses from reports.
- Cross-branch consolidated reporting, charts, scheduled delivery, or embedded invoice PDFs in workbooks.
- Replacing existing operational pages.

## Capabilities

### New Capabilities
- `admin-reports`: Branch-scoped admin report navigation, datasets, period controls, read-only tables, and XLSX exports.

### Modified Capabilities
- None.

## Approach

Create dedicated report pages and shared frontend primitives for period selection, table states, and XLSX export. Reuse existing APIs only when they satisfy report columns and branch isolation; otherwise add narrowly scoped admin report endpoints/serializers. Treat approved payments as income and export invoice URLs as spreadsheet values. Client and prospect reports use the fields already available in their admin list contracts unless later specs explicitly require additions.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `frontend/aesthetic-clinic/src/layouts/AdminLayout.tsx` | Modified | Add Reports navigation. |
| `frontend/aesthetic-clinic/src/App.tsx` | Modified | Register report routes. |
| `frontend/aesthetic-clinic/src/pages/admin/reports/` | New | Add report pages and shared controls. |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Modified | Add report loaders. |
| `frontend/aesthetic-clinic/src/types/admin.ts` | Modified | Define report contracts. |
| `backend/config/` and related domain modules | Modified | Add or adapt branch-safe report APIs. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Cross-branch data leakage | High | Enforce branch scope in backend queries and authorization tests. |
| Large browser exports | Medium | Define pagination/export limits and prefer server filtering where needed. |
| Ambiguous report fields | Medium | Lock columns and status rules in specs before design. |

## Rollback Plan

Remove report routes/navigation/pages and dedicated endpoints; existing operational pages and data remain unchanged.

## Dependencies

- Existing admin authentication, active branch context, payment/expense data, and `xlsx` package.

## Success Criteria

- [ ] Administrators can open all four reports for the active branch.
- [ ] Income includes all recorded payments for the selected month/year.
- [ ] Every report handles loading, error, empty, filtering, and XLSX export states.
- [ ] Invoice exports contain usable URLs rather than embedded PDF files.
- [ ] Existing admin workflows remain unchanged.
