import { ensureCsrfCookie } from './auth'
import { getActiveBranchId } from './activeBranch'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

async function getJson<T>(path: string): Promise<T> {
  const branchId = getActiveBranchId()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'X-Selected-Branch-Id': branchId ? String(branchId) : '',
    },
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error((data as { detail?: string })?.detail || `Error ${response.status}`)
  return data as T
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const csrf = await ensureCsrfCookie()
  const branchId = getActiveBranchId()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrf,
      'X-Selected-Branch-Id': branchId ? String(branchId) : '',
    },
    body: JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error((data as { detail?: string })?.detail || `Error ${response.status}`)
  return data as T
}



async function postForm<T>(path: string, formData: FormData): Promise<T> {
  const csrf = await ensureCsrfCookie()
  const branchId = getActiveBranchId()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'X-CSRFToken': csrf,
      'X-Selected-Branch-Id': branchId ? String(branchId) : '',
    },
    body: formData,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error((data as { detail?: string })?.detail || `Error ${response.status}`)
  return data as T
}
export type TicketStatus = 'ABIERTO' | 'CERRADO'
export type MessageStatus = 'ENVIADO' | 'RESPONDIDO'
export type PermissionSummary = 'ALL_ENABLED' | 'ALL_BLOCKED' | 'MIXED'
export type Ticket = { id:number; subject:string; status:TicketStatus; branchName:string; specialistName:string; adminRecipientId?: number | null; adminRecipientName?: string; updatedAt:string }
export type TicketMessage = { id:number; authorName:string; authorRole:string; body:string; status:MessageStatus; createdAt:string }
export type SpecialistOpenPermission = { specialistId:number; specialistName:string; enabled:boolean }
export type BranchAdminOpenPermission = { adminId:number; adminName:string; branchId:number | null; branchName:string; enabled:boolean }
export type OpenPermissionStatusResponse = {
  branchId:number
  branchName:string
  branchDefaultEnabled:boolean
  summary: PermissionSummary
  specialists: SpecialistOpenPermission[]
  branchAdmins: BranchAdminOpenPermission[]
  mainAdmins: BranchAdminOpenPermission[]
}

export const getTickets = (status?: TicketStatus) => getJson<{tickets: Ticket[]}>(`/api/tickets/${status ? `?status=${status}`:''}`)
export const createTicket = (payload: {subject:string; message:string; specialistId?:number; adminRecipientId?: number; attachment?: File | null}) => {
  if (payload.attachment) {
    const formData = new FormData()
    formData.append('subject', payload.subject)
    formData.append('message', payload.message)
    if (payload.specialistId) formData.append('specialistId', String(payload.specialistId))
    if (payload.adminRecipientId) formData.append('adminRecipientId', String(payload.adminRecipientId))
    formData.append('attachment', payload.attachment)
    return postForm('/api/tickets/crear/', formData)
  }
  return postJson('/api/tickets/crear/', payload)
}
export const getTicketDetail = (ticketId:number) => getJson<{ticket:Ticket; messages:TicketMessage[]}>(`/api/tickets/${ticketId}/`)
export const replyTicket = (ticketId:number, message:string, attachment?: File | null) => {
  if (attachment) {
    const formData = new FormData()
    formData.append('message', message)
    formData.append('attachment', attachment)
    return postForm(`/api/tickets/${ticketId}/responder/`, formData)
  }
  return postJson(`/api/tickets/${ticketId}/responder/`, { message })
}
export const closeTicket = (ticketId:number) => postJson(`/api/tickets/${ticketId}/cerrar/`, {})
export const reopenTicket = (ticketId:number) => postJson(`/api/tickets/${ticketId}/reabrir/`, {})
export const getOpenPermissionStatus = () => getJson<OpenPermissionStatusResponse>('/api/tickets/permisos/apertura/estado/')
export const setSpecialistOpenPermission = (enabled:boolean, specialistId?: number) => postJson('/api/tickets/permisos/apertura/', { enabled, specialistId })

export const setBranchAdminOpenPermission = (enabled:boolean, adminUserId?: number) => postJson('/api/tickets/permisos/apertura/', adminUserId ? { enabled, adminUserId } : { enabled, target: 'branch_admins' })
