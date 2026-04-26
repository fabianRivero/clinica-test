import type {
  ClientReservationAvailabilityResponse,
  ClientDashboardResponse,
  ClientReservationsResponse,
  ClientPaymentsResponse,
  ClientTreatmentsResponse,
  CreateClientReservationPayload,
  CreateClientReservationResponse,
  UploadClientPaymentReceiptPayload,
  UploadClientPaymentReceiptResponse,
} from '../../types/client'
import { ensureCsrfCookie } from './auth'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

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

async function requestFormDataWithBody<T>(path: string, body: FormData): Promise<T> {
  const csrfToken = await ensureCsrfCookie()

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'X-CSRFToken': csrfToken,
    },
    body,
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

export function uploadClientPaymentReceipt(
  quotaId: number,
  payload: UploadClientPaymentReceiptPayload,
) {
  const formData = new FormData()
  formData.append('amount', payload.amount)
  formData.append('details', payload.details)
  formData.append('receiptFile', payload.receiptFile)

  return requestFormDataWithBody<UploadClientPaymentReceiptResponse>(
    `/api/client/pagos/cuotas/${quotaId}/comprobante/`,
    formData,
  )
}
