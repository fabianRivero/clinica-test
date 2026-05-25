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
      <div className="booking-modal-content" style={{ maxWidth: '480px' }}>
        <header className="booking-modal-header">
          <div>
            <h2 style={{ margin: 0 }}>{options.title}</h2>
          </div>
        </header>
        <div className="booking-modal-body" style={{ padding: '1rem 1.5rem' }}>
          <p style={{ marginTop: 0, whiteSpace: 'pre-line' }}>{options.message}</p>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
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