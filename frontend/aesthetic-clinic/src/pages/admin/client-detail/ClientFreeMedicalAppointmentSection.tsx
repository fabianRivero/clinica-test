import { SectionCard } from '../../../components/admin/SectionCard'
import type { AdminConcurrencyCheckResponse } from '../../../types/admin'

interface ClientFreeMedicalAppointmentSectionProps {
  freeSelectedDate: string
  freeSelectedTime: string
  freeConcurrencyInfo: AdminConcurrencyCheckResponse | null
  isChecking: boolean
  isFreeBookingKey: string | null
  setFreeSelectedDate: (date: string) => void
  setFreeSelectedTime: (time: string) => void
  setFreeConcurrencyInfo: (info: AdminConcurrencyCheckResponse | null) => void
  handleCheckFreeConcurrency: () => void
  handleReserveFreeMedicalAppointment: () => void
}

export function ClientFreeMedicalAppointmentSection({
  freeSelectedDate,
  freeSelectedTime,
  freeConcurrencyInfo,
  isChecking,
  isFreeBookingKey,
  setFreeSelectedDate,
  setFreeSelectedTime,
  setFreeConcurrencyInfo,
  handleCheckFreeConcurrency,
  handleReserveFreeMedicalAppointment,
}: ClientFreeMedicalAppointmentSectionProps) {
  return (
    <section className="dashboard-grid">
      <SectionCard eyebrow="Cita medica" title="Reservar cita medica libre" description="Agenda una consulta sin asociarla a un tratamiento activo. Disponible tambien para clientes inactivos.">
        <div className="form-grid">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <label className="field">
              <span>Fecha</span>
              <input type="date" className="input" value={freeSelectedDate} onChange={e => { setFreeSelectedDate(e.target.value); setFreeConcurrencyInfo(null); }} />
            </label>
            <label className="field">
              <span>Hora de Inicio</span>
              <input type="time" className="input" value={freeSelectedTime} onChange={e => { setFreeSelectedTime(e.target.value); setFreeConcurrencyInfo(null); }} />
            </label>
          </div>
          
          <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
            <button type="button" className="button button--secondary" disabled={!freeSelectedDate || !freeSelectedTime || isChecking} onClick={() => void handleCheckFreeConcurrency()}>
              {isChecking ? 'Verificando...' : 'Verificar Disponibilidad'}
            </button>
          </div>
        </div>
      </SectionCard>

      {freeConcurrencyInfo && (
        <SectionCard title="Resultados de disponibilidad">
          <div style={{ padding: '1rem', background: 'var(--c-neutral-100)', borderRadius: '8px' }}>
            <p style={{ marginBottom: '0.5rem' }}>
              <strong>Citas simultaneas de 1 hora antes a 1 hora despues ({freeConcurrencyInfo.hora_inicio} a {freeConcurrencyInfo.hora_fin}):</strong> {freeConcurrencyInfo.concurrency}
            </p>
            <p style={{ marginBottom: '0.5rem' }}>
              <strong>Especialistas en turno {freeConcurrencyInfo.hora_seleccionada}:</strong> {freeConcurrencyInfo.presentes.length > 0 ? freeConcurrencyInfo.presentes.map(p => p.usuario__primer_nombre).join(', ') : 'Ninguno registrado'}
            </p>
            <div style={{ marginTop: '1.5rem' }}>
               <button type="button" className="button button--primary" onClick={() => void handleReserveFreeMedicalAppointment()} disabled={Boolean(isFreeBookingKey)}>
                 {isFreeBookingKey ? 'Confirmando...' : 'Confirmar Cita Medica'}
               </button>
            </div>
          </div>
        </SectionCard>
      )}
    </section>
  )
}