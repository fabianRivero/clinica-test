import type { AppointmentStatus } from '../types/admin'
import type { ClientAppointment } from '../types/client'

export const appointmentStatusTone: Record<AppointmentStatus, 'neutral' | 'warning' | 'success'> = {
  programada: 'neutral',
  pendiente_verificacion: 'warning',
  confirmada: 'success',
}

export const appointmentStatusLabel: Record<AppointmentStatus, string> = {
  programada: 'Programada',
  pendiente_verificacion: 'Pendiente de verificacion',
  confirmada: 'Confirmada',
}

export const confirmationStatusTone: Record<ClientAppointment['confirmationStatus'], 'approved' | 'pending' | 'warning'> = {
  biometria: 'approved',
  qr: 'pending',
  pendiente: 'warning',
}

export const verificationStatusTone: Record<NonNullable<ClientAppointment['verificationStatus']>, 'approved' | 'pending' | 'warning'> = {
  verificada: 'approved',
  pendiente: 'pending',
  no_requerida: 'warning',
}
