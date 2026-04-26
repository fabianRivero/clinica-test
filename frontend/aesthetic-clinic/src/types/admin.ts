export type AdminMetric = {
  id: string
  label: string
  value: string
  delta: string
  tone: 'primary' | 'success' | 'warning' | 'danger'
}

export type AdminAlert = {
  id: string
  title: string
  description: string
  severity: 'high' | 'medium' | 'low'
  action: string
}

export type VerificationPayment = {
  id: string
  patient: string
  operation: string
  amount: string
  submittedAt: string
  bank: string
  status: 'pendiente' | 'observado' | 'aprobado'
  quota?: string
  dueDate?: string
  verifier?: string
  receiptUrl?: string
  note?: string
}

export type PaymentQrConfig = {
  hasQr: boolean
  qrImageUrl: string
  instructions: string
}

export type AgendaItem = {
  id: string
  time: string
  patient: string
  procedure: string
  specialist: string
  status: 'programada' | 'biometria' | 'confirmada'
}

export type ProspectLead = {
  id: string
  rawId?: number
  name: string
  phone: string
  interest: string
  registeredBy: string
  stage: 'nuevo' | 'seguimiento' | 'propuesta' | 'convertido'
  state?: string
  createdAt?: string
  convertedAt?: string
}

export type OperationCardData = {
  id: string
  rawId: number
  patient: string
  procedure: string
  specialist: string
  sessions: string
  nextAppointment: string
  quotaStatus: string
  status?: string
  price?: string
}

export type CatalogHealthItem = {
  id: string
  name: string
  count: number
  note: string
}

export type StaffCapacityItem = {
  id: string
  specialist: string
  specialty: string
  load: number
  pendingValidations: number
  phone?: string
  activeOperations?: number
  upcomingAppointments?: number
}

export type ClientSnapshot = {
  id: string
  name: string
  phone: string
  status: string
  activeOperations: number
  totalOperations: number
  lastAnalysis: string
}

export type DashboardResponse = {
  metrics: AdminMetric[]
  payments: VerificationPayment[]
  agenda: AgendaItem[]
  prospects: ProspectLead[]
  alerts: AdminAlert[]
  operations: OperationCardData[]
  catalogHealth: CatalogHealthItem[]
  staffCapacity: StaffCapacityItem[]
}

export type ProspectsResponse = {
  metrics: AdminMetric[]
  prospects: ProspectLead[]
  clients: ClientSnapshot[]
}

export type OperationsResponse = {
  metrics: AdminMetric[]
  operations: OperationCardData[]
}

export type OperationDetailAppointment = {
  id: string
  dateTime: string
  specialist: string
  status: string
  biometricStatus: string
}

export type OperationDetailQuota = {
  id: string
  number: number
  dueDate: string
  status: string
  paymentsCount: number
}

export type OperationDetailData = {
  id: string
  rawId: number
  patient: string
  procedure: string
  serviceType: string
  procedureType: string
  specialist: string
  sessions: string
  nextAppointment: string
  quotaStatus: string
  status: string
  price: string
  startDate: string
  endDate: string
  zonaGeneral: string
  zonaEspecifica: string
  detallesOperacion: string
  recomendaciones: string
  medicalRecordDate: string
  medicalRecordReason: string
  medicalRecordNotes: string
  consentAccepted: boolean
  documentPdfUrl: string
  documentPdfName: string
  appointments: OperationDetailAppointment[]
  quotas: OperationDetailQuota[]
}

export type OperationDetailResponse = {
  operation: OperationDetailData
}

export type PaymentsResponse = {
  metrics: AdminMetric[]
  paymentQrConfig: PaymentQrConfig
  payments: VerificationPayment[]
}

export type UpdateAdminPaymentQrConfigResponse = {
  detail: string
  paymentQrConfig: PaymentQrConfig
}

export type CatalogsResponse = {
  metrics: AdminMetric[]
  catalogs: CatalogHealthItem[]
}

export type StaffResponse = {
  metrics: AdminMetric[]
  staff: StaffCapacityItem[]
}

export type CreateAdminProspectPayload = {
  nombres: string
  apellidos: string
  telefono: string
  estado: 'PASAJERO' | 'DESCARTADO'
  observaciones: string
}

export type CreateAdminProspectResponse = {
  detail: string
  prospect: ProspectLead
}

export type AdminAvailabilityOption = {
  id: number
  label: string
  secondaryLabel?: string
}

export type AdminWeekdayOption = {
  value: number
  label: string
}

export type AdminTimeSlot = {
  id: number
  label: string
  startTime: string
  endTime: string
  detail: string
  active: boolean
  futureSlots: number
  reservedFutureSlots: number
}

export type AdminSpecialistAvailabilitySummary = {
  id: number
  label: string
  secondaryLabel: string
  futureSlots: number
  nextSlot: string
  habitualRules: number
  exceptions: number
}

export type AdminHabitualSchedule = {
  id: number
  specialistId: number
  specialist: string
  startDate: string
  endDate: string
  weekdayCodes: number[]
  weekdayLabels: string[]
  timeSlotIds: number[]
  timeSlotLabels: string[]
  scope: string[]
  serviceTypeIds: number[]
  procedureTypeIds: number[]
  procedureIds: number[]
  active: boolean
  detail: string
}

export type AdminSpecialistAvailabilityException = {
  id: number
  specialistId: number
  specialist: string
  date: string
  dateLabel: string
  type: 'AGREGAR' | 'BLOQUEAR'
  typeLabel: string
  timeSlotIds: number[]
  timeSlotLabels: string[]
  scope: string[]
  serviceTypeIds: number[]
  procedureTypeIds: number[]
  procedureIds: number[]
  active: boolean
  detail: string
}

export type AdminGlobalAvailabilityBlock = {
  id: number
  date: string
  dateLabel: string
  active: boolean
  detail: string
}

export type AdminAvailabilitySlot = {
  id: string
  rawId: number
  specialistId: number
  specialist: string
  dateTime: string
  date: string
  time: string
  timeRange: string
  timeSlotId: number | null
  status: 'disponible' | 'reservado' | 'expirado' | 'inactivo'
  coverage: string[]
  patient: string
  operation: string
  reservationState: string
  active: boolean
  detail: string
}

export type AdminAvailabilityResponse = {
  metrics: AdminMetric[]
  filters: {
    specialists: AdminAvailabilityOption[]
    serviceTypes: AdminAvailabilityOption[]
    procedureTypes: AdminAvailabilityOption[]
    procedures: AdminAvailabilityOption[]
    timeSlots: AdminTimeSlot[]
    weekdayOptions: AdminWeekdayOption[]
  }
  specialistSummaries: AdminSpecialistAvailabilitySummary[]
  habitualRules: AdminHabitualSchedule[]
  exceptions: AdminSpecialistAvailabilityException[]
  globalBlocks: AdminGlobalAvailabilityBlock[]
  slots: AdminAvailabilitySlot[]
}

export type CreateAdminTimeSlotPayload = {
  startTime: string
  endTime: string
  detail: string
  order?: number
}

export type UpdateAdminTimeSlotPayload = CreateAdminTimeSlotPayload & {
  active: boolean
}

export type UpsertAdminHabitualSchedulePayload = {
  specialistId: number | null
  startDate: string
  endDate: string
  weekdayCodes: number[]
  timeSlotIds: number[]
  serviceTypeIds: number[]
  procedureTypeIds: number[]
  procedureIds: number[]
  detail: string
}

export type CreateAdminAvailabilityExceptionPayload = {
  specialistId: number | null
  type: 'AGREGAR' | 'BLOQUEAR'
  dates: string[]
  timeSlotIds: number[]
  serviceTypeIds: number[]
  procedureTypeIds: number[]
  procedureIds: number[]
  detail: string
}

export type ManageAdminGlobalAvailabilityPayload = {
  action: 'BLOQUEAR' | 'RESTAURAR'
  date: string
  detail: string
}

export type AdminAvailabilityMutationResponse = {
  detail: string
  syncSummary: {
    created: number
    updated: number
    deactivated: number
  }
}
