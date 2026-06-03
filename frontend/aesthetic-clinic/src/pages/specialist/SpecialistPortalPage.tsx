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

export function SpecialistPortalPage() {
  const [activeTab, setActiveTab] = useState<'AGENDA' | 'MENSAJES'>('AGENDA')
  const { loading, availability, error, refetch } = useSpecialistAvailability()

  const days = useMemo(() => availability?.days ?? [], [availability?.days])

  const today = new Date().toISOString().split('T')[0]
  const [selectedDate, setSelectedDate] = useState<string>(today)

  const selectedDay = useMemo((): DayAvailability | null => {
    if (!days.length) return null
    return days.find((item) => item.date === selectedDate) ?? days[0] ?? null
  }, [days, selectedDate])

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
        <>
          {loading ? (
            <Spinner />
          ) : null}

          {!loading && (!availability || (days.length > 0 && days.every((day) => day.shifts.length === 0 && day.blocks.length === 0))) ? (
            <DataState
              title="Sin agenda configurada"
              message="Contacta al administrador para configurar tu disponibilidad."
              tone="warning"
            />
          ) : null}

          {!loading && error && !availability ? (
            <DataState
              title="Error"
              message={error}
              tone="danger"
            />
          ) : null}

          {!loading && error && !availability ? (
            <div style={{ textAlign: 'center', marginTop: '1rem' }}>
              <button className="button" type="button" onClick={refetch}>
                Reintentar
              </button>
            </div>
          ) : null}

          {!loading && availability && days.length > 0 && !days.every((day) => day.shifts.length === 0 && day.blocks.length === 0) ? (
            <section className="dashboard-grid">
              <SectionCard eyebrow="Semana" title="Calendario de disponibilidad" description="Selecciona un dia para revisar horarios y excepciones.">
                <div className="capacity-list">
                  {days.map((day) => {
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

              <SectionCard eyebrow="Detalle diario" title={`${selectedDay?.weekdayLabel ?? ''} · ${selectedDay?.date ?? ''}`} description="Tu disponibilidad para este dia.">
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
                      {selectedDay?.shifts.map((shift) => (
                        <tr key={`${shift.start}-${shift.end}`}>
                          <td>{shift.start} - {shift.end}</td>
                          <td>{shift.source === 'HABITUAL' ? 'Agenda habitual' : 'Excepcion'}</td>
                          <td><StatusBadge tone="success">Disponible</StatusBadge></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!selectedDay?.shifts.length && selectedDay ? <DataState title="Sin bloques disponibles" message="No hay franjas activas para este dia." tone="warning" /> : null}
                {selectedDay?.blocks.length && selectedDay ? (
                  <div className="alert-list _mt-md">
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
          ) : null}
        </>
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