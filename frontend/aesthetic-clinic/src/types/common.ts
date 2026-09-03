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
  paidAmount?: string
  paidAmountValue?: string
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
  /**
   * `VIRTUAL` (default for legacy rows), `FISICO` for desk payments, or
   * `MIXTO` for split payments. Rendered only when not `VIRTUAL`.
   */
  paymentMethod?: string
  /** Formatted "Bs X.XX" — present for any method. */
  physicalAmount?: string
  virtualAmount?: string
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
  canCancelFromVerification: boolean
  isFreeMedicalAppointment?: boolean
  // Planning fields (populated at reservation; used by the RescheduleModal
  // prefill and the 'Datos reales al cierre' comparison modal).
  duracionEstimadaMinutos?: number | null
  procedimientoPlanificado?: string
  zonaCuerpoPlanificada?: string
  /**
   * Backend response shape (object with name + id) OR legacy shape
   * (just the id). The frontend tolerates both — the modal's selection
   * logic reads the id from either form.
   */
  especialistasPlanificados?: Array<number | { especialista_id: number }>
  maquinariaPlanificada?: Array<{ maquinariaId: number; cantidad: number }>
  // Real-time close data (populated via POST /cerrar/ after the client
  // confirms and the admin sets the close fields).
  hasRealTimeData?: boolean
  horaRealInicio?: string | null
  horaRealFin?: string | null
  procedimientoRealizado?: string
  zonaCuerpoRealizada?: string
  descripcionGeneral?: string
  notasPrevias?: string
  notasPost?: string
  especialistasAtendieron?: Array<{
    especialista_id: number
    especialista__usuario__first_name?: string
    especialista__usuario__last_name?: string
    especialista__usuario__username?: string
  }>
  maquinariaUtilizada?: Array<{
    maquinaria_id: number
    cantidad: number
    maquinaria__nombre?: string
    maquinaria__marca?: string
  }>
  fotoAntesUrl?: string
  fotoDespuesUrl?: string
  // --- Cita-level payment breakdown (populated by the admin detail /
  // operation detail payloads; absent on the client portal + kiosko
  // payloads because those pages don't need the breakdown).
  /** Cita price (Bs, formatted "0.00"); backend default is 0. */
  precio?: string
  /** Residual balance after APROBADO `PagoCita` rows (Bs, formatted). */
  saldoPendiente?: string
  /** Count of `PagoCita` rows attached to the cita. */
  pagos_count?: number
  /** Read serializer payments array. */
  pagos?: Array<{
    id: number
    monto_pagado: string
    metodo_pago: 'VIRTUAL' | 'FISICO' | 'MIXTO'
    monto_fisico: string
    monto_virtual: string
    comprobante_url: string
    estado_verificacion: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO'
    detalles_pago: string
    created_at: string
  }>
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