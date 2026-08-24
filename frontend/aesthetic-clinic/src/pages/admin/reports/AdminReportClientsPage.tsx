import { useCallback, useState } from 'react'

import {
  MultiFieldSearch,
  type MultiFieldSearchField,
} from '../../../components/admin/MultiFieldSearch'
import { useBranchContext } from '../../../providers/BranchProvider'
import { getAdminReportClients } from '../../../services/api/admin'
import type { ReportClient, ReportResponse } from '../../../types/admin'
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
  { key: 'ci', label: 'CI' },
  { key: 'status', label: 'Estado' },
  { key: 'lastAppointmentDate', label: 'Última cita', render: dateTimeCell('lastAppointmentDate') },
  { key: 'nextAppointmentDate', label: 'Próxima cita', render: dateTimeCell('nextAppointmentDate') },
  { key: 'lastPaymentDate', label: 'Último pago', render: dateTimeCell('lastPaymentDate') },
  { key: 'nextPaymentDate', label: 'Próximo pago', render: dateTimeCell('nextPaymentDate') },
]

/**
 * Branch-scoped clients report.
 *
 * Reuses the `/api/admin/reportes/clientes/` endpoint via `getAdminReportClients`.
 * The endpoint returns a `ReportResponse<ReportClient>` envelope so the page
 * only needs to plug a `rowsSelector` and column list into the shared
 * `ReportLayout` shell.
 *
 * Filtering: a client-side multi-input search grid narrows the dataset on
 * Nombre (tokenized across `firstName + " " + lastName`), CI, Estado, and
 * Código cliente so admins can locate a specific client without re-hitting
 * the API. The filter is purely visual — the export still reflects the
 * entire dataset so the workbook stays consistent with the page header.
 * To export the filtered subset only, extend `buildExport` to use the
 * same predicate.
 *
 * Read-only by design: no edit/delete actions.
 */
export function AdminReportClientsPage() {
  const { activeBranch } = useBranchContext()
  const [searchName, setSearchName] = useState('')
  const [searchCi, setSearchCi] = useState('')
  const [searchStatus, setSearchStatus] = useState('')
  const [searchCodigo, setSearchCodigo] = useState('')

  const loader = useCallback(() => getAdminReportClients(), [])
  const rowsSelector = useCallback(
    (data: ReportResponse<ReportClient>) => data.rows ?? [],
    [],
  )

  const branchSuffix = activeBranch ? ` de ${activeBranch.nombre}` : ''
  const filename = `clientes_${branchNameToSlug(activeBranch?.nombre)}.xlsx`

  const searchFields: ReadonlyArray<MultiFieldSearchField> = [
    { key: 'name', label: 'Nombre', placeholder: 'María López' },
    { key: 'ci', label: 'CI', placeholder: '1234567' },
    { key: 'status', label: 'Estado', placeholder: 'Activo / Inactivo' },
    { key: 'codigo', label: 'Código', placeholder: 'CLI-XXXXXX' },
  ]

  const searchValues: FieldFilters = {
    name: searchName,
    ci: searchCi,
    status: searchStatus,
    codigo: searchCodigo,
  }

  const searchFieldsByKey: Record<string, FieldDef> = {
    name: { key: 'fullName', type: 'tokenized' },
    ci: { key: 'ci', type: 'includes' },
    status: { key: 'status', type: 'includes' },
    codigo: { key: 'clienteCodigo', type: 'includes' },
  }

  function handleSearchChange(key: string, value: string) {
    if (key === 'name') setSearchName(value)
    else if (key === 'ci') setSearchCi(value)
    else if (key === 'status') setSearchStatus(value)
    else if (key === 'codigo') setSearchCodigo(value)
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
      if (!searchName && !searchCi && !searchStatus && !searchCodigo) return rows
      const enriched = rows.map((r) => {
        const row = r as Record<string, unknown>
        const firstName = String(row.firstName ?? '')
        const lastName = String(row.lastName ?? '')
        return { ...row, fullName: `${firstName} ${lastName}`.trim() }
      })
      return enriched.filter((r) => matchesFieldFilters(r, searchValues, searchFieldsByKey))
    },
    [searchName, searchCi, searchStatus, searchCodigo, searchValues],
  )

  const hasActiveFilter =
    searchName.length > 0 || searchCi.length > 0 || searchStatus.length > 0 || searchCodigo.length > 0

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