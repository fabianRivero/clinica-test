import type { AdminMetric } from './admin'
import type { PaymentQrConfig } from './admin'
import type {
  ClientOperation,
  ClientAppointment,
  ClientPayment,
  ClientQuota,
  ClientReservationAvailabilityResponse,
  CreateClientReservationResponse,
} from './common'
export type {
  ClientOperation,
  ClientAppointment,
  ClientPayment,
  ClientQuota,
  ClientReservationAvailabilityResponse,
  CreateClientReservationResponse,
}

export type ClientAlert = {
  id: string
  title: string
  description: string
  severity: 'high' | 'medium' | 'low'
  action: string
}

export type ClientWelcome = {
  name: string
  status: string
  phone: string
  ci: string
  lastAnalysis: string
  activeOperations: number
  totalOperations: number
}

export type ClientDashboardResponse = {
  welcome: ClientWelcome
  metrics: AdminMetric[]
  alerts: ClientAlert[]
  operations: ClientOperation[]
  pendingQuotas: ClientQuota[]
  recentPayments: ClientPayment[]
  upcomingAppointments: ClientAppointment[]
}

export type ClientTreatmentsResponse = {
  metrics: AdminMetric[]
  operations: ClientOperation[]
}

export type ClientPaymentsResponse = {
  metrics: AdminMetric[]
  paymentQrConfig: PaymentQrConfig
  activeQuotas: ClientQuota[]
  payments: ClientPayment[]
}

export type ClientReservationsResponse = {
  metrics: AdminMetric[]
  appointments: ClientAppointment[]
  operations: ClientOperation[]
}

export type CreateClientReservationPayload = {
  slotId: number
}

export type UpdateClientReservationPayload = {
  slotId: number
}

export type UpdateClientReservationResponse = {
  detail: string
  appointment: ClientAppointment
  operation: ClientOperation
}

export type CancelClientReservationResponse = {
  detail: string
  appointment: ClientAppointment
  operation: ClientOperation
}

export type UploadClientPaymentReceiptPayload = {
  amount: string
  details: string
  receiptFile: File
}

export type UploadClientPaymentReceiptResponse = {
  detail: string
  payment: ClientPayment
  quota: ClientQuota
}
