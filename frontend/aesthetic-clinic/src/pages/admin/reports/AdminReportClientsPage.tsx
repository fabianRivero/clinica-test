import { useCallback } from 'react'

import { useBranchContext } from '../../../providers/BranchProvider'
import { getAdminReportClients } from '../../../services/api/admin'
import type { ReportClient, ReportResponse } from '../../../types/admin'
import { branchNameToSlug } from './reportUtils'
import { ReportLayout } from './ReportLayout'
import { ReportTable, type ReportTableColumn } from './ReportTable'
import { buildReportExcelExport } from './useReportExcelExport'

const COLUMNS: ReportTableColumn[] = [
  { key: 'firstName', label: 'Nombre' },
  { key: 'lastName', label: 'Apellido' },
  { key: 'ci', label: 'CI' },
  { key: 'status', label: 'Estado' },
  { key: 'lastAppointmentDate', label: 'Última cita' },
]

/**
 * Branch-scoped clients report.
 *
 * Reuses the new `/api/admin/reportes/clientes/` endpoint (added in Phase 1)
 * via `getAdminReportClients`. The endpoint returns a `ReportResponse<ReportClient>`
 * envelope so the page only needs to plug a `rowsSelector` and column list into
 * the shared `ReportLayout` shell.
 *
 * Read-only by design: no edit/delete actions, mirroring the rest of the
 * `/cms/reportes/*` family.
 */
export function AdminReportClientsPage() {
  const { activeBranch } = useBranchContext()

  const loader = useCallback(() => getAdminReportClients(), [])
  const rowsSelector = useCallback(
    (data: ReportResponse<ReportClient>) => data.rows ?? [],
    [],
  )

  const branchSuffix = activeBranch ? ` de ${activeBranch.nombre}` : ''
  const filename = `clientes_${branchNameToSlug(activeBranch?.nombre)}.xlsx`

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
      {({ rows }) => (
        <ReportTable
          columns={COLUMNS}
          rows={rows as ReportClient[] as unknown as Record<string, unknown>[]}
        />
      )}
    </ReportLayout>
  )
}