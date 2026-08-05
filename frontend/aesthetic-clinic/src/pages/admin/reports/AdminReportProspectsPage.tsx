import { useCallback, useState } from 'react'

import { useBranchContext } from '../../../providers/BranchProvider'
import { getAdminReportProspects } from '../../../services/api/admin'
import type { ReportProspect, ReportResponse } from '../../../types/admin'
import { branchNameToSlug, dateTimeCell } from './reportUtils'
import { ReportLayout } from './ReportLayout'
import { ReportSearch } from './ReportSearch'
import { matchesReportSearch } from './reportSearchFilter'
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
  { key: 'lastAppointmentDate', label: 'Última cita', render: dateTimeCell('lastAppointmentDate') },
  { key: 'nextAppointmentDate', label: 'Próxima cita', render: dateTimeCell('nextAppointmentDate') },
]

/**
 * Keys used for the client-side search filter on the prospects report. CI
 * may be a dash placeholder when missing, but it still matches the search
 * input as a string when populated.
 */
const SEARCH_KEYS = [
  'firstName',
  'lastName',
  'phone',
  'ci',
  'interest',
  'state',
  'registeredBy',
] as const

/**
 * Branch-scoped prospects report.
 *
 * Reuses the new `/api/admin/reportes/prospectos/` endpoint (added in Phase 1)
 * via `getAdminReportProspects`. Column layout matches the prospect row shape
 * documented in `design.md` (`firstName`, `lastName`, `phone`, `ci`,
 * `interest`, `state`, `createdAt`, `registeredBy`, plus the two appointment
 * date columns added in the follow-up).
 *
 * Filtering: a client-side text filter narrows the dataset on the columns
 * that uniquely identify a prospect — name, phone, CI, interest, state, or
 * registrar — so admins can locate a specific row without re-hitting the
 * API. Export remains unfiltered so the workbook matches the page header.
 *
 * Read-only by design: no edit/delete actions.
 */
export function AdminReportProspectsPage() {
  const { activeBranch } = useBranchContext()
  const [searchTerm, setSearchTerm] = useState('')

  const loader = useCallback(() => getAdminReportProspects(), [])
  const rowsSelector = useCallback(
    (data: ReportResponse<ReportProspect>) => data.rows ?? [],
    [],
  )

  const branchSuffix = activeBranch ? ` de ${activeBranch.nombre}` : ''
  const filename = `prospectos_${branchNameToSlug(activeBranch?.nombre)}.xlsx`

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
      {({ rows }) => {
        const filteredRows = hasActiveFilter ? filterRows(rows) : rows
        const tableRows = (filteredRows as ReportProspect[] as unknown as Record<string, unknown>[])
        return (
          <>
            <ReportSearch
              value={searchTerm}
              onChange={setSearchTerm}
              placeholder="Nombre, CI, teléfono o estado"
              label="Buscar prospecto"
            />
            <ReportTable columns={COLUMNS} rows={tableRows} />
          </>
        )
      }}
    </ReportLayout>
  )
}