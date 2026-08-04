import { type FormEvent } from 'react'

import type { ProspectConversionBiometricData } from '../../../types/prospectConversion'

import type { FieldErrors } from './conversionHelpers'
import {
  BiometricCaptureModal,
  type BiometricCaptureConfirmResult,
} from './BiometricCaptureModal'

type Props = {
  biometricForm: ProspectConversionBiometricData
  biometricStatus: string | null
  biometricModalOpen: boolean
  biometricModalSubjectName: string
  biometricSuspended: boolean
  fieldErrors: FieldErrors
  isSaving: boolean
  isCancelling: boolean
  onOpenBiometricModal: () => void
  onCloseBiometricModal: () => void
  onConfirmCapture: () => Promise<BiometricCaptureConfirmResult>
  onSubmit: (event: FormEvent) => void
  onBack: () => void
  onCancel: () => void
}

export function ConversionStepBiometric({
  biometricForm,
  biometricStatus,
  biometricModalOpen,
  biometricModalSubjectName,
  biometricSuspended,
  fieldErrors,
  isSaving,
  isCancelling,
  onOpenBiometricModal,
  onCloseBiometricModal,
  onConfirmCapture,
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
            <p>
              {biometricSuspended
                ? 'La captura por huella esta temporalmente suspendida. Podes continuar y finalizar la conversion sin huella; los datos existentes del cliente (si los hay) quedan intactos.'
                : 'Solicita al cliente que apoye el dedo en el lector DigitalPersona 4500.'}
            </p>
          </div>
          {biometricSuspended ? null : (
            <button
              className="button button--ghost button--compact"
              disabled={isSaving || isCancelling}
              type="button"
              onClick={onOpenBiometricModal}
            >
              {isCaptured ? 'Volver a capturar' : 'Capturar huella'}
            </button>
          )}
        </div>
        {biometricSuspended ? (
          <div
            className="banner banner--warning"
            data-testid="biometric-suspended-banner"
            role="status"
            aria-live="polite"
          >
            <strong>Huella biometrica suspendida.</strong>
            <span>
              Esta conversion se registrara sin captura; el backend omitira la escritura de la
              huella y del intento biometrico.
            </span>
          </div>
        ) : null}
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

      <BiometricCaptureModal
        open={biometricModalOpen}
        onClose={onCloseBiometricModal}
        onConfirm={onConfirmCapture}
        providerLabel={providerLabel}
        subjectName={biometricModalSubjectName}
      />
    </form>
  )
}