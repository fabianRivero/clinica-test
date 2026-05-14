import { useMemo, useState } from 'react'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'

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

export function SpecialistPortalPage() {
  const [activeTab, setActiveTab] = useState<'AGENDA' | 'MENSAJES'>('AGENDA')
  const [selectedDate, setSelectedDate] = useState(WEEK_AVAILABILITY[0].date)
  const selectedDay = useMemo(() => WEEK_AVAILABILITY.find((item) => item.date === selectedDate) ?? WEEK_AVAILABILITY[0], [selectedDate])

  return (
    <div className="page-stack">
      <PageHeader eyebrow="Portal de especialista" title="Agenda abierta y comunicacion de sucursal" description="Consulta tu disponibilidad semanal y comunicate con administracion en formato tipo correo." />
      <div className="section-tabs" aria-label="Pestañas especialista">
        <button className={`section-tabs__item ${activeTab === 'AGENDA' ? 'is-active' : ''}`} type="button" onClick={() => setActiveTab('AGENDA')}>Agenda semanal</button>
        <button className={`section-tabs__item ${activeTab === 'MENSAJES' ? 'is-active' : ''}`} type="button" onClick={() => setActiveTab('MENSAJES')}>Mensajes a administracion</button>
      </div>
      {activeTab === 'AGENDA' ? (
        <div className="dashboard-grid" style={{ gridTemplateColumns: '1fr 1.4fr' }}>
          <SectionCard title="Calendario semanal" description="Selecciona un dia para ver detalle de disponibilidad.">
            <div className="form-stack">
              {WEEK_AVAILABILITY.map((day) => <button key={day.date} type="button" className={`button ${day.date === selectedDate ? '' : 'button--ghost'}`} onClick={() => setSelectedDate(day.date)}>{day.weekdayLabel} · {day.date}</button>)}
            </div>
          </SectionCard>
          <SectionCard title={`Disponibilidad del ${selectedDay.weekdayLabel}`} description="La agenda es abierta: las reservas se atienden por cualquier especialista disponible en turno.">
            <p><strong>Sucursal:</strong> {selectedDay.branch}</p>
            <h4>Bloques disponibles</h4>
            {selectedDay.shifts.length ? <ul>{selectedDay.shifts.map((shift) => <li key={`${shift.start}-${shift.end}`}>{shift.start} - {shift.end} ({shift.source === 'HABITUAL' ? 'Agenda habitual' : 'Excepcion AGREGAR'})</li>)}</ul> : <p>No hay bloques de disponibilidad para este dia.</p>}
            <h4>Bloqueos / observaciones</h4>
            {selectedDay.blocks.length ? <ul>{selectedDay.blocks.map((block) => <li key={block.reason}>{block.reason}</li>)}</ul> : <p>Sin bloqueos registrados.</p>}
          </SectionCard>
        </div>
      ) : (
        <div className="dashboard-grid" style={{ gridTemplateColumns: '1fr 1.2fr' }}>
          <SectionCard title="Bandeja" description="Conversaciones con administracion de tu sucursal.">
            <ul>
              <li><strong>[NUEVO]</strong> Ajuste de horarios por mantenimiento (Admin Norte)</li>
              <li>Confirmacion de cobertura de turno sabado (Admin Norte)</li>
              <li>Solicitud de respaldo de documento clinico (Admin Norte)</li>
            </ul>
          </SectionCard>
          <SectionCard title="Nuevo mensaje" description="Formato tipo correo con adjuntos.">
            <form className="form-stack" onSubmit={(e) => e.preventDefault()}>
              <div className="form-group"><label>Para</label><input className="input" value="Administrador Sucursal Norte" readOnly /></div>
              <div className="form-group"><label>Asunto</label><input className="input" placeholder="Escribe el asunto" /></div>
              <div className="form-group"><label>Mensaje</label><textarea className="input" rows={6} placeholder="Redacta tu mensaje al administrador" /></div>
              <div className="form-group"><label>Adjuntar imagenes o documentos</label><input className="input" type="file" multiple accept="image/*,.pdf,.doc,.docx" /></div>
              <button className="button" type="submit">Enviar mensaje</button>
            </form>
          </SectionCard>
        </div>
      )}
    </div>
  )
}
