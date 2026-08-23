import {
  type ChangeEvent,
  type FormEvent,
  useState,
} from 'react'

import { useAuth } from '../../providers/AuthProvider'
import { useNotifications } from '../../providers/NotificationProvider'

/**
 * Inescapable change-password modal driven by `user.mustChangePassword`.
 *
 * Mounted once at the root of `App`. While the flag is true (set by
 * the admin-assisted reset flow in /cms/equipo/recuperar), the modal
 * is always open and cannot be dismissed: there is no close button,
 * the backdrop click does nothing, and Escape is captured. The
 * only way out is to submit a new password that clears the flag,
 * or to log out (the modal exposes a secondary "Cerrar sesion"
 * link because some users will need to fall back to the recovery
 * flow instead of typing a new password here).
 *
 * The modal only renders the password field on purpose. Username,
 * email, and phone stay visible in the regular ProfileEditModal but
 * are deliberately hidden here so the user is not tempted to
 * fiddle with anything except the password they must change.
 *
 * State lifecycle: when the flag flips back to false (after a
 * successful password change), the component returns null and
 * unmounts, so the next time the flag flips on we get fresh state
 * with no leftover draft.
 */
export function ForcePasswordChange() {
  const { user, updateProfile, logout } = useAuth()
  const { showNotification } = useNotifications()
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)

  if (!user?.mustChangePassword) {
    return null
  }

  const handlePasswordChange = (event: ChangeEvent<HTMLInputElement>) => {
    setPassword(event.target.value)
    if (error) setError(null)
  }
  const handleConfirmChange = (event: ChangeEvent<HTMLInputElement>) => {
    setConfirmPassword(event.target.value)
    if (error) setError(null)
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (isSaving || loggingOut) return

    if (password.length < 8) {
      setError('La contrasena debe tener al menos 8 caracteres.')
      return
    }
    if (password !== confirmPassword) {
      setError('La contrasena y su confirmacion no coinciden.')
      return
    }

    setIsSaving(true)
    setError(null)
    try {
      await updateProfile({ password })
      showNotification({
        title: 'Contrasena actualizada',
        message: 'Tu cuenta esta lista para usar.',
        tone: 'success',
      })
      // The AuthProvider's updateProfile re-fetches /me/ and the flag
      // will already be false, so the modal will unmount on the next
      // render.
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo actualizar la contrasena.',
      )
    } finally {
      setIsSaving(false)
    }
  }

  const handleLogout = async () => {
    if (loggingOut) return
    setLoggingOut(true)
    try {
      await logout()
    } finally {
      setLoggingOut(false)
    }
  }

  // Block Escape so the user can't accidentally dismiss the modal.
  // The keydown handler is on the form element (which always
  // renders) so it captures the event before any other element
  // could handle it.
  const blockEscape = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
    }
  }

  return (
    <div
      className="booking-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="force-password-title"
      // No onClick on the overlay: backdrop click is intentionally
      // disabled because the modal must be inescapable.
    >
      <div
        className="booking-modal-content"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="booking-modal-header">
          <h2 id="force-password-title">Cambia tu contrasena</h2>
        </header>
        <div className="booking-modal-body">
          <p>
            Un administrador restablecio tu contrasena. Para seguir
            trabajando, define una nueva contrasena. Tendra al menos 8
            caracteres.
          </p>
          <form
            className="form-grid"
            onSubmit={handleSubmit}
            onKeyDown={blockEscape}
          >
            <label className="field field--full">
              <span>Nueva contrasena</span>
              <input
                className="input"
                type="password"
                name="password"
                value={password}
                onChange={handlePasswordChange}
                autoFocus
                autoComplete="new-password"
                minLength={8}
                required
                aria-invalid={error ? true : undefined}
              />
            </label>
            <label className="field field--full">
              <span>Confirmar nueva contrasena</span>
              <input
                className="input"
                type="password"
                name="confirmPassword"
                value={confirmPassword}
                onChange={handleConfirmChange}
                autoComplete="new-password"
                minLength={8}
                required
                aria-invalid={error ? true : undefined}
              />
            </label>
            {error ? (
              <p className="field__error _col-full">{error}</p>
            ) : null}
            <div className="form-actions field--full">
              <button
                className="button button--ghost"
                type="button"
                onClick={handleLogout}
                disabled={isSaving || loggingOut}
              >
                {loggingOut ? 'Cerrando sesion...' : 'Cerrar sesion'}
              </button>
              <button
                className="button"
                type="submit"
                disabled={isSaving || loggingOut || !password || !confirmPassword}
              >
                {isSaving ? 'Guardando...' : 'Actualizar contrasena'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}