import { useState, type ChangeEvent, type FormEvent } from 'react'

import type { AdminAppointment } from '../../types/admin'
import { PaymentQrPanel } from './PaymentQrPanel'

type PaymentMethod = 'VIRTUAL' | 'FISICO' | 'MIXTO'

export type AdminRegisterAppointmentPaymentModalProps = {
  appointment: AdminAppointment | null
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
 * Parameter variant of `AdminRegisterPaymentModal`. Opens from the
 * admin cita sections to charge a `CitaMedica` or `CitaClienteLibre`
 * at the consultorio. Header shows `<patient> | Cita <datetime>`,
 * reuses the VIRTUAL/FISICO/MIXTO + optional receipt form, and
 * disables submit when `precio == 0 || saldoPendiente == 0` per the
 * spec.
 *
 * Mirrors the cuota modal intentionally (no shared hook): the
 * disabled-when-over-paid rule, header shape, and submit payload
 * diverge enough that a shared `usePaymentForm` would carry more
 * conditionals than it removes. PR 3 keeps the form copy explicit
 * so the modal's contract is readable on its own.
 */
export function AdminRegisterAppointmentPaymentModal({
  appointment,
  isOpen,
  isSubmitting,
  errorMessage,
  onClose,
  onSubmit,
}: AdminRegisterAppointmentPaymentModalProps) {
  // Derive a stable key for the open session; remounting on appointment
  // change resets the form fields without an effect-driven setState cascade.
  const sessionKey =
    isOpen && appointment ? `${appointment.rawId}:${appointment.precio ?? '0'}` : 'closed'

  if (!isOpen || !appointment) {
    return null
  }

  return (
    <AdminRegisterAppointmentPaymentModalBody
      key={sessionKey}
      isOpen={isOpen}
      appointment={appointment}
      isSubmitting={isSubmitting}
      errorMessage={errorMessage}
      onClose={onClose}
      onSubmit={onSubmit}
    />
  )
}

function AdminRegisterAppointmentPaymentModalBody({
  isOpen,
  appointment,
  isSubmitting,
  errorMessage,
  onClose,
  onSubmit,
}: {
  isOpen: boolean
  appointment: AdminAppointment
  isSubmitting: boolean
  errorMessage: string | null
  onClose: () => void
  onSubmit: AdminRegisterAppointmentPaymentModalProps['onSubmit']
}) {
  // ``precio`` arrives from the backend formatted by ``currency()`` as
  // either ``"Bs 80.00"`` or just ``"0.00"`` (legacy zero stays
  // prefix-less). Parse defensively so both shapes work.
  const parseCurrency = (raw: string | undefined): number => {
    if (raw === undefined || raw === null || raw === '') return 0
    const cleaned = String(raw).replace(/^Bs\s*/i, '').replace(/,/g, '').trim()
    const num = Number(cleaned)
    return Number.isFinite(num) ? num : 0
  }
  const precioNumber = parseCurrency(appointment.precio)
  // Mirror the backend derivation: `precio - sum(APROBADO)`. We trust
  // the server-supplied `saldoPendiente` when present; otherwise fall
  // back to `precio` minus the sum of approved rows in the local
  // `pagos[]`.
  const approvedSum = (appointment.pagos ?? []).reduce((acc, pago) => {
    if (pago.estado_verificacion !== 'APROBADO') return acc
    const amount = Number(pago.monto_pagado) || 0
    return acc + amount
  }, 0)
  const backendSaldoRaw = parseCurrency(appointment.saldoPendiente)
  const backendSaldo = backendSaldoRaw > 0 ? backendSaldoRaw : 0
  const computedSaldo = backendSaldo > 0
    ? backendSaldo
    : Math.max(precioNumber - approvedSum, 0)
  const saldoPendiente = computedSaldo > 0 ? computedSaldo : 0
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
  // The branch QR is loaded + rendered by ``PaymentQrPanel`` (shared
  // with the cuota cobro modal). It owns its own fetch / lightbox
  // state so this modal stays focused on the form.

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

  // The spec disables submit when `precio == 0` (legacy non-billable
  // cita) OR when `saldoPendiente == 0` (already paid in full).
  const submitDisabled =
    precioNumber === 0 || saldoPendiente === 0 || isSubmitting

  // Header: `<patient> | Cita <datetime>`. For free appointments the
  // patient string is absent on the cita row itself; the parent page
  // resolves the patient label and forwards it via `operation` as a
  // visual stand-in (matching the cuota-modal contract). We fall back
  // to a generic label otherwise.
  const headerPatient = appointment.operation || appointment.specialist || 'Cita'

  return (
    <div
      className="payment-modal"
      role="dialog"
      aria-modal="true"
      aria-label="Cobrar cita"
    >
      <button
        aria-label="Cerrar modal de cobro"
        className="payment-modal__backdrop"
        type="button"
        onClick={onClose}
      />
      <div className="payment-modal__content">
        <header className="payment-modal__header">
          <div>
            <span>{headerPatient}</span>
            <strong>Cita {appointment.dateTime}</strong>
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
                Precio: Bs {precioNumber.toFixed(2)}
                {approvedSum > 0 ? ` (ya aprobado Bs ${approvedSum.toFixed(2)})` : ''}
              </span>
            </label>
            <label className="field">
              <span>
                Saldo pendiente: Bs {amount}
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
            <PaymentQrPanel paymentMethod={paymentMethod} isOpen={isOpen} />
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
          {precioNumber === 0 ? (
            <div className="form-error">
              Esta cita no tiene precio asignado; asigna uno antes de cobrar.
            </div>
          ) : null}
          {precioNumber > 0 && saldoPendiente === 0 ? (
            <div className="form-error">
              Esta cita ya fue cobrada en su totalidad.
            </div>
          ) : null}
          <div className="form-actions">
            <button
              className="button button--ghost"
              disabled={isSubmitting}
              type="button"
              onClick={onClose}
            >
              Cancelar
            </button>
            <button
              className="button"
              disabled={submitDisabled}
              type="submit"
            >
              {isSubmitting ? 'Registrando cobro...' : 'Cobrar cita'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
