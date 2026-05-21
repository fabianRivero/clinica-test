import type { ClientAppointment } from '../types/client'

export function normalizeClientAppointment(appointment: ClientAppointment): ClientAppointment {
  return {
    ...appointment,
    verificationStatus: appointment.verificationStatus ?? 'no_requerida',
    verificationMethod: appointment.verificationMethod ?? null,
  }
}

export function normalizeClientAppointments(appointments: ClientAppointment[]): ClientAppointment[] {
  return appointments.map(normalizeClientAppointment)
}
