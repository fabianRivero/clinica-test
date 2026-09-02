import { useState, type ChangeEvent, type FormEvent } from 'react'

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
    amount: string
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
  // Derive a stable key for the open session; remounting on quota change
  // resets the form fields without an effect-driven setState cascade.
  const sessionKey = isOpen && quota ? `${quota.rawId}:${quota.amount}` : 'closed'

  if (!isOpen || !quota) {
    return null
  }

  return (
    <AdminRegisterPaymentModalBody
      key={sessionKey}
      quota={quota}
      isSubmitting={isSubmitting}
      errorMessage={errorMessage}
      onClose={onClose}
      onSubmit={onSubmit}
    />
  )
}

function AdminRegisterPaymentModalBody({
  quota,
  isSubmitting,
  errorMessage,
  onClose,
  onSubmit,
}: {
  quota: AdminPaymentQuota
  isSubmitting: boolean
  errorMessage: string | null
  onClose: () => void
  onSubmit: AdminRegisterPaymentModalProps['onSubmit']
}) {
  // The amount to register is fixed: it's the residual balance on the
  // cuota (programado - ya pagado). The admin registers the full
  // outstanding amount against the cuota; partial sub-payments are
  // tracked through the breakdown for MIXTO and the backend still
  // validates that the total matches the cuota before saving.
  const saldoPendiente = (() => {
    const programado = Number(quota.amount) || 0
    const pagado = Number(quota.paidAmount ?? '0') || 0
    const restante = programado - pagado
    return restante > 0 ? restante : programado
  })()
  const amount = saldoPendiente.toFixed(2)

  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('FISICO')
  // Pre-fill MIXTO breakdown so the two halves always sum to `amount`.
  // Default split is 50/50; the admin tweaks one side and the other
  // side recomputes automatically.
  const halfAmount = (saldoPendiente / 2).toFixed(2)
  const [montoFisico, setMontoFisico] = useState(halfAmount)
  const [montoVirtual, setMontoVirtual] = useState(halfAmount)
  const [receiptFile, setReceiptFile] = useState<File | null>(null)
  const [details, setDetails] = useState('')

  const handleReceiptFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setReceiptFile(event.target.files?.[0] || null)
  }

  const handleFisicoChange = (raw: string) => {
    setMontoFisico(raw)
    if (raw === '') return
    const fisico = Number(raw) || 0
    const clamped = Math.min(Math.max(fisico, 0), saldoPendiente)
    const virtual = Math.max(saldoPendiente - clamped, 0)
    setMontoVirtual(virtual.toFixed(2))
  }

  const handleVirtualChange = (raw: string) => {
    setMontoVirtual(raw)
    if (raw === '') return
    const virtual = Number(raw) || 0
    const clamped = Math.min(Math.max(virtual, 0), saldoPendiente)
    const fisico = Math.max(saldoPendiente - clamped, 0)
    setMontoFisico(fisico.toFixed(2))
  }

  const handleMethodChange = (method: PaymentMethod) => {
    setPaymentMethod(method)
    if (method === 'MIXTO') {
      // Reset breakdown to a clean 50/50 split on every entry into MIXTO.
      const half = (saldoPendiente / 2).toFixed(2)
      setMontoFisico(half)
      setMontoVirtual(half)
    }
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    void onSubmit({
      paymentMethod,
      amount,
      ...(paymentMethod === 'MIXTO'
        ? { montoFisico, montoVirtual }
        : {}),
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
              <span>
                Saldo pendiente: Bs {amount}
                {quota.paidAmount && Number(quota.paidAmount) > 0
                  ? ` (programado Bs ${quota.amount}, ya pagado Bs ${quota.paidAmount})`
                  : ''}
              </span>
              <input
                className="input"
                type="text"
                value={`Bs ${amount}`}
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
                  handleMethodChange(event.target.value as PaymentMethod)
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
                    onChange={(event) => handleFisicoChange(event.target.value)}
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
                    onChange={(event) => handleVirtualChange(event.target.value)}
                  />
                </label>
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
