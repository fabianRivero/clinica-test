import type { AdminConcurrencyCheckResponse } from '../../../types/admin'
import { SectionCard } from '../../../components/admin/SectionCard'
import { DataState } from '../../../components/admin/DataState'

interface ClientReservationSectionProps {
  effectiveOperationId: number | ''
  reservableOperations: any[]
  selectedDate: string
  selectedTime: string
  concurrencyInfo: AdminConcurrencyCheckResponse | null
  isChecking: boolean
  isBookingKey: string | null
  onOperationChange: (value: number) => void
  onDateChange: (value: string) => void
  onTimeChange: (value: string) => void
  onCheckConcurrency: () => void
  onReserve: () => void
}

export function ClientReservationSection({
  effectiveOperationId,
  reservableOperations,
  selectedDate,
  selectedTime,
  concurrencyInfo,
  isChecking,
  isBookingKey,
  onOperationChange,
  onDateChange,
  onTimeChange,
  onCheckConcurrency,
  onReserve,
}: ClientReservationSectionProps) {
  if (!reservableOperations.length) {
    return (
      <SectionCard eyebrow="Reservas" title="Hacer reserva para este cliente" description="Agendar hora libre (Agenda abierta).">
        <DataState title="Sin procedimientos en proceso" message="Este cliente no tiene tratamientos activos para nuevas reservas." />
      </SectionCard>
    )
  }

  return (
    <>
      <SectionCard eyebrow="Reservas" title="Hacer reserva para este cliente" description="Agendar hora libre (Agenda abierta).">
        <div className="form-grid">
          <label className="field field--full">
            <span>Procedimiento</span>
            <select className="input" value={effectiveOperationId} onChange={(event) => onOperationChange(Number(event.target.value))}>
              <option value="">Elegir procedimiento...</option>
              {reservableOperations.map((operation: any) => (
                <option key={operation.id} value={operation.rawId}>
                  {operation.selectLabel}
                </option>
              ))}
            </select>
          </label>

          <div className="_grid-2cols">
            <label className="field">
              <span>Fecha</span>
              <input type="date" className="input" value={selectedDate} onChange={e => onDateChange(e.target.value)} />
            </label>
            <label className="field">
              <span>Hora de Inicio</span>
              <input type="time" className="input" value={selectedTime} onChange={e => onTimeChange(e.target.value)} />
            </label>
          </div>

          <div className="_mt-md _flex-gap-sm">
            <button type="button" className="button button--secondary" disabled={!selectedDate || !selectedTime || isChecking} onClick={() => void onCheckConcurrency()}>
              {isChecking ? 'Verificando...' : 'Verificar Disponibilidad'}
            </button>
          </div>
        </div>
      </SectionCard>

      {concurrencyInfo && (
        <SectionCard title="Resultados de disponibilidad">
          <div className="_panel-card">
            <p className="_mb-sm">
              <strong>Citas simultáneas de 1 hora antes a 1 hora después ({concurrencyInfo.hora_inicio} a {concurrencyInfo.hora_fin}):</strong> {concurrencyInfo.concurrency}
            </p>

            {concurrencyInfo.appointments && concurrencyInfo.appointments.length > 0 ? (
              <div style={{ marginTop: '0.75rem', paddingLeft: '0.5rem', borderLeft: '2px solid var(--color-border)' }}>
                <ul style={{ fontSize: '0.82rem', color: 'var(--color-text-soft)', paddingLeft: '1.2rem', margin: 0 }}>
                  {concurrencyInfo.appointments.map((apt, idx) => (
                    <li key={idx} style={{ marginBottom: '0.3rem' }}>
                      <span style={{ fontWeight: 500 }}>{apt.cliente_nombre ?? 'Cliente no registrado'}</span>
                      {' — '}
                      {apt.tratamiento_nombre ?? 'Sin tratamiento'}
                      {' — '}
                      {new Date(apt.hora).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p style={{ fontSize: '0.85rem', color: 'var(--color-text-soft)', marginTop: '0.5rem' }}>Sin citas simultáneas</p>
            )}
            <p className="_mb-sm">
              <strong>Especialistas en turno {concurrencyInfo.hora_seleccionada}:</strong> {concurrencyInfo.presentes.length > 0 ? concurrencyInfo.presentes.map(p => `${p.usuario__primer_nombre} ${p.usuario__apellido_paterno}`).join(', ') : 'Ninguno registrado'}
            </p>
            {concurrencyInfo.concurrency >= concurrencyInfo.presentes.length && concurrencyInfo.presentes.length > 0 && (
              <p className="_text-danger _mt-sm _font-bold">
                Aviso: Hay más citas ({concurrencyInfo.concurrency}) que especialistas en turno ({concurrencyInfo.presentes.length}).
              </p>
            )}
            {concurrencyInfo.presentes.length === 0 && (
              <p className="_text-warning _mt-sm _font-bold">
                Aviso: No hay especialistas en turno configurados para esta sucursal a esa hora.
              </p>
            )}
            <div className="_mt-lg">
              <button type="button" className="button button--primary" onClick={() => void onReserve()} disabled={Boolean(isBookingKey)}>
                {isBookingKey ? 'Confirmando...' : 'Confirmar Reserva en esta Hora'}
              </button>
            </div>
          </div>
        </SectionCard>
      )}
    </>
  )
}