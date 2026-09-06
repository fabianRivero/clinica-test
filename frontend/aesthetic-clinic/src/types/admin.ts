import type {
  ClientAppointment,
  ClientOperation,
  ClientPayment,
  ClientQuota,
  ClientReservationAvailabilityResponse,
  CreateClientReservationResponse,
} from './common'

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
  clientId: number
  patient: string
  operation: string
  amount: string
  submittedAt: string
  bank: string
  status: 'pendiente' | 'observado' | 'aprobado' | 'cancelado'
  quota?: string
  note?: string
  dueDate?: string
  receiptUrl?: string
  verifier?: string
  /** Payment channel — `VIRTUAL` / `FISICO` / `MIXTO`. */
  paymentMethod?: string
  /** Formatted "Bs X.XX" — present for every method. */
  physicalAmount?: string
  virtualAmount?: string
}

/**
 * Payload used by `registerAdminPayment`. Mirrors the write serializer on
 * the backend (`PagoRealizadoCreateSerializer`): `paymentMethod` is
 * always required; `montoFisico` / `montoVirtual` are required only when
 * the method is `MIXTO`. Receipt and details are optional regardless of
 * method — admins may register a desk cash payment without a receipt.
 */
export type RegisterAdminPaymentPayload = {
  paymentMethod: 'VIRTUAL' | 'FISICO' | 'MIXTO'
  amount: string
  montoFisico?: string
  montoVirtual?: string
  receiptFile?: File
  details?: string
}

export type RegisterAdminPaymentResponse = {
  detail: string
  payment: VerificationPayment
}

/**
 * Single `PagoCita` row as serialised by `PagoCitaSerializer` on the backend.
 * Mirrors the read payload exactly (`monto_pagado`, `metodo_pago`,
 * `monto_fisico`, `monto_virtual`, `comprobante_url`, `estado_verificacion`,
 * `detalles_pago`, `created_at`) so the frontend can render the cita's
 * payment breakdown without remapping.
 */
export type AdminAppointmentPayment = {
  id: number
  monto_pagado: string
  metodo_pago: 'VIRTUAL' | 'FISICO' | 'MIXTO'
  monto_fisico: string
  monto_virtual: string
  comprobante_url: string
  estado_verificacion: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO'
  detalles_pago: string
  created_at: string
}

/**
 * Cita union passed into `AdminRegisterAppointmentPaymentModal`.
 * Extends `ClientAppointment` so the modal can reuse the same
 * `operation` / `specialist` / `dateTime` / `isFreeMedicalAppointment`
 * fields already rendered by the cita sections. The four payment
 * fields (`precio`, `saldoPendiente`, `pagos_count`, `pagos`) are
 * optional here because not every call-site payload surfaces them
 * yet (e.g. client portal / kiosko); the modal reads them defensively
 * and the admin detail page always populates them.
 */
export type AdminAppointment = ClientAppointment & {
  /** Cita price (Bs, formatted "0.00"); backend default is 0. */
  precio?: string
  /** Residual balance after APROBADO payments (Bs, formatted). */
  saldoPendiente?: string
  /** Count of `PagoCita` rows attached to the cita. */
  pagos_count?: number
  /** Read serializer payments array (may be absent on legacy payloads). */
  pagos?: AdminAppointmentPayment[]
}

/**
 * Payload for `registerAdminAppointmentPayment` /
 * `registerAdminFreeAppointmentPayment`. Mirrors the backend
 * `PagoCitaCreateSerializer`: `paymentMethod` always required,
 * `montoFisico` / `montoVirtual` only for `MIXTO`, receipt optional
 * regardless of method (admin collected in person).
 */
export type RegisterAdminAppointmentPaymentPayload = {
  paymentMethod: 'VIRTUAL' | 'FISICO' | 'MIXTO'
  amount: string
  montoFisico?: string
  montoVirtual?: string
  receiptFile?: File
  details?: string
}

export type RegisterAdminAppointmentPaymentResponse = {
  detail: string
  payment: AdminAppointmentPayment
  /** Refreshed cita item carrying the new `precio` / `saldoPendiente` / `pagos[]`. */
  appointment: AdminAppointment
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

export type ExpenseCategory = {
  id: number
  name: string
  description: string
}

export type ExpenseItem = {
  id: string
  rawId: number
  date: string
  dateLabel: string
  categoryId: number
  category: string
  concept: string
  units: string
  unitCost: string
  total: string
  totalLabel: string
  provider: string
  invoiceUrl: string
  invoiceName: string
  details: string
  branchId: number
  branchName: string
  registeredBy: string
}

export type ExpensesResponse = {
  month: number
  year: number
  branch: {
    id: number
    name: string
  }
  metrics: AdminMetric[]
  categories: ExpenseCategory[]
  expenses: ExpenseItem[]
}

// --- Admin Reports ---
// Backend emits explicit camelCase rows under
// `/api/admin/reportes/{clientes,prospectos,ingresos}/` so the frontend never
// has to rename backend fields. The envelope mirrors the shape returned by
// `admin_report_clients` / `admin_report_prospects` / `admin_report_income`
// (`backend/config/api_views.py`): `{ branch, rows, cap, truncated }`, with
// `month`/`year` added on the income response.

export type ReportClient = {
  id: string
  rawId: number
  clienteCodigo?: string
  firstName: string
  lastName: string
  ci: string
  status: string
  lastAppointmentDate: string | null
  nextAppointmentDate: string | null
  lastPaymentDate: string | null
  nextPaymentDate: string | null
}

export type ReportProspect = {
  id: string
  rawId: number
  firstName: string
  lastName: string
  phone: string
  ci: string
  interest: string
  state: string
  createdAt: string
  registeredBy: string
  lastAppointmentDate: string | null
  nextAppointmentDate: string | null
}

export type ReportIncomeItem = {
  paymentId: number
  date: string
  time: string
  amount: string
  clientName: string
  serviceName: string
  status: string
  invoiceUrl: string | null
  invoiceName: string | null
}

export type ReportResponse<T> = {
  branch: {
    id: number
    name: string
  } | null
  rows: T[]
  cap: number
  truncated: boolean
  month?: number
  year?: number
}

export type UpsertAdminExpensePayload = {
  date: string
  categoryId: number | string
  concept: string
  units: string
  unitCost: string
  total: string
  provider: string
  details: string
  invoice?: File | null
}

export type AdminExpenseMutationResponse = {
  detail: string
  expense: ExpenseItem
}

export type AdminExpenseDeleteResponse = {
  detail: string
}

export type LegacyAgendaStatus = 'programada' | 'biometria' | 'confirmada'
export type AppointmentStatus = 'programada' | 'pendiente_verificacion' | 'confirmada'
export type VerificationStatus = 'pendiente' | 'verificada' | 'no_requerida'
export type VerificationMethod = 'biometria' | 'qr' | 'manual' | 'otro' | null

export type AgendaItemLegacy = {
  id: string
  time: string
  dateLabel: string
  patient: string
  clientId: number
  procedure: string
  operationId: number
  specialist: string
  status: LegacyAgendaStatus
  appointmentStatus: AppointmentStatus
  verificationStatus: VerificationStatus
  verificationMethod: VerificationMethod
  isToday: boolean
  isThisWeek: boolean
}

export type AgendaItem = Omit<AgendaItemLegacy, 'status'> & {
  status: AppointmentStatus
  verificationStatus: VerificationStatus
  verificationMethod: VerificationMethod
}

export type ProspectLead = {
  id: string
  rawId?: number
  name: string
  firstName?: string
  lastName?: string
  primerNombre?: string
  segundoNombre?: string
  apellidoPaterno?: string
  apellidoMaterno?: string
  phone: string
  interest: string
  registeredBy: string
  stage: string
  state?: string
  stateValue?: string
  /** Origen del prospecto, emitido por el backend en el payload de listado. */
  origen?: 'NUEVO' | 'RECURRENTE_PRE_SISTEMA'
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
  // --- citas-pagos follow-on: pago breakdown surfaced by the backend ---
  precio?: string
  saldoPendiente?: string
  pagos_count?: number
  pagos?: AdminAppointmentPayment[]
}

export type OperationCardData = {
  id: string
  rawId: number | null
  patient: string
  procedure: string
  branch: string
  branchId: number | null
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
  fechaNacimiento?: string
}

export type ClientSnapshot = {
  id: string
  rawId: number
  branchId?: number | null
  sucursalId?: number | null
  name: string
  phone: string
  ci: string
  status: string
  activeOperations: number
  totalOperations: number
  lastAnalysis: string
  scheduledAppointments: ClientScheduledAppointment[]
  hasBiometricEnrollment?: boolean
  email?: string
  clienteCodigo?: string
  // Entry-channel tag (NUEVO | RECURRENTE_PRE_SISTEMA) — surfaced per the
  // ``cliente-origen`` spec requirement that every Cliente-shaped payload
  // expose this field. The frontend renders it as a badge on the
  // ``/cms/clientes`` listing.
  origen?: 'NUEVO' | 'RECURRENTE_PRE_SISTEMA'
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
  canCancelFromVerification: boolean
  canManage: boolean
  // Planning fields used by the RescheduleModal prefill.
  duracionEstimadaMinutos?: number | null
  descripcionGeneral?: string
  notasPrevias?: string
  procedimientoPlanificado?: string
  zonaCuerpoPlanificada?: string
  especialistasPlanificados?: Array<{
    especialista_id: number
    especialista__usuario__first_name?: string
    especialista__usuario__last_name?: string
    especialista__usuario__username?: string
  }>
  maquinariaPlanificada?: Array<{
    maquinariaId: number
    cantidad: number
    maquinaria__nombre?: string
    maquinaria__marca?: string
  }>
  // Real-time close data populated by POST /cerrar/ once the client
  // confirms and the admin sets the close fields.
  hasRealTimeData?: boolean
  horaRealInicio?: string | null
  horaRealFin?: string | null
  procedimientoRealizado?: string
  zonaCuerpoRealizada?: string
  // descripcionGeneral / notasPrevias are already in the planning
  // block above; we just re-use them for the close panel.
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
  // --- Cita-level payment breakdown (mirrors the client-detail payload
  // so the operation-detail page can drive the same Cobrar cita modal).
  // `precio` / `saldoPendiente` / `pagos_count` / `pagos` are produced
  // by the backend helper `_cita_payment_breakdown`; they are optional
  // here because legacy payloads from before PR 2 may not surface them.
  precio?: string
  saldoPendiente?: string
  pagos_count?: number
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

export type OperationDetailQuota = {
  id: string
  rawId: number
  number: number
  amount: string
  amountValue: string
  paidAmount?: string
  paidAmountValue?: string
  dueDate: string
  status: string
  paymentsCount: number
  hasPendingReview?: boolean
  hasRejectedPayments?: boolean
}

export type OperacionFoto = {
  id: number
  /** Absolute URL ready for `<img src>` (the backend builds it from `request.build_absolute_uri`). */
  url: string
  /** ISO 8601 timestamp. */
  uploadedAt: string
  /** Filename the admin picked on disk (without the storage prefix). */
  fileName: string
}

export type OperationDetailData = {
  id: string
  rawId: number
  patient: string
  /**
   * `paciente_id` (Cliente.pk). Lo expone la API para que la pagina
   * de detalle de operacion pueda llamar al endpoint de reserva sin
   * tener que navegar al detalle del cliente.
   */
  patientId?: number
  /**
   * Cupos que quedan para una nueva reserva segun el backend
   * (mismo calculo que `operacion.sesiones_disponibles`). El frontend
   * usa este numero directo para bloquear el formulario "Reservar
   * nueva cita" sin parsear el string `sessions`.
   */
  availableAppointments?: number
  procedure: string
  serviceType: string
  procedureType: string
  branch: string
  branchId: number | null
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
  documentPdfUrl: string
  documentPdfName: string
  hasBiometricEnrollment: boolean
  appointments: OperationDetailAppointment[]
  quotas: OperationDetailQuota[]
  /**
   * Persistent before/after photo gallery embedded in the detail
   * payload. Ordered by `uploadedAt ASC, id ASC` per the spec.
   */
  fotosAntes: OperacionFoto[]
  fotosDespues: OperacionFoto[]
}

export type OperationDetailResponse = {
  operation: OperationDetailData
}

export type UpdateAdminOperationDetailsPayload = {
  details: string
  recommendations: string
  sessionsTotal: number
}

/**
 * Precondition report shared by ``Operacion.puede_cerrar`` (server)
 * and the client-side helper that powers the disabled state +
 * confirmation modal. Mirrors the backend JSON shape exactly:
 *
 *   {
 *     ok: false,
 *     sesiones: { ok, expected, confirmed, reserved, pending, missing },
 *     cuotas:  { ok, pending: [{ nroCuota, estado }, ...] },
 *     monto:   { ok, precioTotal, sumaMontoProgramado, diff }
 *   }
 *
 * Monetary fields are 2dp DECIMAL STRINGS (not numbers) to preserve
 * precision in the JSON round-trip and in JavaScript arithmetic.
 */
export type OperationClosurePreconditionSectionSesiones = {
  ok: boolean
  expected: number
  confirmed: number
  reserved: number
  pending: number
  missing: number
}

export type OperationClosurePreconditionSectionCuotas = {
  ok: boolean
  pending: Array<{ nroCuota: number; estado: string }>
}

export type OperationClosurePreconditionSectionMonto = {
  ok: boolean
  precioTotal: string
  sumaMontoProgramado: string
  diff: string
}

export type OperationClosurePreconditionsReport = {
  ok: boolean
  sesiones: OperationClosurePreconditionSectionSesiones
  cuotas: OperationClosurePreconditionSectionCuotas
  monto: OperationClosurePreconditionSectionMonto
}

/**
 * Successful 200 response from ``POST /api/admin/operaciones/<id>/finalizar/``
 * and ``POST /api/admin/operaciones/<id>/suspender/``. Shape mirrors
 * ``admin_update_operation_details`` so the page can ``reload()``
 * without a follow-up GET.
 */
export type OperationClosureResponse = {
  detail: string
  operation: OperationDetailData
}

/**
 * 409 response. Two sub-shapes share the same envelope:
 *
 *   * Precondition failure:
 *       { estado, preconditions: OperationClosurePreconditionsReport }
 *   * Source-state rejection:
 *       { detail: string, estado: string }
 *
 * The presence of ``preconditions`` is the discriminator. The page
 * helper checks it first and falls back to ``detail`` otherwise.
 */
export type OperationClosurePreconditionFailure = {
  detail?: string
  estado?: string
  preconditions?: OperationClosurePreconditionsReport
}

export type UpdateAdminOperationObservacionesResponse = {
  detail: string
  operation: OperationDetailData
}

export type UploadAdminOperationPhotosResponse = {
  detail: string
  saved: OperacionFoto[]
  /**
   * Per-file failure keys (`"archivos[1]"` style) keyed by their index
   * in the original request. Empty when every file was accepted.
   */
  errors: Record<string, string>
  operation: OperationDetailData
}

export type OperationPricePlanQuotaEdit = {
  nroCuota: number
  montoProgramado: string
  fechaVencimiento: string
}

export type UpdateAdminOperationPricePayload = {
  priceTotal: string
  quotaCount: number
  /**
   * Edicion opcional por cuota. Si se envia, cada item actualiza el
   * monto y la fecha de la cuota indicada; la suma de los nuevos
   * montos pendientes + lo ya pagado debe cerrar exacto con
   * `priceTotal`.
   */
  quotas?: OperationPricePlanQuotaEdit[]
}


export type PaymentsResponse = {
  month: number
  year: number
  metrics: AdminMetric[]
  paymentQrConfig: PaymentQrConfig
  payments: VerificationPayment[]
  quotas: AdminPaymentQuota[]
}

export type AdminPaymentQuota = {
  id: string
  rawId: number
  clientId: number
  patient: string
  operation: string
  quotaNumber: number
  amount: string
  paidAmount?: string
  dueDate: string
  status: string
  paymentsCount: number
}

export type UpdateAdminPaymentQrConfigResponse = {
  detail: string
  paymentQrConfig: PaymentQrConfig
}

export type GetAdminPaymentQrConfigResponse = {
  paymentQrConfig: PaymentQrConfig
}

export type UpdateAdminPaymentStatusPayload = {
  status: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO'
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
  | 'tipos-procedimiento'
  | 'campos-ficha'
  | 'patologias-cutaneas'
  | 'especialidades'
  | 'grupos-opciones'
  | 'categorias-gasto'
  | 'sectores'
  | 'secciones-ficha'
  | 'maquinaria'

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
  fechaNacimiento: string
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
  primerNombre: string
  segundoNombre: string
  apellidoPaterno: string
  apellidoMaterno: string
  telefono: string
  estado: 'PASAJERO' | 'DESCARTADO'
  observaciones: string
  /**
   * Tag the prospect with the entry-channel the radio at the top of
   * ``AdminProspectCreatePage`` collects. Mirrors the literal
   * union on ``Cliente.origen``; omitting the field falls back to
   * ``NUEVO`` at the backend (see migration 0016 and the
   * ``admin_crear_prospecto`` handler).
   */
  origen?: 'NUEVO' | 'RECURRENTE_PRE_SISTEMA'
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
  branchId: number
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

export type AppointmentDetail = {
  cliente_nombre: string | null
  tratamiento_nombre: string | null
  hora: string
  tipo: 'CitasMedicas' | 'CitasProspectos' | 'CitasClientesLibres'
}

export type AdminConcurrencyCheckResponse = {
  concurrency: number
  appointments?: AppointmentDetail[]
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
  specialistId?: number | null
  specialistIds?: number[]
  branchId: number | null
  type: 'AGREGAR' | 'BLOQUEAR'
  dates: string[]
  startTime: string
  endTime: string
  detail: string
  rangeStartDate?: string
  rangeEndDate?: string
  weekdayCodes?: number[]
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

// --- Admin User Recovery (assistant for forgotten username/password) ---
// Shapes returned by `/api/admin/usuarios/*` endpoints. The search endpoint
// returns the same `AdminUserRecoveryItem` shape as the detail endpoint,
// plus a wrapper envelope. The reset endpoint returns the temporary
// password plus a slim `user` subshape (the full payload is not echoed
// back to keep the response surface narrow after a security-sensitive op).

export type AdminUserRecoveryKind =
  | 'admin_principal'
  | 'admin_sucursal'
  | 'trabajador'
  | 'cliente'
  | 'otro'

export type AdminUserRecoveryItem = {
  id: number
  username: string
  fullName: string
  rol: string
  kind: AdminUserRecoveryKind
  email: string
  telefono: string
  ci: string
  sucursal: string
  sucursalId: number | null
  isActive: boolean
  mustChangePassword: boolean
}

export type AdminUserRecoveryDetail = AdminUserRecoveryItem & {
  createdAt: string | null
  lastLogin: string | null
}

export type AdminUserRecoverySearchResponse = {
  users: AdminUserRecoveryItem[]
}

export type AdminUserRecoveryResetResponse = {
  detail: string
  user: {
    id: number
    username: string
    fullName: string
  }
  temporaryPassword: string
  mustChangePassword: boolean
  sessionInvalidated: boolean
}

// --- Admin Database Backups ---
// Shapes returned by the `/api/admin/backups/*` endpoints. The list endpoint
// returns `{ results: BackupFile[] }`; the trigger endpoint streams the dump
// (octet-stream) so the frontend receives a `Blob`. `BackupFile.id` is the
// opaque server-side filename (also usable as `name`) and acts as the only
// stable identifier surfaced to the table.

export type BackupFile = {
  id: string
  name: string
  size: number
  modifiedAt: string
  /**
   * Server-computed Spanish relative-time label ("recien", "hace 2 dias",
   * "hace mas de 1 mes"). The table renders this as its own "Hace" column
   * so the operator can scan the freshness of every dump at a glance.
   */
  ageLabel: string
  isWeekly: boolean
}

export type BackupListResponse = {
  results: BackupFile[]
}

// -----------------------------------------------------------------------------
// Appointment Reservation Redesign
// -----------------------------------------------------------------------------

export type MaquinariaItem = {
  id: number
  nombre: string
  marca: string
  descripcion: string
  cantidadTotal: number
  sucursalId: number | null
  sucursalNombre: string | null
  activo: boolean
}

export type MaquinariaConflict = {
  maquinariaId: number
  nombre: string
  cantidadSolicitada: number
  cantidadDisponible: number
  citasQueLaUsan: Array<{
    citaId: number
    cliente: string
    fecha: string
    horaInicio: string
    horaFin: string
    planificada: boolean
  }>
}

export type MaquinariaConflictResponse = {
  conflictos: MaquinariaConflict[]
}

/**
 * Per-maquinaria availability, returned by
 * GET /api/admin/disponibilidad/check-maquinaria/. Always one entry per
 * requested maquinaría (even when there is no over-assignment) so the
 * admin can see what is already booked for the window.
 */
export type MaquinariaDisponibilidad = {
  maquinariaId: number
  nombre: string
  cantidadTotal: number
  cantidadSolicitada: number
  cantidadDisponible: number
  sobreAsignada: boolean
  citasQueLaUsan: Array<{
    citaId: number
    cliente: string
    fecha: string
    horaInicio: string
    horaFin: string
    planificada: boolean
  }>
}

/**
 * Per-specialist availability, returned by
 * GET /api/admin/disponibilidad/check-especialistas/. Lists every
 * specialist that was requested along with the citas where they are
 * assigned in the window.
 */
export type EspecialistaDisponibilidad = {
  especialistaId: number
  nombre: string
  citasAsignadas: Array<{
    citaId: number
    cliente: string
    fecha: string
    horaInicio: string
    horaFin: string
    planificada: boolean
  }>
}

export type EspecialistaDisponibilidadResponse = {
  disponibilidad: EspecialistaDisponibilidad[]
}

// Body for createAdminClientReservation: existing {branchId, dateTime} is
// kept for backward compat; all new fields are optional.
export type AdminReservationExtendedPayload = {
  branchId: number
  dateTime: string
  duracionEstimadaMinutos?: number | null
  descripcionGeneral?: string
  notasPrevias?: string
  procedimientoPlanificado?: string
  zonaCuerpoPlanificada?: string
  especialistasPlanificados?: Array<{
    especialista_id: number
    especialista__usuario__first_name?: string
    especialista__usuario__last_name?: string
    especialista__usuario__username?: string
  }>
  maquinariaPlanificada?: Array<{
    maquinariaId: number
    cantidad: number
    maquinaria__nombre?: string
    maquinaria__marca?: string
  }>
}

// Body for pendiente-biometria (close). All fields optional.
export type AdminCloseExtendedPayload = {
  horaRealInicio?: string
  horaRealFin?: string
  procedimientoRealizado?: string
  zonaCuerpoRealizada?: string
  especialistasAtendieron?: number[]
  maquinariaUtilizada?: Array<{ maquinariaId: number; cantidad: number }>
  /**
   * Optional photo files uploaded alongside the close payload.
   * The /cerrar/ endpoint accepts multipart so both text fields and
   * image files share one round-trip; missing files are a no-op so
   * JSON-only callers keep working unchanged.
   */
  fotoAntes?: File
  fotoDespues?: File
}

// PATCH /citas/<id>/notas/ — multipart; text fields and photos share one endpoint.
export type AdminAppointmentNotesPatchPayload = {
  descripcionGeneral?: string
  notasPrevias?: string
  notasPost?: string
  fotoAntes?: File
  fotoDespues?: File
}

export type AdminAppointmentNotesPatchResponse = {
  detail: string
  cita: unknown
}

export type MisCitasMaquinariaItem = {
  nombre: string
  cantidad: number
  planificada: boolean
}

export type MisCitasItem = {
  id: string
  rawId: number
  cliente: string
  fecha: string
  horaInicio: string
  duracionEstimadaMinutos: number | null
  procedimientoPlanificado: string
  zonaCuerpoPlanificada: string
  descripcionGeneral: string
  notasPrevias: string
  notasPost: string
  sucursal: string | null
  estado: string
  status?: string
  operation?: string
  maquinaria: MisCitasMaquinariaItem[]
}

export type MisCitasResponse = {
  citas: MisCitasItem[]
}
