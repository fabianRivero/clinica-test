import { ensureCsrfCookie } from './auth'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: 'include', headers: { Accept: 'application/json' } })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error((data as { detail?: string })?.detail || `Error ${response.status}`)
  return data as T
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const csrf = await ensureCsrfCookie()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
    body: JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error((data as { detail?: string })?.detail || `Error ${response.status}`)
  return data as T
}

export type TicketStatus = 'ABIERTO' | 'CERRADO'
export type MessageStatus = 'ENVIADO' | 'RESPONDIDO'
export type PermissionSummary = 'ALL_ENABLED' | 'ALL_BLOCKED' | 'MIXED'
export type Ticket = { id:number; subject:string; status:TicketStatus; branchName:string; specialistName:string; updatedAt:string }
export type TicketMessage = { id:number; authorName:string; authorRole:string; body:string; status:MessageStatus; createdAt:string }
export type SpecialistOpenPermission = { specialistId:number; specialistName:string; enabled:boolean }
export type OpenPermissionStatusResponse = {
  branchId:number
  branchName:string
  branchDefaultEnabled:boolean
  summary: PermissionSummary
  specialists: SpecialistOpenPermission[]
}

export const getTickets = (status?: TicketStatus) => getJson<{tickets: Ticket[]}>(`/api/tickets/${status ? `?status=${status}`:''}`)
export const createTicket = (payload: {subject:string; message:string; specialistId?:number}) => postJson('/api/tickets/crear/', payload)
export const getTicketDetail = (ticketId:number) => getJson<{ticket:Ticket; messages:TicketMessage[]}>(`/api/tickets/${ticketId}/`)
export const replyTicket = (ticketId:number, message:string) => postJson(`/api/tickets/${ticketId}/responder/`, { message })
export const closeTicket = (ticketId:number) => postJson(`/api/tickets/${ticketId}/cerrar/`, {})
export const reopenTicket = (ticketId:number) => postJson(`/api/tickets/${ticketId}/reabrir/`, {})
export const getOpenPermissionStatus = () => getJson<OpenPermissionStatusResponse>('/api/tickets/permisos/apertura/estado/')
export const setSpecialistOpenPermission = (enabled:boolean, specialistId?: number) => postJson('/api/tickets/permisos/apertura/', { enabled, specialistId })
