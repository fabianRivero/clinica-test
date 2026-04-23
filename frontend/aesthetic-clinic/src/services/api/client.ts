import type {
  ClientReservationAvailabilityResponse,
  ClientDashboardResponse,
  ClientReservationsResponse,
  ClientPaymentsResponse,
  ClientTreatmentsResponse,
  CreateClientReservationPayload,
  CreateClientReservationResponse,
} from '../../types/client'
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

  const responseBody = (await response.json().catch(() => null)) as { detail?: string } | null

  if (!response.ok) {
    throw new Error(responseBody?.detail || `No se pudo completar ${path} (${response.status})`)
  }

  return responseBody as T
}

export function getClientDashboard() {
  return requestJson<ClientDashboardResponse>('/api/client/dashboard/')
}

export function getClientTreatments() {
  return requestJson<ClientTreatmentsResponse>('/api/client/tratamientos/')
}

export function getClientPayments() {
  return requestJson<ClientPaymentsResponse>('/api/client/pagos/')
}

export function getClientReservations() {
  return requestJson<ClientReservationsResponse>('/api/client/reservas/')
}

export function getClientReservationAvailability(operationId: string) {
  return requestJson<ClientReservationAvailabilityResponse>(
    `/api/client/reservas/${operationId}/disponibilidad/`,
  )
}

export function createClientReservation(
  operationId: string,
  payload: CreateClientReservationPayload,
) {
  return requestJsonWithBody<CreateClientReservationResponse>(
    `/api/client/reservas/${operationId}/crear/`,
    payload,
  )
}
