import { useCallback, useRef } from 'react'

import { getAdminExpenses } from '../../../services/api/admin'
import type { ExpenseItem, ExpensesResponse } from '../../../types/admin'
import { ReportLayout } from './ReportLayout'
import { ReportTable, type ReportTableColumn } from './ReportTable'

const COLUMNS: ReportTableColumn[] = [
  { key: 'dateLabel', label: 'Fecha' },
  { key: 'category', label: 'Categoria' },
  { key: 'concept', label: 'Concepto' },
  {
    key: 'units',
    label: 'Unidades x Unitario',
    render: (row) => {
      const units = typeof row.units === 'string' ? row.units : String(row.units ?? '')
      const unitCost = typeof row.unitCost === 'string' ? row.unitCost : String(row.unitCost ?? '')
      return `${units} x Bs ${unitCost}`
    },
  },
  { key: 'provider', label: 'Proveedor' },
  { key: 'totalLabel', label: 'Total' },
  {
    key: 'invoiceUrl',
    label: 'Factura',
    render: (row) => {
      const url = typeof row.invoiceUrl === 'string' ? row.invoiceUrl : ''
      if (!url) return 'Sin factura'
      return (
        <a href={url} rel="noreferrer" target="_blank">
          Ver factura
        </a>
      )
    },
  },
]

/**
 * Branch-scoped expenses report.
 *
 * Reuses the existing `/api/admin/gastos/` endpoint via `getAdminExpenses`
 * (already branch-scoped, month/year filtered, and returns `invoiceUrl`).
 * Renders the same columns the existing `AdminExpenseListPage` exposes so
 * the report reads as a snapshot of that list.
 *
 * Read-only by design: no edit/delete actions, no category-summary card —
 * the goal is a printable/exportable mirror, not a duplicate management UI.
 */
export function AdminReportExpensesPage() {
  const now = new Date()
  const monthRef = useRef(now.getMonth() + 1)
  const yearRef = useRef(now.getFullYear())

  const loader = useCallback(
    () => getAdminExpenses(monthRef.current, yearRef.current),
    [],
  )
  const rowsSelector = useCallback(
    (data: ExpensesResponse) => data.expenses ?? [],
    [],
  )

  return (
    <ReportLayout<ExpensesResponse>
      title="Reporte de gastos"
      description="Gastos del mes seleccionado, con vinculo directo a la factura cuando esta disponible."
      loader={loader}
      rowsSelector={rowsSelector}
      withPeriod
      emptyTitle="Sin gastos en el mes seleccionado"
      emptyMessage="No se registran gastos para el periodo que estas consultando."
      periodLabel="Periodo de gastos"
    >
      {({ rows, period }) => {
        // Sync refs with the period owned by `ReportLayout` so the loader
        // closure reads the current month/year when `useApiResource`
        // re-fetches.
        monthRef.current = period.month
        yearRef.current = period.year

        return (
          <ReportTable
            columns={COLUMNS}
            rows={rows as ExpenseItem[] as unknown as Record<string, unknown>[]}
            filename={`gastos_${period.month}_${period.year}.xlsx`}
            sheetName="Gastos"
            withHyperlinks
          />
        )
      }}
    </ReportLayout>
  )
}