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

export function SpecialistPortalPage() {
  const [activeTab, setActiveTab] = useState<'AGENDA' | 'MENSAJES'>('AGENDA')
  const [selectedDate, setSelectedDate] = useState(WEEK_AVAILABILITY[0].date)
  const selectedDay = useMemo(() => WEEK_AVAILABILITY.find((item) => item.date === selectedDate) ?? WEEK_AVAILABILITY[0], [selectedDate])

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Portal de especialista"
        title="Agenda semanal y mensajeria"
        description="Interfaz operativa alineada al modelo de agenda abierta de la sucursal."
      />

      <nav className="section-tabs" aria-label="Subsecciones de especialista">
        <button className={`section-tabs__item ${activeTab === 'AGENDA' ? 'is-active' : ''}`} type="button" onClick={() => setActiveTab('AGENDA')}>
          Agenda semanal
        </button>
        <button className={`section-tabs__item ${activeTab === 'MENSAJES' ? 'is-active' : ''}`} type="button" onClick={() => setActiveTab('MENSAJES')}>
          Mensajeria interna
        </button>
      </nav>

      {activeTab === 'AGENDA' ? (
        <section className="dashboard-grid">
          <SectionCard eyebrow="Semana" title="Calendario de disponibilidad" description="Selecciona un dia para revisar horarios y excepciones.">
            <div className="capacity-list">
              {WEEK_AVAILABILITY.map((day) => {
                const active = day.date === selectedDate
                const hasShifts = day.shifts.length > 0
                return (
                  <article className="capacity-item" key={day.date}>
                    <div className="capacity-item__header">
                      <div>
                        <strong>{day.weekdayLabel}</strong>
                        <p>{day.date}</p>
                      </div>
                      <StatusBadge tone={hasShifts ? 'success' : 'warning'}>{hasShifts ? 'Con turno' : 'Sin turno'}</StatusBadge>
                    </div>
                    <button className={`button ${active ? '' : 'button--ghost'} button--compact`} type="button" onClick={() => setSelectedDate(day.date)}>
                      {active ? 'Dia seleccionado' : 'Ver detalle'}
                    </button>
                  </article>
                )
              })}
            </div>
          </SectionCard>

          <SectionCard eyebrow="Detalle diario" title={`${selectedDay.weekdayLabel} · ${selectedDay.date}`} description="La reserva la atiende cualquier especialista presente en la franja horaria.">
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
                      <td>{shift.start} - {shift.end}</td>
                      <td>{shift.source === 'HABITUAL' ? 'Agenda habitual' : 'Excepcion AGREGAR'}</td>
                      <td><StatusBadge tone="success">Disponible</StatusBadge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!selectedDay.shifts.length ? <DataState title="Sin bloques disponibles" message="No hay franjas activas para este dia." tone="warning" /> : null}
            {selectedDay.blocks.length ? (
              <div className="alert-list" style={{ marginTop: '1rem' }}>
                {selectedDay.blocks.map((block) => (
                  <article className="alert-card alert-card--warning" key={block.reason}>
                    <div>
                      <strong>Bloqueo / observacion</strong>
                      <p>{block.reason}</p>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
          </SectionCard>
        </section>
      ) : (
        <section className="dashboard-grid dashboard-grid--secondary">
          <SectionCard eyebrow="Bandeja" title="Mensajes con administracion" description="Comunicacion interna por sucursal con formato tipo correo.">
            <div className="table-card">
              <table>
                <thead>
                  <tr>
                    <th>Estado</th>
                    <th>Asunto</th>
                    <th>Remitente</th>
                    <th>Fecha</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td><StatusBadge tone="warning">Nuevo</StatusBadge></td><td>Ajuste de horarios por mantenimiento</td><td>Admin Norte</td><td>2026-05-14 09:20</td></tr>
                  <tr><td><StatusBadge tone="neutral">Leido</StatusBadge></td><td>Confirmacion de cobertura sabado</td><td>Admin Norte</td><td>2026-05-13 16:45</td></tr>
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard eyebrow="Redactar" title="Nuevo mensaje" description="Puedes adjuntar documentos e imagenes para coordinacion interna.">
            <form className="form-stack" onSubmit={(e) => e.preventDefault()}>
              <div className="form-group"><label>Para</label><input className="input" value="Administrador Sucursal Norte" readOnly /></div>
              <div className="form-group"><label>Asunto</label><input className="input" placeholder="Escribe el asunto" /></div>
              <div className="form-group"><label>Mensaje</label><textarea className="input" rows={6} placeholder="Redacta tu mensaje al administrador" /></div>
              <div className="form-group"><label>Adjuntar imagenes o documentos</label><input className="input" type="file" multiple accept="image/*,.pdf,.doc,.docx" /></div>
              <button className="button" type="submit">Enviar mensaje</button>
            </form>
          </SectionCard>
        </section>
      )}
    </div>
  )
}
