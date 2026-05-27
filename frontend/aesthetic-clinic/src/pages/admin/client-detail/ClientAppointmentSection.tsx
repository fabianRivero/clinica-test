import { verificationStatusLabel } from '../../../constants/verification'
import { StatusBadge } from '../../../components/admin/StatusBadge'
import { DataState } from '../../../components/admin/DataState'
import { SectionCard } from '../../../components/admin/SectionCard'
import type { AdminConcurrencyCheckResponse } from '../../../types/admin'

interface ClientAppointmentSectionProps {
  appointments: any[]
  appointmentActionId: number | null
  rescheduleAppointmentId: number | null
  rescheduleDate: string
  rescheduleTime: string
  rescheduleCheck: AdminConcurrencyCheckResponse | null
  isCheckingReschedule: boolean
  onCancelAppointment: (id: number) => void
  onMarkPendingBiometric: (id: number) => void
  onConfirmBiometric: (id: number, template: string) => void
  onSetRescheduleAppointment: (id: number) => void
  onRescheduleDateChange: (value: string) => void
  onRescheduleTimeChange: (value: string) => void
  onCheckRescheduleAvailability: () => void
  onRescheduleAppointment: () => void
  onCancelReschedule: () => void
}

export function ClientAppointmentSection({
  appointments,
  appointmentActionId,
  rescheduleAppointmentId,
  rescheduleDate,
  rescheduleTime,
  rescheduleCheck,
  isCheckingReschedule,
  onCancelAppointment,
  onMarkPendingBiometric,
  onConfirmBiometric,
  onSetRescheduleAppointment,
  onRescheduleDateChange,
  onRescheduleTimeChange,
  onCheckRescheduleAvailability,
  onRescheduleAppointment,
  onCancelReschedule,
}: ClientAppointmentSectionProps) {
  return (
    <SectionCard eyebrow="Agenda" title="Todas las citas del cliente" description="Historial completo de reservas, sesiones realizadas, cancelaciones y pendientes de verificacion.">
      {appointments.length ? (
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>Operacion</th>
                <th>Especialista</th>
                <th>Fecha</th>
                <th>Estado</th>
                <th>Verificacion</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {appointments.map((appointment) => (
                <tr key={appointment.id}>
                  <td><strong>{appointment.operation}</strong><span>{appointment.details}</span></td>
                  <td>{appointment.specialist}</td>
                  <td>{appointment.dateTime}</td>
                  <td><StatusBadge tone={appointment.statusTone}>{appointment.status}</StatusBadge></td>
                  <td>{verificationStatusLabel[appointment.verificationStatus]}</td>
                  <td>
                    <div className="table-action-list">
                      {appointment.canMarkPendingBiometric ? (
                        <button
                          className="button button--ghost button--compact"
                          disabled={appointmentActionId !== null}
                          type="button"
                          onClick={() => void onMarkPendingBiometric(appointment.rawId)}
                        >
                          {appointmentActionId === appointment.rawId ? 'Actualizando...' : 'Cambiar a pendiente de verificacion'}
                        </button>
                      ) : null}
                      {['programada', 'no asistio'].includes(appointment.status?.toLowerCase?.() ?? '') ? (
                        <button
                          className="button button--ghost button--compact"
                          disabled={appointmentActionId !== null}
                          type="button"
                          onClick={() => onSetRescheduleAppointment(appointment.rawId)}
                        >
                          Reprogramar reserva
                        </button>
                      ) : null}
                      {appointment.canManage ? (
                        <button
                          className="button button--ghost button--compact"
                          disabled={appointmentActionId !== null}
                          type="button"
                          onClick={() => void onCancelAppointment(appointment.rawId)}
                        >
                          Cancelar reserva
                        </button>
                      ) : null}
                      {appointment.canConfirmBiometric ? (
                        <button
                          className="button button--ghost button--compact"
                          disabled={appointmentActionId !== null}
                          type="button"
                          onClick={() => void onConfirmBiometric(appointment.rawId, appointment.biometricMockTemplate)}
                        >
                          {appointmentActionId === appointment.rawId ? 'Validando...' : 'Confirmar huella mock'}
                        </button>
                      ) : null}
                      {!appointment.canManage && !appointment.canMarkPendingBiometric && !appointment.canConfirmBiometric ? (
                        <span className="table-muted">Sin cambios</span>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <DataState title="Sin citas registradas" message="El cliente aun no tiene citas asociadas." />}
      {rescheduleAppointmentId ? (
        <div style={{ marginTop: '1rem', padding: '1rem', background: 'var(--c-neutral-100)', borderRadius: '8px' }}>
          <p style={{ marginBottom: '1rem' }}><strong>Reprogramar cita seleccionada</strong></p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <label className="field">
              <span>Nueva fecha</span>
              <input type="date" className="input" value={rescheduleDate} onChange={(e) => { onRescheduleDateChange(e.target.value) }} />
            </label>
            <label className="field">
              <span>Nueva hora</span>
              <input type="time" className="input" value={rescheduleTime} onChange={(e) => { onRescheduleTimeChange(e.target.value) }} />
            </label>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
            <button type="button" className="button button--secondary" disabled={!rescheduleDate || !rescheduleTime || isCheckingReschedule} onClick={() => void onCheckRescheduleAvailability()}>
              {isCheckingReschedule ? 'Verificando...' : 'Verificar disponibilidad'}
            </button>
            <button type="button" className="button button--primary" disabled={!rescheduleCheck || appointmentActionId !== null} onClick={() => void onRescheduleAppointment()}>
              {appointmentActionId === rescheduleAppointmentId ? 'Confirmando...' : 'Confirmar reprogramacion en esta hora'}
            </button>
            <button type="button" className="button button--ghost" onClick={onCancelReschedule}>
              Cancelar
            </button>
          </div>
          {rescheduleCheck ? (
            <p style={{ marginTop: '0.75rem' }}>
              Citas simultaneas de 1 hora antes a 1 hora despues ({rescheduleCheck.hora_inicio} a {rescheduleCheck.hora_fin}): {rescheduleCheck.concurrency}. Especialistas en turno {rescheduleCheck.hora_seleccionada}: {rescheduleCheck.presentes.length > 0 ? rescheduleCheck.presentes.map((p) => p.usuario__primer_nombre).join(', ') : 'Ninguno registrado'}.
            </p>
          ) : null}
        </div>
      ) : null}
    </SectionCard>
  )
}