import type { ClientAppointment } from '../types/client'

export function normalizeClientAppointment(appointment: ClientAppointment): ClientAppointment {
  const status = appointment.status.toLowerCase()
  const isCancelledOrNoShow = status.includes('cancel') || status.includes('no asist')
  const defaultVerificationStatus =
    isCancelledOrNoShow || appointment.isFreeMedicalAppointment ? 'no_requerida' : 'pendiente'

  return {
    ...appointment,
    verificationStatus: appointment.verificationStatus ?? defaultVerificationStatus,
    verificationMethod: appointment.verificationMethod ?? null,
  }
}

export function normalizeClientAppointments(appointments: ClientAppointment[]): ClientAppointment[] {
  return appointments.map(normalizeClientAppointment)
}
