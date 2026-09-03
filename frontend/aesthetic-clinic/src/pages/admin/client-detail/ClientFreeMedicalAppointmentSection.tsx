import { useState } from 'react'

import { SectionCard } from '../../../components/admin/SectionCard'
import { AdminRegisterAppointmentPaymentModal } from '../../../components/admin/AdminRegisterAppointmentPaymentModal'
import { EditAppointmentPriceModal } from '../../../components/admin/EditAppointmentPriceModal'
import { useNotifications } from '../../../providers/NotificationProvider'
import {
  registerAdminFreeAppointmentPayment,
  updateAdminFreeAppointmentPrice,
} from '../../../services/api/admin'
import type {
  AdminAppointment,
  AdminConcurrencyCheckResponse,
  RegisterAdminAppointmentPaymentPayload,
} from '../../../types/admin'
import type { ClientAppointment } from '../../../types/common'

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
  /**
   * Reserves a free medical appointment for this client. The parent
   * owns the network call so the section stays focused on form state.
   * ``bookingPrecio`` (optional) is the cita price the admin quotes at
   * booking time — stored with the cita and consumed by the cobro
   * modal later. Empty string means "leave at 0" (legacy default).
   */
  handleReserveFreeMedicalAppointment: (bookingPrecio: string) => Promise<void>
  /**
   * Free appointments already registered for this client. The parent
   * page (AdminClientDetailPage) filters them from the unified
   * ``data.appointments`` list using ``isFreeMedicalAppointment === true``.
   * The section renders a "Citas libres registradas" panel with the
   * "Cobrar cita" + "Editar precio" buttons per row, mirroring the
   * citas-pagos UX used by prospecto appointments.
   */
  freeAppointments: ClientAppointment[]
  // Refetch the surrounding page after a successful cobro so the cita
  // row re-renders with the new `pagos[]` / `saldoPendiente`.
  onPaymentRegistered: () => void
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
  freeAppointments,
  onPaymentRegistered,
}: ClientFreeMedicalAppointmentSectionProps) {
  const { showNotification } = useNotifications()
  // Booking-time precio (optional, empty = 0).
  const [bookingPrecio, setBookingPrecio] = useState('')

  // Estado del modal de cobro. Misma forma que `ClientAppointmentSection`:
  // vive aqui para mantener la accion dentro de la seccion y dispara
  // el POST al endpoint libre (no requiere operationId).
  const [cobrarAppointment, setCobrarAppointment] = useState<AdminAppointment | null>(null)
  const [cobrarError, setCobrarError] = useState<string | null>(null)
  const [isCobrarSubmitting, setIsCobrarSubmitting] = useState(false)

  // Edit-precio modal state (locks the appointment until the user
  // confirms or cancels; mirrors the prospecto flow).
  const [editingPrecioCita, setEditingPrecioCita] = useState<ClientAppointment | null>(null)

  const closeCobrarModal = () => {
    setCobrarAppointment(null)
    setCobrarError(null)
  }

  // --- helpers (shared cobro-state derivation) -------------------------
  // The `precio` field arrives formatted as ``"Bs 80.00"`` by the
  // backend ``currency()`` helper. Parse defensively so the absence
  // of the ``Bs`` prefix (legacy zero) and any odd whitespace still
  // yield a usable number.
  const parsePrecioLocal = (raw: string | undefined | null): number => {
    if (raw === undefined || raw === null || raw === '') return 0
    const cleaned = String(raw).replace(/^Bs\s*/i, '').replace(/,/g, '').trim()
    const num = Number(cleaned)
    return Number.isFinite(num) ? num : 0
  }
  function deriveCobroState(appointment: ClientAppointment) {
    const precio = parsePrecioLocal(appointment.precio)
    const saldo = parsePrecioLocal(appointment.saldoPendiente)
    const pagosCount = appointment.pagos_count ?? 0
    const approvedSum = (appointment.pagos ?? []).reduce((acc, pago) => {
      if (pago.estado_verificacion !== 'APROBADO') return acc
      return acc + (Number(pago.monto_pagado) || 0)
    }, 0)
    return {
      precio,
      saldo,
      approvedSum,
      pagosCount,
      isFullyPaid: precio > 0 && saldo <= 0,
      isPartiallyPaid: approvedSum > 0 && saldo > 0,
    }
  }

  // Cobro handler — posts a multipart payload so the optional receipt
  // file attached via the modal survives the trip. Mirrors the
  // prospecto cobro flow.
  const handleCobrarSubmit = async (
    payload: RegisterAdminAppointmentPaymentPayload,
  ) => {
    if (!cobrarAppointment) return
    setIsCobrarSubmitting(true)
    setCobrarError(null)
    try {
      const response = await registerAdminFreeAppointmentPayment(cobrarAppointment.rawId, payload)
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

  const handleConfirmEditPrice = async (newPrecio: string) => {
    if (!editingPrecioCita) return
    try {
      await updateAdminFreeAppointmentPrice(editingPrecioCita.rawId, newPrecio)
      showNotification({
        title: 'Precio actualizado',
        message: 'El precio de la cita fue actualizado.',
        tone: 'success',
      })
      setEditingPrecioCita(null)
      onPaymentRegistered()
    } catch (requestError) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo actualizar el precio.'
      showNotification({
        title: 'No se pudo actualizar',
        message,
        tone: 'danger',
      })
    }
  }

  // Misma regla de habilitacion que ClientAppointmentSection: precio
  // positivo y estado no terminal. CANCELADA / NO_ASISTIO son rechazados
  // por el backend con 400, asi que bloqueamos aca para no enviar un
  // POST que siempre fallaria. Una vez la cita esta cobrada en su
  // totalidad (saldoPendiente === 0) los botones se deshabilitan
  // proactivamente — el backend over-payment guard los rechaza, pero
  // el admin no deberia verlos habilitados.
  const canCobrarAppointment = (appointment: ClientAppointment): boolean => {
    const cobro = deriveCobroState(appointment)
    if (cobro.precio <= 0) return false
    const status = (appointment.status ?? '').toLowerCase()
    if (status === 'cancelada' || status === 'no asistio') return false
    return !cobro.isFullyPaid
  }

  const handleReserveClick = () => {
    void handleReserveFreeMedicalAppointment(bookingPrecio)
    setBookingPrecio('')
  }

  return (
    <section className="dashboard-grid">
      <SectionCard eyebrow="Cita medica" title="Reservar cita médica" description="Agenda una consulta sin asociarla a un tratamiento activo. Disponible tambien para clientes inactivos. Puedes indicar el precio al reservar o dejarlo en 0 y asignarlo después.">
        <div className="form-grid">
          <div className="_grid-2cols">
            <label className="field">
              <span>Fecha</span>
              <input type="date" className="input" value={freeSelectedDate} onChange={e => { setFreeSelectedDate(e.target.value); setFreeConcurrencyInfo(null); }} />
            </label>
            <label className="field">
              <span>Hora de Inicio</span>
              <input type="time" className="input" value={freeSelectedTime} onChange={e => { setFreeSelectedTime(e.target.value); setFreeConcurrencyInfo(null); }} />
            </label>
          </div>

          {/* citas-pagos follow-on: optional precio captured at booking
              time. Empty means "leave at 0" — admin can still edit the
              price later from the citas-libres table below. */}
          <label className="field">
            <span>Precio de la cita (opcional)</span>
            <input
              type="number"
              className="input"
              min="0"
              step="0.01"
              placeholder="0.00"
              value={bookingPrecio}
              onChange={(e) => setBookingPrecio(e.target.value)}
            />
            <small className="field__hint">
              Deja en 0 para agendar sin cobrar. Podras asignar el precio despues.
            </small>
          </label>

          <div className="_mt-md _flex-gap-sm">
            <button type="button" className="button button--secondary" disabled={!freeSelectedDate || !freeSelectedTime || isChecking} onClick={() => void handleCheckFreeConcurrency()}>
              {isChecking ? 'Verificando...' : 'Verificar Disponibilidad'}
            </button>
          </div>
        </div>
      </SectionCard>

      {freeConcurrencyInfo && (
        <SectionCard title="Resultados de disponibilidad">
          <div className="_panel-card">
            <p className="_mb-sm">
              <strong>Citas simultaneas de 1 hora antes a 1 hora despues ({freeConcurrencyInfo.hora_inicio} a {freeConcurrencyInfo.hora_fin}):</strong> {freeConcurrencyInfo.concurrency}
            </p>
            <p className="_mb-sm">
              <strong>Especialistas en turno {freeConcurrencyInfo.hora_seleccionada}:</strong> {freeConcurrencyInfo.presentes.length > 0 ? freeConcurrencyInfo.presentes.map(p => p.usuario__primer_nombre).join(', ') : 'Ninguno registrado'}
            </p>
            <div className="_mt-lg">
               <button type="button" className="button button--primary" onClick={handleReserveClick} disabled={Boolean(isFreeBookingKey)}>
                 {isFreeBookingKey ? 'Confirmando...' : 'Confirmar Cita Medica'}
               </button>
            </div>
          </div>
        </SectionCard>
      )}

      {freeAppointments.length > 0 ? (
        <SectionCard
          eyebrow="Cobrar cita libre"
          title="Citas libres registradas"
          description="Citas medicas libres ya agendadas para este cliente. Cobra la consulta en consultorio cuando asista."
        >
          <div className="table-card">
            <table>
              <thead>
                <tr>
                  <th>Fecha y hora</th>
                  <th>Especialista</th>
                  <th>Estado</th>
                  <th>Precio / Saldo</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {freeAppointments.map((appointment) => {
                  const cobro = deriveCobroState(appointment)
                  const buttonsDisabled = cobro.isFullyPaid
                  return (
                    <tr key={appointment.id}>
                      <td><strong>{appointment.dateTime}</strong></td>
                      <td>{appointment.specialist}</td>
                      <td>{appointment.status}</td>
                      <td>
                        {appointment.precio ? `Bs ${appointment.precio}` : 'Sin precio'}
                        {cobro.pagosCount > 0 ? (
                          <small className="field__hint" style={{ display: 'block', marginTop: '0.25rem' }}>
                            Saldo: Bs {appointment.saldoPendiente ?? '0.00'}
                            {cobro.isFullyPaid
                              ? ` — Ya cobrada (${cobro.pagosCount} ${cobro.pagosCount === 1 ? 'pago' : 'pagos'})`
                              : cobro.isPartiallyPaid
                                ? ` — Cobrado Bs ${cobro.approvedSum.toFixed(2)} / falta Bs ${cobro.saldo.toFixed(2)}`
                                : ''}
                          </small>
                        ) : null}
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <button
                            className="button button--ghost button--compact"
                            disabled={isCobrarSubmitting || !canCobrarAppointment(appointment)}
                            type="button"
                            title={
                              buttonsDisabled
                                ? 'La cita ya esta cobrada en su totalidad.'
                                : !canCobrarAppointment(appointment)
                                  ? 'La cita no es cobrable (precio 0 o estado terminal).'
                                  : undefined
                            }
                            style={buttonsDisabled ? { opacity: 0.5, cursor: 'not-allowed' } : undefined}
                            aria-label={`Cobrar cita libre ${appointment.rawId}`}
                            data-testid={`cobrar-cita-libre-${appointment.rawId}`}
                            onClick={() => {
                              setCobrarError(null)
                              setCobrarAppointment(appointment as AdminAppointment)
                            }}
                          >
                            Cobrar cita
                          </button>
                          <button
                            className="button button--ghost button--compact"
                            disabled={buttonsDisabled}
                            type="button"
                            title={
                              buttonsDisabled
                                ? 'No puedes cambiar el precio despues de un cobro aprobado.'
                                : undefined
                            }
                            style={buttonsDisabled ? { opacity: 0.5, cursor: 'not-allowed' } : undefined}
                            onClick={() => setEditingPrecioCita(appointment)}
                          >
                            Editar precio
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <AdminRegisterAppointmentPaymentModal
            appointment={cobrarAppointment}
            isOpen={cobrarAppointment !== null}
            isSubmitting={isCobrarSubmitting}
            errorMessage={cobrarError}
            onClose={closeCobrarModal}
            onSubmit={handleCobrarSubmit}
          />
          {editingPrecioCita ? (
            <EditAppointmentPriceModal
              key={editingPrecioCita.id}
              citaRawId={editingPrecioCita.rawId}
              currentPrecio={editingPrecioCita.precio ?? 'Bs 0.00'}
              onClose={() => setEditingPrecioCita(null)}
              onSubmit={handleConfirmEditPrice}
            />
          ) : null}
        </SectionCard>
      ) : null}
    </section>
  )
}