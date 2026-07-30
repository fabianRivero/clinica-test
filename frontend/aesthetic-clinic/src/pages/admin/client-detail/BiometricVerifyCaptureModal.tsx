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

import { biometricClient } from '../../../services/fingerprint/biometricClient'

/**
 * Minimum time (ms) the loading state stays on screen before the modal
 * transitions to success/error. The DigitalPersona 4500 can return
 * ``verify-no-match`` within ~200ms when fprintd has stale state from
 * the previous attempt (the second ``VerifyStart`` never waits for a
 * finger). Without this floor the operator would see the "Esperando
 * huella..." message for a single frame before the error renders.
 *
 * 3000ms is short enough to feel responsive on a happy path and long
 * enough for the operator to register the prompt.
 */
const MIN_LOADING_DISPLAY_MS = 3000

/**
 * Modal that drives the biometric verify flow on the appointment
 * confirmation path.
 *
 * State machine:
 *
 *   idle    → user pressed "Activar lector" → loading
 *   loading → verify-init succeeded         → success or error
 *           → verify-init failed             → error
 *   success → user dismissed                 → parent closes the modal
 *   error   → "Reintentar"                   → idle (next "Activar lector"
 *                                                runs another round-trip)
 *           → "Cancelar"                     → parent closes the modal
 *
 * The modal owns the `/verify-init` + `/verify-confirm` round-trip so
 * the parent no longer needs to know how the biometric backend works.
 * On success it fires `onConfirmResult({matched, message, citaId})`
 * and the parent decides whether to refetch.
 *
 * The shell follows the same `booking-modal-*` style as the rest of
 * the admin app so the visual language stays consistent.
 */

type IdleState = { kind: 'idle' }
type LoadingState = { kind: 'loading' }
type SuccessState = { kind: 'success'; matched: boolean; message: string }
type ErrorState = { kind: 'error'; message: string }
type ModalState = IdleState | LoadingState | SuccessState | ErrorState

export type BiometricVerifyResult = {
  matched: boolean
  message: string
  citaId: number
}

type Props = {
  open: boolean
  onClose: () => void
  citaId: number
  onConfirmResult: (result: BiometricVerifyResult) => void
  onAfterAttempt?: () => void
}

const FALLBACK_ERROR_MESSAGE = 'No se pudo confirmar la huella. Intenta nuevamente.'

export function BiometricVerifyCaptureModal({
  open,
  onClose,
  citaId,
  onConfirmResult,
  onAfterAttempt,
}: Props) {
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)
  const titleId = useId()

  const [state, setState] = useState<ModalState>({ kind: 'idle' })

  // Ref that guards against double-clicks / re-entrant activations.
  // ``state.kind === 'loading'`` would normally gate this, but the
  // guard is checked synchronously inside ``handleActivate`` so a fast
  // double-click before React re-renders the disabled button still
  // gets rejected.
  const inFlightRef = useRef(false)

  const isLoading = state.kind === 'loading'

  /**
   * Holds the loading state visible for at least ``MIN_LOADING_DISPLAY_MS``
   * milliseconds. We always wait the remainder of the budget before
   * transitioning to success/error so the operator sees the
   * "Esperando huella..." prompt long enough to put a finger on the
   * reader.
   */
  const ensureMinLoading = useCallback(async (startedAt: number) => {
    const elapsed = Date.now() - startedAt
    const remaining = MIN_LOADING_DISPLAY_MS - elapsed
    if (remaining > 0) {
      await new Promise((resolve) => window.setTimeout(resolve, remaining))
    }
  }, [])

  // Reset to idle whenever the modal opens so the operator always
  // sees the "Activar lector" affordance first. The pre-existing
  // modal pattern across the codebase (BiometricCaptureModal,
  // OptionGroupModal, ProfileEditModal, useConfirmDialog) uses the
  // same setState-in-effect shape, so we keep the same style here.
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
    // Re-entrancy guard. The button is also disabled while loading,
    // but a fast double-click before React commits the disabled prop
    // can still hit this handler twice; we reject the second call
    // synchronously instead of firing two parallel round-trips.
    if (inFlightRef.current) return
    inFlightRef.current = true

    const startedAt = Date.now()
    setState({ kind: 'loading' })

    try {
      const init = await biometricClient.verifyInit(citaId)

      // If the cliente has no fingerprint on file, the backend asks
      // us to fall back to manual confirmation. We surface that as an
      // error state so the operator clicks "Cancelar" and uses the
      // existing manual confirmation path.
      if (init.manual_only || init.has_fingerprint === false || !init.capture_token) {
        await ensureMinLoading(startedAt)
        setState({
          kind: 'error',
          message: 'Este cliente no tiene huella registrada. Usa la confirmacion manual.',
        })
        return
      }

      const confirm = await biometricClient.verifyConfirm(citaId, {
        capture_token: init.capture_token,
        score: init.score ?? 0,
      })

      // Hold the loading screen for the minimum display time so the
      // operator always sees "Esperando huella..." long enough to put
      // a finger on the reader — even when fprintd returned
      // ``verify-no-match`` in <3000ms.
      await ensureMinLoading(startedAt)

      if (confirm.matched) {
        setState({
          kind: 'success',
          matched: true,
          message: confirm.message,
        })
        onConfirmResult({
          matched: true,
          message: confirm.message,
          citaId,
        })
        return
      }

      // 200 OK with matched=false is a normal outcome (mock templates,
      // wrong finger, etc.). The operator needs to be able to retry.
      setState({
        kind: 'error',
        message: confirm.message || FALLBACK_ERROR_MESSAGE,
      })
    } catch (caughtError) {
      // Surface the backend's `detail` (already extracted by postJson)
      // instead of a generic "Failed to fetch" so the operator sees
      // the real reason (INVALID_TOKEN, LOW_QUALITY, etc.).
      await ensureMinLoading(startedAt)
      setState({
        kind: 'error',
        message:
          caughtError instanceof Error
            ? caughtError.message
            : FALLBACK_ERROR_MESSAGE,
      })
    } finally {
      inFlightRef.current = false
    }
  }, [citaId, ensureMinLoading, onConfirmResult])

  const handleRetry = useCallback(() => {
    // Reset to idle and re-focus the dialog so the operator can
    // immediately press "Activar lector" without having to Tab back
    // to the focusable dialog wrapper. The in-flight guard is cleared
    // by the ``finally`` in ``handleActivate`` so we don't need to
    // touch it here, but we still clear it defensively in case the
    // modal is closed and reopened mid-flight.
    inFlightRef.current = false
    setState({ kind: 'idle' })
    window.setTimeout(() => {
      dialogRef.current?.focus()
    }, 0)
  }, [])

  const handleSuccessClose = useCallback(() => {
    onClose()
    onAfterAttempt?.()
  }, [onClose, onAfterAttempt])

  if (!open) return null

  return createPortal(
    <div
      aria-hidden={!open}
      className="booking-modal-overlay biometric-capture-modal"
      data-testid="biometric-verify-capture-modal"
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
            <span className="biometric-capture-modal__eyebrow">Cita · Verificacion biometrica</span>
            <h2 id={titleId} className="_m-0 biometric-capture-modal__title">
              Confirmar cita con huella
            </h2>
          </div>
          <button
            aria-label="Cerrar modal de confirmacion"
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
              <p className="_m-0">
                Pide al cliente que apoye el dedo en el lector para confirmar la cita.
              </p>
              <p className="_mt-sm biometric-capture-modal__hint">
                Cuando estes listo, activa el lector. El sistema captura la huella,
                la compara con la plantilla guardada y, si coincide, la cita pasa a
                CONFIRMADA automaticamente.
              </p>
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
                  disabled={isLoading}
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
                Mantene el dedo apoyado hasta que el lector confirme la lectura.
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
              <strong>Huella confirmada. La cita paso a CONFIRMADA.</strong>
              {state.message ? (
                <p className="_mt-sm biometric-capture-modal__hint">{state.message}</p>
              ) : null}
              <div className="_flex-end _flex-gap-md _mt-lg">
                <button
                  className="button"
                  type="button"
                  onClick={handleSuccessClose}
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
              <div
                className="biometric-capture-modal__icon biometric-capture-modal__icon--error"
                aria-hidden="true"
              >
                !
              </div>
              <strong>No se pudo confirmar la huella</strong>
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

export default BiometricVerifyCaptureModal
