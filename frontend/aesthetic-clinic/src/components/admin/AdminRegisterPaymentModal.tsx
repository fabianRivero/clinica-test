import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'

import type { AdminPaymentQuota } from '../../types/admin'

type PaymentMethod = 'VIRTUAL' | 'FISICO' | 'MIXTO'

export type AdminRegisterPaymentModalProps = {
  quota: AdminPaymentQuota | null
  isOpen: boolean
  isSubmitting: boolean
  errorMessage: string | null
  onClose: () => void
  /**
   * Submits the form. Parent owns the API call and the success/error
   * notification; the modal only surfaces the form state and the
   * `errorMessage` prop. Resolves when the call finishes so the modal
   * can keep the spinner running while the request is in flight.
   */
  onSubmit: (payload: {
    paymentMethod: PaymentMethod
    montoFisico?: string
    montoVirtual?: string
    receiptFile?: File
    details?: string
  }) => Promise<void>
}

/**
 * Modal opened from the admin "Todas las cuotas" tab to register a
 * payment on behalf of a client. Reuses the same form shape as the
 * client page (VIRTUAL / FISICO / MIXTO selector + conditional
 * fields) but keeps the receipt optional regardless of method.
 */
export function AdminRegisterPaymentModal({
  quota,
  isOpen,
  isSubmitting,
  errorMessage,
  onClose,
  onSubmit,
}: AdminRegisterPaymentModalProps) {
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('FISICO')
  const [montoFisico, setMontoFisico] = useState('')
  const [montoVirtual, setMontoVirtual] = useState('')
  const [receiptFile, setReceiptFile] = useState<File | null>(null)
  const [details, setDetails] = useState('')

  // Reset the form whenever a different cuota is opened or the modal closes.
  useEffect(() => {
    if (isOpen) {
      setPaymentMethod('FISICO')
      setMontoFisico('')
      setMontoVirtual('')
      setReceiptFile(null)
      setDetails('')
    }
  }, [isOpen, quota?.rawId])

  if (!isOpen || !quota) {
    return null
  }

  const handleReceiptFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setReceiptFile(event.target.files?.[0] || null)
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    void onSubmit({
      paymentMethod,
      ...(montoFisico ? { montoFisico } : {}),
      ...(montoVirtual ? { montoVirtual } : {}),
      ...(receiptFile ? { receiptFile } : {}),
      ...(details ? { details } : {}),
    })
  }

  return (
    <div className="payment-modal" role="dialog" aria-modal="true" aria-label="Registrar pago">
      <button
        aria-label="Cerrar modal de pago"
        className="payment-modal__backdrop"
        type="button"
        onClick={onClose}
      />
      <div className="payment-modal__content">
        <header className="payment-modal__header">
          <div>
            <span>{quota.patient}</span>
            <strong>
              {quota.operation} | Cuota {quota.quotaNumber}
            </strong>
          </div>
          <button
            className="button button--ghost button--compact"
            type="button"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <form className="payment-upload-form" onSubmit={handleSubmit}>
          <div className="payment-upload-form__grid">
            <label className="field">
              <span>Monto programado</span>
              <input
                className="input"
                type="text"
                value={quota.amount}
                readOnly
                aria-readonly="true"
              />
            </label>
            <label className="field">
              <span>Metodo de pago</span>
              <select
                className="input"
                value={paymentMethod}
                onChange={(event) =>
                  setPaymentMethod(event.target.value as PaymentMethod)
                }
              >
                <option value="FISICO">Fisico (caja del consultorio)</option>
                <option value="VIRTUAL">Virtual (QR + comprobante)</option>
                <option value="MIXTO">Mixto (parte QR + parte caja)</option>
              </select>
            </label>
            {paymentMethod === 'MIXTO' ? (
              <>
                <label className="field">
                  <span>Bs fisico</span>
                  <input
                    className="input"
                    type="number"
                    min="0"
                    step="0.01"
                    value={montoFisico}
                    onChange={(event) => setMontoFisico(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Bs virtual</span>
                  <input
                    className="input"
                    type="number"
                    min="0"
                    step="0.01"
                    value={montoVirtual}
                    onChange={(event) => setMontoVirtual(event.target.value)}
                  />
                </label>
                <small className="field__hint field--full">
                  La suma debe ser igual al monto programado.
                </small>
              </>
            ) : null}
            <label className="field field--full">
              <span>Comprobante (opcional)</span>
              <input
                accept=".png,.jpg,.jpeg,.webp,.pdf,image/png,image/jpeg,image/webp,application/pdf"
                className="input input--file"
                type="file"
                onChange={handleReceiptFileChange}
              />
              <small className="field__hint">
                {receiptFile
                  ? `Archivo seleccionado: ${receiptFile.name}`
                  : 'Sube el comprobante si lo tienes; un pago en caja no lo requiere.'}
              </small>
            </label>
            <label className="field field--full">
              <span>Detalle</span>
              <textarea
                className="input textarea"
                rows={3}
                value={details}
                onChange={(event) => setDetails(event.target.value)}
                placeholder="Ejemplo: pago recibido en caja"
              />
            </label>
          </div>
          {errorMessage ? <div className="form-error">{errorMessage}</div> : null}
          <div className="form-actions">
            <button
              className="button button--ghost"
              disabled={isSubmitting}
              type="button"
              onClick={onClose}
            >
              Cancelar
            </button>
            <button className="button" disabled={isSubmitting} type="submit">
              {isSubmitting ? 'Registrando pago...' : 'Registrar pago'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
