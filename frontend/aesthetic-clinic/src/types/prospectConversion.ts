import type { ProspectLead } from './admin'

export type ConversionStep = 1 | 2 | 3 | 4 | 5

export type ProspectConversionUserData = {
  primerNombre: string
  segundoNombre: string
  apellidoPaterno: string
  apellidoMaterno: string
  username: string
  email: string
  telefono: string
  ci: string
  codBiometrico: string
  fechaNacimiento: string
  nroHijos: number
  direccionDomicilio: string
  ocupacion: string
  observacionesCliente: string
  hasPassword: boolean
}

/**
 * Strict subset of `ProspectConversionUserData` accepted by
 * `PATCH /api/admin/clientes/<pk>/perfil/`. The endpoint is a partial
 * update, but the modal always sends the full 13-field payload so the
 * local type keeps every field required.
 *
 * Notably missing vs `ProspectConversionUserData`:
 * - `codBiometrico` — biometric code, not editable through this endpoint
 * - `hasPassword` — server-side signal only, not editable
 */
export type AdminClientProfilePatchPayload = {
  primerNombre: string
  segundoNombre: string
  apellidoPaterno: string
  apellidoMaterno: string
  username: string
  email: string
  telefono: string
  ci: string
  fechaNacimiento: string
  nroHijos: number
  direccionDomicilio: string
  ocupacion: string
  observacionesCliente: string
}

/**
 * Response envelope of `PATCH /api/admin/clientes/<pk>/perfil/`. The
 * server returns the full live snapshot of the 13 contract fields plus
 * the `hasPassword` signal under `client`, which matches the
 * `ProspectConversionUserData` shape (minus `codBiometrico`, which the
 * endpoint does not surface).
 */
export type AdminClientProfilePatchResponse = {
  client: Omit<ProspectConversionUserData, 'codBiometrico'>
}

export type ProspectConversionOperationData = {
  serviceConfigId: string
  zonaGeneral: string
  zonaEspecifica: string
  precioTotal: string
  // `cuotasTotales` y `sesionesTotales` pueden llegar `null` desde el
  // backend cuando el admin aun no las definio en el paso 2; el plan de
  // pagos y la cantidad de sesiones se completaran despues en otro flujo.
  cuotasTotales: number | null
  sesionesTotales: number | null
  fechaInicio: string
  fechaFinal: string
  estado: string
  detallesOperacion: string
  recomendaciones: string
  fechasVencimientoCuotas: string[]
}

export type ProspectConversionAntecedente = {
  antecedenteId: string
  tipoAntecedente: 'FAMILIAR' | 'PERSONAL'
  detalle: string
}

export type ProspectConversionImplante = {
  implanteId: string
  detalle: string
}

export type ProspectConversionCirugia = {
  cirugiaId: string
  haceCuantoTiempo: string
  detalle: string
}

export type ProspectConversionFieldResponse = {
  valueText: string
  valueNumber: string
  valueDate: string
  valueBoolean: boolean | null
  detail: string
  optionIds: number[]
}

export type ProspectConversionAnalysisData = {
  tipoPielId: string
  gradoDeshidratacionId: string
  grosorPielId: string
  patologiaIds: number[]
}

export type ProspectConversionMedicalData = {
  fechaFicha: string
  motivoConsulta: string
  observaciones: string
  consentimientoAceptado: boolean
  firmaPacienteCi: string
  analisisEstetico: ProspectConversionAnalysisData
  antecedentes: ProspectConversionAntecedente[]
  implantes: ProspectConversionImplante[]
  cirugias: ProspectConversionCirugia[]
  fieldResponses: Record<string, ProspectConversionFieldResponse>
}

export type ProspectConversionBiometricData = {
  provider: 'MOCK_LEGACY' | 'SECU_GEN_LEGACY' | 'DIGITAL_PERSONA'
  template: string
  quality: number
  deviceSerial: string
  consentAccepted: boolean
  capturedAt: string
}

export type ProspectConversionDraft = {
  currentStep: ConversionStep
  stepUserCompleted: boolean
  stepOperationCompleted: boolean
  stepMedicalCompleted: boolean
  stepBiometricCompleted: boolean
  userData: ProspectConversionUserData
  operationData: ProspectConversionOperationData
  medicalData: ProspectConversionMedicalData
  biometricData: ProspectConversionBiometricData
}

export type ProspectConversionServiceConfig = {
  id: number
  label: string
  serviceType: string
  procedureName: string
  procedureId: number | null
  basePrice: string
}

export type ProspectConversionStateOption = {
  value: string
  label: string
}

export type ProspectConversionCatalogItem = {
  id: number
  nombre: string
}

export type ProspectConversionFieldOption = {
  id: number
  code: string
  name: string
  value: string
}

export type ProspectConversionField = {
  id: number
  code: string
  label: string
  type: 'TEXTO' | 'NUMERO' | 'FECHA' | 'BOOLEANO' | 'SELECCION' | 'MULTISELECCION'
  isMultiple: boolean
  allowsDetail: boolean
  required: boolean
  options: ProspectConversionFieldOption[]
}

export type ProspectConversionSection = {
  id: number
  code: string
  name: string
  fields: ProspectConversionField[]
}

export type ProspectConversionMedicalConfig = {
  procedureId: number | null
  procedureName: string
  sections: ProspectConversionSection[]
  antecedentes: ProspectConversionCatalogItem[]
  implantes: ProspectConversionCatalogItem[]
  cirugias: ProspectConversionCatalogItem[]
  tiposPiel: ProspectConversionCatalogItem[]
  gradosDeshidratacion: ProspectConversionCatalogItem[]
  grosoresPiel: ProspectConversionCatalogItem[]
  patologiasCutaneas: ProspectConversionCatalogItem[]
}

export type ProspectConversionResponse = {
  prospect: ProspectLead | null
  client?: { id: number; name: string; ci: string; status: string; } | null
  /**
   * Top-level draft PK surfaced by the direct-mode initialize endpoint so
   * the wizard can build URLs of the form
   * `/api/admin/clientes/directo/<int:direct_id>/<step>/`. Optional on the
   * type because prospect / reactivation responses don't ship it (the
   * wizard routes those via URL params instead).
   */
  draftId?: number
  draft: ProspectConversionDraft
  serviceConfigs: ProspectConversionServiceConfig[]
  operationStates: ProspectConversionStateOption[]
  medicalConfig: ProspectConversionMedicalConfig
  crossCityWarning?: string | null
}

export type ProspectConversionFinalizeResponse = {
  detail: string
  client: {
    id: number
    name: string
  }
  operation: {
    id: number
    procedure: string
  }
}
