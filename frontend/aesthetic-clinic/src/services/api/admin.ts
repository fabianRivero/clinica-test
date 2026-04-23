import type {
  AdminAvailabilityResponse,
  CatalogsResponse,
  CreateAdminAvailabilityPayload,
  CreateAdminAvailabilityResponse,
  CreateAdminProspectPayload,
  CreateAdminProspectResponse,
  DashboardResponse,
  OperationsResponse,
  PaymentsResponse,
  ProspectsResponse,
  StaffResponse,
} from '../../types/admin'
import type {
  ProspectConversionFinalizeResponse,
  ProspectConversionMedicalData,
  ProspectConversionOperationData,
  ProspectConversionResponse,
  ProspectConversionUserData,
} from '../../types/prospectConversion'
import { ensureCsrfCookie } from './auth'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

function getCookie(name: string) {
  const cookie = document.cookie
    .split('; ')
    .find((item) => item.startsWith(`${name}=`))

  return cookie ? decodeURIComponent(cookie.split('=').slice(1).join('=')) : ''
}

async function requestJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`No se pudo cargar ${path} (${response.status})`)
  }

  return (await response.json()) as T
}

async function requestJsonWithBody<T>(path: string, body: unknown): Promise<T> {
  await ensureCsrfCookie()
  const csrfToken = getCookie('csrftoken')

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

  const responseBody = (await response.json().catch(() => null)) as
    | { detail?: string; errors?: Record<string, string> }
    | null

  if (!response.ok) {
    const error = new Error(responseBody?.detail || `No se pudo completar ${path} (${response.status})`) as Error & {
      fieldErrors?: Record<string, string>
    }
    if (responseBody?.errors) {
      error.fieldErrors = responseBody.errors
    }
    throw error
  }

  return responseBody as T
}

export function getAdminDashboard() {
  return requestJson<DashboardResponse>('/api/admin/dashboard/')
}

export function getAdminProspects() {
  return requestJson<ProspectsResponse>('/api/admin/prospectos/')
}

export function getAdminOperations() {
  return requestJson<OperationsResponse>('/api/admin/operaciones/')
}

export function getAdminAvailability() {
  return requestJson<AdminAvailabilityResponse>('/api/admin/disponibilidad/')
}

export function getAdminPayments() {
  return requestJson<PaymentsResponse>('/api/admin/pagos/')
}

export function getAdminCatalogs() {
  return requestJson<CatalogsResponse>('/api/admin/catalogos/')
}

export function getAdminStaff() {
  return requestJson<StaffResponse>('/api/admin/equipo/')
}

export function createAdminProspect(payload: CreateAdminProspectPayload) {
  return requestJsonWithBody<CreateAdminProspectResponse>('/api/admin/prospectos/crear/', payload)
}

export function createAdminAvailability(payload: CreateAdminAvailabilityPayload) {
  return requestJsonWithBody<CreateAdminAvailabilityResponse>('/api/admin/disponibilidad/crear/', payload)
}

export function getAdminProspectConversion(prospectId: string) {
  return requestJson<ProspectConversionResponse>(`/api/admin/prospectos/${prospectId}/conversion/`)
}

export function cancelAdminProspectConversion(prospectId: string) {
  return requestJsonWithBody<{ detail: string }>(
    `/api/admin/prospectos/${prospectId}/conversion/cancelar/`,
    {},
  )
}

export function saveAdminProspectConversionUserStep(prospectId: string, payload: ProspectConversionUserData & { password?: string }) {
  return requestJsonWithBody<ProspectConversionResponse>(
    `/api/admin/prospectos/${prospectId}/conversion/paso-1/`,
    payload,
  )
}

export function saveAdminProspectConversionOperationStep(prospectId: string, payload: ProspectConversionOperationData) {
  return requestJsonWithBody<ProspectConversionResponse>(
    `/api/admin/prospectos/${prospectId}/conversion/paso-2/`,
    payload,
  )
}

export function saveAdminProspectConversionMedicalStep(prospectId: string, payload: ProspectConversionMedicalData) {
  return requestJsonWithBody<ProspectConversionResponse>(
    `/api/admin/prospectos/${prospectId}/conversion/paso-3/`,
    payload,
  )
}

export function finalizeAdminProspectConversion(prospectId: string) {
  return requestJsonWithBody<ProspectConversionFinalizeResponse>(
    `/api/admin/prospectos/${prospectId}/conversion/finalizar/`,
    {},
  )
}
