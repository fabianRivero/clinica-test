import type {
  ConversionStep,
  ProspectConversionAntecedente,
  ProspectConversionBiometricData,
  ProspectConversionCirugia,
  ProspectConversionDraft,
  ProspectConversionFieldResponse,
  ProspectConversionImplante,
} from '../../../types/prospectConversion'

export const stepLabels: Array<{ step: ConversionStep; label: string }> = [
  { step: 1, label: 'Datos de usuario' },
  { step: 2, label: 'Operación' },
  { step: 3, label: 'Ficha médica' },
  { step: 4, label: 'Huella biométrica' },
  { step: 5, label: 'Primer pago (opcional)' },
]

export type FieldErrors = Record<string, string>

export function getInitialStep(draft: ProspectConversionDraft): ConversionStep {
  if (!draft.stepUserCompleted) return 1
  if (!draft.stepOperationCompleted) return 2
  if (!draft.stepMedicalCompleted) return 3
  return draft.stepBiometricCompleted ? 5 : 4
}

export function emptyFieldResponse(): ProspectConversionFieldResponse {
  return {
    valueText: '',
    valueNumber: '',
    valueDate: '',
    valueBoolean: null,
    detail: '',
    optionIds: [],
  }
}

export function blankAntecedente(): ProspectConversionAntecedente {
  return {
    antecedenteId: '',
    tipoAntecedente: 'PERSONAL',
    detalle: '',
  }
}

export function blankImplante(): ProspectConversionImplante {
  return {
    implanteId: '',
    detalle: '',
  }
}

export function blankCirugia(): ProspectConversionCirugia {
  return {
    cirugiaId: '',
    haceCuantoTiempo: '',
    detalle: '',
  }
}

export function blankBiometricData(): ProspectConversionBiometricData {
  return {
    provider: 'DIGITAL_PERSONA',
    template: '',
    quality: 0,
    deviceSerial: '',
    consentAccepted: true,
    capturedAt: '',
  }
}

export function buildDueDateList(count: number, currentValues: string[]) {
  return Array.from({ length: count }, (_, index) => currentValues[index] || '')
}
