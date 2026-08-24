import { useCallback, useState } from 'react'

import {
  MultiFieldSearch,
  type MultiFieldSearchField,
} from '../../../components/admin/MultiFieldSearch'
import { useBranchContext } from '../../../providers/BranchProvider'
import { getAdminReportProspects } from '../../../services/api/admin'
import type { ReportProspect, ReportResponse } from '../../../types/admin'
import {
  matchesFieldFilters,
  type FieldDef,
  type FieldFilters,
} from '../../../utils/matchesFieldFilters'
import { branchNameToSlug, dateTimeCell } from './reportUtils'
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
  { key: 'lastAppointmentDate', label: 'Última cita', render: dateTimeCell('lastAppointmentDate') },
  { key: 'nextAppointmentDate', label: 'Próxima cita', render: dateTimeCell('nextAppointmentDate') },
]

/**
 * Branch-scoped prospects report.
 *
 * Reuses the `/api/admin/reportes/prospectos/` endpoint via
 * `getAdminReportProspects`. Column layout matches the prospect row shape
 * (`firstName`, `lastName`, `phone`, `ci`, `interest`, `state`, `createdAt`,
 * `registeredBy`, plus the two appointment date columns).
 *
 * Filtering: a client-side multi-input search grid narrows the dataset on
 * Nombre (tokenized across `firstName + " " + lastName`), CI, Teléfono, and
 * Interés so admins can locate a specific row without re-hitting the API.
 *
 * Note: prospectos no son clientes aún, so this grid intentionally does NOT
 * expose a `Código` field — `ReportProspect` has no `clienteCodigo` and the
 * backend `_report_prospect_row()` does not surface it. `state` filtering
 * remains available via the page header dropdown; `registeredBy` was
 * dropped from the search grid because it is rarely the target of a search.
 *
 * Export remains unfiltered so the workbook matches the page header.
 *
 * Read-only by design: no edit/delete actions.
 */
export function AdminReportProspectsPage() {
  const { activeBranch } = useBranchContext()
  const [searchName, setSearchName] = useState('')
  const [searchCi, setSearchCi] = useState('')
  const [searchPhone, setSearchPhone] = useState('')
  const [searchInterest, setSearchInterest] = useState('')

  const loader = useCallback(() => getAdminReportProspects(), [])
  const rowsSelector = useCallback(
    (data: ReportResponse<ReportProspect>) => data.rows ?? [],
    [],
  )

  const branchSuffix = activeBranch ? ` de ${activeBranch.nombre}` : ''
  const filename = `prospectos_${branchNameToSlug(activeBranch?.nombre)}.xlsx`

  const searchFields: ReadonlyArray<MultiFieldSearchField> = [
    { key: 'name', label: 'Nombre', placeholder: 'María López' },
    { key: 'ci', label: 'CI', placeholder: '1234567' },
    { key: 'phone', label: 'Teléfono', placeholder: '70012345' },
    { key: 'interest', label: 'Interés', placeholder: 'Procedimiento' },
  ]

  const searchValues: FieldFilters = {
    name: searchName,
    ci: searchCi,
    phone: searchPhone,
    interest: searchInterest,
  }

  const searchFieldsByKey: Record<string, FieldDef> = {
    name: { key: 'fullName', type: 'tokenized' },
    ci: { key: 'ci', type: 'includes' },
    phone: { key: 'phone', type: 'includes' },
    interest: { key: 'interest', type: 'tokenized' },
  }

  function handleSearchChange(key: string, value: string) {
    if (key === 'name') setSearchName(value)
    else if (key === 'ci') setSearchCi(value)
    else if (key === 'phone') setSearchPhone(value)
    else if (key === 'interest') setSearchInterest(value)
  }

  /**
   * Filter callback exposed via the render prop so `ReportLayout`'s shell
   * can render both the unfiltered dataset (export) and the filtered one
   * (table). The callback closes over the four search inputs so the filter
   * recomputes on every keystroke without forcing the layout to re-render.
   *
   * The `fullName` synthesis lets `matchesFieldFilters` tokenize across
   * `firstName + " " + lastName` without teaching the helper about composed
   * keys.
   */
  const filterRows = useCallback(
    (rows: unknown[]) => {
      if (!searchName && !searchCi && !searchPhone && !searchInterest) return rows
      const enriched = rows.map((r) => {
        const row = r as Record<string, unknown>
        const firstName = String(row.firstName ?? '')
        const lastName = String(row.lastName ?? '')
        return { ...row, fullName: `${firstName} ${lastName}`.trim() }
      })
      return enriched.filter((r) => matchesFieldFilters(r, searchValues, searchFieldsByKey))
    },
    [searchName, searchCi, searchPhone, searchInterest, searchValues],
  )

  const hasActiveFilter =
    searchName.length > 0 || searchCi.length > 0 || searchPhone.length > 0 || searchInterest.length > 0

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
            <div className="_mb-md">
              <MultiFieldSearch
                fields={searchFields}
                values={searchValues}
                onChange={handleSearchChange}
                gridClassName="form-grid--four"
              />
            </div>
            <ReportTable columns={COLUMNS} rows={tableRows} />
          </>
        )
      }}
    </ReportLayout>
  )
}