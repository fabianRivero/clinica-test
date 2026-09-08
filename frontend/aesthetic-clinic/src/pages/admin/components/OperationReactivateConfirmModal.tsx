import { type ReactElement } from 'react'

interface OperationReactivateConfirmModalProps {
  open: boolean
  operationLabel: string
  isSubmitting: boolean
  sourceStateError?: string | null
  onClose: () => void
  onConfirm: () => void
}

/**
 * Confirmation modal for the operation-detail "Reactivar tratamiento"
 * flow. Inverse of ``OperationClosureConfirmModal``'s suspender mode:
 * no preconditions to satisfy (the source state is the only gate, and
 * the server already enforces SUSPENDIDA -> EN_PROCESO). Kept as a
 * dedicated modal — reusing ``OperationClosureConfirmModal`` would
 * have to thread an inert precondition report just to make the
 * suspender-branch render, which adds noise to a flow that is
 * intentionally simpler than finalize / suspend.
 */
export function OperationReactivateConfirmModal({
  open,
  operationLabel,
  isSubmitting,
  sourceStateError,
  onClose,
  onConfirm,
}: OperationReactivateConfirmModalProps): ReactElement | null {
  if (!open) return null
  return (
    <div
      className="booking-modal-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Reactivar operacion"
      data-testid="operation-reactivate-confirm-modal"
    >
      <div
        className="booking-modal-content _max-w-modal-md"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="booking-modal-header">
          <h2>Reactivar operacion</h2>
          <button type="button" className="booking-modal-close" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="booking-modal-body _p-modal">
          <p className="_mb-md">
            Vas a reactivar el tratamiento <strong>{operationLabel}</strong>. Las citas y
            cuotas existentes vuelven a estar editables; el plan de pagos y el conteo de
            sesiones no se modifican automaticamente, asi que podras revisarlos antes de
            continuar.
          </p>
          {sourceStateError ? (
            <div
              className="_panel-card"
              style={{
                border: '1px solid rgba(220, 53, 69, 0.45)',
                background: 'rgba(220, 53, 69, 0.08)',
                marginBottom: '1rem',
              }}
              data-testid="operation-reactivate-source-error"
            >
              <strong>No se puede reactivar la operacion:</strong> {sourceStateError}
            </div>
          ) : null}
          <div className="_panel-card">
            <strong>Estado actual: Suspendida.</strong>
            <p className="field__hint _mt-sm _mb-0">
              Esta accion mueve la operacion de Suspendida a En proceso y limpia los
              campos de auditoria del cierre manual (quien la cerro y cuando).
            </p>
          </div>
        </div>
        <footer
          className="booking-modal-footer"
          style={{
            padding: '1rem 1.5rem 1.5rem',
            display: 'flex',
            gap: '0.75rem',
            justifyContent: 'flex-end',
          }}
        >
          <button
            type="button"
            className="button button--ghost"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancelar
          </button>
          <button
            type="button"
            className="button button--primary"
            onClick={onConfirm}
            disabled={isSubmitting}
            data-testid="operation-reactivate-confirm-button"
          >
            {isSubmitting ? 'Procesando...' : 'Reactivar operacion'}
          </button>
        </footer>
      </div>
    </div>
  )
}