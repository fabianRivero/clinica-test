import { useEffect, useState } from 'react'

import { getAdminPaymentQrConfig } from '../../services/api/admin'

/**
 * QR thumbnail + lightbox shared by every admin cobro modal.
 *
 * The cobre modal for citas (`AdminRegisterAppointmentPaymentModal`) and
 * the cobre modal for cuotas (`AdminRegisterPaymentModal`) both want
 * to surface the branch QR under the ``Método de pago`` selector when
 * the admin picks VIRTUAL or MIXTO. The full request/lightbox/close
 * logic lives here so both modals stay focused on the form.
 *
 * Hidden when:
 *   * the admin picked FISICO (no QR makes sense for cash), OR
 *   * the branch has no QR configured.
 *
 * Click on the thumbnail → fullscreen lightbox (z-index above the
 * modal itself so it actually zooms).
 */
export type PaymentQrPanelProps = {
  paymentMethod: 'VIRTUAL' | 'FISICO' | 'MIXTO'
  /** When the modal opens, the panel kicks off a QR fetch. */
  isOpen: boolean
}

export function PaymentQrPanel({ paymentMethod, isOpen }: PaymentQrPanelProps) {
  const [qrImageUrl, setQrImageUrl] = useState<string | null>(null)
  const [qrExpanded, setQrExpanded] = useState(false)

  useEffect(() => {
    // Re-load on every modal open so the branch QR stays current.
    if (!isOpen) {
      setQrImageUrl(null)
      setQrExpanded(false)
      return
    }
    let cancelled = false
    getAdminPaymentQrConfig()
      .then((response) => {
        if (cancelled) return
        setQrImageUrl(
          response.paymentQrConfig.hasQr
            ? response.paymentQrConfig.qrImageUrl
            : null,
        )
      })
      .catch(() => {
        if (cancelled) return
        setQrImageUrl(null)
      })
    return () => {
      cancelled = true
    }
  }, [isOpen])

  if (paymentMethod === 'FISICO' || !qrImageUrl) {
    return null
  }

  return (
    <div className="field field--full">
      <span>QR para pagos virtuales</span>
      <button
        type="button"
        className="payment-modal__qr-trigger"
        aria-label="Ampliar QR"
        onClick={() => setQrExpanded(true)}
      >
        <img
          src={qrImageUrl}
          alt="QR configurado para la sucursal"
          style={{
            maxWidth: '180px',
            maxHeight: '180px',
            borderRadius: '8px',
            border: '1px solid var(--color-border)',
            padding: '4px',
            background: '#fff',
            display: 'block',
          }}
        />
        <small className="field__hint">Click para ampliar.</small>
      </button>
      {qrExpanded ? (
        <div
          className="payment-modal__qr-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label="QR ampliado"
          onClick={() => setQrExpanded(false)}
        >
          <button
            type="button"
            className="button button--ghost button--compact payment-modal__qr-lightbox-close"
            aria-label="Cerrar QR ampliado"
            onClick={(event) => {
              event.stopPropagation()
              setQrExpanded(false)
            }}
          >
            ×
          </button>
          <img
            src={qrImageUrl}
            alt="QR configurado para la sucursal (ampliado)"
            onClick={(event) => event.stopPropagation()}
            style={{
              maxWidth: 'min(90vw, 480px)',
              maxHeight: 'min(90vh, 480px)',
              borderRadius: '12px',
              background: '#fff',
              padding: '12px',
            }}
          />
        </div>
      ) : null}
    </div>
  )
}