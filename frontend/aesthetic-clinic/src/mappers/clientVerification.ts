import type { ClientAppointment } from '../types/client'

export function normalizeClientAppointment(appointment: ClientAppointment): ClientAppointment {
  const status = appointment.status.toLowerCase()
  const isCancelledOrNoShow = status.includes('cancel') || status.includes('no asist')
  const canBeNotRequired = isCancelledOrNoShow || appointment.isFreeMedicalAppointment
  const incomingStatus = appointment.verificationStatus ?? (canBeNotRequired ? 'no_requerida' : 'pendiente')
  const normalizedVerificationStatus =
    incomingStatus === 'no_requerida' && !canBeNotRequired ? 'pendiente' : incomingStatus

  return {
    ...appointment,
    verificationStatus: normalizedVerificationStatus,
    verificationMethod: appointment.verificationMethod ?? null,
  }
}

export function normalizeClientAppointments(appointments: ClientAppointment[]): ClientAppointment[] {
  return appointments.map(normalizeClientAppointment)
}
