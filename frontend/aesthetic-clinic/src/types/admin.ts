import type {
  ClientAppointment,
  ClientOperation,
  ClientPayment,
  ClientQuota,
  ClientReservationAvailabilityResponse,
  CreateClientReservationResponse,
} from './client'

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
  rawId: number
  patient: string
  operation: string
  amount: string
  submittedAt: string
  bank: string
  status: 'pendiente' | 'observado' | 'aprobado'
  quota?: string
  note?: string
}

export type UpcomingPayment = {
  id: number
  dueDate: string
  dueDateLabel: string
  amount: string
  client: string
  clientId: number
  operation: string
  operationId: number
  quotaNumber: number
  isToday: boolean
  isThisWeek: boolean
}

export type PaymentQrConfig = {
  hasQr: boolean
  qrImageUrl: string
  instructions: string
}

export type AgendaItem = {
  id: string
  time: string
  dateLabel: string
  patient: string
  procedure: string
  operationId: number
  specialist: string
  status: 'programada' | 'biometria' | 'confirmada'
  isToday: boolean
  isThisWeek: boolean
}

export type ProspectLead = {
  id: string
  rawId?: number
  name: string
  firstName?: string
  lastName?: string
  phone: string
  interest: string
  registeredBy: string
  stage: string
  state?: string
  stateValue?: string
  observations?: string
  createdAt?: string
  convertedAt?: string
  medicalAppointments?: ProspectMedicalAppointment[]
}

export type ProspectMedicalAppointment = {
  id: string
  rawId: number
  prospectRawId: number
  dateTime: string
  specialist: string
  service: string
  status: string
  statusValue?: string
  statusTone?: 'approved' | 'danger' | 'observed' | 'pending'
  canCancel: boolean
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
  rawId: number
  specialist: string
  specialty: string
  specialtyIds: number[]
  load: number
  pendingValidations: number
  username: string
  email: string
  primerNombre: string
  segundoNombre: string
  apellidoPaterno: string
  apellidoMaterno: string
  ci: string
  phone?: string
  status: string
  isActive: boolean
  activeOperations?: number
  upcomingAppointments?: number
  observations?: string
}

export type ClientSnapshot = {
  id: string
  rawId: number
  name: string
  phone: string
  ci: string
  status: string
  activeOperations: number
  totalOperations: number
  lastAnalysis: string
  scheduledAppointments: ClientScheduledAppointment[]
}

export type ClientScheduledAppointment = {
  id: string
  rawId: number
  dateTime: string
  operation: string
  specialist: string
  status: string
}

export type AdminClientDetailResponse = {
  client: ClientSnapshot
  metrics: AdminMetric[]
  operations: ClientOperation[]
  appointments: ClientAppointment[]
  sessions: ClientAppointment[]
  payments: ClientPayment[]
  pendingQuotas: ClientQuota[]
}

export type AdminClientReservationAvailabilityResponse = {
  operation: ClientOperation
}

export type CreateAdminClientReservationResponse = CreateClientReservationResponse

export type AdminClientFreeMedicalAvailabilityResponse = {
  client: ClientSnapshot
  service: {
    rawId: number
    name: string
  }
}

export type CreateAdminClientFreeMedicalAppointmentResponse = {
  detail: string
  appointment: ClientAppointment
}

export type AdminClientInactivateResponse = {
  detail: string
  client: ClientSnapshot
}

export type AdminProspectMedicalAvailabilityResponse = {
  prospect: ProspectLead
  service: {
    rawId: number
    name: string
  }
  calendar: ClientReservationAvailabilityResponse['calendar']
}

export type CreateAdminProspectMedicalAppointmentResponse = {
  detail: string
  appointment: ProspectMedicalAppointment
}

export type CancelAdminProspectMedicalAppointmentResponse = {
  detail: string
  appointment: ProspectMedicalAppointment
}

export type DashboardResponse = {
  metrics: AdminMetric[]
  alerts: AdminAlert[]
}

export type DashboardPaymentsResponse = {
  month: number
  year: number
  payments: UpcomingPayment[]
}

export type DashboardAgendaResponse = {
  month: number
  year: number
  agenda: AgendaItem[]
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
  rawId: number
  dateTime: string
  specialist: string
  status: string
  biometricStatus: string
  canConfirmBiometric: boolean
}

export type OperationDetailQuota = {
  id: string
  rawId: number
  number: number
  amount: string
  amountValue: string
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
  hasBiometricEnrollment: boolean
  biometricMockTemplate: string
  appointments: OperationDetailAppointment[]
  quotas: OperationDetailQuota[]
}

export type OperationDetailResponse = {
  operation: OperationDetailData
}

export type UpdateAdminOperationDetailsPayload = {
  details: string
  recommendations: string
  sessionsTotal: number
}

export type UpdateAdminOperationPricePayload = {
  priceTotal: string
  quotaCount: number
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

export type UpdateAdminPaymentStatusPayload = {
  status: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO'
  note: string
}

export type UpdateAdminPaymentStatusResponse = {
  detail: string
  payment: VerificationPayment
}

export type CatalogsResponse = {
  metrics: AdminMetric[]
  catalogs: CatalogHealthItem[]
}

export type AdminCatalogKey =
  | 'todos-los-servicios'
  | 'procedimientos-esteticos'
  | 'tipos-servicio'
  | 'campos-ficha'
  | 'patologias-cutaneas'
  | 'especialidades'
  | 'grupos-opciones'

export type AdminCatalogFormValue = string | number | boolean | null

export type AdminCatalogFieldOption = {
  value: string | number
  label: string
  secondaryLabel?: string
}

export type AdminCatalogFieldDefinition = {
  name: string
  label: string
  inputType: 'text' | 'textarea' | 'number' | 'select' | 'checkbox'
  required: boolean
  placeholder?: string
  hint?: string
  valueType: 'string' | 'number' | 'boolean'
  allowEmpty: boolean
  minValue?: number
  options?: AdminCatalogFieldOption[]
}

export type AdminCatalogMetadataItem = {
  label: string
  value: string
}

export type AdminCatalogEntry = {
  id: number
  title: string
  subtitle: string
  active: boolean
  activeLabel: string
  metadata: AdminCatalogMetadataItem[]
  values: Record<string, AdminCatalogFormValue>
}

export type AdminCatalogDetailResponse = {
  catalog: {
    key: AdminCatalogKey
    title: string
    description: string
    createLabel: string
  }
  metrics: AdminMetric[]
  fields: AdminCatalogFieldDefinition[]
  items: AdminCatalogEntry[]
}

export type AdminCatalogMutationResponse = {
  detail: string
  item: AdminCatalogEntry
}

export type UpdateAdminCatalogItemStatePayload = {
  active: boolean
}

export type StaffResponse = {
  metrics: AdminMetric[]
  staff: StaffCapacityItem[]
  specialtyOptions: Array<{
    id: number
    label: string
  }>
}

export type CreateAdminStaffPayload = {
  username: string
  password: string
  email: string
  primerNombre: string
  segundoNombre: string
  apellidoPaterno: string
  apellidoMaterno: string
  ci: string
  telefono: string
  observaciones: string
  specialtyIds: number[]
}

export type UpdateAdminStaffPayload = Omit<CreateAdminStaffPayload, 'password'> & {
  password?: string
}

export type UpdateAdminStaffStatusPayload = {
  active: boolean
}

export type AdminStaffMutationResponse = {
  detail: string
  staffMember: StaffCapacityItem
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

export type CheckAdminProspectDuplicatesResponse = {
  exists: boolean
  message?: string
  match?: {
    id: number
    name: string
    branch: string
  }
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

export type AdminBranch = {
  id: number
  nombre: string
  es_principal: boolean
}

export type AdminHabitualSchedule = {
  id: number
  specialistId: number
  branchId: number
  startDate: string
  endDate: string | null
  weekdayCodes: number[]
  weekdayLabels: string[]
  startTime: string
  endTime: string
  detail: string
  active: boolean
}

export type AdminSpecialistAvailabilityException = {
  id: number
  specialistId: number
  branchId: number
  date: string
  dateLabel: string
  type: 'AGREGAR' | 'BLOQUEAR'
  typeLabel: string
  startTime: string
  endTime: string
  detail: string
  active: boolean
}

export type AdminGlobalAvailabilityBlock = {
  id: number
  date: string
  dateLabel: string
  active: boolean
  detail: string
}

export type AdminConcurrencyCheckResponse = {
  concurrency: number
  presentes: Array<{
    id: number
    usuario__primer_nombre: string
    usuario__apellido_paterno: string
    especialidad: string
  }>
  hora_inicio?: string
  hora_fin?: string
  hora_seleccionada?: string
}

export type AdminAvailabilityResponse = {
  metrics: AdminMetric[]
  branches: AdminBranch[]
  filters: {
    specialists: AdminAvailabilityOption[]
    weekdayOptions: AdminWeekdayOption[]
  }
  habitualRules: AdminHabitualSchedule[]
  exceptions: AdminSpecialistAvailabilityException[]
  globalBlocks: AdminGlobalAvailabilityBlock[]
}

export type UpsertAdminHabitualSchedulePayload = {
  specialistId?: number | null
  specialistIds?: number[]
  branchId: number | null
  startDate: string
  endDate: string | null
  weekdayCodes: number[]
  startTime: string
  endTime: string
  detail: string
}

export type CreateAdminAvailabilityExceptionPayload = {
  specialistId: number | null
  branchId: number | null
  type: 'AGREGAR' | 'BLOQUEAR'
  dates: string[]
  startTime: string
  endTime: string
  detail: string
}

export type ManageAdminGlobalAvailabilityPayload = {
  action: 'BLOQUEAR' | 'RESTAURAR'
  date: string
  detail: string
}

export type AdminAvailabilityMutationResponse = {
  detail: string
}

export type AdminCancelAppointmentResponse = {
  detail: string
  appointment: ClientScheduledAppointment
}
