import { type FormEvent } from 'react'

import type { ProspectConversionBiometricData } from '../../../types/prospectConversion'

import type { FieldErrors } from './conversionHelpers'

type Props = {
  biometricForm: ProspectConversionBiometricData
  biometricStatus: string | null
  fieldErrors: FieldErrors
  isSaving: boolean
  isCancelling: boolean
  onCapture: () => void
  onSubmit: (event: FormEvent) => void
  onBack: () => void
  onCancel: () => void
}

export function ConversionStepBiometric({
  biometricForm,
  biometricStatus,
  fieldErrors,
  isSaving,
  isCancelling,
  onCapture,
  onSubmit,
  onBack,
  onCancel,
}: Props) {
  const providerLabel =
    biometricForm.provider === 'DIGITAL_PERSONA'
      ? 'DigitalPersona 4500'
      : biometricForm.provider === 'SECU_GEN_LEGACY'
        ? 'SecuGen (legacy)'
        : 'Simulador (legacy)'
  const isCaptured = Boolean(biometricForm.deviceSerial && biometricForm.quality > 0)
  return (
    <form className="form-grid" onSubmit={onSubmit}>
      <div className="wizard-block field--full">
        <div className="wizard-block__header">
          <div>
            <strong>Captura biometrica</strong>
            <p>Solicita al cliente que apoye el dedo en el lector DigitalPersona 4500. La captura la orquesta el backend.</p>
          </div>
          <button
            className="button button--ghost button--compact"
            disabled={isSaving || isCancelling}
            type="button"
            onClick={onCapture}
          >
            {isCaptured ? 'Volver a capturar' : 'Capturar huella'}
          </button>
        </div>
        <div className="operation-card__note-grid">
          <article>
            <span>Proveedor</span>
            <p>{providerLabel}</p>
          </article>
          <article>
            <span>Dispositivo</span>
            <p>{biometricForm.deviceSerial || 'Sin captura'}</p>
          </article>
          <article>
            <span>Calidad</span>
            <p>{biometricForm.quality ? `${biometricForm.quality}/100` : 'Pendiente'}</p>
          </article>
          <article>
            <span>Capturada</span>
            <p>{biometricForm.capturedAt || 'Pendiente'}</p>
          </article>
        </div>
        {biometricStatus ? <small className="field__hint">{biometricStatus}</small> : null}
        {fieldErrors.template ? <small className="field__error">{fieldErrors.template}</small> : null}
        {fieldErrors.quality ? <small className="field__error">{fieldErrors.quality}</small> : null}
      </div>

      <div className="form-actions field--full">
        <button
          className="button button--ghost"
          disabled={isSaving || isCancelling}
          type="button"
          onClick={onCancel}
        >
          {isCancelling ? 'Cancelando...' : 'Cancelar conversion'}
        </button>
        <button className="button button--ghost" disabled={isSaving || isCancelling} type="button" onClick={onBack}>
          Volver
        </button>
        <button className="button" disabled={isSaving || isCancelling} type="submit">
          {isSaving ? 'Guardando...' : 'Guardar y continuar'}
        </button>
      </div>
    </form>
  )
}
