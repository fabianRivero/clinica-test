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
  name: string
  phone: string
  interest: string
  registeredBy: string
  stage: 'nuevo' | 'seguimiento' | 'propuesta' | 'convertido'
}

export type OperationCardData = {
  id: string
  patient: string
  procedure: string
  specialist: string
  sessions: string
  nextAppointment: string
  quotaStatus: string
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
}
