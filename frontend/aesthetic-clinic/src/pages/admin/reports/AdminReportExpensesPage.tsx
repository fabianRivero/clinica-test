import { useCallback, useMemo, useState } from 'react'

import { DataState } from '../../../components/admin/DataState'
import { PageHeader } from '../../../components/admin/PageHeader'
import { SectionCard } from '../../../components/admin/SectionCard'
import { useApiResource } from '../../../hooks/useApiResource'
import { useBranchContext } from '../../../providers/BranchProvider'
import { useNotifications } from '../../../providers/NotificationProvider'
import { getAdminExpenses } from '../../../services/api/admin'
import type { ExpenseItem, ExpensesResponse } from '../../../types/admin'
import { monthNames } from '../expenses/expenseUtils'
import { ReportTable, type ReportTableColumn } from './ReportTable'
import { buildReportExcelExport } from './useReportExcelExport'

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
]

/**
 * Branch-scoped expenses report.
 *
 * Reuses `/api/admin/gastos/` via `getAdminExpenses(month, year)`. Renders
 * the same columns the existing `AdminExpenseListPage` exposes so the
 * report reads as a snapshot of that list.
 *
 * Self-contained: owns its own month/year state. The loader is keyed on
 * `[month, year]` through `useCallback`, which means `useApiResource`
 * refetches automatically whenever the period changes. This pattern
 * removes the children-render-prop bug that left the page stuck on the
 * last period whenever the previous fetch returned no rows.
 *
 * Read-only by design: no edit/delete actions, no category-summary card —
 * the goal is a printable/exportable mirror, not a duplicate management UI.
 */
export function AdminReportExpensesPage() {
  const { activeBranch } = useBranchContext()
  const { showNotification } = useNotifications()
  const now = new Date()
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [year, setYear] = useState(now.getFullYear())

  const loader = useCallback(
    () => getAdminExpenses(month, year),
    [month, year],
  )
  const { data, isLoading, error } = useApiResource<ExpensesResponse>(loader)

  const rows = useMemo<ExpenseItem[]>(() => {
    if (!data) return []
    return Array.isArray(data.expenses) ? data.expenses : []
  }, [data])

  const branchSuffix = activeBranch ? ` de ${activeBranch.nombre}` : ''
  const title = 'Reporte de gastos'
  const description =
    'Gastos del mes seleccionado, con vinculo directo a la factura cuando esta disponible.'
  const viewedMonthLabel = `${monthNames[month - 1]} ${year}`

  const changeMonth = (direction: -1 | 1) => {
    let nextMonth = month + direction
    let nextYear = year
    if (nextMonth < 1) {
      nextMonth = 12
      nextYear -= 1
    } else if (nextMonth > 12) {
      nextMonth = 1
      nextYear += 1
    }
    setMonth(nextMonth)
    setYear(nextYear)
  }

  const handleExport = () => {
    if (rows.length === 0) {
      showNotification({
        title: 'Sin datos',
        message: 'No hay gastos para exportar en el periodo seleccionado.',
        tone: 'info',
      })
      return
    }
    buildReportExcelExport({
      columns: COLUMNS,
      rows: rows as unknown as Record<string, unknown>[],
      filename: `gastos_${month}_${year}.xlsx`,
      sheetName: 'Gastos',
      withHyperlinks: true,
    })()
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Reportes"
        title={`${title}${branchSuffix}`}
        description={description}
      />

      {isLoading && !data ? (
        <SectionCard title="Sincronizando datos">
          <DataState title="Sincronizando datos" message="Cargando la informacion del reporte seleccionado." />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar el reporte">
          <DataState title="No pudimos cargar el reporte" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <SectionCard
          title={`${title} - ${viewedMonthLabel}`}
          description={description}
          action={
            <div className="expense-period-controls">
              <button
                className="button button--ghost"
                type="button"
                onClick={() => changeMonth(-1)}
                aria-label="Mes anterior"
              >
                ←
              </button>
              <div>
                <span className="eyebrow">Periodo de gastos</span>
                <h3>{viewedMonthLabel}</h3>
              </div>
              <button
                className="button button--ghost"
                type="button"
                onClick={() => changeMonth(1)}
                aria-label="Mes siguiente"
              >
                →
              </button>
              {rows.length > 0 ? (
                <button
                  className="button button--ghost"
                  style={{ minWidth: '4.5rem', minHeight: '2.6rem', padding: '0 0.75rem' }}
                  type="button"
                  onClick={handleExport}
                  title="Descargar Excel"
                >
                  ↓ Excel
                </button>
              ) : null}
            </div>
          }
        >
          {rows.length ? (
            <ReportTable
              columns={COLUMNS}
              rows={rows as unknown as Record<string, unknown>[]}
            />
          ) : (
            <DataState
              title="Sin gastos en el mes seleccionado"
              message="No se registran gastos para el periodo que estas consultando."
            />
          )}
        </SectionCard>
      ) : null}
    </div>
  )
}