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
  data: any
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
  data,
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
              {reservableOperations.map((operation: any) => (
                <option key={operation.id} value={operation.rawId}>
                  {operation.selectLabel}
                </option>
              ))}
            </select>
          </label>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <label className="field">
              <span>Fecha</span>
              <input type="date" className="input" value={selectedDate} onChange={e => onDateChange(e.target.value)} />
            </label>
            <label className="field">
              <span>Hora de Inicio</span>
              <input type="time" className="input" value={selectedTime} onChange={e => onTimeChange(e.target.value)} />
            </label>
          </div>

          <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
            <button type="button" className="button button--secondary" disabled={!selectedDate || !selectedTime || isChecking} onClick={() => void onCheckConcurrency()}>
              {isChecking ? 'Verificando...' : 'Verificar Disponibilidad'}
            </button>
          </div>
        </div>
      </SectionCard>

      {concurrencyInfo && (
        <SectionCard title="Resultados de disponibilidad">
          <div style={{ padding: '1rem', background: 'var(--c-neutral-100)', borderRadius: '8px' }}>
            <p style={{ marginBottom: '0.5rem' }}>
              <strong>Citas simultaneas de 1 hora antes a 1 hora despues ({concurrencyInfo.hora_inicio} a {concurrencyInfo.hora_fin}):</strong> {concurrencyInfo.concurrency}
            </p>
            <p style={{ marginBottom: '0.5rem' }}>
              <strong>Especialistas en turno {concurrencyInfo.hora_seleccionada}:</strong> {concurrencyInfo.presentes.length > 0 ? concurrencyInfo.presentes.map(p => p.usuario__primer_nombre).join(', ') : 'Ninguno registrado'}
            </p>
            {concurrencyInfo.concurrency >= concurrencyInfo.presentes.length && concurrencyInfo.presentes.length > 0 && (
              <p style={{ color: 'var(--c-danger-600)', marginTop: '0.5rem', fontWeight: 600 }}>
                Aviso: Hay mas citas ({concurrencyInfo.concurrency}) que especialistas en turno ({concurrencyInfo.presentes.length}).
              </p>
            )}
            {concurrencyInfo.presentes.length === 0 && (
              <p style={{ color: 'var(--c-warning-600)', marginTop: '0.5rem', fontWeight: 600 }}>
                Aviso: No hay especialistas en turno configurados para esta sucursal a esa hora.
              </p>
            )}
            <div style={{ marginTop: '1.5rem' }}>
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