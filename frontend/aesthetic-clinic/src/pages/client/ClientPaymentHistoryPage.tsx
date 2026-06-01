import { useState } from 'react'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getClientPayments } from '../../services/api/client'
import { monthNames } from '../admin/expenses/expenseUtils'

function parsePaymentDate(value?: string, currentYear?: number): Date | null {
  if (!value) return null
  const trimmed = value.trim()
  if (!trimmed) return null

  // Try DD/MM HH:MM format (e.g., "30/05 23:25")
  const shortFormat = trimmed.match(/^(\d{2})\/(\d{2})\s+(\d{2}):(\d{2})/)
  if (shortFormat) {
    const [, dd, mm] = shortFormat
    const year = currentYear ?? new Date().getFullYear()
    const date = new Date(year, parseInt(mm) - 1, parseInt(dd))
    if (!Number.isNaN(date.getTime())) return date
  }

  // Try DD/MM/YYYY format
  const ddmmyyyy = trimmed.match(/^(\d{2})\/(\d{2})\/(\d{4})/)
  if (ddmmyyyy) {
    const [, dd, mm, yyyy] = ddmmyyyy
    const date = new Date(parseInt(yyyy), parseInt(mm) - 1, parseInt(dd))
    if (!Number.isNaN(date.getTime())) return date
  }

  // Try ISO format first (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
  const isoMatch = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (isoMatch) {
    const [, yyyy, mm, dd] = isoMatch
    const date = new Date(parseInt(yyyy), parseInt(mm) - 1, parseInt(dd))
    if (!Number.isNaN(date.getTime())) return date
  }

  // Try DD-MM-YYYY format
  const ddmmyyyyDash = trimmed.match(/^(\d{2})-(\d{2})-(\d{4})/)
  if (ddmmyyyyDash) {
    const [, dd, mm, yyyy] = ddmmyyyyDash
    const date = new Date(parseInt(yyyy), parseInt(mm) - 1, parseInt(dd))
    if (!Number.isNaN(date.getTime())) return date
  }

  // Try MM/DD/YYYY format (US format)
  const mmddyyyy = trimmed.match(/^(\d{2})\/(\d{2})\/(\d{4})/)
  if (mmddyyyy) {
    const [, mm, dd, yyyy] = mmddyyyy
    const date = new Date(parseInt(yyyy), parseInt(mm) - 1, parseInt(dd))
    if (!Number.isNaN(date.getTime())) return date
  }

  // Last resort: try native Date parsing
  const native = new Date(trimmed)
  if (!Number.isNaN(native.getTime())) return native

  return null
}

export function ClientPaymentHistoryPage() {
  const now = new Date()
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [year, setYear] = useState(now.getFullYear())
  const [statusFilter, setStatusFilter] = useState('')
  const [showMonthPicker, setShowMonthPicker] = useState(false)
  const [pickerMonth, setPickerMonth] = useState(month)
  const [pickerYear, setPickerYear] = useState(year)

  const viewedMonthLabel = `${monthNames[month - 1]} ${year}`

  const { data, isLoading, error } = useApiResource(getClientPayments)

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

  const changeMonth = (direction: -1 | 1) => {
    let nextMonth = month + direction
    let nextYear = year

    if (nextMonth < 1) {
      nextMonth = 12
      nextYear = year - 1
    } else if (nextMonth > 12) {
      nextMonth = 1
      nextYear = year + 1
    }

    setYear(nextYear)
    setMonth(nextMonth)
  }

  const filteredPayments = (data?.payments ?? []).filter((payment) => {
    if (statusFilter && payment.status.toLowerCase() !== statusFilter.toLowerCase()) {
      return false
    }

    const paymentDate = parsePaymentDate(payment.submittedAt, year)
    if (paymentDate) {
      if (paymentDate.getMonth() + 1 !== month) return false
      if (paymentDate.getFullYear() !== year) return false
    }

    return true
  })

  const paymentStatuses = data ? [...new Set(data.payments.map((p) => p.status))] : []

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Historial de pagos"
        title="Todos tus comprobantes"
        description="Revisa todos tus pagos organizados por mes, con filtro por estado."
      />

      {isLoading && !data ? (
        <SectionCard title="Cargando historial">
          <DataState title="Sincronizando pagos" message="Estamos trayendo tu historial de comprobantes." />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar el historial">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <SectionCard
          eyebrow="Comprobantes"
          title={`Pagos de ${viewedMonthLabel}`}
          description="Historial completo de comprobantes cargados en el mes seleccionado."
          action={
            <div className="expense-period-controls">
              <button className="button button--ghost" type="button" onClick={() => changeMonth(-1)}>←</button>
              <div style={{ cursor: 'pointer' }} onClick={openMonthPicker}>
                <span className="eyebrow">Mes seleccionado</span>
                <h3 style={{ cursor: 'pointer' }}>{viewedMonthLabel}</h3>
              </div>
              <button className="button button--ghost" type="button" onClick={() => changeMonth(1)}>→</button>
            </div>
          }
        >
          <div className="form-grid _mb-md">
            <label className="field">
              <span>Estado</span>
              <select className="input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="">Todos los estados</option>
                {paymentStatuses.map((status) => (
                  <option key={status} value={status}>{status}</option>
                ))}
              </select>
            </label>
          </div>
          {filteredPayments.length ? (
            <div className="table-card">
              <table>
                <thead>
                  <tr>
                    <th>Operacion</th>
                    <th>Cuota</th>
                    <th>Monto</th>
                    <th>Fecha</th>
                    <th>Estado</th>
                    <th>Comprobante</th>
                    <th>Revision</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPayments.map((payment) => (
                    <tr key={payment.id}>
                      <td>
                        <strong>{payment.operation}</strong>
                      </td>
                      <td>
                        <strong>{payment.quotaLabel}</strong>
                        <span>Vence {payment.dueDate}</span>
                      </td>
                      <td>{payment.amount}</td>
                      <td>{payment.submittedAt}</td>
                      <td>
                        <StatusBadge tone={payment.statusTone}>{payment.status}</StatusBadge>
                      </td>
                      <td>
                        {payment.receiptUrl ? (
                          <a className="button button--ghost button--compact" href={payment.receiptUrl} target="_blank" rel="noreferrer">
                            Ver archivo
                          </a>
                        ) : (
                          <span>Sin archivo</span>
                        )}
                      </td>
                      <td>
                        <strong>{payment.verifier}</strong>
                        <span>{payment.note}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <DataState
              title="Sin pagos en este mes"
              message={`No hay comprobantes registrados para ${viewedMonthLabel}.`}
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
                <strong>Elige el mes y ano</strong>
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
                  onChange={(e) => setPickerMonth(parseInt(e.target.value))}
                >
                  {monthNames.map((name, index) => (
                    <option key={name} value={index + 1}>{name}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Ano</span>
                <select
                  className="input"
                  value={pickerYear}
                  onChange={(e) => setPickerYear(parseInt(e.target.value))}
                >
                  {[2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027, 2028].map((y) => (
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
