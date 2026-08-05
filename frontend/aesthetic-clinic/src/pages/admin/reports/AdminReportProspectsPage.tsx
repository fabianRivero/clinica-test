import { useCallback } from 'react'

import { useBranchContext } from '../../../providers/BranchProvider'
import { getAdminReportProspects } from '../../../services/api/admin'
import type { ReportProspect, ReportResponse } from '../../../types/admin'
import { branchNameToSlug } from './reportUtils'
import { ReportLayout } from './ReportLayout'
import { ReportTable, type ReportTableColumn } from './ReportTable'
import { buildReportExcelExport } from './useReportExcelExport'

const COLUMNS: ReportTableColumn[] = [
  { key: 'firstName', label: 'Nombre' },
  { key: 'lastName', label: 'Apellido' },
  { key: 'phone', label: 'Teléfono' },
  { key: 'ci', label: 'CI' },
  { key: 'interest', label: 'Interés' },
  { key: 'state', label: 'Estado' },
  { key: 'createdAt', label: 'Fecha de registro' },
  { key: 'registeredBy', label: 'Registrado por' },
]

/**
 * Branch-scoped prospects report.
 *
 * Reuses the new `/api/admin/reportes/prospectos/` endpoint (added in Phase 1)
 * via `getAdminReportProspects`. Column layout matches the prospect row shape
 * documented in `design.md` (`firstName`, `lastName`, `phone`, `ci`,
 * `interest`, `state`, `createdAt`, `registeredBy`).
 *
 * Read-only by design: no edit/delete actions.
 */
export function AdminReportProspectsPage() {
  const { activeBranch } = useBranchContext()

  const loader = useCallback(() => getAdminReportProspects(), [])
  const rowsSelector = useCallback(
    (data: ReportResponse<ReportProspect>) => data.rows ?? [],
    [],
  )

  const branchSuffix = activeBranch ? ` de ${activeBranch.nombre}` : ''
  const filename = `prospectos_${branchNameToSlug(activeBranch?.nombre)}.xlsx`

  return (
    <ReportLayout<ReportResponse<ReportProspect>>
      title="Reporte de prospectos"
      description={`Listado completo de prospectos registrados${branchSuffix}, listo para exportar a Excel.`}
      loader={loader}
      rowsSelector={rowsSelector}
      emptyTitle="Sin prospectos para mostrar"
      emptyMessage="No hay prospectos registrados en la sucursal activa."
      buildExport={(rows) =>
        buildReportExcelExport({
          columns: COLUMNS,
          rows: rows as Record<string, unknown>[],
          filename,
          sheetName: 'Prospectos',
          withHyperlinks: false,
        })
      }
    >
      {({ rows }) => (
        <ReportTable
          columns={COLUMNS}
          rows={rows as ReportProspect[] as unknown as Record<string, unknown>[]}
        />
      )}
    </ReportLayout>
  )
}