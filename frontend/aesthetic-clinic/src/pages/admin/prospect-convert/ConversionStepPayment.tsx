import { type ChangeEvent, type FormEvent } from 'react'

import type { FieldErrors } from './conversionHelpers'

type PaymentMethod = 'VIRTUAL' | 'FISICO' | 'MIXTO'

type Props = {
  shouldRegisterFirstPayment: boolean
  firstPaymentDetails: string
  firstPaymentReceipt: File | null
  firstPaymentAmount: string
  firstPaymentMethod: PaymentMethod
  firstPaymentFisico: string
  firstPaymentVirtual: string
  paymentQrImageUrl: string
  cuotasTotales: number | null
  fieldErrors: FieldErrors
  isSaving: boolean
  isCancelling: boolean
  onTogglePayment: (checked: boolean) => void
  onMethodChange: (method: PaymentMethod) => void
  onFisicoChange: (value: string) => void
  onVirtualChange: (value: string) => void
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
  firstPaymentReceipt,
  firstPaymentAmount,
  firstPaymentMethod,
  firstPaymentFisico,
  firstPaymentVirtual,
  paymentQrImageUrl,
  cuotasTotales,
  fieldErrors,
  isSaving,
  isCancelling,
  onTogglePayment,
  onMethodChange,
  onFisicoChange,
  onVirtualChange,
  onReceiptChange,
  onDetailsChange,
  onQrModalToggle,
  onSubmit,
  onBack,
  onCancel,
}: Props) {
  const showVirtualField = firstPaymentMethod === 'VIRTUAL' || firstPaymentMethod === 'MIXTO'
  const showFisicoField = firstPaymentMethod === 'FISICO' || firstPaymentMethod === 'MIXTO'
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
          {cuotasTotales == null ? (
            <small className="field__hint field--full">
              No definiste un plan de cuotas en el paso 2. Si registras un pago
              aquí, se creará automáticamente una cuota única por el precio
              total del tratamiento.
            </small>
          ) : null}
          {paymentQrImageUrl ? (
            <>
              <img
                src={paymentQrImageUrl}
                alt="QR de pago"
                className="_cursor-zoom-in"
                style={{ maxWidth: 280, width: '100%', borderRadius: 12 }}
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
          <span>Metodo de pago</span>
          <select
            className="input"
            disabled={!shouldRegisterFirstPayment}
            value={firstPaymentMethod}
            onChange={(event) => onMethodChange(event.target.value as PaymentMethod)}
          >
            <option value="VIRTUAL">Virtual (QR + comprobante)</option>
            <option value="FISICO">Fisico (caja del consultorio)</option>
            <option value="MIXTO">Mixto (parte QR + parte caja)</option>
          </select>
        </label>
        {showVirtualField ? (
          <label className="field">
            <span>Bs virtual</span>
            <input
              className="input"
              type="number"
              min="0"
              step="0.01"
              disabled={!shouldRegisterFirstPayment}
              value={firstPaymentVirtual}
              onChange={(event) => onVirtualChange(event.target.value)}
            />
          </label>
        ) : null}
        {showFisicoField ? (
          <label className="field">
            <span>Bs fisico</span>
            <input
              className="input"
              type="number"
              min="0"
              step="0.01"
              disabled={!shouldRegisterFirstPayment}
              value={firstPaymentFisico}
              onChange={(event) => onFisicoChange(event.target.value)}
            />
          </label>
        ) : null}
        {firstPaymentMethod === 'MIXTO' ? (
          <small className="field__hint field--full">
            La suma debe ser igual a Bs {firstPaymentAmount}.
          </small>
        ) : null}
        <label className="field">
          <span>Monto del primer pago</span>
          <input className="input" readOnly value={firstPaymentAmount} />
          {fieldErrors.primerPagoMonto ? <small className="field__error">{fieldErrors.primerPagoMonto}</small> : null}
        </label>
        <label className="field field--full">
          <span>Comprobante (opcional salvo metodo Virtual)</span>
          <input
            className="input input--file"
            disabled={!shouldRegisterFirstPayment}
            type="file"
            accept=".png,.jpg,.jpeg,.webp,.pdf,application/pdf,image/*"
            onChange={onReceiptChange}
          />
          {firstPaymentMethod === 'VIRTUAL' && !firstPaymentReceipt ? (
            <small className="field__hint">El metodo Virtual requiere comprobante.</small>
          ) : null}
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
