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

export type PaymentsResponse = {
  metrics: AdminMetric[]
  payments: VerificationPayment[]
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

export type AdminAvailabilitySlot = {
  id: string
  rawId: number
  specialist: string
  dateTime: string
  date: string
  time: string
  status: 'disponible' | 'reservado' | 'expirado' | 'inactivo'
  coverage: string[]
  patient: string
  operation: string
  reservationState: string
  active: boolean
}

export type AdminAvailabilityResponse = {
  metrics: AdminMetric[]
  filters: {
    specialists: AdminAvailabilityOption[]
    serviceTypes: AdminAvailabilityOption[]
    procedureTypes: AdminAvailabilityOption[]
    procedures: AdminAvailabilityOption[]
  }
  slots: AdminAvailabilitySlot[]
}

export type CreateAdminAvailabilityPayload = {
  specialistId: number | null
  dates: string[]
  times: string[]
  serviceTypeIds: number[]
  procedureTypeIds: number[]
  procedureIds: number[]
}

export type CreateAdminAvailabilityResponse = {
  detail: string
  createdCount: number
  updatedCount: number
  conflictCount: number
}
