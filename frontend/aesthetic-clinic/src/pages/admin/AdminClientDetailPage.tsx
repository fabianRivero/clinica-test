import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { DataState } from '../../components/admin/DataState'
import { AdminRelationshipTabs } from '../../components/admin/AdminRelationshipTabs'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import {
  cancelAdminAppointment,
  confirmAdminAppointmentBiometric,
  createAdminClientReservation,
  getAdminClientDetail,
  getAdminClientReservationAvailability,
  inactivateAdminClient,
  markAdminAppointmentPendingBiometric,
} from '../../services/api/admin'
import { verifyMockFingerprint } from '../../services/fingerprint/mockFingerprint'
import type { AdminClientReservationAvailabilityResponse } from '../../types/admin'

const WEEKDAY_LABELS = ['Lun', 'Mar', 'Mie', 'Jue', 'Vie', 'Sab', 'Dom']

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

export function AdminClientDetailPage() {
  const { clientId = '' } = useParams()
  const { showNotification } = useNotifications()
  const loader = useCallback(() => getAdminClientDetail(clientId), [clientId])
  const { data, isLoading, error, reload } = useApiResource(loader)
  const [selectedOperationId, setSelectedOperationId] = useState<number | ''>('')
  const [availability, setAvailability] = useState<AdminClientReservationAvailabilityResponse | null>(null)
  const [availabilityError, setAvailabilityError] = useState<string | null>(null)
  const [isLoadingAvailability, setIsLoadingAvailability] = useState(false)
  const [selectedDate, setSelectedDate] = useState('')
  const [visibleMonth, setVisibleMonth] = useState<Date>(monthStart(new Date()))
  const [isBookingKey, setIsBookingKey] = useState<string | null>(null)
  const [isInactivating, setIsInactivating] = useState(false)
  const [appointmentActionId, setAppointmentActionId] = useState<number | null>(null)

  const reservableOperations = useMemo(
    () => data?.operations.filter((operation) => operation.status === 'En proceso') ?? [],
    [data],
  )
  const effectiveOperationId = selectedOperationId || reservableOperations[0]?.rawId || ''

  useEffect(() => {
    let cancelled = false

    async function loadAvailability() {
      if (!data || !effectiveOperationId) {
        setAvailability(null)
        return
      }
      setIsLoadingAvailability(true)
      setAvailabilityError(null)
      try {
        const response = await getAdminClientReservationAvailability(data.client.rawId, effectiveOperationId)
        if (cancelled) return
        setAvailability(response)
        const firstAvailableDate = response.calendar.availableDates[0]?.date ?? ''
        setSelectedDate(firstAvailableDate)
        setVisibleMonth(monthStart(firstAvailableDate ? new Date(`${firstAvailableDate}T00:00:00`) : new Date()))
      } catch (requestError) {
        if (!cancelled) {
          setAvailability(null)
          setAvailabilityError(
            requestError instanceof Error
              ? requestError.message
              : 'No se pudo cargar la disponibilidad.',
          )
        }
      } finally {
        if (!cancelled) setIsLoadingAvailability(false)
      }
    }

    void loadAvailability()
    return () => {
      cancelled = true
    }
  }, [data, effectiveOperationId])

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

  async function handleCancelAppointment(appointmentId: number) {
    const shouldCancel = window.confirm('Se cancelara esta reserva y el cupo volvera a quedar disponible. ¿Deseas continuar?')
    if (!shouldCancel) return

    try {
      const response = await cancelAdminAppointment(appointmentId)
      showNotification({ title: 'Cita cancelada', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo cancelar la cita',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  async function handleMarkPendingBiometric(appointmentId: number) {
    setAppointmentActionId(appointmentId)
    try {
      const response = await markAdminAppointmentPendingBiometric(appointmentId)
      showNotification({
        title: 'Cita pendiente de biometria',
        message: response.detail,
        tone: 'success',
      })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo actualizar la cita',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    } finally {
      setAppointmentActionId(null)
    }
  }

  async function handleConfirmBiometric(appointmentId: number, biometricMockTemplate: string) {
    if (!biometricMockTemplate) {
      showNotification({
        title: 'Sin huella registrada',
        message: 'Este cliente no tiene una huella mock disponible para comparar.',
        tone: 'danger',
      })
      return
    }

    setAppointmentActionId(appointmentId)
    try {
      const capture = await verifyMockFingerprint(biometricMockTemplate)
      const response = await confirmAdminAppointmentBiometric(appointmentId, {
        provider: capture.provider,
        template: capture.template,
        quality: capture.quality,
        deviceSerial: capture.deviceSerial,
      })
      showNotification({
        title: 'Huella confirmada',
        message: 'La cita fue confirmada con la huella biometrica simulada.',
        tone: 'success',
      })
      reload()
      void response
    } catch (requestError) {
      showNotification({
        title: 'No se pudo confirmar la huella',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    } finally {
      setAppointmentActionId(null)
    }
  }

  async function handleReserve(slotId: number) {
    if (!data || !effectiveOperationId) return
    const selectedSlot = Object.values(availability?.calendar.slotsByDate ?? {})
      .flat()
      .find((item) => item.slotId === slotId)
    const bookingKey = selectedSlot ? `${selectedSlot.date}-${selectedSlot.time}-${selectedSlot.specialistId}` : `slot-${slotId}`
    setIsBookingKey(bookingKey)

    try {
      const response = await createAdminClientReservation(data.client.rawId, effectiveOperationId, slotId)
      showNotification({ title: 'Reserva registrada', message: response.detail, tone: 'success' })
      reload()
      setSelectedOperationId('')
      setAvailability(null)
    } catch (requestError) {
      showNotification({
        title: 'No se pudo reservar',
        message: requestError instanceof Error ? requestError.message : 'No se pudo registrar la reserva.',
        tone: 'danger',
      })
    } finally {
      setIsBookingKey(null)
    }
  }

  async function handleInactivateClient() {
    if (!data) return
    const activeOperations = data.operations.filter((operation) => operation.status === 'En proceso')
    const pendingSessions = activeOperations.reduce(
      (total, operation) =>
        total + Math.max(operation.sessions.total - operation.sessions.confirmed, 0),
      0,
    )
    const pendingQuotas = data.pendingQuotas.length
    const warningDetail =
      pendingSessions || pendingQuotas
        ? `Advertencia: este cliente aun tiene ${pendingSessions} sesion(es) y ${pendingQuotas} cuota(s) pendiente(s). `
        : ''
    const confirmed = window.confirm(
      `${warningDetail}El cliente pasara a inactivo, se cancelaran sus procedimientos en proceso y sus citas programadas. ¿Deseas continuar?`,
    )
    if (!confirmed) return

    setIsInactivating(true)
    try {
      const response = await inactivateAdminClient(data.client.rawId)
      showNotification({ title: 'Cliente inactivo', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo inactivar',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    } finally {
      setIsInactivating(false)
    }
  }

  if (isLoading && !data) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="Clientes" title="Cargando cliente" description="Estamos preparando su historial administrativo." />
        <SectionCard title="Sincronizando">
          <DataState title="Cargando informacion" message="Consultando citas, sesiones, pagos y procedimientos." />
        </SectionCard>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="Clientes" title="No pudimos cargar el cliente" description="Revisa la lista e intenta nuevamente." actions={[{ label: 'Volver a clientes', variant: 'ghost', to: '/admin/clientes' }]} />
        <SectionCard title="Cliente no disponible">
          <DataState title="Conexion no disponible" message={error || 'No encontramos el cliente solicitado.'} tone="danger" />
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Administrador de cliente"
        title={data.client.name}
        description={`${data.client.status} | ${data.client.phone} | Ultimo analisis: ${data.client.lastAnalysis}`}
        actions={[
          { label: 'Volver a clientes', variant: 'ghost', to: '/admin/clientes' },
        ]}
      />

      <AdminRelationshipTabs />

      <section className="metrics-grid metrics-grid--compact">
        {data.metrics.map((metric) => (
          <MetricCard key={metric.id} metric={metric} />
        ))}
      </section>

      <SectionCard eyebrow="Estado" title="Gestion del cliente" description="Permite retirar al cliente de sus procedimientos vigentes cuando corresponde.">
        <div className="client-inline-meta">
          <StatusBadge tone={data.client.status === 'Activo' ? 'success' : 'neutral'}>{data.client.status}</StatusBadge>
          <span>{data.client.activeOperations} procedimiento(s) activo(s)</span>
          <button className="button button--ghost" disabled={data.client.status !== 'Activo' || isInactivating} type="button" onClick={() => void handleInactivateClient()}>
            {isInactivating ? 'Inactivando...' : 'Convertir a inactivo'}
          </button>
        </div>
      </SectionCard>

      <section className="dashboard-grid">
        <SectionCard eyebrow="Reservas" title="Hacer reserva para este cliente" description="Selecciona un procedimiento en proceso y un cupo publicado por administracion.">
          {reservableOperations.length ? (
            <div className="form-grid">
              <label className="field field--full">
                <span>Procedimiento</span>
                <select className="input" value={effectiveOperationId} onChange={(event) => setSelectedOperationId(Number(event.target.value))}>
                  {reservableOperations.map((operation) => (
                    <option key={operation.id} value={operation.rawId}>
                      {operation.procedure} | {operation.reserveMessage}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : (
            <DataState title="Sin procedimientos en proceso" message="Este cliente no tiene tratamientos activos para nuevas reservas." />
          )}

          {isLoadingAvailability ? <DataState title="Cargando cupos" message="Buscando horarios disponibles para el procedimiento." /> : null}
          {availabilityError ? <DataState title="No hay disponibilidad" message={availabilityError} tone="danger" /> : null}

          {availability ? (
            <div className="reservation-calendar">
              <div className="reservation-calendar__header">
                <button className="button button--ghost button--compact" disabled={!canGoPreviousMonth} type="button" onClick={() => setVisibleMonth((current) => addMonths(current, -1))}>
                  Mes anterior
                </button>
                <strong>{monthLabel(visibleMonth)}</strong>
                <button className="button button--ghost button--compact" disabled={!canGoNextMonth} type="button" onClick={() => setVisibleMonth((current) => addMonths(current, 1))}>
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
                    <button key={day.key} className={`reservation-calendar__day ${isAvailable ? 'is-available' : ''} ${selectedDate === day.key ? 'is-selected' : ''} ${!day.inCurrentMonth ? 'is-outside' : ''}`} type="button" onClick={() => setSelectedDate(day.key)}>
                      <span>{day.dayNumber}</span>
                      {isAvailable ? <small>{availability.calendar.availableDates.find((item) => item.date === day.key)?.slotCount ?? 0} cupos</small> : null}
                    </button>
                  )
                })}
              </div>
            </div>
          ) : null}
        </SectionCard>

        <SectionCard eyebrow="Horarios" title={selectedDate ? `Disponibilidad para ${longDateLabel(selectedDate)}` : 'Selecciona un dia'} description="Al confirmar, la cita quedara registrada para este cliente.">
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
                      {isBookingKey === bookingKey ? 'Reservando...' : 'Confirmar reserva'}
                    </button>
                  </article>
                )
              })}
            </div>
          ) : (
            <DataState title="Sin horarios seleccionados" message="Elige un dia resaltado para ver cupos o cambia de procedimiento." />
          )}
        </SectionCard>
      </section>

      <SectionCard eyebrow="Agenda" title="Todas las citas del cliente" description="Historial completo de reservas, sesiones realizadas, cancelaciones y pendientes de biometria.">
        {data.appointments.length ? (
          <div className="table-card">
            <table>
              <thead>
                <tr>
                  <th>Operacion</th>
                  <th>Especialista</th>
                  <th>Fecha</th>
                  <th>Estado</th>
                  <th>Biometria</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {data.appointments.map((appointment) => (
                  <tr key={appointment.id}>
                    <td><strong>{appointment.operation}</strong><span>{appointment.details}</span></td>
                    <td>{appointment.specialist}</td>
                    <td>{appointment.dateTime}</td>
                    <td><StatusBadge tone={appointment.statusTone}>{appointment.status}</StatusBadge></td>
                    <td>{appointment.biometric}</td>
                    <td>
                      <div className="table-action-list">
                        {appointment.canManage ? (
                          <button
                            className="button button--ghost button--compact"
                            disabled={appointmentActionId !== null}
                            type="button"
                            onClick={() => void handleCancelAppointment(appointment.rawId)}
                          >
                            Cancelar reserva
                          </button>
                        ) : null}
                        {appointment.canMarkPendingBiometric ? (
                          <button
                            className="button button--ghost button--compact"
                            disabled={appointmentActionId !== null}
                            type="button"
                            onClick={() => void handleMarkPendingBiometric(appointment.rawId)}
                          >
                            {appointmentActionId === appointment.rawId ? 'Actualizando...' : 'Pendiente biometria'}
                          </button>
                        ) : null}
                        {appointment.canConfirmBiometric ? (
                          <button
                            className="button button--ghost button--compact"
                            disabled={appointmentActionId !== null}
                            type="button"
                            onClick={() => void handleConfirmBiometric(appointment.rawId, appointment.biometricMockTemplate)}
                          >
                            {appointmentActionId === appointment.rawId ? 'Validando...' : 'Confirmar huella mock'}
                          </button>
                        ) : null}
                        {!appointment.canManage && !appointment.canMarkPendingBiometric && !appointment.canConfirmBiometric ? (
                          <span className="table-muted">Sin cambios</span>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <DataState title="Sin citas registradas" message="El cliente aun no tiene citas asociadas." />}
      </SectionCard>

      <section className="dashboard-grid">
        <SectionCard eyebrow="Sesiones" title="Sesiones realizadas" description="Citas confirmadas con validacion biometrica.">
          {data.sessions.length ? (
            <div className="capacity-list">
              {data.sessions.map((session) => (
                <article className="capacity-item" key={session.id}>
                  <div className="capacity-item__header">
                    <div><strong>{session.operation}</strong><p>{session.dateTime} | {session.specialist}</p></div>
                    <StatusBadge tone={session.statusTone}>{session.status}</StatusBadge>
                  </div>
                </article>
              ))}
            </div>
          ) : <DataState title="Sin sesiones realizadas" message="Todavia no hay sesiones confirmadas con biometria." />}
        </SectionCard>

        <SectionCard eyebrow="Pagos" title="Pagos pendientes" description="Cuotas aun no pagadas o pendientes de completar.">
          {data.pendingQuotas.length ? (
            <div className="capacity-list">
              {data.pendingQuotas.map((quota) => (
                <article className="capacity-item" key={quota.id}>
                  <div className="capacity-item__header">
                    <div><strong>{quota.operation} | {quota.quotaLabel}</strong><p>{quota.amount} | Vence: {quota.dueDate}</p></div>
                    <StatusBadge tone={quota.statusTone}>{quota.status}</StatusBadge>
                  </div>
                </article>
              ))}
            </div>
          ) : <DataState title="Sin pagos pendientes" message="No hay cuotas pendientes para este cliente." />}
        </SectionCard>
      </section>

      <SectionCard eyebrow="Pagos" title="Pagos realizados" description="Comprobantes y pagos historicos registrados para el cliente.">
        {data.payments.length ? (
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
                </tr>
              </thead>
              <tbody>
                {data.payments.map((payment) => (
                  <tr key={payment.id}>
                    <td>{payment.operation}</td>
                    <td>{payment.quotaLabel}</td>
                    <td>{payment.amount}</td>
                    <td>{payment.submittedAt}</td>
                    <td><StatusBadge tone={payment.statusTone}>{payment.status}</StatusBadge></td>
                    <td>{payment.receiptUrl ? <a className="table-strong-link" href={payment.receiptUrl} target="_blank" rel="noreferrer">Ver</a> : 'Sin archivo'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <DataState title="Sin pagos registrados" message="El cliente aun no tiene pagos en su historial." />}
      </SectionCard>

      <SectionCard eyebrow="Tratamientos" title="Procedimientos del cliente" description="Resumen operativo de tratamientos activos e historicos.">
        {data.operations.length ? (
          <div className="capacity-list">
            {data.operations.map((operation) => (
              <article className="capacity-item" key={operation.id}>
                <div className="capacity-item__header">
                  <div>
                    <strong>{operation.procedure}</strong>
                    <p>{operation.zone} | {operation.quotaSummary}</p>
                  </div>
                  <StatusBadge tone={operation.statusTone}>{operation.status}</StatusBadge>
                </div>
                <div className="operation-card__stats">
                  <article><span>Totales</span><strong>{operation.sessions.total}</strong></article>
                  <article><span>Confirmadas</span><strong>{operation.sessions.confirmed}</strong></article>
                  <article><span>Reservadas</span><strong>{operation.sessions.reserved}</strong></article>
                  <article><span>Libres</span><strong>{operation.sessions.available}</strong></article>
                </div>
                <Link className="button button--ghost" to={`/admin/operaciones/${operation.rawId}`}>Ver operacion</Link>
              </article>
            ))}
          </div>
        ) : <DataState title="Sin procedimientos" message="No hay procedimientos asociados a este cliente." />}
      </SectionCard>
    </div>
  )
}
