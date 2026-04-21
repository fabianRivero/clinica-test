import type {
  ClientDashboardResponse,
  ClientPaymentsResponse,
  ClientReservationsResponse,
  ClientTreatmentsResponse,
} from '../../types/client'

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
