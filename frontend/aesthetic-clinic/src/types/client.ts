import type { AdminMetric } from './admin'

export type ClientAlert = {
  id: string
  title: string
  description: string
  severity: 'high' | 'medium' | 'low'
  action: string
}

export type ClientSessionSummary = {
  total: number
  confirmed: number
  pendingBiometric: number
  reserved: number
  available: number
}

export type ClientOperation = {
  id: string
  rawId: number
  procedure: string
  serviceType: string
  specialist: string
  status: string
  statusTone: 'primary' | 'success' | 'warning' | 'danger'
  price: string
  zone: string
  startedAt: string
  endedAt: string
  nextAppointment: string
  recommendations: string
  details: string
  sessions: ClientSessionSummary
  canReserve: boolean
  reserveMessage: string
  quotaSummary: string
}

export type ClientQuota = {
  id: string
  operation: string
  quotaLabel: string
  amount: string
  dueDate: string
  status: string
  statusTone: 'approved' | 'pending' | 'danger'
  latestPaymentStatus: string
  latestPaymentTone: 'approved' | 'observed' | 'pending' | 'neutral'
  canUploadReceipt: boolean
}

export type ClientPayment = {
  id: string
  operation: string
  quotaLabel: string
  amount: string
  submittedAt: string
  status: string
  statusTone: 'approved' | 'observed' | 'pending'
  dueDate: string
  receiptUrl: string
  verifier: string
  note: string
}

export type ClientAppointment = {
  id: string
  rawId: number
  operation: string
  specialist: string
  dateTime: string
  status: string
  statusTone: 'approved' | 'warning' | 'danger' | 'observed' | 'pending'
  biometric: string
  details: string
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
  activeQuotas: ClientQuota[]
  payments: ClientPayment[]
}

export type ClientReservationsResponse = {
  metrics: AdminMetric[]
  appointments: ClientAppointment[]
  operations: ClientOperation[]
}

export type ClientReservationSlot = {
  slotId: number
  specialistId: number
  specialist: string
  date: string
  time: string
  dateTimeLabel: string
}

export type ClientReservationCalendarDay = {
  date: string
  label: string
  slotCount: number
  weekday: string
}

export type ClientReservationAvailabilityResponse = {
  operation: ClientOperation
  calendar: {
    windowStart: string | null
    windowEnd: string | null
    monthLabel: string
    availableDates: ClientReservationCalendarDay[]
    slotsByDate: Record<string, ClientReservationSlot[]>
    slotCount: number
  }
}

export type CreateClientReservationPayload = {
  slotId: number
}

export type CreateClientReservationResponse = {
  detail: string
  appointment: ClientAppointment
  operation: ClientOperation
}
