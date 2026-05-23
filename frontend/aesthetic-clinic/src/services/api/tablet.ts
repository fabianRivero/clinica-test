import { ensureCsrfCookie } from './auth'
import type {
  TabletClientLoginResponse,
  TabletConfirmResponse,
  TabletCurrentAppointmentResponse,
  TabletKioskLoginResponse,
  TabletResetResponse,
} from '../../types/tablet'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const csrfToken = await ensureCsrfCookie()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    },
    body: JSON.stringify(body),
  })
  const responseBody = (await response.json().catch(() => null)) as { detail?: string } | null
  if (!response.ok) {
    throw new Error(responseBody?.detail || `No se pudo completar ${path} (${response.status})`)
  }
  return responseBody as T
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  const responseBody = (await response.json().catch(() => null)) as { detail?: string } | null
  if (!response.ok) {
    throw new Error(responseBody?.detail || `No se pudo cargar ${path} (${response.status})`)
  }
  return responseBody as T
}

export function tabletKioskLogin(codigo: string, clave: string) {
  return postJson<TabletKioskLoginResponse>('/api/client/tablet/auth/login/', { codigo, clave })
}

export function tabletClientLogin(username: string, password: string) {
  return postJson<TabletClientLoginResponse>('/api/client/tablet/client/login/', { username, password })
}

export function tabletCurrentAppointment() {
  return getJson<TabletCurrentAppointmentResponse>('/api/client/tablet/cita-actual/')
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

export function tabletSyncOfflineEvents(events: TabletOfflineSyncEventPayload[]) {
  return postJson<TabletOfflineSyncResponse>('/api/client/tablet/offline/sync-events/', { events })
}
