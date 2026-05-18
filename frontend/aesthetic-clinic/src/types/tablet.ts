export interface TabletKioskLoginResponse {
  detail: string
  kiosk: {
    id: number
    codigo: string
    nombre: string
    branchId: number
  }
}

export interface TabletClientLoginResponse {
  detail: string
  clientId: number
  fullName: string
}

export interface TabletResetResponse {
  detail: string
}

export interface TabletAppointmentItem {
  rawId: number
  operationRawId: number
  operation: string
  dateTime: string
  status: string
}

export interface TabletProcedureOption {
  operation: {
    rawId: number
    procedure: string
    reserveMessage: string
  }
  appointments: TabletAppointmentItem[]
}

export interface TabletCurrentAppointmentResponse {
  currentAppointment: TabletAppointmentItem | null
  pendingAppointmentsCount: number
  procedureOptions: TabletProcedureOption[]
}

export interface TabletConfirmResponse {
  detail: string
  appointment: TabletAppointmentItem
}
