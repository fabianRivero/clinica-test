import { useMemo, useState } from 'react'

import { DataState } from '../../components/admin/DataState'
import { AdminRelationshipTabs } from '../../components/admin/AdminRelationshipTabs'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import {
  cancelAdminProspectMedicalAppointment,
  createAdminProspectMedicalAppointment,
  getAdminProspectMedicalAvailability,
  getAdminProspects,
} from '../../services/api/admin'
import type { AdminProspectMedicalAvailabilityResponse, ProspectLead } from '../../types/admin'
import { Link, useLocation } from 'react-router-dom'

const WEEKDAY_LABELS = ['Lun', 'Mar', 'Mie', 'Jue', 'Vie', 'Sab', 'Dom']
const PROSPECT_STATUS_OPTIONS = ['Pasajero', 'Convertido', 'Descartado']

function toDateKey(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function monthStart(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), 1)
}

function addMonths(value: Date, amount: number) {
  return new Date(value.getFullYear(), value.getMonth() + amount, 1)
}

function buildCalendarGrid(monthValue: Date) {
  const start = monthStart(monthValue)
  const firstWeekday = (start.getDay() + 6) % 7
  const firstVisibleDay = new Date(start)
  firstVisibleDay.setDate(start.getDate() - firstWeekday)

  return Array.from({ length: 42 }, (_, index) => {
    const current = new Date(firstVisibleDay)
    current.setDate(firstVisibleDay.getDate() + index)
    return {
      key: toDateKey(current),
      dayNumber: current.getDate(),
      inCurrentMonth: current.getMonth() === monthValue.getMonth(),
    }
  })
}

function monthLabel(value: Date) {
  return value.toLocaleDateString('es-BO', { month: 'long', year: 'numeric' })
}

function longDateLabel(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString('es-BO', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })
}

export function AdminProspectsPage() {
  const location = useLocation()
  const { showNotification } = useNotifications()
  const { data, isLoading, error, reload } = useApiResource(getAdminProspects)
  const [bookingProspect, setBookingProspect] = useState<ProspectLead | null>(null)
  const [availability, setAvailability] = useState<AdminProspectMedicalAvailabilityResponse | null>(null)
  const [bookingError, setBookingError] = useState<string | null>(null)
  const [isLoadingAvailability, setIsLoadingAvailability] = useState(false)
  const [selectedDate, setSelectedDate] = useState('')
  const [visibleMonth, setVisibleMonth] = useState<Date>(monthStart(new Date()))
  const [isBookingKey, setIsBookingKey] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('TODOS')
  const flashMessage =
    typeof location.state === 'object' && location.state && 'flashMessage' in location.state
      ? String(location.state.flashMessage)
      : null

  const availableDateSet = useMemo(
    () => new Set(availability?.calendar.availableDates.map((item) => item.date) ?? []),
    [availability],
  )
  const calendarDays = useMemo(() => buildCalendarGrid(visibleMonth), [visibleMonth])
  const selectedSlots = availability?.calendar.slotsByDate[selectedDate] ?? []
  const minMonth = availability?.calendar.windowStart
    ? monthStart(new Date(`${availability.calendar.windowStart}T00:00:00`))
    : null
  const maxMonth = availability?.calendar.windowEnd
    ? monthStart(new Date(`${availability.calendar.windowEnd}T00:00:00`))
    : null
  const canGoPreviousMonth = minMonth ? visibleMonth.getTime() > minMonth.getTime() : false
  const canGoNextMonth = maxMonth ? visibleMonth.getTime() < maxMonth.getTime() : false
  const filteredProspects = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase()
    return (data?.prospects ?? []).filter((lead) => {
      const matchesSearch =
        !normalizedSearch ||
        lead.name.toLowerCase().includes(normalizedSearch)
      const matchesStatus = statusFilter === 'TODOS' || lead.state === statusFilter
      return matchesSearch && matchesStatus
    })
  }, [data, searchTerm, statusFilter])

  async function handleOpenBooking(lead: ProspectLead) {
    if (!lead.rawId) return
    setBookingProspect(lead)
    setAvailability(null)
    setBookingError(null)
    setIsLoadingAvailability(true)
    try {
      const response = await getAdminProspectMedicalAvailability(lead.rawId)
      setAvailability(response)
      const firstDate = response.calendar.availableDates[0]?.date ?? ''
      setSelectedDate(firstDate)
      setVisibleMonth(monthStart(firstDate ? new Date(`${firstDate}T00:00:00`) : new Date()))
    } catch (requestError) {
      setBookingError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo cargar la disponibilidad para cita medica.',
      )
    } finally {
      setIsLoadingAvailability(false)
    }
  }

  async function handleReserve(slotId: number) {
    if (!bookingProspect?.rawId) return
    const selectedSlot = Object.values(availability?.calendar.slotsByDate ?? {})
      .flat()
      .find((item) => item.slotId === slotId)
    const bookingKey = selectedSlot ? `${selectedSlot.date}-${selectedSlot.time}-${selectedSlot.specialistId}` : `slot-${slotId}`
    setIsBookingKey(bookingKey)

    try {
      const response = await createAdminProspectMedicalAppointment(bookingProspect.rawId, slotId)
      showNotification({ title: 'Cita medica agendada', message: response.detail, tone: 'success' })
      setBookingProspect(null)
      setAvailability(null)
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo agendar',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    } finally {
      setIsBookingKey(null)
    }
  }

  async function handleCancelAppointment(appointmentId: number) {
    const confirmed = window.confirm('Se cancelara la cita medica del prospecto. ¿Deseas continuar?')
    if (!confirmed) return

    try {
      const response = await cancelAdminProspectMedicalAppointment(appointmentId)
      showNotification({ title: 'Cita cancelada', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo cancelar',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Relacion comercial"
        title="Prospectos y clientes"
        description="Administra prospectos pasajeros, su avance comercial y el momento en que pasan a clientes formales."
        actions={[
          { label: 'Registrar prospecto', variant: 'primary', to: '/admin/prospectos/nuevo' },
          { label: 'Importar contactos', variant: 'ghost' },
        ]}
      />

      <AdminRelationshipTabs />

      {flashMessage ? <DataState title="Registro actualizado" message={flashMessage} /> : null}

      {isLoading && !data ? (
        <SectionCard title="Cargando relacion comercial">
          <DataState
            title="Sincronizando prospectos"
            message="Estamos trayendo prospectos, conversiones y clientes con cuenta."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar la relacion comercial">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <>
          <section className="metrics-grid metrics-grid--compact">
            {data.metrics.slice(0, 2).map((metric) => (
              <MetricCard key={metric.id} metric={metric} />
            ))}
          </section>

          <SectionCard
            eyebrow="Seguimiento"
            title="Prospectos registrados"
            description="Registros internos que todavia no son clientes formales o ya fueron convertidos."
          >
            <div className="form-grid">
              <label className="field">
                <span>Buscar prospecto</span>
                <input
                  className="input"
                  placeholder="Nombre"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Estado</span>
                <select
                  className="input"
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                >
                  <option value="TODOS">Todos</option>
                  {PROSPECT_STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {filteredProspects.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Telefono</th>
                      <th>Interes</th>
                      <th>Registrado por</th>
                      <th>Etapa</th>
                      <th>Estado</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredProspects.map((lead) => (
                      <tr key={lead.id}>
                        <td>
                          <strong>{lead.name}</strong>
                          <span>{lead.createdAt}</span>
                        </td>
                        <td>{lead.phone}</td>
                        <td>{lead.interest}</td>
                        <td>{lead.registeredBy}</td>
                        <td>
                          <StatusBadge tone="primary">{lead.stage}</StatusBadge>
                        </td>
                        <td>{lead.state}</td>
                        <td>
                          {lead.state === 'Pasajero' ? (
                            <div className="table-actions">
                              <Link className="button button--ghost button--compact" to={`/admin/prospectos/${lead.rawId}/convertir`}>
                                Convertir
                              </Link>
                              {lead.scheduledMedicalAppointment ? (
                                <>
                                  <div className="table-muted">
                                    {lead.scheduledMedicalAppointment.dateTime} | {lead.scheduledMedicalAppointment.specialist}
                                  </div>
                                  {lead.scheduledMedicalAppointment.canCancel ? (
                                    <button
                                      className="button button--ghost button--compact"
                                      type="button"
                                      onClick={() => void handleCancelAppointment(lead.scheduledMedicalAppointment!.rawId)}
                                    >
                                      Cancelar cita
                                    </button>
                                  ) : null}
                                </>
                              ) : (
                                <button
                                  className="button button--ghost button--compact"
                                  type="button"
                                  onClick={() => void handleOpenBooking(lead)}
                                >
                                  Agendar cita medica
                                </button>
                              )}
                            </div>
                          ) : (
                            <span>-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <DataState
                title={data.prospects.length ? 'Sin resultados' : 'Sin prospectos cargados'}
                message={
                  data.prospects.length
                    ? 'No hay prospectos que coincidan con la busqueda o el filtro seleccionado.'
                    : 'Todavia no hay pasajeros o conversiones registradas en la base real.'
                }
              />
            )}
          </SectionCard>

          {bookingProspect ? (
            <section className="dashboard-grid">
              <SectionCard
                eyebrow="Cita medica"
                title={`Agendar cita para ${bookingProspect.name}`}
                description={availability ? `Servicio: ${availability.service.name}` : 'Buscando cupos publicados para cita medica.'}
              >
                <div className="client-inline-meta">
                  <button className="button button--ghost button--compact" type="button" onClick={() => setBookingProspect(null)}>
                    Cerrar
                  </button>
                  <span>{bookingProspect.phone}</span>
                </div>

                {isLoadingAvailability ? (
                  <DataState title="Cargando cupos" message="Consultando disponibilidad para cita medica." />
                ) : null}
                {bookingError ? (
                  <DataState title="No se pudo cargar disponibilidad" message={bookingError} tone="danger" />
                ) : null}

                {availability ? (
                  <div className="reservation-calendar">
                    <div className="reservation-calendar__header">
                      <button
                        className="button button--ghost button--compact"
                        disabled={!canGoPreviousMonth}
                        type="button"
                        onClick={() => setVisibleMonth((current) => addMonths(current, -1))}
                      >
                        Mes anterior
                      </button>
                      <strong>{monthLabel(visibleMonth)}</strong>
                      <button
                        className="button button--ghost button--compact"
                        disabled={!canGoNextMonth}
                        type="button"
                        onClick={() => setVisibleMonth((current) => addMonths(current, 1))}
                      >
                        Mes siguiente
                      </button>
                    </div>
                    <div className="reservation-calendar__weekdays">
                      {WEEKDAY_LABELS.map((label) => <span key={label}>{label}</span>)}
                    </div>
                    <div className="reservation-calendar__grid">
                      {calendarDays.map((day) => {
                        const isAvailable = availableDateSet.has(day.key)
                        return (
                          <button
                            key={day.key}
                            className={`reservation-calendar__day ${isAvailable ? 'is-available' : ''} ${selectedDate === day.key ? 'is-selected' : ''} ${!day.inCurrentMonth ? 'is-outside' : ''}`}
                            type="button"
                            onClick={() => setSelectedDate(day.key)}
                          >
                            <span>{day.dayNumber}</span>
                            {isAvailable ? (
                              <small>{availability.calendar.availableDates.find((item) => item.date === day.key)?.slotCount ?? 0} cupos</small>
                            ) : null}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ) : null}
              </SectionCard>

              <SectionCard
                eyebrow="Horarios"
                title={selectedDate ? `Disponibilidad para ${longDateLabel(selectedDate)}` : 'Selecciona un dia'}
                description="Al confirmar, el cupo quedara reservado para este prospecto."
              >
                {selectedDate && selectedSlots.length ? (
                  <div className="reservation-slot-list">
                    {selectedSlots.map((slot) => {
                      const bookingKey = `${slot.date}-${slot.time}-${slot.specialistId}`
                      return (
                        <article className="reservation-slot-card" key={bookingKey}>
                          <div>
                            <strong>{slot.timeRange}</strong>
                            <p>{slot.specialist}</p>
                            <span>{slot.dateTimeLabel}</span>
                          </div>
                          <button className="button" disabled={Boolean(isBookingKey)} type="button" onClick={() => void handleReserve(slot.slotId)}>
                            {isBookingKey === bookingKey ? 'Agendando...' : 'Confirmar cita'}
                          </button>
                        </article>
                      )
                    })}
                  </div>
                ) : (
                  <DataState title="Sin horarios seleccionados" message="Elige un dia resaltado para ver cupos disponibles." />
                )}
              </SectionCard>
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  )
}
