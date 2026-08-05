# Admin Reports Exploration

## Exploration: Admin reports section

### Current State
The admin UI is a React 19 + Vite TypeScript application under `frontend/aesthetic-clinic`, with Django 5.2 + DRF backend services. The admin layout defines grouped sidebar navigation in `src/layouts/AdminLayout.tsx`; routes are nested under `/cms` in `src/App.tsx`. Existing client and prospect pages already load their respective datasets and render searchable/status-aware tables. Existing payments are exposed through `getAdminPayments(month, year, filters?)`, and expenses through `getAdminExpenses(month, year)`.

The expense list at `src/pages/admin/expenses/AdminExpenseListPage.tsx` is the closest reusable interaction pattern: branch-aware data loading, month/year navigation and picker, loading/error/empty states, table rendering, invoice links, and XLSX export using the `xlsx` package. The requested reports feature should reuse the same visual primitives and period controls rather than duplicate unrelated layout behavior.

The requested feature is not currently present: there is no Reports navigation group or `/cms/reportes` route. Client and prospect lists are currently separate pages, while the requested report section should provide report-oriented copies of those datasets plus monthly income and expenses.

### Affected Areas
- `frontend/aesthetic-clinic/src/layouts/AdminLayout.tsx` — add the Reports navigation group and report child routes.
- `frontend/aesthetic-clinic/src/App.tsx` — register the reports route and report subroutes/pages.
- `frontend/aesthetic-clinic/src/pages/admin/AdminClientsPage.tsx` — source of existing client fields, filters, and table behavior to adapt into a report view.
- `frontend/aesthetic-clinic/src/pages/admin/AdminProspectsPage.tsx` — source of existing prospect fields, filters, and table behavior to adapt into a report view.
- `frontend/aesthetic-clinic/src/pages/admin/AdminPaymentsPage.tsx` — source of monthly payment data, filters, invoice/document fields, and payment table behavior.
- `frontend/aesthetic-clinic/src/pages/admin/expenses/AdminExpenseListPage.tsx` — canonical monthly report/table/export pattern for expenses.
- `frontend/aesthetic-clinic/src/services/api/admin.ts` — existing admin client/prospect/payment/expense API functions; likely needs a dedicated client report endpoint or a normalized report loader depending on required branch scope.
- `frontend/aesthetic-clinic/src/types/admin.ts` — response types for report rows and any missing invoice/payment fields.
- Backend admin API modules under `backend/` — must be checked during design to confirm whether current list endpoints provide all requested fields and whether payment records are branch-scoped correctly.

### Approaches
1. **Dedicated reports pages backed by existing endpoints** — create a Reports shell with four child pages, calling existing clients/prospects/payments/expenses endpoints and adding report-specific XLSX exports.
   - Pros: aligns with current routing and page patterns; lower backend risk when existing endpoints expose required fields; each report remains independently maintainable.
   - Cons: may duplicate table/filter UI from existing client/prospect/payment pages; endpoint payloads may not contain every requested report field.
   - Effort: Medium

2. **Dedicated consolidated reports API and shared report components** — add report-specific backend endpoints/serializers, then build a shared report table/period-control/export component used by all four pages.
   - Pros: precise fields, explicit branch/month semantics, less frontend data-shaping ambiguity, better long-term reporting contract.
   - Cons: higher backend and verification effort; requires careful authorization and query-performance review; introduces new API surface.
   - Effort: High

### Recommendation
Use dedicated Reports pages with shared frontend report primitives, while reusing existing endpoints wherever their payloads satisfy the requested columns. Add dedicated backend report endpoints only for datasets or fields that are missing, especially monthly income rows with service, exact payment timestamp, branch scope, and invoice PDF URL. Keep expenses in the report section as a read-only reuse of the existing monthly expense behavior, including its existing Excel export. Every report must use the active branch context and provide loading, error, empty, filtering, period selection where applicable, and Excel download behavior consistent with the expense list.

### Risks
- Existing client/prospect endpoints may be global or branch-filtered differently; branch isolation must be verified server-side, not assumed from the frontend selector.
- Payment payloads may represent pending/approved/cancelled records differently; the income report needs an explicit inclusion rule, likely approved payments only, confirmed in the proposal/spec phase.
- Invoice PDFs cannot be embedded into `.xlsx` by simply exporting the URL; the spreadsheet should include a usable invoice URL or a clearly defined download/link column unless backend-generated workbook attachments are explicitly required.
- Large client/prospect/payment datasets may require pagination or server-side filtering to avoid slow screens and oversized browser exports.
- The requested “same way as gastos” can mean visual behavior, filters, period controls, permissions, or all of them; the proposal should define the shared contract explicitly.

### Ready for Proposal
Yes. Before proposal, confirm the business rule for which payments count as income (approved only versus every recorded payment), the exact columns expected for clients/prospects, and whether Excel should contain invoice URLs or actual embedded PDFs. Then proceed to `sdd-propose`.
