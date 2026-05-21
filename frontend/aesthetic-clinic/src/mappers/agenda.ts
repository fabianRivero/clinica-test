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
  const mappedStatus = legacyStatusMap[item.status]
  const verificationStatus: VerificationStatus =
    mappedStatus === 'pendiente_verificacion'
      ? 'pendiente'
      : mappedStatus === 'confirmada'
        ? 'verificada'
        : 'no_requerida'

  const verificationMethod: VerificationMethod =
    item.status === 'biometria' ? 'biometria' : null

  return {
    ...item,
    status: mappedStatus,
    verificationStatus,
    verificationMethod,
  }
}

