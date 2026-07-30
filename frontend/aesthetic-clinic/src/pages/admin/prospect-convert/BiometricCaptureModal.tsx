import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
} from 'react'
import { createPortal } from 'react-dom'

/**
 * Modal that drives the live fingerprint capture at step 4 of the
 * prospect-to-cliente conversion wizard.
 *
 * State machine:
 *
 *   idle    → user pressed "Activar lector" → loading
 *   loading → onConfirm resolved { success: true }  → success
 *           → onConfirm resolved { success: false }  → error
 *   success → user dismissed → parent closes the modal
 *   error   → "Reintentar" → idle (next "Activar lector" runs another
 *             onConfirm round-trip)
 *
 * The parent owns the actual capture (it knows the prospect / cliente
 * id and which endpoint to call). This component only renders the
 * UI states and calls back through `onConfirm`.
 *
 * The modal follows the existing `booking-modal-*` style so it
 * matches every other dialog in the admin app.
 */

export type BiometricCaptureConfirmResult = {
  success: boolean
  errorMessage?: string
  calidadCaptura?: number
}

type Props = {
  open: boolean
  onClose: () => void
  onConfirm: () => Promise<BiometricCaptureConfirmResult>
  providerLabel?: string
  subjectName?: string
}

type IdleState = { kind: 'idle' }
type LoadingState = { kind: 'loading' }
type SuccessState = { kind: 'success'; calidadCaptura?: number }
type ErrorState = { kind: 'error'; message: string }
type ModalState = IdleState | LoadingState | SuccessState | ErrorState

export function BiometricCaptureModal({
  open,
  onClose,
  onConfirm,
  providerLabel = 'DigitalPersona 4500',
  subjectName,
}: Props) {
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)
  const titleId = useId()

  const [state, setState] = useState<ModalState>({ kind: 'idle' })

  const isLoading = state.kind === 'loading'

  // Reset to idle whenever the modal opens so the operator always
  // sees the "Activar lector" affordance first. The pre-existing
  // modal pattern across the codebase (OptionGroupModal,
  // ProfileEditModal, useConfirmDialog) uses the same setState-in-
  // effect shape, so we keep the same style here for consistency.
  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setState({ kind: 'idle' })
    }
  }, [open])

  // Lock body scroll while open + restore focus on close so screen
  // readers and keyboard users land back where they started.
  useEffect(() => {
    if (!open) {
      return
    }
    const previousOverflow = document.body.style.overflow
    const previousActiveElement = document.activeElement as HTMLElement | null
    previousFocusRef.current = previousActiveElement
    document.body.style.overflow = 'hidden'
    // Defer focus until after the modal mounts.
    const focusHandle = window.setTimeout(() => {
      dialogRef.current?.focus()
    }, 0)
    return () => {
      document.body.style.overflow = previousOverflow
      window.clearTimeout(focusHandle)
      previousFocusRef.current?.focus?.()
    }
  }, [open])

  const handleClose = useCallback(() => {
    if (isLoading) return
    onClose()
  }, [isLoading, onClose])

  const handleBackdropClick = useCallback(
    (event: MouseEvent<HTMLDivElement>) => {
      if (event.target === event.currentTarget) {
        handleClose()
      }
    },
    [handleClose],
  )

  const handleBackdropKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        handleClose()
      }
    },
    [handleClose],
  )

  const handleActivate = useCallback(async () => {
    setState({ kind: 'loading' })
    try {
      const result = await onConfirm()
      if (result.success) {
        setState({
          kind: 'success',
          calidadCaptura:
            typeof result.calidadCaptura === 'number'
              ? result.calidadCaptura
              : undefined,
        })
      } else {
        setState({
          kind: 'error',
          message: result.errorMessage || 'No se pudo capturar la huella.',
        })
      }
    } catch (caughtError) {
      setState({
        kind: 'error',
        message:
          caughtError instanceof Error
            ? caughtError.message
            : 'No se pudo capturar la huella.',
      })
    }
  }, [onConfirm])

  const handleRetry = useCallback(() => {
    setState({ kind: 'idle' })
  }, [])

  if (!open) return null

  const introLabel = subjectName
    ? `Es el momento de que ${subjectName} registre su huella en el lector ${providerLabel}.`
    : `Es el momento de que el cliente registre su huella en el lector ${providerLabel}.`
  const bodyHint = `Pedile que apoye el dedo indice sobre el lector cuando estes listo. El sistema captura la imagen, valida la calidad y cifra la plantilla antes de guardarla.`

  return createPortal(
    <div
      aria-hidden={!open}
      className="booking-modal-overlay biometric-capture-modal"
      data-testid="biometric-capture-modal"
      onClick={handleBackdropClick}
      onKeyDown={handleBackdropKeyDown}
      role="presentation"
    >
      <div
        aria-labelledby={titleId}
        aria-modal="true"
        className="booking-modal-content biometric-capture-modal__content"
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="booking-modal-header">
          <div>
            <span className="biometric-capture-modal__eyebrow">Paso 4 · Huella biometrica</span>
            <h2 id={titleId} className="_m-0 biometric-capture-modal__title">
              Capturar huella del cliente
            </h2>
          </div>
          <button
            aria-label="Cerrar modal de captura"
            className="button button--ghost button--compact"
            disabled={isLoading}
            type="button"
            onClick={handleClose}
          >
            Cerrar
          </button>
        </header>

        <div className="booking-modal-body biometric-capture-modal__body">
          {state.kind === 'idle' ? (
            <div className="biometric-capture-modal__section">
              <p className="_m-0">{introLabel}</p>
              <p className="_mt-sm biometric-capture-modal__hint">{bodyHint}</p>
              <div className="_flex-end _flex-gap-md _mt-lg">
                <button
                  className="button button--ghost"
                  type="button"
                  onClick={handleClose}
                >
                  Cancelar
                </button>
                <button
                  className="button"
                  type="button"
                  onClick={handleActivate}
                >
                  Activar lector
                </button>
              </div>
            </div>
          ) : null}

          {state.kind === 'loading' ? (
            <div
              className="biometric-capture-modal__section biometric-capture-modal__loading"
              role="status"
              aria-live="polite"
            >
              <div className="biometric-capture-modal__spinner" aria-hidden="true" />
              <strong>Esperando huella en el lector...</strong>
              <p className="_mt-sm biometric-capture-modal__hint">
                Mantene el dedo apoyado hasta que el lector confirme la captura.
              </p>
            </div>
          ) : null}

          {state.kind === 'success' ? (
            <div
              className="biometric-capture-modal__section biometric-capture-modal__success"
              role="status"
              aria-live="polite"
            >
              <div className="biometric-capture-modal__icon" aria-hidden="true">
                OK
              </div>
              <strong>
                Huella capturada
                {typeof state.calidadCaptura === 'number'
                  ? ` con calidad ${state.calidadCaptura}/100`
                  : '.'}
              </strong>
              <p className="_mt-sm biometric-capture-modal__hint">
                El template fue cifrado y guardado. Puedes cerrar este diálogo y
                continuar con la conversión.
              </p>
              <div className="_flex-end _flex-gap-md _mt-lg">
                <button
                  className="button"
                  type="button"
                  onClick={handleClose}
                >
                  Cerrar
                </button>
              </div>
            </div>
          ) : null}

          {state.kind === 'error' ? (
            <div
              className="biometric-capture-modal__section biometric-capture-modal__error"
              role="alert"
            >
              <div className="biometric-capture-modal__icon biometric-capture-modal__icon--error" aria-hidden="true">
                !
              </div>
              <strong>No se pudo capturar la huella</strong>
              <p className="_mt-sm biometric-capture-modal__hint">{state.message}</p>
              <div className="_flex-end _flex-gap-md _mt-lg">
                <button
                  className="button button--ghost"
                  type="button"
                  onClick={handleClose}
                >
                  Cancelar
                </button>
                <button
                  className="button"
                  type="button"
                  onClick={handleRetry}
                >
                  Reintentar
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>,
    document.body,
  )
}

export default BiometricCaptureModal