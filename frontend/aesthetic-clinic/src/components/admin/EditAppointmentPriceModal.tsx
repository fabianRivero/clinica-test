import { useState } from 'react'

/**
 * Modal for editing the ``precio`` of a prospect appointment.
 *
 * The backend locks the price once the first APROBADO PagoCita exists
 * (see ``admin_update_prospect_medical_appointment_precio`` in
 * ``backend/config/api_views.py``); this modal mirrors that constraint
 * by simply forwarding the call and surfacing whatever error the
 * backend returns.
 *
 * The modal is intentionally minimal — it only edits ``precio`` for
 * prospecto appointments. The cliente and cliente-libre flows reuse
 * existing edit surfaces (operation details, free appointment card).
 */
export type EditAppointmentPriceModalProps = {
  citaRawId: number
  currentPrecio: string  // formatted "Bs 0.00"
  isOpen?: boolean
  isSubmitting?: boolean
  errorMessage?: string | null
  onClose: () => void
  onSubmit: (newPrecio: string) => Promise<void> | void
}

function parsePrecioCurrency(label: string): string {
  // Strip "Bs " prefix and commas, return the bare number string.
  return label.replace(/^Bs\s*/i, '').replace(/,/g, '').trim()
}

export function EditAppointmentPriceModal({
  citaRawId,
  currentPrecio,
  isOpen = true,
  isSubmitting = false,
  errorMessage = null,
  onClose,
  onSubmit,
}: EditAppointmentPriceModalProps) {
  // Strip the ``Bs `` prefix + commas from the backend-formatted price
  // so the controlled <input type="number"> starts at the right value.
  const initialDraft = parsePrecioCurrency(currentPrecio)
  const [draft, setDraft] = useState(initialDraft)

  if (!isOpen) return null

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    void onSubmit(draft)
  }

  return (
    <div
      className="payment-modal"
      role="dialog"
      aria-modal="true"
      aria-label="Editar precio de la cita"
    >
      <button
        aria-label="Cerrar modal de precio"
        className="payment-modal__backdrop"
        type="button"
        onClick={onClose}
      />
      <div className="payment-modal__content">
        <header className="payment-modal__header">
          <div>
            <span>Cita #{citaRawId}</span>
            <strong>Editar precio</strong>
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
              <span>Precio actual</span>
              <input className="input" type="text" value={currentPrecio} readOnly aria-readonly="true" />
            </label>
            <label className="field">
              <span>Nuevo precio (Bs)</span>
              <input
                className="input"
                type="number"
                min="0"
                step="0.01"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                required
                aria-label="Nuevo precio de la cita"
              />
              <small className="field__hint">
                Una vez registrado el primer cobro aprobado, el precio queda fijo.
              </small>
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
              {isSubmitting ? 'Guardando...' : 'Guardar precio'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}