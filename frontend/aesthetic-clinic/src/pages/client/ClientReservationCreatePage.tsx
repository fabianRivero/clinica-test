import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import {
  createClientReservation,
  getClientReservationAvailability,
} from '../../services/api/client'
import type { ClientReservationAvailabilityResponse } from '../../types/client'

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
      date: current,
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

export function ClientReservationCreatePage() {
  const navigate = useNavigate()
  const { operationId = '' } = useParams()

  const [data, setData] = useState<ClientReservationAvailabilityResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedDate, setSelectedDate] = useState<string>('')
  const [visibleMonth, setVisibleMonth] = useState<Date>(monthStart(new Date()))
  const [isBookingKey, setIsBookingKey] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadAvailability() {
      setIsLoading(true)
      setError(null)
      try {
        const response = await getClientReservationAvailability(operationId)
        if (cancelled) return
        setData(response)
        const firstAvailableDate = response.calendar.availableDates[0]?.date ?? ''
        setSelectedDate(firstAvailableDate)
        const monthSeed = firstAvailableDate ? new Date(`${firstAvailableDate}T00:00:00`) : new Date()
        setVisibleMonth(monthStart(monthSeed))
      } catch (requestError) {
        if (!cancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : 'No se pudo cargar la disponibilidad de reservas.',
          )
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    void loadAvailability()
    return () => {
      cancelled = true
    }
  }, [operationId])

  const availableDateSet = useMemo(
    () => new Set(data?.calendar.availableDates.map((item) => item.date) ?? []),
    [data],
  )

  const calendarDays = useMemo(() => buildCalendarGrid(visibleMonth), [visibleMonth])
  const selectedSlots = data?.calendar.slotsByDate[selectedDate] ?? []
  const minMonth = data?.calendar.windowStart
    ? monthStart(new Date(`${data.calendar.windowStart}T00:00:00`))
    : null
  const maxMonth = data?.calendar.windowEnd
    ? monthStart(new Date(`${data.calendar.windowEnd}T00:00:00`))
    : null

  const canGoPreviousMonth = minMonth ? visibleMonth.getTime() > minMonth.getTime() : false
  const canGoNextMonth = maxMonth ? visibleMonth.getTime() < maxMonth.getTime() : false

  async function handleReserve(slotId: number) {
    if (!data) return
    setSubmitError(null)
    const selectedSlot = Object.values(data.calendar.slotsByDate)
      .flat()
      .find((item) => item.slotId === slotId)
    const bookingKey = selectedSlot ? `${selectedSlot.date}-${selectedSlot.time}-${selectedSlot.specialistId}` : `slot-${slotId}`
    setIsBookingKey(bookingKey)

    try {
      const response = await createClientReservation(operationId, { slotId })
      navigate('/cliente/reservas', {
        replace: true,
        state: {
          flashMessage: `${response.detail} ${response.appointment.operation} - ${response.appointment.dateTime}`,
        },
      })
    } catch (requestError) {
      setSubmitError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo registrar la reserva.',
      )
      setIsBookingKey(null)
    }
  }

  if (isLoading) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Nueva reserva"
          title="Preparando calendario"
          description="Estamos consultando dias disponibles y horarios libres para tu tratamiento."
          actions={[{ label: 'Volver a reservas', variant: 'ghost', to: '/cliente/reservas' }]}
        />
        <SectionCard title="Cargando disponibilidad">
          <DataState
            title="Buscando espacios"
            message="Consultando los horarios que administracion ya publico para tu tratamiento."
          />
        </SectionCard>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Nueva reserva"
          title="No pudimos cargar el calendario"
          description="Puede que el tratamiento ya no tenga cupo o que el horario disponible haya cambiado."
          actions={[{ label: 'Volver a reservas', variant: 'ghost', to: '/cliente/reservas' }]}
        />
        <SectionCard title="Calendario no disponible">
          <DataState
            title="No disponible"
            message={error || 'No encontramos disponibilidad para esta operacion.'}
            tone="danger"
          />
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Nueva reserva"
        title={`Reservar cita para ${data.operation.procedure}`}
        description="Selecciona un dia destacado en el calendario y luego confirma uno de los horarios disponibles."
        actions={[{ label: 'Volver a reservas', variant: 'ghost', to: '/cliente/reservas' }]}
      />

      <section className="client-summary-card">
        <div>
          <span className="client-summary-card__eyebrow">{data.operation.serviceType}</span>
          <h2>{data.operation.procedure}</h2>
          <p>
            Zona: {data.operation.zone} | Especialista habitual: {data.operation.specialist}
          </p>
        </div>

        <div className="client-summary-card__grid">
          <article>
            <span>Sesiones libres</span>
            <strong>{data.operation.sessions.available}</strong>
          </article>
          <article>
            <span>Horarios publicados</span>
            <strong>{data.calendar.slotCount}</strong>
          </article>
        </div>
      </section>

      {submitError ? (
        <DataState
          title="No pudimos confirmar la reserva"
          message={submitError}
          tone="danger"
        />
      ) : null}

      <section className="dashboard-grid">
        <SectionCard
          eyebrow="Calendario"
          title="Dias disponibles"
          description="Los dias resaltados tienen al menos un horario publicado por administracion y aun libre para reservar."
        >
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
              {WEEKDAY_LABELS.map((label) => (
                <span key={label}>{label}</span>
              ))}
            </div>

            <div className="reservation-calendar__grid">
              {calendarDays.map((day) => {
                const isAvailable = availableDateSet.has(day.key)
                const isSelected = selectedDate === day.key
                const isOutOfMonth = !day.inCurrentMonth
                return (
                  <button
                    key={day.key}
                    className={`reservation-calendar__day ${
                      isAvailable ? 'is-available' : ''
                    } ${isSelected ? 'is-selected' : ''} ${
                      isOutOfMonth ? 'is-outside' : ''
                    }`}
                    type="button"
                    onClick={() => setSelectedDate(day.key)}
                  >
                    <span>{day.dayNumber}</span>
                    {isAvailable ? (
                      <small>
                        {data.calendar.availableDates.find((item) => item.date === day.key)?.slotCount ?? 0}{' '}
                        cupos
                      </small>
                    ) : null}
                  </button>
                )
              })}
            </div>
          </div>
        </SectionCard>

        <SectionCard
          eyebrow="Horarios"
          title={selectedDate ? `Disponibilidad para ${longDateLabel(selectedDate)}` : 'Selecciona un dia'}
          description="Cada tarjeta representa un horario libre. Al confirmar, la cita quedara registrada como programada."
        >
          {selectedDate ? (
            selectedSlots.length ? (
              <div className="reservation-slot-list">
                {selectedSlots.map((slot) => {
                  const bookingKey = `${slot.date}-${slot.time}-${slot.specialistId}`
                  const isBooking = isBookingKey === bookingKey

                  return (
                    <article className="reservation-slot-card" key={bookingKey}>
                      <div>
                        <strong>{slot.time}</strong>
                        <p>{slot.specialist}</p>
                        <span>{slot.dateTimeLabel}</span>
                      </div>
                      <button
                        className="button"
                        disabled={Boolean(isBookingKey)}
                        type="button"
                        onClick={() => handleReserve(slot.slotId)}
                      >
                        {isBooking ? 'Reservando...' : 'Confirmar reserva'}
                      </button>
                    </article>
                  )
                })}
              </div>
            ) : (
              <DataState
                title="Sin horarios en este dia"
                message="Ese dia no tiene espacios libres. Prueba con una fecha resaltada en el calendario."
              />
            )
          ) : (
            <DataState
              title="Selecciona un dia"
              message="Haz clic en un dia del calendario para ver la lista de horarios disponibles."
            />
          )}
        </SectionCard>
      </section>

      <SectionCard
        eyebrow="Estado actual"
        title="Resumen del tratamiento"
        description="Asi se calcula tu capacidad real antes de habilitar nuevas reservas."
      >
        <div className="operation-card__stats">
          <article>
            <span>Confirmadas</span>
            <strong>{data.operation.sessions.confirmed}</strong>
          </article>
          <article>
            <span>Pend. biometria</span>
            <strong>{data.operation.sessions.pendingBiometric}</strong>
          </article>
          <article>
            <span>Reservadas</span>
            <strong>{data.operation.sessions.reserved}</strong>
          </article>
          <article>
            <span>Libres</span>
            <strong>{data.operation.sessions.available}</strong>
          </article>
        </div>
        <div className="client-inline-meta">
          <StatusBadge tone={data.operation.canReserve ? 'success' : 'warning'}>
            {data.operation.canReserve ? 'Con cupo' : 'Sin cupo'}
          </StatusBadge>
          <span>{data.operation.reserveMessage}</span>
        </div>
      </SectionCard>
    </div>
  )
}
