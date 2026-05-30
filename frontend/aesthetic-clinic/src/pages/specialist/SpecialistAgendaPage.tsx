import { useMemo, useState } from 'react'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'

type WeekdayAvailability = {
  date: string
  weekdayLabel: string
  branch: string
  shifts: Array<{ start: string; end: string; source: 'HABITUAL' | 'EXCEPCION' }>
  blocks: Array<{ reason: string }>
}

const WEEK_AVAILABILITY: WeekdayAvailability[] = [
  { date: '2026-05-18', weekdayLabel: 'Lunes', branch: 'Sucursal Norte', shifts: [{ start: '08:00', end: '14:00', source: 'HABITUAL' }], blocks: [] },
  { date: '2026-05-19', weekdayLabel: 'Martes', branch: 'Sucursal Norte', shifts: [{ start: '10:00', end: '18:00', source: 'HABITUAL' }], blocks: [] },
  { date: '2026-05-20', weekdayLabel: 'Miercoles', branch: 'Sucursal Norte', shifts: [{ start: '08:00', end: '12:00', source: 'HABITUAL' }, { start: '15:00', end: '18:00', source: 'EXCEPCION' }], blocks: [] },
  { date: '2026-05-21', weekdayLabel: 'Jueves', branch: 'Sucursal Norte', shifts: [], blocks: [{ reason: 'Bloqueo por capacitacion interna (todo el dia)' }] },
  { date: '2026-05-22', weekdayLabel: 'Viernes', branch: 'Sucursal Norte', shifts: [{ start: '09:00', end: '17:00', source: 'HABITUAL' }], blocks: [] },
  { date: '2026-05-23', weekdayLabel: 'Sabado', branch: 'Sucursal Norte', shifts: [{ start: '09:00', end: '13:00', source: 'HABITUAL' }], blocks: [] },
  { date: '2026-05-24', weekdayLabel: 'Domingo', branch: 'Sucursal Norte', shifts: [], blocks: [{ reason: 'Sin agenda configurada' }] },
]

export function SpecialistAgendaPage() {
  const [selectedDate, setSelectedDate] = useState(WEEK_AVAILABILITY[0].date)
  const selectedDay = useMemo(
    () => WEEK_AVAILABILITY.find((item) => item.date === selectedDate) ?? WEEK_AVAILABILITY[0],
    [selectedDate],
  )

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
        description="Selecciona un dia de la semana; los botones se distribuyen uniformemente en el contenedor."
      >
        <div className="_grid-7col _gap-sm">
          {WEEK_AVAILABILITY.map((day) => {
            const isActive = day.date === selectedDate
            const hasShifts = day.shifts.length > 0
            return (
              <button
                key={day.date}
                className={`button ${isActive ? '' : 'button--ghost'} button--compact`}
                style={{ width: '100%', minWidth: 0, padding: '0.45rem 0.5rem', fontSize: '0.8rem', display: 'grid', gap: '0.3rem', justifyItems: 'center' }}
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

      <SectionCard
        eyebrow="Detalle diario"
        title={`${selectedDay.weekdayLabel} · ${selectedDay.date}`}
        description="Modelo de agenda abierta: atiende quien este disponible en la franja."
      >
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>Sucursal</th>
                <th>Bloque</th>
                <th>Origen</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {selectedDay.shifts.map((shift) => (
                <tr key={`${shift.start}-${shift.end}`}>
                  <td>{selectedDay.branch}</td>
                  <td>
                    {shift.start} - {shift.end}
                  </td>
                  <td>{shift.source === 'HABITUAL' ? 'Agenda habitual' : 'Excepcion AGREGAR'}</td>
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
    </div>
  )
}
