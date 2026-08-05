import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { DataState } from '../../../components/admin/DataState'
import { PageHeader } from '../../../components/admin/PageHeader'
import { SectionCard } from '../../../components/admin/SectionCard'
import { useApiResource } from '../../../hooks/useApiResource'
import { useBranchContext } from '../../../providers/BranchProvider'

const REPORT_MONTHS = [
  'Enero',
  'Febrero',
  'Marzo',
  'Abril',
  'Mayo',
  'Junio',
  'Julio',
  'Agosto',
  'Septiembre',
  'Octubre',
  'Noviembre',
  'Diciembre',
]

const REPORT_YEARS = (() => {
  const now = new Date().getFullYear()
  const years: number[] = []
  for (let y = now - 3; y <= now + 3; y += 1) {
    years.push(y)
  }
  return years
})()

type ReportLayoutProps<T> = {
  eyebrow?: string
  title: string
  description?: string
  loader: () => Promise<T>
  rowsSelector: (data: T) => unknown[]
  withPeriod?: boolean
  defaultMonth?: number
  defaultYear?: number
  loadingTitle?: string
  loadingMessage?: string
  errorTitle?: string
  emptyTitle: string
  emptyMessage: string
  periodLabel?: string
  extraHeader?: ReactNode
  children: (context: {
    rows: unknown[]
    data: T
    reload: () => void
    period: { month: number; year: number }
  }) => ReactNode
}

/**
 * Shared shell for every page under `/cms/reportes/*`.
 *
 * Responsibilities:
 *   - Render the same `PageHeader` + branch context used by the rest of the
 *     admin area (description interpolates `activeBranch.nombre`).
 *   - Provide loading / error / empty wrappers via `DataState` + `SectionCard`
 *     so individual pages do not reinvent the same JSX.
 *   - Run the page-supplied loader through `useApiResource` (so ETag revalidation
 *     and the keep-previous-data behaviour stay consistent with the rest of the
 *     admin SPA).
 *   - Optionally render month/year controls inside the section header's `action`
 *     slot when `withPeriod` is true. Pages that don't need a period (clients,
 *     prospects) leave the prop off.
 *
 * The shell does NOT render a table: pages render their own `<ReportTable />`
 * inside the `children` render prop, which receives `rows` extracted via
 * `rowsSelector`. This keeps the layout ignorant of report-specific columns.
 */
export function ReportLayout<T>({
  eyebrow = 'Reportes',
  title,
  description,
  loader,
  rowsSelector,
  withPeriod = false,
  defaultMonth,
  defaultYear,
  loadingTitle = 'Sincronizando datos',
  loadingMessage = 'Cargando la informacion del reporte seleccionado.',
  errorTitle = 'No pudimos cargar el reporte',
  emptyTitle,
  emptyMessage,
  periodLabel = 'Mes seleccionado',
  extraHeader,
  children,
}: ReportLayoutProps<T>) {
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  const now = new Date()
  const [month, setMonth] = useState(defaultMonth ?? now.getMonth() + 1)
  const [year, setYear] = useState(defaultYear ?? now.getFullYear())

  const { data, isLoading, error, reload } = useApiResource<T>(loader)

  // The page-supplied loader closes over refs (so its identity is stable),
  // which means `useApiResource` won't refetch on its own when the user
  // navigates the period or switches branch. Trigger the refetch explicitly
  // when any of those inputs change. The first run is skipped because
  // `useApiResource` already fires its own fetch on mount.
  const hasMountedRef = useRef(false)
  useEffect(() => {
    if (!hasMountedRef.current) {
      hasMountedRef.current = true
      return
    }
    reload()
  }, [branchId, month, year, reload])

  const rows = useMemo<unknown[]>(() => {
    if (!data) return []
    try {
      const next = rowsSelector(data)
      return Array.isArray(next) ? next : []
    } catch {
      return []
    }
  }, [data, rowsSelector])

  const branchSuffix = activeBranch ? ` de ${activeBranch.nombre}` : ''
  const composedDescription =
    description ?? `Consulta y exporta la informacion${branchSuffix}.`
  const composedTitle = `${title}${branchSuffix}`

  const changePeriod = (direction: -1 | 1) => {
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

  const periodActions = withPeriod ? (
    <div className="expense-period-controls">
      <button
        className="button button--ghost"
        type="button"
        onClick={() => changePeriod(-1)}
        aria-label="Mes anterior"
      >
        ←
      </button>
      <div>
        <span className="eyebrow">{periodLabel}</span>
        <h3>{`${REPORT_MONTHS[month - 1]} ${year}`}</h3>
      </div>
      <button
        className="button button--ghost"
        type="button"
        onClick={() => changePeriod(1)}
        aria-label="Mes siguiente"
      >
        →
      </button>
      <label className="field" style={{ marginLeft: '0.5rem' }}>
        <span className="visually-hidden">Mes</span>
        <select
          className="input"
          value={month}
          onChange={(event) => setMonth(parseInt(event.target.value, 10))}
        >
          {REPORT_MONTHS.map((name, index) => (
            <option key={name} value={index + 1}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span className="visually-hidden">Año</span>
        <select
          className="input"
          value={year}
          onChange={(event) => setYear(parseInt(event.target.value, 10))}
        >
          {REPORT_YEARS.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </label>
    </div>
  ) : null

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={eyebrow}
        title={composedTitle}
        description={composedDescription}
      />

      {isLoading && !data ? (
        <SectionCard title={loadingTitle}>
          <DataState title={loadingTitle} message={loadingMessage} />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title={errorTitle}>
          <DataState title={errorTitle} message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <SectionCard
          title={
            withPeriod
              ? `${title} - ${REPORT_MONTHS[month - 1]} ${year}`
              : title
          }
          description={composedDescription}
          action={periodActions}
        >
          {rows.length ? (
            children({ rows, data, reload, period: { month, year } })
          ) : (
            <DataState title={emptyTitle} message={emptyMessage} />
          )}
        </SectionCard>
      ) : null}

      {extraHeader}
    </div>
  )
}
