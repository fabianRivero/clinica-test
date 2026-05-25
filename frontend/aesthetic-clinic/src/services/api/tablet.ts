import { requestJsonNoBranch, postJson } from './apiClient'
import type {
  TabletClientLoginResponse,
  TabletConfirmResponse,
  TabletCurrentAppointmentResponse,
  TabletKioskLoginResponse,
  TabletResetResponse,
} from '../../types/tablet'

export function tabletKioskLogin(codigo: string, clave: string) {
  return postJson<TabletKioskLoginResponse>('/api/client/tablet/auth/login/', { codigo, clave })
}

export function tabletClientLogin(username: string, password: string) {
  return postJson<TabletClientLoginResponse>('/api/client/tablet/client/login/', { username, password })
}

export function tabletCurrentAppointment() {
  return requestJsonNoBranch<TabletCurrentAppointmentResponse>('/api/client/tablet/cita-actual/')
}

export function tabletConfirmProcedure(operationId: number) {
  return postJson<TabletConfirmResponse>('/api/client/tablet/confirmar-procedimiento/', { operationId })
}

export function tabletClientReset() {
  return postJson<TabletResetResponse>('/api/client/tablet/client/reset/', {})
}


export interface TabletOfflineSyncEventPayload {
  eventId: string
  operationId: number
  createdAt: string
}

export interface TabletOfflineSyncResponseItem {
  eventId: string | null
  status: "accepted" | "duplicate" | "conflict" | "rejected"
  reason?: string
  appointmentId?: number
}

export interface TabletOfflineSyncResponse {
  detail: string
  results: TabletOfflineSyncResponseItem[]
}

export function tabletSyncOfflineEvents(events: TabletOfflineSyncEventPayload[], deviceId: string) {
  return postJson<TabletOfflineSyncResponse>('/api/client/tablet/offline/sync-events/', { events, deviceId })
}
