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
  DashboardResponse,
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
  UpdateAdminPaymentQrConfigResponse,
  UpdateAdminPaymentStatusPayload,
  UpdateAdminPaymentStatusResponse,
  AdminConcurrencyCheckResponse,
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

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

async function requestJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`No se pudo cargar ${path} (${response.status})`)
  }

  return (await response.json()) as T
}

async function requestJsonWithBody<T>(path: string, body: unknown): Promise<T> {
  const csrfToken = await ensureCsrfCookie()

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
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

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'X-CSRFToken': csrfToken,
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

export function getAdminProspects() {
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

export function updateAdminProspect(prospectId: number, data: { firstName?: string; lastName?: string; phone?: string; observations?: string }) {
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

export function getAdminAvailability() {
  return requestJson<AdminAvailabilityResponse>('/api/admin/disponibilidad/')
}

export function removeAdminVisibleAvailability(slotId: number) {
  return requestJsonWithBody<AdminAvailabilityMutationResponse>(
    `/api/admin/disponibilidad/cupos/${slotId}/retirar/`,
    {},
  )
}

export function getAdminPayments() {
  return requestJson<PaymentsResponse>('/api/admin/pagos/')
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

export function getAdminStaff() {
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

export function finalizeAdminProspectConversion(prospectId: string, documentFile: File) {
  const formData = new FormData()
  formData.append('documentoFichaPdf', documentFile)

  return requestFormDataWithBody<ProspectConversionFinalizeResponse>(
    `/api/admin/prospectos/${prospectId}/conversion/finalizar/`,
    formData,
  )
}

export function getAdminBranches() {
  return requestJson<{ branches: AdminBranch[] }>('/api/admin/disponibilidad/sucursales/')
}

