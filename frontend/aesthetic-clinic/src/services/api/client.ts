import type {
  CancelClientReservationResponse,
  ClientReservationAvailabilityResponse,
  ClientDashboardResponse,
  ClientReservationsResponse,
  ClientPaymentsResponse,
  ClientTreatmentsResponse,
  CreateClientReservationPayload,
  CreateClientReservationResponse,
  UpdateClientReservationPayload,
  UpdateClientReservationResponse,
  UploadClientPaymentReceiptPayload,
  UploadClientPaymentReceiptResponse,
} from '../../types/client'
import { requestJsonNoBranch, requestJsonWithBody, requestFormDataWithBody } from './apiClient'
import { normalizeClientAppointment, normalizeClientAppointments } from '../../mappers/clientVerification'

export async function getClientDashboard() {
  const response = await requestJsonNoBranch<ClientDashboardResponse>('/api/client/dashboard/')
  return {
    ...response,
    upcomingAppointments: normalizeClientAppointments(response.upcomingAppointments),
  }
}

export function getClientTreatments() {
  return requestJsonNoBranch<ClientTreatmentsResponse>('/api/client/tratamientos/')
}

export function getClientPayments() {
  return requestJsonNoBranch<ClientPaymentsResponse>('/api/client/pagos/')
}

export async function getClientReservations() {
  const response = await requestJsonNoBranch<ClientReservationsResponse>('/api/client/reservas/')
  return {
    ...response,
    appointments: normalizeClientAppointments(response.appointments),
  }
}

export async function getClientReservationAvailability(operationId: string) {
  const response = await requestJsonNoBranch<ClientReservationAvailabilityResponse>(
    `/api/client/reservas/${operationId}/disponibilidad/`,
  )
  return {
    ...response,
    appointment: response.appointment ? normalizeClientAppointment(response.appointment) : response.appointment,
  }
}

export async function getClientEditReservationAvailability(appointmentId: string) {
  const response = await requestJsonNoBranch<ClientReservationAvailabilityResponse>(
    `/api/client/reservas/citas/${appointmentId}/disponibilidad/`,
  )
  return {
    ...response,
    appointment: response.appointment ? normalizeClientAppointment(response.appointment) : response.appointment,
  }
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

export function updateClientReservation(
  appointmentId: string,
  payload: UpdateClientReservationPayload,
) {
  return requestJsonWithBody<UpdateClientReservationResponse>(
    `/api/client/reservas/citas/${appointmentId}/actualizar/`,
    payload,
  )
}

export function cancelClientReservation(appointmentId: number) {
  return requestJsonWithBody<CancelClientReservationResponse>(
    `/api/client/reservas/citas/${appointmentId}/cancelar/`,
    {},
  )
}

export function uploadClientPaymentReceipt(
  quotaId: number,
  payload: UploadClientPaymentReceiptPayload,
) {
  const formData = new FormData()
  formData.append('paymentMethod', payload.paymentMethod)
  formData.append('amount', payload.amount)
  if (payload.montoFisico) formData.append('montoFisico', payload.montoFisico)
  if (payload.montoVirtual) formData.append('montoVirtual', payload.montoVirtual)
  formData.append('details', payload.details)
  if (payload.receiptFile) formData.append('receiptFile', payload.receiptFile)

  return requestFormDataWithBody<UploadClientPaymentReceiptResponse>(
    `/api/client/pagos/cuotas/${quotaId}/comprobante/`,
    formData,
  )
}
