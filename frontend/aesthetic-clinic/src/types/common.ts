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
  branch: string
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
  firstPaymentVerified: boolean
  reserveMessage: string
  quotaSummary: string
}

export type ClientQuota = {
  id: string
  rawId: number
  operation: string
  quotaLabel: string
  amount: string
  amountValue: string
  dueDate: string
  status: string
  statusTone: 'approved' | 'pending' | 'danger' | 'observed'
  latestPaymentStatus: string
  latestPaymentTone: 'approved' | 'observed' | 'pending' | 'neutral'
  canUploadReceipt: boolean
  canReplaceReceipt: boolean
  uploadActionLabel: string
}

export type ClientPayment = {
  id: string
  rawId: number
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
  operationRawId: number | null
  operation: string
  specialist: string
  dateTime: string
  status: string
  statusTone: 'approved' | 'warning' | 'danger' | 'observed' | 'pending'
  verificationStatus: 'pendiente' | 'verificada' | 'no_requerida'
  verificationMethod: 'biometria' | 'qr' | 'manual' | 'otro' | null
  details: string
  canManage: boolean
  canMarkPendingBiometric: boolean
  canConfirmBiometric: boolean
  biometricMockTemplate: string
  isFreeMedicalAppointment?: boolean
}

export type ClientReservationSlot = {
  slotId: number
  specialistId: number
  specialist: string
  date: string
  time: string
  timeRange: string
  dateTimeLabel: string
  isCurrentSelection: boolean
}

export type ClientReservationCalendarDay = {
  date: string
  label: string
  slotCount: number
  weekday: string
}

export type ClientReservationAvailabilityResponse = {
  operation: ClientOperation
  appointment?: ClientAppointment
  currentSlotId?: number | null
  calendar: {
    windowStart: string | null
    windowEnd: string | null
    monthLabel: string
    availableDates: ClientReservationCalendarDay[]
    slotsByDate: Record<string, ClientReservationSlot[]>
    slotCount: number
  }
}

export type CreateClientReservationResponse = {
  detail: string
  appointment: ClientAppointment
  operation: ClientOperation
}