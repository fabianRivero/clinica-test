import { useState } from 'react'

import { verificationStatusLabel } from '../../../constants/verification'
import { StatusBadge } from '../../../components/admin/StatusBadge'
import { DataState } from '../../../components/admin/DataState'
import { SectionCard } from '../../../components/admin/SectionCard'
import { AdminRegisterAppointmentPaymentModal } from '../../../components/admin/AdminRegisterAppointmentPaymentModal'
import { useNotifications } from '../../../providers/NotificationProvider'
import {
  registerAdminAppointmentPayment,
  registerAdminFreeAppointmentPayment,
} from '../../../services/api/admin'
import type {
  AdminAppointment,
  AdminConcurrencyCheckResponse,
  RegisterAdminAppointmentPaymentPayload,
} from '../../../types/admin'
import type { ClientAppointment } from '../../../types/common'

interface ClientAppointmentSectionProps {
  // Pagination & Navigation
  visibleAppointments: ClientAppointment[]
  appointmentMonth: number
  appointmentYear: number
  changeAppointmentMonth: (direction: -1 | 1) => void
  viewedMonthLabel: string
  // Propagated by the parent (which reads `isBiometricSuspended()`
  // once). Keeps this component free of build-flag plumbing.
  biometricSuspended: boolean
  // Filter
  appointmentStatusFilter: string
  setAppointmentStatusFilter: (value: string) => void
  appointmentStatuses: string[]
  // Pagination state
  visibleAppointmentCount: number
  setVisibleAppointmentCount: (value: number | ((prev: number) => number)) => void
  filteredAppointmentsLength: number
  hasMore: boolean
  hasLess: boolean
  // Existing props
  appointmentActionId: number | null
  rescheduleAppointmentId: number | null
  rescheduleDate: string
  rescheduleTime: string
  rescheduleCheck: AdminConcurrencyCheckResponse | null
  isCheckingReschedule: boolean
  onCancelAppointment: (id: number) => void
  onCancelFreeMedicalAppointment: (id: number) => void
  onConfirmFreeMedicalAppointment: (id: number) => void
  onMarkPendingBiometric: (id: number) => void
  onConfirmBiometric: (id: number) => void
  onCancelFromVerification: (id: number) => void
  onSetRescheduleAppointment: (id: number) => void
  onRescheduleDateChange: (value: string) => void
  onRescheduleTimeChange: (value: string) => void
  onCheckRescheduleAvailability: () => void
  onRescheduleAppointment: () => void
  onCancelReschedule: () => void
  // Refetch the surrounding page after a successful cobro so the cita
  // row re-renders with the new `pagos[]` / `saldoPendiente`. The
  // parent owns the data fetch (useClientDetail / useApiResource).
  onPaymentRegistered: () => void
}

export function ClientAppointmentSection({
  visibleAppointments,
  changeAppointmentMonth,
  viewedMonthLabel,
  appointmentStatusFilter,
  setAppointmentStatusFilter,
  appointmentStatuses,
  visibleAppointmentCount,
  setVisibleAppointmentCount,
  filteredAppointmentsLength,
  hasMore,
  hasLess,
  appointmentActionId,
  rescheduleAppointmentId,
  rescheduleDate,
  rescheduleTime,
  rescheduleCheck,
  isCheckingReschedule,
  biometricSuspended,
  onCancelAppointment,
  onCancelFreeMedicalAppointment,
  onConfirmFreeMedicalAppointment,
  onMarkPendingBiometric,
  onConfirmBiometric,
  onCancelFromVerification,
  onSetRescheduleAppointment,
  onRescheduleDateChange,
  onRescheduleTimeChange,
  onCheckRescheduleAvailability,
  onRescheduleAppointment,
  onCancelReschedule,
  onPaymentRegistered,
}: ClientAppointmentSectionProps) {
  const { showNotification } = useNotifications()
  // Estado local del modal `AdminRegisterAppointmentPaymentModal`. Lo
  // mantiene este componente (no la pagina padre) porque la accion solo
  // aparece dentro de la tabla de citas; pasamos el `AdminAppointment`
  // resuelto al modal y disparamos el POST desde aca. El modal ya sabe
  // cuando `precio == 0` o `saldoPendiente == 0` y deshabilita el submit.
  const [cobrarAppointment, setCobrarAppointment] = useState<AdminAppointment | null>(null)
  const [cobrarError, setCobrarError] = useState<string | null>(null)
  const [isCobrarSubmitting, setIsCobrarSubmitting] = useState(false)

  const closeCobrarModal = () => {
    setCobrarAppointment(null)
    setCobrarError(null)
  }

  const handleCobrarSubmit = async (
    payload: RegisterAdminAppointmentPaymentPayload,
  ) => {
    if (!cobrarAppointment) return
    setIsCobrarSubmitting(true)
    setCobrarError(null)
    try {
      // Las citas medicas requieren operationId en el URL; las libres
      // usan un endpoint sin operationId. Discriminamos por la flag que
      // expone el backend en cada row.
      const response = cobrarAppointment.isFreeMedicalAppointment
        ? await registerAdminFreeAppointmentPayment(cobrarAppointment.rawId, payload)
        : await registerAdminAppointmentPayment(
            cobrarAppointment.operationRawId ?? 0,
            cobrarAppointment.rawId,
            payload,
          )
      showNotification({
        title: 'Pago registrado',
        message: response.detail,
        tone: 'success',
      })
      setCobrarAppointment(null)
      onPaymentRegistered()
    } catch (requestError) {
      setCobrarError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo registrar el pago de la cita.',
      )
    } finally {
      setIsCobrarSubmitting(false)
    }
  }

  // Habilita el boton "Cobrar cita" cuando la cita tiene precio y
  // esta en un estado que admite cobros. CANCELADA / NO_ASISTIO son
  // terminales segun el spec y el backend rechaza con 400, asi que
  // bloqueamos aca para evitar un POST que siempre retornaria 400.
  const canCobrarAppointment = (appointment: ClientAppointment): boolean => {
    const precioNumber = Number(appointment.precio ?? '0') || 0
    if (precioNumber <= 0) return false
    const status = (appointment.status ?? '').toLowerCase()
    if (status === 'cancelada' || status === 'no asistio') return false
    return true
  }

  return (
    <SectionCard
      eyebrow="Agenda"
      title="Todas las citas del cliente"
      description="Historial completo de reservas, sesiones realizadas, cancelaciones y pendientes de verificación."
      action={
        <div className="expense-period-controls">
          <button className="button button--ghost" type="button" onClick={() => changeAppointmentMonth(-1)}>←</button>
          <div>
            <span className="eyebrow">Mes seleccionado</span>
            <h3>{viewedMonthLabel}</h3>
          </div>
          <button className="button button--ghost" type="button" onClick={() => changeAppointmentMonth(1)}>→</button>
        </div>
      }
    >
      {/* Status Filter */}
      <div className="_mb-md">
        <select
          className="input"
          value={appointmentStatusFilter}
          onChange={(event) => setAppointmentStatusFilter(event.target.value)}
        >
          <option value="">Todos</option>
          {appointmentStatuses.map(status => (
            <option key={status} value={status}>{status}</option>
          ))}
        </select>
      </div>

      {/* Table or Empty State */}
      {visibleAppointments.length ? (
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>Operación</th>
                <th>Especialista</th>
                <th>Fecha</th>
                <th>Estado</th>
                <th>Verificación</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {visibleAppointments.map((appointment) => (
                <tr key={appointment.id}>
                  <td><strong>{appointment.operation}</strong><span>{appointment.details}</span></td>
                  <td>{appointment.specialist}</td>
                  <td>{appointment.dateTime}</td>
                  <td><StatusBadge tone={appointment.statusTone}>{appointment.status}</StatusBadge></td>
                  <td>{verificationStatusLabel[appointment.verificationStatus]}</td>
                  <td>
                    <div className="table-action-list">
                      {appointment.isFreeMedicalAppointment && appointment.status?.toLowerCase() === 'programada' ? (
                        <>
                          <button
                            className="button button--primary button--compact"
                            disabled={appointmentActionId !== null}
                            type="button"
                            onClick={() => void onConfirmFreeMedicalAppointment(appointment.rawId)}
                          >
                            Confirmar cita
                          </button>
                          <button
                            className="button button--ghost button--compact"
                            disabled={appointmentActionId !== null}
                            type="button"
                            onClick={() => void onCancelFreeMedicalAppointment(appointment.rawId)}
                          >
                            Cancelar reserva
                          </button>
                        </>
                      ) : null}
                      {appointment.canMarkPendingBiometric ? (
                        <button
                          className="button button--ghost button--compact"
                          disabled={appointmentActionId !== null}
                          type="button"
                          onClick={() => void onMarkPendingBiometric(appointment.rawId)}
                        >
                          {appointmentActionId === appointment.rawId ? 'Actualizando...' : 'Cambiar a pendiente de verificación'}
                        </button>
                      ) : null}
                      {!appointment.isFreeMedicalAppointment && ['programada', 'no asistio'].includes(appointment.status?.toLowerCase?.() ?? '') ? (
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
                      {appointment.canConfirmBiometric && !biometricSuspended ? (
                        <button
                          className="button button--ghost button--compact"
                          disabled={appointmentActionId !== null}
                          type="button"
                          onClick={() => void onConfirmBiometric(appointment.rawId)}
                        >
                          {appointmentActionId === appointment.rawId ? 'Validando...' : 'Confirmar con huella'}
                        </button>
                      ) : null}
                      {appointment.canCancelFromVerification ? (
                        <button
                          className="button button--ghost button--compact"
                          disabled={appointmentActionId !== null}
                          type="button"
                          onClick={() => void onCancelFromVerification(appointment.rawId)}
                        >
                          Cancelar
                        </button>
                      ) : null}
                      {canCobrarAppointment(appointment) ? (
                        <button
                          className="button button--ghost button--compact"
                          disabled={isCobrarSubmitting}
                          type="button"
                          aria-label={`Cobrar cita ${appointment.rawId}`}
                          data-testid={`cobrar-cita-${appointment.rawId}`}
                          onClick={() => {
                            setCobrarError(null)
                            setCobrarAppointment(appointment as AdminAppointment)
                          }}
                        >
                          Cobrar cita
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <DataState title={`No hay citas en ${viewedMonthLabel}`} message="Este mes no tiene citas registradas." />}

      {/* Pagination Info + Controls */}
      {filteredAppointmentsLength > 0 && (
        <div className="_flex-between _mt-md">
          <span>Mostrando {visibleAppointmentCount} de {filteredAppointmentsLength} citas de {viewedMonthLabel}</span>
          <div>
            {hasLess && (
              <button
                type="button"
                className="button button--ghost"
                onClick={() => setVisibleAppointmentCount(c => c - 5)}
              >
                Ver menos
              </button>
            )}
            {hasMore && (
              <button
                type="button"
                className="button button--secondary"
                onClick={() => setVisibleAppointmentCount(c => c + 5)}
              >
                Ver más
              </button>
            )}
          </div>
        </div>
      )}

      {rescheduleAppointmentId ? (
        <div className="_mt-md _panel-card">
          <p className="_mb-md"><strong>Reprogramar cita seleccionada</strong></p>
          <div className="_grid-2cols">
            <label className="field">
              <span>Nueva fecha</span>
              <input type="date" className="input" value={rescheduleDate} onChange={(e) => { onRescheduleDateChange(e.target.value) }} />
            </label>
            <label className="field">
              <span>Nueva hora</span>
              <input type="time" className="input" value={rescheduleTime} onChange={(e) => { onRescheduleTimeChange(e.target.value) }} />
            </label>
          </div>
          <div className="_flex-gap-sm _mt-md">
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
            <p className="_mt-sm">
              Citas simultaneas de 1 hora antes a 1 hora despues ({rescheduleCheck.hora_inicio} a {rescheduleCheck.hora_fin}): {rescheduleCheck.concurrency}. Especialistas en turno {rescheduleCheck.hora_seleccionada}: {rescheduleCheck.presentes.length > 0 ? rescheduleCheck.presentes.map((p) => p.usuario__primer_nombre).join(', ') : 'Ninguno registrado'}.
            </p>
          ) : null}
        </div>
      ) : null}

      <AdminRegisterAppointmentPaymentModal
        appointment={cobrarAppointment}
        isOpen={cobrarAppointment !== null}
        isSubmitting={isCobrarSubmitting}
        errorMessage={cobrarError}
        onClose={closeCobrarModal}
        onSubmit={handleCobrarSubmit}
      />
    </SectionCard>
  )
}