import type { ProspectLead } from './admin'

export type ConversionStep = 1 | 2 | 3

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

export type ProspectConversionOperationData = {
  serviceConfigId: string
  zonaGeneral: string
  zonaEspecifica: string
  precioTotal: string
  cuotasTotales: number
  sesionesTotales: number
  fechaInicio: string
  fechaFinal: string
  estado: string
  detallesOperacion: string
  recomendaciones: string
  primeraFechaVencimiento: string
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

export type ProspectConversionDraft = {
  currentStep: ConversionStep
  stepUserCompleted: boolean
  stepOperationCompleted: boolean
  stepMedicalCompleted: boolean
  userData: ProspectConversionUserData
  operationData: ProspectConversionOperationData
  medicalData: ProspectConversionMedicalData
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
  prospect: ProspectLead
  draft: ProspectConversionDraft
  serviceConfigs: ProspectConversionServiceConfig[]
  operationStates: ProspectConversionStateOption[]
  medicalConfig: ProspectConversionMedicalConfig
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
