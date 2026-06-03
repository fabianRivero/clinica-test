import { useState } from 'react'
import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { verificationStatusLabel, verificationStatusTone } from '../../constants/verification'
import { useApiResource } from '../../hooks/useApiResource'
import { getClientReservations } from '../../services/api/client'
import { useLocation } from 'react-router-dom'
import { monthNames } from '../admin/expenses/expenseUtils'

function parseAppointmentDate(value?: string, currentYear?: number): Date | null {
  if (!value) return null
  const trimmed = value.trim()
  if (!trimmed) return null

  // Try DD/MM HH:MM or DD/MM/YYYY HH:MM format
  const shortFormat = trimmed.match(/^(\d{2})\/(\d{2})\s+(\d{2}:\d{2})/)
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

  // Try ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
  const isoMatch = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (isoMatch) {
    const [, yyyy, mm, dd] = isoMatch
    const date = new Date(parseInt(yyyy), parseInt(mm) - 1, parseInt(dd))
    if (!Number.isNaN(date.getTime())) return date
  }

  // Last resort: try native Date parsing
  const native = new Date(trimmed)
  if (!Number.isNaN(native.getTime())) return native

  return null
}

export function ClientReservationsPage() {
  const location = useLocation()
  const { data, isLoading, error } = useApiResource(getClientReservations)
  const flashMessage =
    typeof location.state === 'object' && location.state && 'flashMessage' in location.state
      ? String(location.state.flashMessage)
      : null

  const now = new Date()
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [year, setYear] = useState(now.getFullYear())
  const [statusFilter, setStatusFilter] = useState('')
  const [showMonthPicker, setShowMonthPicker] = useState(false)
  const [pickerMonth, setPickerMonth] = useState(month)
  const [pickerYear, setPickerYear] = useState(year)

  const viewedMonthLabel = `${monthNames[month - 1]} ${year}`

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

  const filteredAppointments = (data?.appointments ?? []).filter((appointment) => {
    if (statusFilter && appointment.status.toLowerCase() !== statusFilter.toLowerCase()) {
      return false
    }

    const appointmentDate = parseAppointmentDate(appointment.dateTime, year)
    if (appointmentDate) {
      if (appointmentDate.getMonth() + 1 !== month) return false
      if (appointmentDate.getFullYear() !== year) return false
    }

    return true
  })

  const appointmentStatuses = data ? [...new Set(data.appointments.map((a) => a.status))] : []

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Agenda y reservas"
        title="Mis reservas"
        description="Consulta citas registradas y su estado de confirmación."
      />

      {flashMessage ? <DataState title="Reserva registrada" message={flashMessage} /> : null}

      {isLoading && !data ? (
        <SectionCard title="Cargando reservas">
          <DataState title="Sincronizando agenda" message="Estamos cargando tus citas y cupos disponibles." />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar tus reservas">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <SectionCard
          eyebrow="Agenda"
          title={`Citas de ${viewedMonthLabel}`}
          description="Incluye citas futuras y tambien las que esperan confirmación o quedaron con observaciones."
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
                {appointmentStatuses.map((status) => (
                  <option key={status} value={status}>{status}</option>
                ))}
              </select>
            </label>
          </div>
          {filteredAppointments.length ? (
            <div className="table-card">
              <table>
                <thead>
                  <tr>
                    <th>Operación</th>
                    <th>Especialista</th>
                    <th>Fecha</th>
                    <th>Estado</th>
                    <th>Confirmación</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAppointments.map((appointment) => (
                    <tr key={appointment.id}>
                      <td>
                        <strong>{appointment.operation}</strong>
                        <span>{appointment.details}</span>
                      </td>
                      <td>{appointment.specialist}</td>
                      <td>{appointment.dateTime}</td>
                      <td>
                        <StatusBadge tone={appointment.statusTone}>{appointment.status}</StatusBadge>
                      </td>
                      <td>
                        <StatusBadge tone={verificationStatusTone[appointment.verificationStatus ?? 'pendiente']}>
                          {verificationStatusLabel[appointment.verificationStatus ?? 'pendiente']}
                        </StatusBadge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <DataState
              title="Sin citas en este mes"
              message={`No hay citas registradas para ${viewedMonthLabel}.`}
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
