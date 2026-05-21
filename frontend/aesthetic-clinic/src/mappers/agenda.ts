import type { AgendaItem, AgendaItemLegacy } from '../types/admin'

export function normalizeAgendaItem(item: AgendaItemLegacy): AgendaItem {
  return {
    ...item,
    status: item.appointmentStatus,
  }
}
