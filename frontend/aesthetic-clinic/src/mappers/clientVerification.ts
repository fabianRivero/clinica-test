import type { ClientAppointment } from '../types/client'

function deriveVerificationStatus(confirmationStatus: ClientAppointment['confirmationStatus']) {
  if (confirmationStatus === 'biometria') return 'verificada' as const
  if (confirmationStatus === 'qr') return 'pendiente' as const
  return 'pendiente' as const
}

function deriveVerificationMethod(confirmationStatus: ClientAppointment['confirmationStatus']) {
  if (confirmationStatus === 'biometria') return 'biometria' as const
  if (confirmationStatus === 'qr') return 'qr' as const
  return null
}

export function normalizeClientAppointment(appointment: ClientAppointment): ClientAppointment {
  return {
    ...appointment,
    verificationStatus:
      appointment.verificationStatus ?? deriveVerificationStatus(appointment.confirmationStatus),
    verificationMethod:
      appointment.verificationMethod ?? deriveVerificationMethod(appointment.confirmationStatus),
  }
}

export function normalizeClientAppointments(appointments: ClientAppointment[]): ClientAppointment[] {
  return appointments.map(normalizeClientAppointment)
}

