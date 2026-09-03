import type {
  AdminAvailabilityResponse,
  AdminBranch,
  AdminCatalogDetailResponse,
  AdminCatalogKey,
  AdminCatalogMutationResponse,
  AdminStaffMutationResponse,
  AdminAvailabilityMutationResponse,
  AdminAppointmentNotesPatchPayload,
  AdminAppointmentNotesPatchResponse,
  AdminCancelAppointmentResponse,
  AdminClientDetailResponse,
  AdminExpenseDeleteResponse,
  AdminExpenseMutationResponse,
  AdminClientFreeMedicalAvailabilityResponse,
  AdminClientInactivateResponse,
  AdminCloseExtendedPayload,
  AdminClientReservationAvailabilityResponse,
  AdminReservationExtendedPayload,
  AdminProspectMedicalAvailabilityResponse,
  AdminUserRecoveryDetail,
  AdminUserRecoveryResetResponse,
  AdminUserRecoverySearchResponse,
  BackupListResponse,
  CancelAdminProspectMedicalAppointmentResponse,
  CatalogsResponse,
  CreateAdminClientFreeMedicalAppointmentResponse,
  CreateAdminClientReservationResponse,
  CreateAdminProspectMedicalAppointmentResponse,
  MaquinariaConflictResponse,
  MaquinariaDisponibilidad,
  EspecialistaDisponibilidadResponse,
  CreateAdminStaffPayload,
  CreateAdminAvailabilityExceptionPayload,
  CreateAdminProspectPayload,
  CreateAdminProspectResponse,
  DashboardAgendaResponse,
  AgendaItemLegacy,
  DashboardPaymentsResponse,
  DashboardResponse,
  ExpensesResponse,
  ManageAdminGlobalAvailabilityPayload,
  OperationDetailResponse,
  UpdateAdminOperationObservacionesResponse,
  UploadAdminOperationPhotosResponse,
  OperationsResponse,
  PaymentsResponse,
  ProspectsResponse,
  RegisterAdminPaymentPayload,
  RegisterAdminPaymentResponse,
  RegisterAdminAppointmentPaymentPayload,
  RegisterAdminAppointmentPaymentResponse,
  ReportClient,
  ReportIncomeItem,
  ReportProspect,
  ReportResponse,
  StaffResponse,
  UpdateAdminOperationDetailsPayload,
  UpdateAdminOperationPricePayload,
  UpdateAdminCatalogItemStatePayload,
  UpdateAdminStaffPayload,
  UpdateAdminStaffStatusPayload,
  UpsertAdminHabitualSchedulePayload,
  UpsertAdminExpensePayload,
  UpdateAdminPaymentQrConfigResponse,
  GetAdminPaymentQrConfigResponse,
  UpdateAdminPaymentStatusPayload,
  UpdateAdminPaymentStatusResponse,
  AdminConcurrencyCheckResponse,
  CheckAdminProspectDuplicatesResponse,
} from '../../types/admin'
import { normalizeAgendaItem } from '../../mappers/agenda'
import type {
  ProspectConversionFinalizeResponse,
  ProspectConversionBiometricData,
  ProspectConversionMedicalData,
  ProspectConversionOperationData,
  ProspectConversionResponse,
  ProspectConversionUserData,
  AdminClientProfilePatchPayload,
  AdminClientProfilePatchResponse,
} from '../../types/prospectConversion'
import {
  requestJson,
  requestJsonWithBody,
  requestJsonWithBodyIdempotent,
  requestFormDataWithBody,
  requestBlob,
  requestDelete,
  patchJsonWithBody,
} from './apiClient'

export function getAdminDashboard() {
  return requestJson<DashboardResponse>('/api/admin/dashboard/')
}

export function getAdminDashboardPayments(month: number, year: number) {
  return requestJson<DashboardPaymentsResponse>(`/api/admin/dashboard/payments/?month=${month}&year=${year}`)
}

export async function getAdminDashboardAgenda(month: number, year: number) {
  const response = await requestJson<Omit<DashboardAgendaResponse, 'agenda'> & { agenda: AgendaItemLegacy[] }>(
    `/api/admin/dashboard/agenda/?month=${month}&year=${year}`,
  )
  return {
    ...response,
    agenda: response.agenda.map(normalizeAgendaItem),
  }
}

export function getAdminProspects(_branchId?: number) {
  return requestJson<ProspectsResponse>('/api/admin/prospectos')
}

export function getAdminProspectMedicalAvailability(prospectId: number, branchId?: number) {
  const query = branchId ? `?branchId=${branchId}` : ''
  return requestJson<AdminProspectMedicalAvailabilityResponse>(
    `/api/admin/prospectos/${prospectId}/cita-medica/disponibilidad/${query}`,
  )
}

export function createAdminProspectMedicalAppointment(prospectId: number, data: { branchId: number, dateTime: string, precio?: string }) {
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

// --- citas-pagos follow-on: cobrar cita de prospecto --------------------
// Same payload shape as ``registerAdminAppointmentPayment`` (admin flow,
// receipt optional regardless of method). The ``rawId`` here is the
// CitaProspecto id, NOT the prospecto id.
export function chargeAdminProspectAppointment(citaId: number, payload: {
  paymentMethod: 'VIRTUAL' | 'FISICO' | 'MIXTO'
  amount: string
  montoFisico?: string
  montoVirtual?: string
  receiptFile?: File
  details?: string
}) {
  // Must use the multipart helper — the receiptFile needs a real
  // multipart payload (Content-Type: multipart/form-data + boundary
  // header set automatically by the browser when given FormData).
  // ``requestJsonWithBody`` would ``JSON.stringify`` the FormData into
  // ``"{}"`` and the backend would 400 because paymentMethod and
  // monto_pagado would be missing.
  const form = new FormData()
  form.append('paymentMethod', payload.paymentMethod)
  form.append('monto_pagado', payload.amount)
  if (payload.montoFisico) form.append('montoFisico', payload.montoFisico)
  if (payload.montoVirtual) form.append('montoVirtual', payload.montoVirtual)
  if (payload.receiptFile) form.append('receiptFile', payload.receiptFile)
  if (payload.details) form.append('details', payload.details)
  return requestFormDataWithBody<unknown>(
    `/api/admin/prospectos/citas/${citaId}/cobrar/`,
    form,
  )
}

// Edit the appointment's ``precio`` after booking. Locked once the first
// APROBADO PagoCita exists; the backend returns 400 in that case.
export function updateAdminProspectAppointmentPrice(citaId: number, precio: string) {
  return requestJsonWithBody<unknown>(
    `/api/admin/prospectos/citas/${citaId}/precio/`,
    { precio },
  )
}

// --- citas-pagos follow-on: edit precio on a free CitaClienteLibre.
// Same contract as ``updateAdminProspectAppointmentPrice`` but the
// endpoint path lives under the free appointments viewset.
export function updateAdminFreeAppointmentPrice(citaId: number, precio: string) {
  return requestJsonWithBody<unknown>(
    `/api/admin/citas-medicas-libres/${citaId}/precio/`,
    { precio },
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

export function createAdminClientReservation(
  clientId: number,
  operationId: number,
  data: AdminReservationExtendedPayload,
) {
  return requestJsonWithBody<CreateAdminClientReservationResponse>(
    `/api/admin/clientes/${clientId}/operaciones/${operationId}/reservar/`,
    data,
  )
}

export function checkAdminMaquinariaConflicts(params: {
  sucursalId: number
  fecha: string
  hora: string
  duracionMinutos: number
  maquinariaIds: number[]
  /**
   * Per-row cantidad, aligned to `maquinariaIds`. Backend defaults to 1 per
   * maquinaría when omitted; pass an explicit array to flag conflicts like
   * "cantidad_total=1 vs solicitud=8" which the default would miss.
   */
  cantidades?: number[]
}): Promise<MaquinariaConflictResponse & { disponibilidad: MaquinariaDisponibilidad[] }> {
  const search = new URLSearchParams({
    sucursalId: String(params.sucursalId),
    fecha: params.fecha,
    hora: params.hora,
    duracionMinutos: String(params.duracionMinutos),
    maquinariaIds: params.maquinariaIds.join(","),
  })
  if (params.cantidades && params.cantidades.length === params.maquinariaIds.length) {
    search.set("cantidades", params.cantidades.join(","))
  }
  return requestJson<MaquinariaConflictResponse & { disponibilidad: MaquinariaDisponibilidad[] }>(
    `/api/admin/disponibilidad/check-maquinaria/?${search.toString()}`,
  )
}

export function checkAdminEspecialistasDisponibilidad(params: {
  sucursalId: number
  fecha: string
  hora: string
  duracionMinutos: number
  especialistaIds: number[]
}): Promise<EspecialistaDisponibilidadResponse> {
  const search = new URLSearchParams({
    sucursalId: String(params.sucursalId),
    fecha: params.fecha,
    hora: params.hora,
    duracionMinutos: String(params.duracionMinutos),
    especialistaIds: params.especialistaIds.join(","),
  })
  return requestJson<EspecialistaDisponibilidadResponse>(
    `/api/admin/disponibilidad/check-especialistas/?${search.toString()}`,
  )
}

/**
 * Catalogo de maquinaria expuesto por el dispatch generico de catalogos
 * (`backend/config/api_views.py`). El backend devuelve la forma estandar
 * `{ key, title, description, fields, items }`; el modal filtra los items
 * por `active === true` y mapea `values.nombre` + `values.cantidadTotal`
 * a las opciones que el admin puede seleccionar.
 */
export function getMaquinariaCatalog() {
  return requestJson<AdminCatalogDetailResponse>('/api/admin/catalogos/maquinaria/')
}

export function markAppointmentPendingBiometricExtended(
  appointmentId: number,
  data: AdminCloseExtendedPayload,
) {
  // Deprecated: pendiente-biometria no longer captures real-time fields.
  // Use closeAppointmentWithRealTimeData() on a CONFIRMADA cita instead.
  return requestJsonWithBody<unknown>(
    `/api/admin/citas/${appointmentId}/pendiente-biometria/`,
    data,
  )
}

/**
 * Persists the real-time close data on a CONFIRMADA cita. Endpoint:
 * POST /api/admin/citas/<id>/cerrar/. Does NOT change the cita's state.
 *
 * Use this after the cita has been marked pending biometric and the client
 * has verified attendance (i.e. estado === CONFIRMADA).
 *
 * Sends multipart/form-data when `fotoAntes` / `fotoDespues` are present
 * so photos can be uploaded in the same round-trip. Otherwise the body
 * is JSON to stay backward-compatible with non-photo callers.
 */
export function closeAppointmentWithRealTimeData(
  appointmentId: number,
  data: AdminCloseExtendedPayload,
) {
  const hasPhotos = !!(data.fotoAntes || data.fotoDespues)
  if (!hasPhotos) {
    return requestJsonWithBody<unknown>(
      `/api/admin/citas/${appointmentId}/cerrar/`,
      data,
    )
  }
  const formData = new FormData()
  Object.entries(data).forEach(([key, value]) => {
    if (value === undefined || value === null) return
    if (value instanceof File) {
      formData.append(key, value)
    } else if (Array.isArray(value) || typeof value === 'object') {
      // M2M arrays / objects serialize as JSON strings inside FormData.
      formData.append(key, JSON.stringify(value))
    } else {
      formData.append(key, String(value))
    }
  })
  return requestFormDataWithBody<unknown>(
    `/api/admin/citas/${appointmentId}/cerrar/`,
    formData,
  )
}

export function patchAppointmentNotes(
  appointmentId: number,
  data: AdminAppointmentNotesPatchPayload,
): Promise<AdminAppointmentNotesPatchResponse> {
  // Notes use multipart so photos can be uploaded.
  const formData = new FormData()
  Object.entries(data).forEach(([key, value]) => {
    if (value === undefined || value === null) return
    if (value instanceof File) {
      formData.append(key, value)
    } else {
      formData.append(key, String(value))
    }
  })
  return requestFormDataWithBody<AdminAppointmentNotesPatchResponse>(
    `/api/admin/citas/${appointmentId}/notas/`,
    formData,
  )
}

export function createAdminClientFreeMedicalAppointment(
  clientId: number,
  data: { branchId: number; dateTime: string; precio?: string },
) {
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

export function cancelAdminFreeMedicalAppointment(appointmentId: number) {
  return requestJsonWithBody<AdminCancelAppointmentResponse>(
    `/api/admin/citas-medicas-libres/${appointmentId}/cancelar/`,
    {},
  )
}

export function confirmAdminFreeMedicalAppointment(appointmentId: number) {
  return requestJsonWithBody<{ detail: string }>(
    `/api/admin/citas-medicas-libres/${appointmentId}/confirmar/`,
    {},
  )
}

export function rescheduleAdminAppointment(
  appointmentId: number,
  payload: AdminReservationExtendedPayload,
) {
  return requestJsonWithBody<{ detail: string }>(
    `/api/admin/citas/${appointmentId}/reprogramar/`,
    payload,
  )
}

export function markAdminAppointmentPendingBiometric(appointmentId: number) {
  return requestJsonWithBody<{ detail: string }>(
    `/api/admin/citas/${appointmentId}/pendiente-biometria/`,
    {},
  )
}

export function cancelAdminAppointmentVerification(appointmentId: number) {
  return requestJsonWithBody<{ detail: string }>(
    `/api/admin/citas/${appointmentId}/cancelar-verificacion/`,
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

/**
 * Save only ``Operacion.detalles_op`` from the new "Observaciones del
 * procedimiento" section. The endpoint is narrow on purpose — it does
 * NOT touch ``recomendaciones`` or ``sesiones_totales`` so the inline
 * editor on the same page can stay focused on one field.
 */
export function updateAdminOperationObservaciones(
  operationId: number,
  payload: { details: string },
) {
  return requestJsonWithBody<UpdateAdminOperationObservacionesResponse>(
    `/api/admin/operaciones/${operationId}/actualizar-observaciones/`,
    payload,
  )
}

/**
 * Upload one or more ``OperacionFoto`` rows for the given ``kind``
 * (``"antes"`` or ``"despues"``). The backend uses partial-success
 * semantics: 201 with ``saved[]`` + ``errors{}`` when at least one file
 * saved, 400 when none did. ``requestFormDataWithBody`` already extracts
 * ``fieldErrors`` on error responses.
 */
export function uploadAdminOperationPhotos(
  operationId: number,
  files: File[],
  kind: 'antes' | 'despues',
) {
  const formData = new FormData()
  files.forEach((file) => formData.append('archivos', file))
  return requestFormDataWithBody<UploadAdminOperationPhotosResponse>(
    `/api/admin/operaciones/${operationId}/fotos/${kind}/`,
    formData,
  )
}

/**
 * Delete a single photo (and its file on disk). 204 on success, 404 if
 * the photo does not exist OR belongs to a different operation. Returns
 * ``null`` on success (204 has no body).
 */
export function deleteAdminOperationPhoto(operationId: number, photoId: number) {
  return requestDelete(
    `/api/admin/operaciones/${operationId}/fotos/${photoId}/`,
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

export function deleteAdminOperationQuota(
  operationId: number,
  payload: { nroCuota: number },
) {
  return requestJsonWithBody<OperationDetailResponse>(
    `/api/admin/operaciones/${operationId}/eliminar-cuota/`,
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
  search?: string
}

export function getAdminPayments(month: number, year: number, filters?: AdminPaymentsFilters) {
  const params = new URLSearchParams()
  params.set('month', String(month))
  params.set('year', String(year))
  if (filters?.status) params.set('status', filters.status)
  if (filters?.search) params.set('search', filters.search)
  const query = params.toString()
  return requestJson<PaymentsResponse>(`/api/admin/pagos/?${query}`)
}

// --- citas-pagos follow-on: read the branch QR for cobro modals ---
// Used by AdminRegisterAppointmentPaymentModal to surface the QR image
// under the ``Método de pago`` selector when the admin picks VIRTUAL or
// MIXTO. Mirrors the read-side of the existing POST endpoint.
export function getAdminPaymentQrConfig() {
  return requestJson<GetAdminPaymentQrConfigResponse>(
    '/api/admin/pagos/configuracion-qr/',
  )
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

/**
 * Register a payment on behalf of a client from the admin CMS.
 *
 * Mirrors the write serializer on the backend: `paymentMethod` is
 * always required, the breakdown is required only for `MIXTO`, and
 * the receipt is optional regardless of method so admins can register
 * desk cash payments without uploading a file.
 */
export function registerAdminPayment(
  cuotaId: number,
  payload: RegisterAdminPaymentPayload,
) {
  const formData = new FormData()
  formData.append('paymentMethod', payload.paymentMethod)
  formData.append('monto_pagado', payload.amount)
  if (payload.montoFisico) formData.append('montoFisico', payload.montoFisico)
  if (payload.montoVirtual) formData.append('montoVirtual', payload.montoVirtual)
  if (payload.receiptFile) formData.append('receiptFile', payload.receiptFile)
  if (payload.details) formData.append('details', payload.details)

  return requestFormDataWithBody<RegisterAdminPaymentResponse>(
    `/api/admin/pagos/cuotas/${cuotaId}/pagos/`,
    formData,
  )
}

/**
 * Multipart builder shared by both cita cobrar endpoints. Mirrors
 * `registerAdminPayment` byte-for-byte (same field names) so the
 * backend `PagoCitaCreateSerializer` can validate against the same
 * contract as `PagoRealizadoCreateSerializer`.
 */
function appointmentPaymentPayloadToFormData(
  payload: RegisterAdminAppointmentPaymentPayload,
): FormData {
  const formData = new FormData()
  formData.append('paymentMethod', payload.paymentMethod)
  formData.append('monto_pagado', payload.amount)
  if (payload.montoFisico) formData.append('montoFisico', payload.montoFisico)
  if (payload.montoVirtual) formData.append('montoVirtual', payload.montoVirtual)
  if (payload.receiptFile) formData.append('receiptFile', payload.receiptFile)
  if (payload.details) formData.append('details', payload.details)
  return formData
}

/**
 * Charge a `CitaMedica` at the consultorio. Mirrors
 * `registerAdminPayment` but POSTs to the new operation-detail
 * cobrar action and returns the refreshed cita item (carrying the
 * new `precio` / `saldoPendiente` / `pagos[]`).
 */
export function registerAdminAppointmentPayment(
  operationId: number,
  citaId: number,
  payload: RegisterAdminAppointmentPaymentPayload,
) {
  return requestFormDataWithBody<RegisterAdminAppointmentPaymentResponse>(
    `/api/admin/operaciones/${operationId}/citas/${citaId}/cobrar/`,
    appointmentPaymentPayloadToFormData(payload),
  )
}

/**
 * Charge a `CitaClienteLibre` at the consultorio. Same payload
 * contract as `registerAdminAppointmentPayment`, no nested
 * `operationId` because free appointments are not attached to an
 * operation.
 */
export function registerAdminFreeAppointmentPayment(
  appointmentId: number,
  payload: RegisterAdminAppointmentPaymentPayload,
) {
  return requestFormDataWithBody<RegisterAdminAppointmentPaymentResponse>(
    `/api/admin/citas-medicas-libres/${appointmentId}/cobrar/`,
    appointmentPaymentPayloadToFormData(payload),
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

// --- Admin Reports ---
// Branch-scoped, read-only datasets used by `ReportLayout` and the four report
// pages. The backend resolves the active branch from the session/header, so we
// don't pass `branchId`. Income requires `month` + `year` because the queryset
// is filtered by `cuota__fecha_vencimiento` inside the requested period.

export function getAdminReportClients() {
  return requestJson<ReportResponse<ReportClient>>('/api/admin/reportes/clientes/')
}

export function getAdminReportProspects() {
  return requestJson<ReportResponse<ReportProspect>>('/api/admin/reportes/prospectos/')
}

export function getAdminReportIncome(month: number, year: number) {
  return requestJson<ReportResponse<ReportIncomeItem>>(
    `/api/admin/reportes/ingresos/?month=${month}&year=${year}`,
  )
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

// --- Nested `OpcionCatalogo` endpoints under `grupos-opciones` ---
// Powers the option-management modal in the admin catalog page. Mirrors the
// backend response shape in `_serialize_opcion` (`backend/config/api_views.py`).

export type GroupOptionItem = {
  id: number
  codigo: string
  nombre: string
  valor: string
  orden: number
  activo: boolean
  grupoId: number
}

export type GroupOptionListResponse = {
  items: GroupOptionItem[]
}

export type GroupOptionMutationResponse = {
  detail: string
  item: GroupOptionItem
}

export type GroupOptionBulkMutationResponse = {
  detail: string
  items: GroupOptionItem[]
}

export type GroupOptionCreatePayload = {
  codigo: string
  nombre: string
  valor: string
  orden?: number | null
  activo?: boolean
}

export type GroupOptionUpdatePayload = {
  nombre?: string
  valor?: string
  orden?: number | null
  activo?: boolean
}

export type GroupOptionTogglePayload = {
  active: boolean
}

export type GetGroupOptionsParams = {
  active?: 'true' | 'false' | 'all'
  q?: string
}

function buildGroupOptionsQuery(grupoId: number, params: GetGroupOptionsParams = {}) {
  const query = new URLSearchParams()
  if (params.active && params.active !== 'all') {
    query.set('active', params.active)
  }
  if (params.q && params.q.trim()) {
    query.set('q', params.q.trim())
  }
  const search = query.toString()
  return `/api/admin/catalogos/grupos-opciones/${grupoId}/opciones/${search ? `?${search}` : ''}`
}

export function getGroupOptions(grupoId: number, params: GetGroupOptionsParams = {}) {
  return requestJson<GroupOptionListResponse>(buildGroupOptionsQuery(grupoId, params))
}

export function createGroupOption(
  grupoId: number,
  payload: GroupOptionCreatePayload,
) {
  return requestJsonWithBody<GroupOptionMutationResponse>(
    `/api/admin/catalogos/grupos-opciones/${grupoId}/opciones/crear/`,
    payload,
  )
}

export function createGroupOptionsBulk(
  grupoId: number,
  options: GroupOptionCreatePayload[],
) {
  return requestJsonWithBody<GroupOptionBulkMutationResponse>(
    `/api/admin/catalogos/grupos-opciones/${grupoId}/opciones/crear-multiples/`,
    { options },
  )
}

export function updateGroupOption(
  grupoId: number,
  opcionId: number,
  payload: GroupOptionUpdatePayload,
) {
  return requestJsonWithBody<GroupOptionMutationResponse>(
    `/api/admin/catalogos/grupos-opciones/${grupoId}/opciones/${opcionId}/actualizar/`,
    payload,
  )
}

export function toggleGroupOptionState(
  grupoId: number,
  opcionId: number,
  active: boolean,
) {
  return requestJsonWithBody<GroupOptionMutationResponse>(
    `/api/admin/catalogos/grupos-opciones/${grupoId}/opciones/${opcionId}/estado/`,
    { active } satisfies GroupOptionTogglePayload,
  )
}

export function getAdminCatalogs() {
  return requestJson<CatalogsResponse>('/api/admin/catalogos/')
}

export type AdminCatalogListParams = {
  q?: string
  active?: 'true' | 'false' | 'all'
}

export function getAdminCatalogDetail(
  catalogKey: AdminCatalogKey,
  params: AdminCatalogListParams = {},
) {
  const query = new URLSearchParams()
  if (params.q && params.q.trim()) query.set('q', params.q.trim())
  if (params.active && params.active !== 'all') query.set('active', params.active)
  const search = query.toString()
  return requestJson<AdminCatalogDetailResponse>(
    `/api/admin/catalogos/${catalogKey}/${search ? `?${search}` : ''}`,
  )
}

export function createAdminCatalogItem(
  catalogKey: AdminCatalogKey,
  payload: Record<string, unknown>,
) {
  // Maquinaria uses dedicated endpoints (admin_required + scope check) so
  // admin_sucursal can CRUD their own rows. All other catalogs use the
  // generic dispatch (admin_principal_required).
  if (catalogKey === 'maquinaria') {
    return requestJsonWithBody<AdminCatalogMutationResponse>(
      '/api/admin/catalogos/maquinaria/crear/',
      payload,
    )
  }
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
  if (catalogKey === 'maquinaria') {
    return requestJsonWithBody<AdminCatalogMutationResponse>(
      `/api/admin/catalogos/maquinaria/${itemId}/actualizar/`,
      payload,
    )
  }
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

export function searchAdminClientsGlobal(filters: {
  name?: string
  ci?: string
  phone?: string
  email?: string
  code?: string
}) {
  const params = new URLSearchParams()
  if (filters.name) params.set('name', filters.name)
  if (filters.ci) params.set('ci', filters.ci)
  if (filters.phone) params.set('phone', filters.phone)
  if (filters.email) params.set('email', filters.email)
  if (filters.code) params.set('code', filters.code)

  return requestJson<{ clients: Array<{
    id: number
    name: string
    ci: string
    phone: string
    email?: string
    clienteCodigo?: string
    branchName: string
    cityName: string
  }> }>(
    `/api/admin/clientes/buscar-global/?${params.toString()}`
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

/**
 * Payload for the optional first-payment block of the conversion /
 * reactivation finalize endpoints. The wizard step 5 sends the full
 * breakdown when the admin picks FISICO / MIXTO; legacy callers that
 * only send `amount` keep working (the backend treats them as
 * VIRTUAL with the flat total).
 */
export type FirstConversionPaymentPayload = {
  paymentMethod?: 'VIRTUAL' | 'FISICO' | 'MIXTO'
  montoFisico?: string
  montoVirtual?: string
  receiptFile?: File | null
  details?: string
  /** Legacy flat-total field. Used when `paymentMethod` is absent. */
  amount?: string
}

export function finalizeAdminProspectConversion(
  prospectId: string,
  documentFile?: File,
  firstPayment?: FirstConversionPaymentPayload,
) {
  const formData = new FormData()
  if (documentFile) {
    formData.append('documentoFichaPdf', documentFile)
  }
  if (firstPayment) {
    if (firstPayment.paymentMethod) {
      formData.append('primerPagoMetodo', firstPayment.paymentMethod)
    }
    if (firstPayment.montoFisico) {
      formData.append('primerPagoMontoFisico', firstPayment.montoFisico)
    }
    if (firstPayment.montoVirtual) {
      formData.append('primerPagoMontoVirtual', firstPayment.montoVirtual)
    }
    if (firstPayment.receiptFile) {
      formData.append('primerPagoComprobante', firstPayment.receiptFile)
    }
    if (firstPayment.amount) {
      formData.append('primerPagoMonto', firstPayment.amount)
    }
    if (firstPayment.details) {
      formData.append('primerPagoDetalle', firstPayment.details)
    }
  }

  return requestFormDataWithBody<ProspectConversionFinalizeResponse>(
    `/api/admin/prospectos/${prospectId}/conversion/finalizar/`,
    formData,
  )
}

export function getAdminBranches() {
  return requestJson<{ branches: AdminBranch[] }>('/api/admin/disponibilidad/sucursales')
}

export function setAdminSessionBranch(branchId: number) {
  return requestJsonWithBody<{ detail: string; branchId: number }>('/api/admin/disponibilidad/sucursales/cambiar/', { branchId })
}

type BranchManagementFilters = {
  status?: 'active' | 'inactive' | 'all'
  city?: string
  adminName?: string
  branchId?: number | null
}

export function getAdminBranchesManagement(filters: BranchManagementFilters = {}) {
  const query = new URLSearchParams()
  if (filters.status) query.set('status', filters.status)
  if (filters.city) query.set('city', filters.city)
  if (filters.adminName) query.set('admin_name', filters.adminName)
  if (filters.branchId) query.set('branch_id', String(filters.branchId))
  return requestJson<{ branches: any[]; total: number }>(`/api/admin/sucursales/${query.size ? `?${query.toString()}` : ''}`)
}

export function getAdminBranchDeactivationImpact(branchId: number) {
  return requestJson<{ branchId: number; impact: { appointments_pending: number; payments_pending: number; processes_pending: number } }>(
    `/api/admin/sucursales/${branchId}/deactivation-impact/`,
  )
}

export function createAdminBranch(payload: { nombre: string; ciudad: string; direccion: string }) {
  return requestJsonWithBodyIdempotent<{ detail: string; branchId: number }>(
    '/api/admin/sucursales/crear/',
    payload,
    crypto.randomUUID(),
  )
}

export function updateAdminBranch(branchId: number, payload: Partial<{ nombre: string; ciudad: string; direccion: string }>) {
  return requestJsonWithBody<{ detail: string }>(`/api/admin/sucursales/${branchId}/actualizar/`, payload)
}

export function toggleAdminBranch(branchId: number, active: boolean, force = false) {
  return requestJsonWithBody<{ detail: string; impact?: Record<string, number> }>(
    `/api/admin/sucursales/${branchId}/estado/`,
    { active, force },
  )
}

export function changeAdminBranchManager(branchId: number, newAdminUserId: number) {
  return requestJsonWithBodyIdempotent<{ detail: string; mode?: 'replace_with_inactive' | 'swap' | 'assign' | 'swap_with_main_admin' }>(
    `/api/admin/sucursales/${branchId}/cambiar-admin/`,
    { newAdminUserId },
    crypto.randomUUID(),
  )
}

export function getAdminBranchAdmins() {
  return requestJson<{ admins: Array<{ id: number; username: string; fullName: string; email: string; telefono?: string; fechaNacimiento?: string; isActive: boolean; branchId: number | null; branchName: string }> }>('/api/admin/equipo/admins-sucursal/')
}

export function createAdminBranchAdmin(payload: {
  username: string
  email?: string
  telefono?: string
  primerNombre: string
  segundoNombre?: string
  apellidoPaterno: string
  apellidoMaterno?: string
  password: string
}) {
  return requestJsonWithBody<{ detail: string }>('/api/admin/equipo/admins-sucursal/crear/', payload)
}


export function getAdminBranchAdminDetail(userId: number) {
  return requestJson<{ admin: { id: number; username: string; fullName: string; email: string; telefono?: string; fechaNacimiento?: string; isActive: boolean; branchId: number | null; branchName: string } }>(`/api/admin/equipo/admins-sucursal/${userId}/`)
}

export function updateAdminBranchAdmin(userId: number, payload: Partial<{ email: string; primerNombre: string; segundoNombre: string; apellidoPaterno: string; apellidoMaterno: string }>) {
  return requestJsonWithBody<{ detail: string }>(`/api/admin/equipo/admins-sucursal/${userId}/actualizar/`, payload)
}

export function toggleAdminBranchAdmin(userId: number, active: boolean) {
  return requestJsonWithBody<{ detail: string }>(`/api/admin/equipo/admins-sucursal/${userId}/estado/`, { active })
}

export function getAdminBranchAuditLogs(branchId?: number | null) {
  const query = new URLSearchParams()
  if (branchId) query.set('branchId', String(branchId))
  return requestJson<{ items: Array<{ id: number; createdAt: string; action: string; detail: string; branchId: number; branchName: string; actor: string; metadata: Record<string, unknown> }>; total: number }>(
    `/api/admin/sucursales/auditoria/${query.size ? `?${query.toString()}` : ''}`,
  )
}

export function initializeAdminBranchWizard() {
  return requestJsonWithBody<{ detail: string; draft: Record<string, unknown> }>('/api/admin/sucursales/wizard/inicializar/', {})
}

export function saveAdminBranchWizardStep1(payload: { nombre: string; ciudad: string; direccion: string }) {
  return requestJsonWithBody<{ detail: string; draft: Record<string, unknown> }>('/api/admin/sucursales/wizard/paso-1/', payload)
}

export function saveAdminBranchWizardStep2ExistingInactive(adminUserId: number) {
  return requestJsonWithBody<{ detail: string; draft: Record<string, unknown> }>('/api/admin/sucursales/wizard/paso-2/', {
    mode: 'existing_inactive',
    adminUserId,
  })
}

export function saveAdminBranchWizardStep2CreateNew(payload: {
  username: string
  email?: string
  primerNombre: string
  segundoNombre?: string
  apellidoPaterno: string
  apellidoMaterno?: string
  ci: string
  telefono?: string
  password: string
}) {
  return requestJsonWithBody<{ detail: string; draft: Record<string, unknown> }>('/api/admin/sucursales/wizard/paso-2/', {
    mode: 'create_new',
    ...payload,
  })
}

export function finalizeAdminBranchWizard(payload: { nombre: string; clave: string }) {
  return requestJsonWithBody<{ detail: string; branchId: number; adminUserId: number; tabletKioskId: number; tabletKioskCode: string }>(
    '/api/admin/sucursales/wizard/finalizar/',
    payload,
  )
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

/**
 * Live profile edit endpoint for the client detail page modal. Issues
 * a `PATCH /api/admin/clientes/<clientId>/perfil/` against the live
 * `Cliente` + `Usuario` rows; the modal hydrates from `response.client`
 * (the full 13-field snapshot + `hasPassword`).
 *
 * The wizard reactivation flow does NOT use this — it still routes
 * identity edits through the draft endpoint, which after Slice 1+2 no
 * longer overwrites live profile fields on finalize.
 */
export function patchAdminClientProfile(
  clientId: string | number,
  payload: AdminClientProfilePatchPayload,
) {
  return patchJsonWithBody<AdminClientProfilePatchResponse>(
    `/api/admin/clientes/${clientId}/perfil/`,
    payload,
  )
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
  firstPayment?: FirstConversionPaymentPayload,
) {
  const formData = new FormData()
  if (pdfFile) {
    formData.append('documento_escaneado_pdf', pdfFile)
  }
  if (firstPayment) {
    if (firstPayment.paymentMethod) {
      formData.append('primerPagoMetodo', firstPayment.paymentMethod)
    }
    if (firstPayment.montoFisico) {
      formData.append('primerPagoMontoFisico', firstPayment.montoFisico)
    }
    if (firstPayment.montoVirtual) {
      formData.append('primerPagoMontoVirtual', firstPayment.montoVirtual)
    }
    if (firstPayment.receiptFile) {
      formData.append('primerPagoComprobante', firstPayment.receiptFile)
    }
    if (firstPayment.amount) {
      formData.append('primerPagoMonto', firstPayment.amount)
    }
    if (firstPayment.details) {
      formData.append('primerPagoDetalle', firstPayment.details)
    }
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

// --- Admin User Recovery ---
// Helper endpoints backing /cms/equipo/recuperar. Branch scoping is
// enforced server-side: branch admins only see users from their own
// branch. The reset endpoint returns a temporary password that the
// admin must hand to the user out-of-band.

/**
 * Per-field filters consumed by `usuario_recovery_search`. At least
 * one field should be non-empty; an empty object returns the empty
 * payload the backend uses to reset the result panel.
 *
 * OR-within-field / AND-across-fields semantics live on the server.
 */
export interface AdminUserRecoveryFilters {
  name?: string
  username?: string
  email?: string
  phone?: string
  ci?: string
}

export function searchAdminUserRecovery(filters: AdminUserRecoveryFilters) {
  const params = new URLSearchParams()
  if (filters.name) params.set('name', filters.name)
  if (filters.username) params.set('username', filters.username)
  if (filters.email) params.set('email', filters.email)
  if (filters.phone) params.set('phone', filters.phone)
  if (filters.ci) params.set('ci', filters.ci)
  return requestJson<AdminUserRecoverySearchResponse>(
    `/api/admin/usuarios/buscar/${params.toString() ? `?${params.toString()}` : ''}`,
  )
}

export function getAdminUserRecoveryDetail(userId: number) {
  return requestJson<AdminUserRecoveryDetail>(
    `/api/admin/usuarios/${userId}/`,
  )
}

export function postAdminUserRecoveryReset(userId: number) {
  return requestJsonWithBody<AdminUserRecoveryResetResponse>(
    `/api/admin/usuarios/${userId}/reset-password/`,
    {},
  )
}

// --- Admin Database Backups ---
// Principal-only endpoints that mirror the `Backups` admin page. The trigger
// streams a freshly-created dump as `application/octet-stream` so the
// frontend saves the bytes as-is; the download endpoint is a normal GET
// reused via `<a href ... download>` (no extra CSRF token because GETs are
// exempt). Delete follows REST semantics (`DELETE`).

export function listAdminBackups() {
  return requestJson<BackupListResponse>('/api/admin/backups/')
}

export function triggerAdminBackup() {
  return requestBlob('/api/admin/backups/trigger/', {})
}

/**
 * Build a download URL for an existing backup file. Used as the `href` for a
 * plain `<a download>` so the browser handles the file save via session
 * cookie (no CSRF token required for GETs).
 */
export function adminBackupDownloadLink(filename: string) {
  return `/api/admin/backups/${encodeURIComponent(filename)}/download/`
}

export function deleteAdminBackup(filename: string) {
  return requestDelete(`/api/admin/backups/${encodeURIComponent(filename)}/`)
}
