import type { AppointmentStatus } from '../types/admin'
import type { ClientAppointment } from '../types/client'

export const appointmentStatusTone: Record<AppointmentStatus, 'neutral' | 'warning' | 'success'> = {
  programada: 'neutral',
  pendiente_verificacion: 'warning',
  confirmada: 'success',
}

export const appointmentStatusLabel: Record<AppointmentStatus, string> = {
  programada: 'Programada',
  pendiente_verificacion: 'Pendiente de verificación',
  confirmada: 'Confirmada',
}

export const verificationStatusTone: Record<NonNullable<ClientAppointment['verificationStatus']>, 'approved' | 'pending' | 'warning'> = {
  verificada: 'approved',
  pendiente: 'pending',
  no_requerida: 'warning',
}

export const verificationStatusLabel: Record<NonNullable<ClientAppointment['verificationStatus']>, string> = {
  verificada: 'Verificada',
  pendiente: 'Pendiente',
  no_requerida: 'No requerida',
}

export const verificationMethodLabel: Record<Exclude<NonNullable<ClientAppointment['verificationMethod']>, null>, string> = {
  biometria: 'Biometria',
  qr: 'QR',
  manual: 'Manual',
  otro: 'Otro',
}
