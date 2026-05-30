import { useCallback, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

type ConfirmOptions = {
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: 'danger' | 'warning' | 'info'
}

type ConfirmDialogProps = {
  isOpen: boolean
  options: ConfirmOptions | null
  onConfirm: () => void
  onCancel: () => void
}

const toneStyles: Record<string, string> = {
  danger: 'button--danger',
  warning: 'button--warning',
  info: '',
}

function ConfirmDialogComponent({ isOpen, options, onConfirm, onCancel }: ConfirmDialogProps) {
  if (!isOpen || !options) return null

  const toneClass = toneStyles[options.tone ?? 'info'] ?? ''

  return createPortal(
    <div className="booking-modal-overlay" role="dialog" aria-modal="true" aria-label={options.title}>
      <div className="booking-modal-content _confirm-modal">
        <header className="booking-modal-header">
          <div>
            <h2 className="_m-0">{options.title}</h2>
          </div>
        </header>
        <div className="booking-modal-body _p-modal">
          <p className="_m-0 _white-space-pre">{options.message}</p>
          <div className="_flex-end _flex-gap-md _mt-md">
            <button className="button button--ghost" type="button" onClick={onCancel}>
              {options.cancelLabel ?? 'Cancelar'}
            </button>
            <button className={`button ${toneClass}`} type="button" onClick={onConfirm}>
              {options.confirmLabel ?? 'Confirmar'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}

export function useConfirmDialog() {
  const [confirmState, setConfirmState] = useState<{
    isOpen: boolean
    options: ConfirmOptions | null
  }>({ isOpen: false, options: null })

  const resolveRef = useRef<(value: boolean) => void>(() => {})

  const confirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve
      setConfirmState({ isOpen: true, options })
    })
  }, [])

  const handleConfirm = useCallback(() => {
    setConfirmState({ isOpen: false, options: null })
    resolveRef.current(true)
  }, [])

  const handleCancel = useCallback(() => {
    setConfirmState({ isOpen: false, options: null })
    resolveRef.current(false)
  }, [])

  const ConfirmDialog = () => (
    <ConfirmDialogComponent
      isOpen={confirmState.isOpen}
      options={confirmState.options}
      onConfirm={handleConfirm}
      onCancel={handleCancel}
    />
  )

  return { confirm, ConfirmDialog }
}