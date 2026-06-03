import { useMemo, useState } from 'react'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useSpecialistAvailability } from '../../hooks/useSpecialistAvailability'
import type { DayAvailability } from '../../types/worker'

function Spinner() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
      <span className="status-badge status-badge--primary">Cargando...</span>
    </div>
  )
}

export function SpecialistAgendaPage() {
  const { loading, availability, error, refetch } = useSpecialistAvailability()

  const days = useMemo(() => availability?.days ?? [], [availability?.days])

  // Default selectedDate to today or first day of the week
  const today = new Date().toISOString().split('T')[0]
  const [selectedDate, setSelectedDate] = useState<string>(today)

  const selectedDay = useMemo((): DayAvailability | null => {
    if (!days.length) return null
    return days.find((item) => item.date === selectedDate) ?? days[0] ?? null
  }, [days, selectedDate])

  if (loading) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Portal de especialista"
          title="Agenda semanal"
          description="Selecciona un dia y revisa la disponibilidad publicada para tus turnos."
        />
        <Spinner />
      </div>
    )
  }

  // Empty state — no shifts and no blocks in all days
  const isEmptyState =
    !!availability &&
    days.length > 0 &&
    days.every((day) => day.shifts.length === 0 && day.blocks.length === 0)

  if (!availability || isEmptyState) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Portal de especialista"
          title="Agenda semanal"
          description="Selecciona un dia y revisa la disponibilidad publicada para tus turnos."
        />
        <DataState
          title="Sin agenda configurada"
          message="Contacta al administrador para configurar tu disponibilidad."
          tone="warning"
        />
      </div>
    )
  }

  if (error && !availability) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Portal de especialista"
          title="Agenda semanal"
          description="Selecciona un dia y revisa la disponibilidad publicada para tus turnos."
        />
        <DataState
          title="Error"
          message={error}
          tone="danger"
        />
        <div style={{ textAlign: 'center', marginTop: '1rem' }}>
          <button className="button" type="button" onClick={refetch}>
            Reintentar
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Portal de especialista"
        title="Agenda semanal"
        description="Selecciona un dia y revisa la disponibilidad publicada para tus turnos."
      />

      <SectionCard
        eyebrow="Semana"
        title="Selector de dias"
        description="Selecciona un dia de la semana."
      >
        <div className="_flex-row _gap-sm" style={{ overflowX: 'auto', paddingBottom: '0.5rem' }}>
          {days.map((day) => {
            const isActive = day.date === selectedDate
            const hasShifts = day.shifts.length > 0
            return (
              <button
                key={day.date}
                className={`button ${isActive ? '' : 'button--ghost'} button--compact`}
                style={{ minWidth: '6rem', padding: '0.45rem 0.75rem', fontSize: '0.8rem', display: 'grid', gap: '0.3rem', justifyItems: 'center', flexShrink: 0 }}
                type="button"
                onClick={() => setSelectedDate(day.date)}
              >
                <span className="_leading-tight">{day.weekdayLabel}</span>
                <StatusBadge tone={hasShifts ? 'success' : 'warning'}>
                  {hasShifts ? 'Con turno' : 'Sin turno'}
                </StatusBadge>
              </button>
            )
          })}
        </div>
      </SectionCard>

      {selectedDay ? (
        <SectionCard
          eyebrow="Detalle diario"
          title={`${selectedDay.weekdayLabel} · ${selectedDay.date}`}
          description="Agenda del dia"
        >
          <div className="table-card">
            <table>
              <thead>
                <tr>
                  <th>Bloque horario</th>
                  <th>Origen</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {selectedDay.shifts.map((shift) => (
                  <tr key={`${shift.start}-${shift.end}`}>
                    <td>
                      {shift.start} - {shift.end}
                    </td>
                    <td>{shift.source === 'HABITUAL' ? 'Agenda habitual' : 'Excepcion'}</td>
                    <td>
                      <StatusBadge tone="success">Disponible</StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!selectedDay.shifts.length ? (
            <DataState
              title="Sin bloques disponibles"
              message="No hay franjas activas para este dia."
              tone="warning"
            />
          ) : null}
        </SectionCard>
      ) : null}
    </div>
  )
}