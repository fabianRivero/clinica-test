import type {
  AdminAvailabilityResponse,
  AdminBranch,
  AdminCatalogDetailResponse,
  AdminCatalogKey,
  AdminCatalogMutationResponse,
  AdminStaffMutationResponse,
  AdminAvailabilityMutationResponse,
  AdminCancelAppointmentResponse,
  AdminClientDetailResponse,
  AdminExpenseDeleteResponse,
  AdminExpenseMutationResponse,
  AdminClientFreeMedicalAvailabilityResponse,
  AdminClientInactivateResponse,
  AdminClientReservationAvailabilityResponse,
  AdminProspectMedicalAvailabilityResponse,
  CancelAdminProspectMedicalAppointmentResponse,
  CatalogsResponse,
  CreateAdminClientFreeMedicalAppointmentResponse,
  CreateAdminClientReservationResponse,
  CreateAdminProspectMedicalAppointmentResponse,
  CreateAdminStaffPayload,
  CreateAdminAvailabilityExceptionPayload,
  CreateAdminProspectPayload,
  CreateAdminProspectResponse,
  DashboardAgendaResponse,
  DashboardPaymentsResponse,
  DashboardResponse,
  ExpensesResponse,
  ManageAdminGlobalAvailabilityPayload,
  OperationDetailResponse,
  OperationsResponse,
  PaymentsResponse,
  ProspectsResponse,
  StaffResponse,
  UpdateAdminOperationDetailsPayload,
  UpdateAdminOperationPricePayload,
  UpdateAdminCatalogItemStatePayload,
  UpdateAdminStaffPayload,
  UpdateAdminStaffStatusPayload,
  UpsertAdminHabitualSchedulePayload,
  UpsertAdminExpensePayload,
  UpdateAdminPaymentQrConfigResponse,
  UpdateAdminPaymentStatusPayload,
  UpdateAdminPaymentStatusResponse,
  AdminConcurrencyCheckResponse,
  CheckAdminProspectDuplicatesResponse,
} from '../../types/admin'
import type {
  ProspectConversionFinalizeResponse,
  ProspectConversionBiometricData,
  ProspectConversionMedicalData,
  ProspectConversionOperationData,
  ProspectConversionResponse,
  ProspectConversionUserData,
} from '../../types/prospectConversion'
import { ensureCsrfCookie } from './auth'
import { getActiveBranchId } from './activeBranch'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

function _appendBranchId(path: string): string {
  // Ya no añadimos branchId a la URL porque usamos el encabezado X-Selected-Branch-Id
  return path
}

async function requestJson<T>(path: string): Promise<T> {
  const branchId = getActiveBranchId()
  const response = await fetch(`${API_BASE_URL}${_appendBranchId(path)}`, {
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'X-Selected-Branch-Id': branchId ? String(branchId) : '',
    },
  })

  if (!response.ok) {
    throw new Error(`No se pudo cargar ${path} (${response.status})`)
  }

  return (await response.json()) as T
}

async function requestJsonWithBody<T>(path: string, body: unknown): Promise<T> {
  const csrfToken = await ensureCsrfCookie()
  const branchId = getActiveBranchId()

  const response = await fetch(`${API_BASE_URL}${_appendBranchId(path)}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
      'X-Selected-Branch-Id': branchId ? String(branchId) : '',
    },
    body: JSON.stringify(body),
  })

  const responseBody = (await response.json().catch(() => null)) as
    | { detail?: string; errors?: Record<string, string> }
    | null

  if (!response.ok) {
    const error = new Error(responseBody?.detail || `No se pudo completar ${path} (${response.status})`) as Error & {
      fieldErrors?: Record<string, string>
    }
    if (responseBody?.errors) {
      error.fieldErrors = responseBody.errors
    }
    throw error
  }

  return responseBody as T
}

async function requestFormDataWithBody<T>(path: string, body: FormData): Promise<T> {
  const csrfToken = await ensureCsrfCookie()
  const branchId = getActiveBranchId()

  const response = await fetch(`${API_BASE_URL}${_appendBranchId(path)}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'X-CSRFToken': csrfToken,
      'X-Selected-Branch-Id': branchId ? String(branchId) : '',
    },
    body,
  })

  const responseBody = (await response.json().catch(() => null)) as
    | { detail?: string; errors?: Record<string, string> }
    | null

  if (!response.ok) {
    const error = new Error(responseBody?.detail || `No se pudo completar ${path} (${response.status})`) as Error & {
      fieldErrors?: Record<string, string>
    }
    if (responseBody?.errors) {
      error.fieldErrors = responseBody.errors
    }
    throw error
  }

  return responseBody as T
}

export function getAdminDashboard() {
  return requestJson<DashboardResponse>('/api/admin/dashboard/')
}

export function getAdminDashboardPayments(month: number, year: number) {
  return requestJson<DashboardPaymentsResponse>(`/api/admin/dashboard/payments/?month=${month}&year=${year}`)
}

export function getAdminDashboardAgenda(month: number, year: number) {
  return requestJson<DashboardAgendaResponse>(`/api/admin/dashboard/agenda/?month=${month}&year=${year}`)
}

export function getAdminProspects(_branchId?: number) {
  // El branchId ahora viaja por el encabezado X-Selected-Branch-Id inyectado en requestJson
  return requestJson<ProspectsResponse>('/api/admin/prospectos/')
}

export function getAdminProspectMedicalAvailability(prospectId: number, branchId?: number) {
  const query = branchId ? `?branchId=${branchId}` : ''
  return requestJson<AdminProspectMedicalAvailabilityResponse>(
    `/api/admin/prospectos/${prospectId}/cita-medica/disponibilidad/${query}`,
  )
}

export function createAdminProspectMedicalAppointment(prospectId: number, data: { branchId: number, dateTime: string }) {
  return requestJsonWithBody<CreateAdminProspectMedicalAppointmentResponse>(
    `/api/admin/prospectos/${prospectId}/cita-medica/reservar/`,
    data,
  )
}

export function cancelAdminProspectMedicalAppointment(appointmentId: number) {
  return requestJsonWithBody<CancelAdminProspectMedicalAppointmentResponse>(
    `/api/admin/prospectos/citas-medicas/${appointmentId}/cancelar/`,
    {},
  )
}

export function updateAdminProspect(
  prospectId: number,
  data: {
    primerNombre?: string
    segundoNombre?: string
    apellidoPaterno?: string
    apellidoMaterno?: string
    phone?: string
    observations?: string
    stateValue?: 'PASAJERO' | 'DESCARTADO'
    appointmentStatuses?: Record<number, string>
  },
) {
  return requestJsonWithBody<{ detail: string; prospect: any }>(
    `/api/admin/prospectos/${prospectId}/actualizar/`,
    data,
  )
}

export async function updateAdminProspectAppointmentStatus(appointmentId: number, status: string) {
  return requestJsonWithBody(`/api/admin/prospectos/citas/${appointmentId}/actualizar/`, { status })
}

export async function updateAdminAppointmentStatus(appointmentId: number, status: string) {
  return requestJsonWithBody(`/api/admin/citas/${appointmentId}/actualizar/`, { status })
}

export function getAdminClientDetail(clientId: string) {
  return requestJson<AdminClientDetailResponse>(`/api/admin/clientes/${clientId}/`)
}

export function getAdminClientReservationAvailability(clientId: number, operationId: number) {
  return requestJson<AdminClientReservationAvailabilityResponse>(
    `/api/admin/clientes/${clientId}/operaciones/${operationId}/disponibilidad/`,
  )
}

export function getAdminClientFreeMedicalAvailability(clientId: number) {
  return requestJson<AdminClientFreeMedicalAvailabilityResponse>(
    `/api/admin/clientes/${clientId}/cita-medica/disponibilidad/`,
  )
}

export function createAdminClientReservation(clientId: number, operationId: number, data: { branchId: number, dateTime: string }) {
  return requestJsonWithBody<CreateAdminClientReservationResponse>(
    `/api/admin/clientes/${clientId}/operaciones/${operationId}/reservar/`,
    data,
  )
}

export function createAdminClientFreeMedicalAppointment(clientId: number, data: { branchId: number, dateTime: string }) {
  return requestJsonWithBody<CreateAdminClientFreeMedicalAppointmentResponse>(
    `/api/admin/clientes/${clientId}/cita-medica/reservar/`,
    data,
  )
}

export function inactivateAdminClient(clientId: number) {
  return requestJsonWithBody<AdminClientInactivateResponse>(
    `/api/admin/clientes/${clientId}/inactivar/`,
    {},
  )
}

export function cancelAdminAppointment(appointmentId: number) {
  return requestJsonWithBody<AdminCancelAppointmentResponse>(
    `/api/admin/citas/${appointmentId}/cancelar/`,
    {},
  )
}

export function rescheduleAdminAppointment(appointmentId: number, payload: { dateTime: string }) {
  return requestJsonWithBody<{ detail: string }>(
    `/api/admin/citas/${appointmentId}/reprogramar/`,
    payload,
  )
}

export function confirmAdminAppointmentBiometric(
  appointmentId: number,
  payload: Pick<ProspectConversionBiometricData, 'template' | 'quality' | 'deviceSerial' | 'provider'>,
) {
  return requestJsonWithBody<OperationDetailResponse>(
    `/api/admin/citas/${appointmentId}/confirmar-biometria/`,
    payload,
  )
}

export function markAdminAppointmentPendingBiometric(appointmentId: number) {
  return requestJsonWithBody<{ detail: string }>(
    `/api/admin/citas/${appointmentId}/pendiente-biometria/`,
    {},
  )
}

export function getAdminOperations() {
  return requestJson<OperationsResponse>('/api/admin/operaciones/')
}

export function getAdminOperationDetail(operationId: string) {
  return requestJson<OperationDetailResponse>(`/api/admin/operaciones/${operationId}/`)
}

export function updateAdminOperationDetails(
  operationId: number,
  payload: UpdateAdminOperationDetailsPayload,
) {
  return requestJsonWithBody<OperationDetailResponse>(
    `/api/admin/operaciones/${operationId}/actualizar-detalles/`,
    payload,
  )
}

export function updateAdminOperationPricePlan(
  operationId: number,
  payload: UpdateAdminOperationPricePayload,
) {
  return requestJsonWithBody<OperationDetailResponse>(
    `/api/admin/operaciones/${operationId}/actualizar-precio/`,
    payload,
  )
}

export function getAdminAvailability(_branchId?: number | null) {
  return requestJson<AdminAvailabilityResponse>('/api/admin/disponibilidad/')
}

export function removeAdminVisibleAvailability(slotId: number) {
  return requestJsonWithBody<AdminAvailabilityMutationResponse>(
    `/api/admin/disponibilidad/cupos/${slotId}/retirar/`,
    {},
  )
}

export type AdminPaymentsFilters = {
  status?: '' | 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO'
  dateFrom?: string
  dateTo?: string
  search?: string
}

export function getAdminPayments(filters?: AdminPaymentsFilters) {
  const params = new URLSearchParams()
  if (filters?.status) params.set('status', filters.status)
  if (filters?.dateFrom) params.set('dateFrom', filters.dateFrom)
  if (filters?.dateTo) params.set('dateTo', filters.dateTo)
  if (filters?.search) params.set('search', filters.search)
  const query = params.toString()
  return requestJson<PaymentsResponse>(`/api/admin/pagos/${query ? `?${query}` : ''}`)
}

export function updateAdminPaymentQrConfig(file: File, instructions: string) {
  const formData = new FormData()
  formData.append('qrImage', file)
  formData.append('instructions', instructions)

  return requestFormDataWithBody<UpdateAdminPaymentQrConfigResponse>(
    '/api/admin/pagos/configuracion-qr/',
    formData,
  )
}

export function updateAdminPaymentStatus(
  paymentId: number,
  payload: UpdateAdminPaymentStatusPayload,
) {
  return requestJsonWithBody<UpdateAdminPaymentStatusResponse>(
    `/api/admin/pagos/${paymentId}/estado/`,
    payload,
  )
}

function expensePayloadToFormData(payload: UpsertAdminExpensePayload) {
  const formData = new FormData()
  formData.append('date', payload.date)
  formData.append('categoryId', String(payload.categoryId))
  formData.append('concept', payload.concept)
  formData.append('units', payload.units)
  formData.append('unitCost', payload.unitCost)
  formData.append('total', payload.total)
  formData.append('provider', payload.provider)
  formData.append('details', payload.details)
  if (payload.invoice) {
    formData.append('invoice', payload.invoice)
  }
  return formData
}

export function getAdminExpenses(month: number, year: number) {
  return requestJson<ExpensesResponse>(`/api/admin/gastos/?month=${month}&year=${year}`)
}

export function createAdminExpense(payload: UpsertAdminExpensePayload) {
  return requestFormDataWithBody<AdminExpenseMutationResponse>(
    '/api/admin/gastos/crear/',
    expensePayloadToFormData(payload),
  )
}

export function updateAdminExpense(expenseId: number, payload: UpsertAdminExpensePayload) {
  return requestFormDataWithBody<AdminExpenseMutationResponse>(
    `/api/admin/gastos/${expenseId}/actualizar/`,
    expensePayloadToFormData(payload),
  )
}

export function deleteAdminExpense(expenseId: number) {
  return requestJsonWithBody<AdminExpenseDeleteResponse>(
    `/api/admin/gastos/${expenseId}/eliminar/`,
    {},
  )
}

export function getAdminCatalogs() {
  return requestJson<CatalogsResponse>('/api/admin/catalogos/')
}

export function getAdminCatalogDetail(catalogKey: AdminCatalogKey) {
  return requestJson<AdminCatalogDetailResponse>(`/api/admin/catalogos/${catalogKey}/`)
}

export function createAdminCatalogItem(
  catalogKey: AdminCatalogKey,
  payload: Record<string, unknown>,
) {
  return requestJsonWithBody<AdminCatalogMutationResponse>(
    `/api/admin/catalogos/${catalogKey}/crear/`,
    payload,
  )
}

export function updateAdminCatalogItem(
  catalogKey: AdminCatalogKey,
  itemId: number,
  payload: Record<string, unknown>,
) {
  return requestJsonWithBody<AdminCatalogMutationResponse>(
    `/api/admin/catalogos/${catalogKey}/${itemId}/actualizar/`,
    payload,
  )
}

export function updateAdminCatalogItemState(
  catalogKey: AdminCatalogKey,
  itemId: number,
  payload: UpdateAdminCatalogItemStatePayload,
) {
  return requestJsonWithBody<AdminCatalogMutationResponse>(
    `/api/admin/catalogos/${catalogKey}/${itemId}/estado/`,
    payload,
  )
}

export function getAdminStaff(_branchId?: number | null) {
  return requestJson<StaffResponse>('/api/admin/equipo/')
}

export function createAdminStaff(payload: CreateAdminStaffPayload) {
  return requestJsonWithBody<AdminStaffMutationResponse>('/api/admin/equipo/crear/', payload)
}

export function updateAdminStaff(specialistId: number, payload: UpdateAdminStaffPayload) {
  return requestJsonWithBody<AdminStaffMutationResponse>(
    `/api/admin/equipo/${specialistId}/actualizar/`,
    payload,
  )
}

export function updateAdminStaffStatus(
  specialistId: number,
  payload: UpdateAdminStaffStatusPayload,
) {
  return requestJsonWithBody<AdminStaffMutationResponse>(
    `/api/admin/equipo/${specialistId}/estado/`,
    payload,
  )
}

export function createAdminProspect(payload: CreateAdminProspectPayload) {
  return requestJsonWithBody<CreateAdminProspectResponse>('/api/admin/prospectos/crear/', payload)
}

export function checkAdminProspectDuplicates(payload: {
  primerNombre: string
  segundoNombre?: string
  apellidoPaterno: string
  apellidoMaterno?: string
  telefono?: string
}) {
  return requestJsonWithBody<CheckAdminProspectDuplicatesResponse>('/api/admin/prospectos/verificar-duplicados/', payload)
}

export function checkAdminConcurrency(
  branchId: number,
  date: string,
  startTime: string,
  endTime: string,
) {
  return requestJsonWithBody<AdminConcurrencyCheckResponse>(
    '/api/admin/disponibilidad/concurrencia/',
    {
      sucursal_id: branchId,
      fecha: date,
      hora_inicio: startTime,
      hora_fin: endTime,
    }
  )
}

export function createAdminHabitualSchedule(payload: UpsertAdminHabitualSchedulePayload) {
  return requestJsonWithBody<AdminAvailabilityMutationResponse>(
    '/api/admin/disponibilidad/habitual/crear/',
    payload,
  )
}

export function updateAdminHabitualSchedule(
  ruleId: number,
  payload: UpsertAdminHabitualSchedulePayload,
) {
  return requestJsonWithBody<AdminAvailabilityMutationResponse>(
    `/api/admin/disponibilidad/habitual/${ruleId}/actualizar/`,
    payload,
  )
}

export function deleteAdminHabitualSchedule(ruleId: number) {
  return requestJsonWithBody<AdminAvailabilityMutationResponse>(
    `/api/admin/disponibilidad/habitual/${ruleId}/eliminar/`,
    {},
  )
}

export function createAdminAvailabilityException(payload: CreateAdminAvailabilityExceptionPayload) {
  return requestJsonWithBody<AdminAvailabilityMutationResponse>(
    '/api/admin/disponibilidad/excepciones/crear/',
    payload,
  )
}

export function deleteAdminAvailabilityException(exceptionId: number) {
  return requestJsonWithBody<AdminAvailabilityMutationResponse>(
    `/api/admin/disponibilidad/excepciones/${exceptionId}/eliminar/`,
    {},
  )
}

export function manageAdminGlobalAvailability(payload: ManageAdminGlobalAvailabilityPayload) {
  return requestJsonWithBody<AdminAvailabilityMutationResponse>(
    '/api/admin/disponibilidad/global/gestionar/',
    payload,
  )
}

export function getAdminProspectConversion(prospectId: string) {
  return requestJson<ProspectConversionResponse>(`/api/admin/prospectos/${prospectId}/conversion/`)
}

export function searchAdminClientsGlobal(query: string) {
  return requestJson<{ clients: Array<{ id: number; name: string; ci: string; phone: string; branchName: string; cityName: string }> }>(
    `/api/admin/clientes/buscar-global/?q=${encodeURIComponent(query)}`
  )
}

export function cancelAdminProspectConversion(prospectId: string) {
  return requestJsonWithBody<{ detail: string }>(
    `/api/admin/prospectos/${prospectId}/conversion/cancelar/`,
    {},
  )
}

export function saveAdminProspectConversionUserStep(prospectId: string, payload: ProspectConversionUserData & { password?: string }) {
  return requestJsonWithBody<ProspectConversionResponse>(
    `/api/admin/prospectos/${prospectId}/conversion/paso-1/`,
    payload,
  )
}

export function saveAdminProspectConversionOperationStep(prospectId: string, payload: ProspectConversionOperationData) {
  return requestJsonWithBody<ProspectConversionResponse>(
    `/api/admin/prospectos/${prospectId}/conversion/paso-2/`,
    payload,
  )
}

export function saveAdminProspectConversionMedicalStep(prospectId: string, payload: ProspectConversionMedicalData) {
  return requestJsonWithBody<ProspectConversionResponse>(
    `/api/admin/prospectos/${prospectId}/conversion/paso-3/`,
    payload,
  )
}

export function saveAdminProspectConversionBiometricStep(prospectId: string, payload: ProspectConversionBiometricData) {
  return requestJsonWithBody<ProspectConversionResponse>(
    `/api/admin/prospectos/${prospectId}/conversion/paso-4/`,
    payload,
  )
}

export function finalizeAdminProspectConversion(
  prospectId: string,
  documentFile?: File,
  firstPayment?: { receiptFile?: File | null; amount?: string; details?: string },
) {
  const formData = new FormData()
  if (documentFile) {
    formData.append('documentoFichaPdf', documentFile)
  }
  if (firstPayment?.receiptFile) {
    formData.append('primerPagoComprobante', firstPayment.receiptFile)
  }
  if (firstPayment?.amount) {
    formData.append('primerPagoMonto', firstPayment.amount)
  }
  if (firstPayment?.details) {
    formData.append('primerPagoDetalle', firstPayment.details)
  }

  return requestFormDataWithBody<ProspectConversionFinalizeResponse>(
    `/api/admin/prospectos/${prospectId}/conversion/finalizar/`,
    formData,
  )
}

export function getAdminBranches() {
  return requestJson<{ branches: AdminBranch[] }>('/api/admin/disponibilidad/sucursales/')
}

export function setAdminSessionBranch(branchId: number) {
  return requestJsonWithBody<{ detail: string; branchId: number }>('/api/admin/disponibilidad/sucursales/cambiar/', { branchId })
}

// Client Reactivation
export function initializeAdminClientReactivation(clientId: string) {
  return requestJson<ProspectConversionResponse>(`/api/admin/clientes/${clientId}/reactivar/initialize/`)
}

export function getAdminClientReactivation(clientId: string) {
  return requestJson<ProspectConversionResponse>(`/api/admin/clientes/${clientId}/reactivar/`)
}

export function cancelAdminClientReactivation(clientId: string) {
  return requestJsonWithBody<{ detail: string }>(`/api/admin/clientes/${clientId}/reactivar/cancelar/`, {})
}

export function saveAdminClientReactivationUserStep(clientId: string, payload: ProspectConversionUserData & { password?: string }) {
  return requestJsonWithBody<ProspectConversionResponse>(`/api/admin/clientes/${clientId}/reactivar/paso-1/`, payload)
}

export function saveAdminClientReactivationOperationStep(clientId: string, payload: ProspectConversionOperationData) {
  return requestJsonWithBody<ProspectConversionResponse>(`/api/admin/clientes/${clientId}/reactivar/paso-2/`, payload)
}

export function saveAdminClientReactivationMedicalStep(clientId: string, payload: ProspectConversionMedicalData, pdfFile?: File) {
  const formData = new FormData()
  formData.append('payload', JSON.stringify(payload))
  if (pdfFile) {
    formData.append('documento_escaneado_pdf', pdfFile)
  }

  return requestFormDataWithBody<ProspectConversionResponse>(`/api/admin/clientes/${clientId}/reactivar/paso-3/`, formData)
}

export function saveAdminClientReactivationBiometricStep(clientId: string, payload: ProspectConversionBiometricData) {
  return requestJsonWithBody<ProspectConversionResponse>(`/api/admin/clientes/${clientId}/reactivar/paso-4/`, payload)
}

export function finalizeAdminClientReactivation(
  clientId: string,
  pdfFile?: File,
  firstPayment?: { receiptFile?: File | null; amount?: string; details?: string },
) {
  const formData = new FormData()
  if (pdfFile) {
    formData.append('documento_escaneado_pdf', pdfFile)
  }
  if (firstPayment?.receiptFile) {
    formData.append('primerPagoComprobante', firstPayment.receiptFile)
  }
  if (firstPayment?.amount) {
    formData.append('primerPagoMonto', firstPayment.amount)
  }
  if (firstPayment?.details) {
    formData.append('primerPagoDetalle', firstPayment.details)
  }

  return requestFormDataWithBody<ProspectConversionFinalizeResponse>(`/api/admin/clientes/${clientId}/reactivar/finalizar/`, formData)
}


export async function migrateAdminClient(clientId: string | number, branchId: number) {
  return requestJsonWithBody<{ detail: string; branch: { id: number; name: string } }>(
    `/api/admin/clientes/${clientId}/migrar/`,
    { branchId }
  )
}

export async function migrateAdminProspect(prospectoId: string | number, branchId: number) {
  return requestJsonWithBody<{ detail: string; branch: { id: number; name: string } }>(
    `/api/admin/prospectos/${prospectoId}/migrar/`,
    { branchId }
  )
}

export async function changeAdminStaffBranch(userId: string | number, branchId: number) {
  return requestJsonWithBody<{ detail: string; branch: { id: number; name: string } }>(
    `/api/admin/equipo/${userId}/cambiar-sucursal/`,
    { branchId }
  )
}
