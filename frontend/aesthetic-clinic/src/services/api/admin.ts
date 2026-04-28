import type {
  AdminAvailabilityResponse,
  AdminAvailabilityMutationResponse,
  CatalogsResponse,
  CreateAdminAvailabilityExceptionPayload,
  CreateAdminProspectPayload,
  CreateAdminProspectResponse,
  CreateAdminTimeSlotPayload,
  DashboardResponse,
  ManageAdminGlobalAvailabilityPayload,
  OperationDetailResponse,
  OperationsResponse,
  PaymentsResponse,
  ProspectsResponse,
  StaffResponse,
  UpdateAdminTimeSlotPayload,
  UpsertAdminHabitualSchedulePayload,
  UpdateAdminPaymentQrConfigResponse,
  UpdateAdminPaymentStatusPayload,
  UpdateAdminPaymentStatusResponse,
} from '../../types/admin'
import type {
  ProspectConversionFinalizeResponse,
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

export function getAdminOperations() {
  return requestJson<OperationsResponse>('/api/admin/operaciones/')
}

export function getAdminOperationDetail(operationId: string) {
  return requestJson<OperationDetailResponse>(`/api/admin/operaciones/${operationId}/`)
}

export function getAdminAvailability() {
  return requestJson<AdminAvailabilityResponse>('/api/admin/disponibilidad/')
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

export function getAdminStaff() {
  return requestJson<StaffResponse>('/api/admin/equipo/')
}

export function createAdminProspect(payload: CreateAdminProspectPayload) {
  return requestJsonWithBody<CreateAdminProspectResponse>('/api/admin/prospectos/crear/', payload)
}

export function createAdminTimeSlot(payload: CreateAdminTimeSlotPayload) {
  console.log('[adminApi] createAdminTimeSlot:request', {
    path: '/api/admin/disponibilidad/horarios/crear/',
    payload,
    at: new Date().toISOString(),
  })
  return requestJsonWithBody<AdminAvailabilityMutationResponse>(
    '/api/admin/disponibilidad/horarios/crear/',
    payload,
  ).then((response) => {
    console.log('[adminApi] createAdminTimeSlot:response', {
      response,
      at: new Date().toISOString(),
    })
    return response
  })
}

export function updateAdminTimeSlot(slotId: number, payload: UpdateAdminTimeSlotPayload) {
  return requestJsonWithBody<AdminAvailabilityMutationResponse>(
    `/api/admin/disponibilidad/horarios/${slotId}/actualizar/`,
    payload,
  )
}

export function deleteAdminTimeSlot(slotId: number) {
  return requestJsonWithBody<AdminAvailabilityMutationResponse>(
    `/api/admin/disponibilidad/horarios/${slotId}/eliminar/`,
    {},
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

export function finalizeAdminProspectConversion(prospectId: string, documentFile: File) {
  const formData = new FormData()
  formData.append('documentoFichaPdf', documentFile)

  return requestFormDataWithBody<ProspectConversionFinalizeResponse>(
    `/api/admin/prospectos/${prospectId}/conversion/finalizar/`,
    formData,
  )
}
