import { useCallback, useState } from 'react'

import { useBranchContext } from '../../../providers/BranchProvider'
import { getAdminReportClients } from '../../../services/api/admin'
import type { ReportClient, ReportResponse } from '../../../types/admin'
import { branchNameToSlug, dateTimeCell } from './reportUtils'
import { ReportLayout } from './ReportLayout'
import { ReportSearch } from './ReportSearch'
import { matchesReportSearch } from './reportSearchFilter'
import { ReportTable, type ReportTableColumn } from './ReportTable'
import { buildReportExcelExport } from './useReportExcelExport'

const COLUMNS: ReportTableColumn[] = [
  { key: 'firstName', label: 'Nombre' },
  { key: 'lastName', label: 'Apellido' },
  { key: 'ci', label: 'CI' },
  { key: 'status', label: 'Estado' },
  { key: 'lastAppointmentDate', label: 'Última cita', render: dateTimeCell('lastAppointmentDate') },
  { key: 'nextAppointmentDate', label: 'Próxima cita', render: dateTimeCell('nextAppointmentDate') },
  { key: 'lastPaymentDate', label: 'Último pago', render: dateTimeCell('lastPaymentDate') },
  { key: 'nextPaymentDate', label: 'Próximo pago', render: dateTimeCell('nextPaymentDate') },
]

/**
 * Keys used for the client-side search filter. CI, first/last name, and
 * status cover the most common lookups for an admin triaging the list.
 */
const SEARCH_KEYS = ['firstName', 'lastName', 'ci', 'status'] as const

/**
 * Branch-scoped clients report.
 *
 * Reuses the new `/api/admin/reportes/clientes/` endpoint (added in Phase 1)
 * via `getAdminReportClients`. The endpoint returns a `ReportResponse<ReportClient>`
 * envelope so the page only needs to plug a `rowsSelector` and column list into
 * the shared `ReportLayout` shell.
 *
 * Filtering: a client-side text filter narrows the dataset on `firstName`,
 * `lastName`, `ci`, and `status` so admins can locate a specific client
 * without re-hitting the API. The filter is purely visual — the export still
 * reflects the entire dataset so the workbook stays consistent with the
 * page header. To export the filtered subset only, extend `buildExport` to
 * use the same predicate.
 *
 * Read-only by design: no edit/delete actions.
 */
export function AdminReportClientsPage() {
  const { activeBranch } = useBranchContext()
  const [searchTerm, setSearchTerm] = useState('')

  const loader = useCallback(() => getAdminReportClients(), [])
  const rowsSelector = useCallback(
    (data: ReportResponse<ReportClient>) => data.rows ?? [],
    [],
  )

  const branchSuffix = activeBranch ? ` de ${activeBranch.nombre}` : ''
  const filename = `clientes_${branchNameToSlug(activeBranch?.nombre)}.xlsx`

  /**
   * Filter callback exposed via the render prop so `ReportLayout`'s shell
   * can render both the unfiltered dataset (export) and the filtered one
   * (table). The callback closes over `searchTerm` so the filter recomputes
   * on every keystroke without forcing the layout to re-render.
   */
  const filterRows = useCallback(
    (rows: unknown[]) => {
      if (!searchTerm.trim()) return rows
      return rows.filter((row) =>
        matchesReportSearch(searchTerm, row as Record<string, unknown>, SEARCH_KEYS),
      )
    },
    [searchTerm],
  )

  const hasActiveFilter = searchTerm.trim().length > 0

  return (
    <ReportLayout<ReportResponse<ReportClient>>
      title="Reporte de clientes"
      description={`Listado completo de clientes con cuenta${branchSuffix}, listo para exportar a Excel.`}
      loader={loader}
      rowsSelector={rowsSelector}
      emptyTitle="Sin clientes para mostrar"
      emptyMessage="No hay clientes registrados en la sucursal activa."
      buildExport={(rows) =>
        buildReportExcelExport({
          columns: COLUMNS,
          rows: rows as Record<string, unknown>[],
          filename,
          sheetName: 'Clientes',
          withHyperlinks: false,
        })
      }
    >
      {({ rows }) => {
        const filteredRows = hasActiveFilter ? filterRows(rows) : rows
        const tableRows = (filteredRows as ReportClient[] as unknown as Record<string, unknown>[])
        return (
          <>
            <ReportSearch
              value={searchTerm}
              onChange={setSearchTerm}
              placeholder="Nombre, apellido, CI o estado"
              label="Buscar cliente"
            />
            <ReportTable columns={COLUMNS} rows={tableRows} />
          </>
        )
      }}
    </ReportLayout>
  )
}