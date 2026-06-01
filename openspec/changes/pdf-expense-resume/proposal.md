# Proposal: PDF Expense Resume — pdf-expense-resume

## Executive Summary

Add a "Descargar PDF" button in the "Lista de gastos" subtab that generates and downloads a monthly expense summary in PDF format. The PDF will show the expense list for the currently selected month, with totals per category and overall total.

**Scope**: Button in AdminExpenseListPage, backend PDF generation endpoint (Django + reportlab), frontend download trigger.

---

## Motivation

The expense list shows monthly data but has no export capability. Users need to share or archive monthly summaries for accounting purposes. A PDF provides a clean, printable format.

---

## Scope

### In
- PDF download button in `AdminExpenseListPage.tsx` (near month navigation)
- Backend endpoint: `GET /api/admin/gastos/resumen-mensual/?month=X&year=Y`
- PDF generation using **reportlab** (backend, Django)
- PDF includes: month/year header, branch name, expense table (date, category, concept, units, unit cost, total, provider), totals per category, grand total
- Frontend: fetch PDF as blob, trigger browser download

### Out
- PDF for other reports
- Email distribution
- Batch export for multiple months
- Customizable templates

---

## Approach

**Backend**: Add `reportlab` dependency, create Django endpoint that queries `GastoSucursal` filtered by month/year/branch, generate PDF using Platypus (reportlab's page layout library).

**Frontend**: Add download button, call endpoint with current month/year, receive PDF blob, create object URL and trigger download via `<a download>`.

### Why backend generation?
- Consistent styling controlled by backend
- No client-side dependency for PDF layout
- Easier to future-proof for email/attached reports

---

## Risks

- `reportlab` adds a Python dependency
- Large expense lists may need pagination
- Date formatting should match existing locale conventions

---

## Next Recommended Phase

**sdd-spec** — Write detailed specification including PDF layout, API contract, and acceptance criteria.
