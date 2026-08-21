import { useCallback, useMemo, useState } from 'react'

import { DataState } from '../../../components/admin/DataState'
import { PageHeader } from '../../../components/admin/PageHeader'
import { SectionCard } from '../../../components/admin/SectionCard'
import { useApiResource } from '../../../hooks/useApiResource'
import { useBranchContext } from '../../../providers/BranchProvider'
import { useNotifications } from '../../../providers/NotificationProvider'
import { getAdminReportIncome } from '../../../services/api/admin'
import type { ReportIncomeItem, ReportResponse } from '../../../types/admin'
import { monthNames } from '../expenses/expenseUtils'
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
 * Pulls `ReportIncomeItem[]` from `/api/admin/reportes/ingresos/` via
 * `getAdminReportIncome(month, year)`. Owns its own month/year state so the
 * period always reflects the latest user input. The loader is keyed on
 * `[month, year]` through `useCallback`, which means `useApiResource`
 * refetches automatically whenever the period changes.
 *
 * Self-contained: ( does not delegate to `ReportLayout` because that shell
 * used a children render prop whose state synchronisation relied on
 * `rows.length > 0` to render the children, which left the page stuck on
 * the last period whenever the previous fetch returned no rows. Inlining
 * the section here removes that footgun.
 *
 * Read-only: row-level invoice URL is rendered as a clickable <a> in the
 * table AND exported as a `HYPERLINK` formula by `ReportTable`.
 */
export function AdminReportIncomePage() {
  const { activeBranch } = useBranchContext()
  const { showNotification } = useNotifications()
  const now = new Date()
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [year, setYear] = useState(now.getFullYear())
  const [showMonthPicker, setShowMonthPicker] = useState(false)
  const [pickerMonth, setPickerMonth] = useState(month)
  const [pickerYear, setPickerYear] = useState(year)

  const loader = useCallback(
    () => getAdminReportIncome(month, year),
    [month, year],
  )
  const { data, isLoading, error } = useApiResource<ReportResponse<ReportIncomeItem>>(loader)

  const rows = useMemo<ReportIncomeItem[]>(() => {
    if (!data) return []
    return Array.isArray(data.rows) ? data.rows : []
  }, [data])

  const branchSuffix = activeBranch ? ` de ${activeBranch.nombre}` : ''
  const title = 'Reporte de ingresos'
  const description =
    'Pagos registrados en el mes seleccionado, con vinculo directo a la factura cuando esta disponible.'
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

  const openMonthPicker = () => {
    setPickerMonth(month)
    setPickerYear(year)
    setShowMonthPicker(true)
  }

  const applyMonthPicker = () => {
    setMonth(pickerMonth)
    setYear(pickerYear)
    setShowMonthPicker(false)
  }

  const handleExport = () => {
    if (rows.length === 0) {
      showNotification({
        title: 'Sin datos',
        message: 'No hay ingresos para exportar en el periodo seleccionado.',
        tone: 'info',
      })
      return
    }
    buildReportExcelExport({
      columns: COLUMNS,
      rows: rows as unknown as Record<string, unknown>[],
      filename: `ingresos_${month}_${year}.xlsx`,
      sheetName: 'Ingresos',
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
              <div style={{ cursor: 'pointer' }} onClick={openMonthPicker}>
                <span className="eyebrow">Periodo de ingresos</span>
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
              title="Sin ingresos en el mes seleccionado"
              message="No se registran pagos para el periodo que estas consultando."
            />
          )}
        </SectionCard>
      ) : null}

      {showMonthPicker ? (
        <div className="qr-modal" role="dialog" aria-modal="true" aria-label="Seleccionar mes">
          <div className="qr-modal__backdrop" onClick={() => setShowMonthPicker(false)} />
          <div className="qr-modal__content">
            <header className="qr-modal__header">
              <div>
                <span>Seleccionar periodo</span>
                <strong>Elige el mes y año</strong>
              </div>
              <button
                className="button button--ghost button--compact"
                type="button"
                onClick={() => setShowMonthPicker(false)}
              >
                Cerrar
              </button>
            </header>
            <div className="form-grid" style={{ marginTop: '1rem' }}>
              <label className="field">
                <span>Mes</span>
                <select
                  className="input"
                  value={pickerMonth}
                  onChange={(e) => setPickerMonth(parseInt(e.target.value, 10))}
                >
                  {monthNames.map((name, index) => (
                    <option key={name} value={index + 1}>{name}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Año</span>
                <select
                  className="input"
                  value={pickerYear}
                  onChange={(e) => setPickerYear(parseInt(e.target.value, 10))}
                >
                  {[2024, 2025, 2026, 2027, 2028, 2029, 2030].map((y) => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="form-actions" style={{ marginTop: '1rem' }}>
              <button
                className="button button--ghost"
                type="button"
                onClick={() => setShowMonthPicker(false)}
              >
                Cancelar
              </button>
              <button
                className="button"
                type="button"
                onClick={applyMonthPicker}
              >
                Aplicar
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}