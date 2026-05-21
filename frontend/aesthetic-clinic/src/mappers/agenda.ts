import type {
  AgendaItem,
  AgendaItemLegacy,
  AppointmentStatus,
  VerificationMethod,
  VerificationStatus,
} from '../types/admin'

const legacyStatusMap: Record<AgendaItemLegacy['status'], AppointmentStatus> = {
  programada: 'programada',
  biometria: 'pendiente_verificacion',
  confirmada: 'confirmada',
}

export function normalizeAgendaItem(item: AgendaItemLegacy): AgendaItem {
  const mappedStatus = item.appointmentStatus ?? legacyStatusMap[item.status]
  const verificationStatus: VerificationStatus =
    item.verificationStatus
    ?? (mappedStatus === 'pendiente_verificacion'
      ? 'pendiente'
      : mappedStatus === 'confirmada'
        ? 'verificada'
        : 'no_requerida')

  const verificationMethod: VerificationMethod =
    item.verificationMethod ?? (item.status === 'biometria' ? 'biometria' : null)

  return {
    ...item,
    status: mappedStatus,
    verificationStatus,
    verificationMethod,
  }
}
