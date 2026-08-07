import { useEffect, useId, useRef } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'

type TriggerBackupModalProps = {
  isOpen: boolean
  isSubmitting: boolean
  errorMessage: string | null
  onCancel: () => void
  onConfirm: () => void
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

/**
 * Inline confirmation dialog before kicking off a manual backup. The trigger
 * endpoint spins up `pg_dump`/`sqlite3 .backup`, which can take a few
 * seconds, so we surface a confirm step that warns the user the action will
 * produce a download. Mirrors the visual language of `booking-modal-*` so the
 * dialog blends with every other admin confirm (e.g. branch deactivation).
 */
export function TriggerBackupModal({
  isOpen,
  isSubmitting,
  errorMessage,
  onCancel,
  onConfirm,
}: TriggerBackupModalProps) {
  const titleId = useId()
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  // Restore focus to the trigger button when the modal closes.
  useEffect(() => {
    if (isOpen) return
    previousFocusRef.current?.focus?.()
  }, [isOpen])

  // Capture focus and ESC key while open.
  useEffect(() => {
    if (!isOpen) return
    const dialogNode = dialogRef.current
    if (!dialogNode) return

    previousFocusRef.current = document.activeElement as HTMLElement | null

    const focusables = dialogNode.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
    const first = focusables[0]
    if (first) {
      first.focus()
    } else {
      dialogNode.focus()
    }

    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onCancel()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = dialogNode?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ?? []
      if (focusable.length === 0) {
        event.preventDefault()
        return
      }
      const firstFocusable = focusable[0]
      const lastFocusable = focusable[focusable.length - 1]
      const active = document.activeElement as HTMLElement | null
      if (event.shiftKey && active === firstFocusable) {
        event.preventDefault()
        lastFocusable.focus()
      } else if (!event.shiftKey && active === lastFocusable) {
        event.preventDefault()
        firstFocusable.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, onCancel])

  if (!isOpen) return null

  function handleBackdropClick(event: React.MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isSubmitting) {
      onCancel()
    }
  }

  function handleBackdropKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape' && !isSubmitting) {
      event.stopPropagation()
      onCancel()
    }
  }

  return (
    <div
      aria-hidden={!isOpen}
      className="booking-modal-overlay"
      data-testid="backup-trigger-modal"
      onClick={handleBackdropClick}
      onKeyDown={handleBackdropKeyDown}
      role="presentation"
    >
      <div
        aria-labelledby={titleId}
        aria-modal="true"
        className="booking-modal-content _confirm-modal"
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="booking-modal-header">
          <div>
            <h2 className="_m-0" id={titleId}>
              Crear respaldo
            </h2>
            <p className="_m-0 _text-muted">Se generara una descarga de la base de datos.</p>
          </div>
        </header>
        <div className="booking-modal-body _p-modal">
          <p className="_m-0">
            Esto generara una descarga de la base de datos, puede tardar unos segundos. ¿Deseas continuar?
          </p>
          {errorMessage ? (
            <div className="form-error _mt-md" data-testid="backup-trigger-error">
              {errorMessage}
            </div>
          ) : null}
          <div className="_flex-end _flex-gap-md _mt-md">
            <button
              className="button button--ghost"
              disabled={isSubmitting}
              type="button"
              onClick={onCancel}
            >
              Cancelar
            </button>
            <button
              className="button"
              data-testid="backup-trigger-confirm"
              disabled={isSubmitting}
              type="button"
              onClick={onConfirm}
            >
              {isSubmitting ? 'Generando...' : 'Crear y descargar'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
