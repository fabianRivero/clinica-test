import type { AdminConcurrencyCheckResponse } from '../../../types/admin'

interface RescheduleModalProps {
  isOpen: boolean
  onClose: () => void
  session: {
    id: string
    operation: string
    dateTime: string
    zona: string
  } | null
  rescheduleDate: string
  setRescheduleDate: (value: string) => void
  rescheduleTime: string
  setRescheduleTime: (value: string) => void
  concurrencyInfo: AdminConcurrencyCheckResponse | null
  isChecking: boolean
  onCheckAvailability: () => void
  onConfirm: () => void
  isBookingKey: string | null
}

export function RescheduleModal({
  isOpen,
  onClose,
  session,
  rescheduleDate,
  setRescheduleDate,
  rescheduleTime,
  setRescheduleTime,
  concurrencyInfo,
  isChecking,
  onCheckAvailability,
  onConfirm,
  isBookingKey,
}: RescheduleModalProps) {
  if (!isOpen || !session) return null

  return (
    <div className="booking-modal-overlay" onClick={onClose}>
      <div className="booking-modal-content" onClick={(e) => e.stopPropagation()}>
        <header className="booking-modal-header">
          <h2>Reprogramar cita</h2>
          <button type="button" className="booking-modal-close" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="booking-modal-body">
          <div className="_panel-card _mb-md">
            <p><strong>Procedimiento:</strong> {session.operation}</p>
            <p><strong>Fecha actual:</strong> {session.dateTime}</p>
            <p><strong>Zona:</strong> {session.zona}</p>
          </div>

          <div className="form-grid">
            <div className="_grid-2cols">
              <label className="field">
                <span>Fecha</span>
                <input
                  type="date"
                  className="input"
                  value={rescheduleDate}
                  onChange={(e) => setRescheduleDate(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Hora</span>
                <input
                  type="time"
                  className="input"
                  value={rescheduleTime}
                  onChange={(e) => setRescheduleTime(e.target.value)}
                />
              </label>
            </div>

            <div className="_mt-md _flex-gap-sm">
              <button
                type="button"
                className="button button--secondary"
                disabled={!rescheduleDate || !rescheduleTime || isChecking}
                onClick={() => void onCheckAvailability()}
              >
                {isChecking ? 'Verificando...' : 'Verificar Disponibilidad'}
              </button>
            </div>
          </div>

          {concurrencyInfo && (
            <div className="_mt-md">
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
                  <button type="button" className="button button--primary" onClick={() => void onConfirm()} disabled={Boolean(isBookingKey)}>
                    {isBookingKey ? 'Confirmando...' : 'Confirmar Reserva en esta Hora'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
