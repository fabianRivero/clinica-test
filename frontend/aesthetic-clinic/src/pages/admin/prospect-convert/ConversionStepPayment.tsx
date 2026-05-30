import { type ChangeEvent, type FormEvent } from 'react'

import type { FieldErrors } from './conversionHelpers'

type Props = {
  shouldRegisterFirstPayment: boolean
  firstPaymentDetails: string
  firstPaymentAmount: string
  paymentQrImageUrl: string
  fieldErrors: FieldErrors
  isSaving: boolean
  isCancelling: boolean
  onTogglePayment: (checked: boolean) => void
  onReceiptChange: (event: ChangeEvent<HTMLInputElement>) => void
  onDetailsChange: (event: ChangeEvent<HTMLTextAreaElement>) => void
  onQrModalToggle: (open: boolean) => void
  onSubmit: (event: FormEvent) => void
  onBack: () => void
  onCancel: () => void
}

export function ConversionStepPayment({
  shouldRegisterFirstPayment,
  firstPaymentDetails,
  firstPaymentAmount,
  paymentQrImageUrl,
  fieldErrors,
  isSaving,
  isCancelling,
  onTogglePayment,
  onReceiptChange,
  onDetailsChange,
  onQrModalToggle,
  onSubmit,
  onBack,
  onCancel,
}: Props) {
  return (
    <form className="form-grid" onSubmit={onSubmit}>
      <label className="field field--full _cursor-pointer">
        <span>Registrar primer pago en este paso</span>
        <input
          checked={shouldRegisterFirstPayment}
          type="checkbox"
          onChange={(event) => onTogglePayment(event.target.checked)}
        />
      </label>
      <div
        className="field--full"
        style={{
          opacity: shouldRegisterFirstPayment ? 1 : 0.5,
          pointerEvents: shouldRegisterFirstPayment ? 'auto' : 'none',
          transition: 'opacity 0.2s ease',
        }}
      >
        <div className="wizard-block field--full">
          {paymentQrImageUrl ? (
            <>
              <img
                src={paymentQrImageUrl}
                alt="QR de pago"
                style={{ maxWidth: 280, width: '100%', borderRadius: 12, cursor: 'zoom-in' }}
                onClick={() => onQrModalToggle(true)}
              />
              <button
                className="button button--ghost button--compact"
                type="button"
                onClick={() => onQrModalToggle(true)}
              >
                Ver QR en grande
              </button>
            </>
          ) : <p>No hay QR configurado.</p>}
        </div>
        <label className="field">
          <span>Monto del primer pago</span>
          <input className="input" readOnly value={firstPaymentAmount} />
          {fieldErrors.primerPagoMonto ? <small className="field__error">{fieldErrors.primerPagoMonto}</small> : null}
        </label>
        <label className="field field--full">
          <span>Comprobante</span>
          <input className="input input--file" disabled={!shouldRegisterFirstPayment} type="file" accept=".png,.jpg,.jpeg,.webp,.pdf,application/pdf,image/*" onChange={onReceiptChange} />
          {fieldErrors.primerPagoComprobante ? <small className="field__error">{fieldErrors.primerPagoComprobante}</small> : null}
        </label>
        <label className="field field--full">
          <span>Detalle</span>
          <textarea className="input textarea" disabled={!shouldRegisterFirstPayment} rows={3} value={firstPaymentDetails} onChange={onDetailsChange} />
        </label>
      </div>
      <div className="form-actions field--full">
        <button className="button button--danger" disabled={isSaving || isCancelling} type="button" onClick={onCancel}>
          {isCancelling ? 'Cancelando...' : 'Cancelar conversion'}
        </button>
        <button className="button button--ghost" disabled={isSaving || isCancelling} type="button" onClick={onBack}>Volver</button>
        <button className="button" disabled={isSaving || isCancelling} type="submit">{isSaving ? 'Confirmando...' : 'Confirmar pago y finalizar'}</button>
      </div>
    </form>
  )
}
