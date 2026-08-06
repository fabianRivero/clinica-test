import { useCallback, useRef } from 'react'

import { getAdminReportIncome } from '../../../services/api/admin'
import type { ReportIncomeItem, ReportResponse } from '../../../types/admin'
import { ReportLayout } from './ReportLayout'
import { ReportTable, type ReportTableColumn } from './ReportTable'
import { buildReportExcelExport } from './useReportExcelExport'

const COLUMNS: ReportTableColumn[] = [
  { key: 'date', label: 'Fecha' },
  { key: 'time', label: 'Hora' },
  { key: 'amount', label: 'Monto' },
  { key: 'clientName', label: 'Cliente' },
  { key: 'serviceName', label: 'Servicio' },
  { key: 'status', label: 'Estado' },
]

/**
 * Branch-scoped income report.
 *
 * Pulls `ReportIncomeItem[]` from the new `/api/admin/reportes/ingresos/`
 * endpoint via `getAdminReportIncome(month, year)`. The page enables the
 * month/year picker inside `ReportLayout` (`withPeriod`) so users can
 * navigate across periods without leaving the page.
 *
 * The loader closure captures the period via refs that are kept in sync with
 * `ReportLayout`'s internal month/year state through the `children` render
 * prop. This is the only way to feed a parameterized loader into the shared
 * shell without rewriting `ReportLayout`.
 *
 * Read-only: row-level invoice URL is rendered as a clickable `<a>` in the
 * table AND exported as a `HYPERLINK` formula by `ReportTable`.
 */
export function AdminReportIncomePage() {
  const now = new Date()
  const monthRef = useRef(now.getMonth() + 1)
  const yearRef = useRef(now.getFullYear())

  const loader = useCallback(
    () => getAdminReportIncome(monthRef.current, yearRef.current),
    [],
  )
  const rowsSelector = useCallback(
    (data: ReportResponse<ReportIncomeItem>) => data.rows ?? [],
    [],
  )

  return (
    <ReportLayout<ReportResponse<ReportIncomeItem>>
      title="Reporte de ingresos"
      description="Pagos registrados en el mes seleccionado, con vinculo directo a la factura cuando esta disponible."
      loader={loader}
      rowsSelector={rowsSelector}
      withPeriod
      emptyTitle="Sin ingresos en el mes seleccionado"
      emptyMessage="No se registran pagos para el periodo que estas consultando."
      periodLabel="Periodo de ingresos"
      buildExport={(rows) =>
        // Filename depends on the current period; resolved at click-time
        // through a closure that reads the latest month/year from refs that
        // are kept in sync inside the children render prop.
        buildReportExcelExport({
          columns: COLUMNS,
          rows: rows as Record<string, unknown>[],
          filename: `ingresos_${monthRef.current}_${yearRef.current}.xlsx`,
          sheetName: 'Ingresos',
          withHyperlinks: true,
        })
      }
    >
      {({ rows, period }) => {
        // Sync refs with the period owned by `ReportLayout`. Updated during
        // render so the subsequent `useApiResource` effect (which re-runs
        // whenever the layout recreates its internal loader) reads the
        // latest month/year when it invokes our loader.
        monthRef.current = period.month
        yearRef.current = period.year

        return (
          <ReportTable
            columns={COLUMNS}
            rows={rows as ReportIncomeItem[] as unknown as Record<string, unknown>[]}
          />
        )
      }}
    </ReportLayout>
  )
}