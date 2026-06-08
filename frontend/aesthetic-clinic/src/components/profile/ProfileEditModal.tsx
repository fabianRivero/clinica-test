import { type ChangeEvent, type FormEvent, useEffect, useState } from 'react'

import { useAuth } from '../../providers/AuthProvider'
import type { ProfileUpdatePayload } from '../../types/auth'

type Props = {
  isOpen: boolean
  onClose: () => void
}

export function ProfileEditModal({ isOpen, onClose }: Props) {
  const { user, updateProfile } = useAuth()
  const [form, setForm] = useState<ProfileUpdatePayload>({
    username: '',
    email: '',
    telefono: '',
    password: '',
  })
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen && user) {
      setForm((prev) => {
        const next = {
          username: user.username || '',
          email: user.email || '',
          telefono: user.telefono || '',
          password: '',
        }
        // Avoid re-setting same values to prevent loops
        if (
          prev.username === next.username &&
          prev.email === next.email &&
          prev.telefono === next.telefono &&
          prev.password === ''
        ) {
          return prev
        }
        return next
      })
      setError(null)
    }
  }, [isOpen, user])

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setIsSaving(true)
    setError(null)

    const payload: ProfileUpdatePayload = {}
    if (form.username && form.username !== user?.username) payload.username = form.username
    if (form.email && form.email !== user?.email) payload.email = form.email
    if (form.telefono !== undefined) payload.telefono = form.telefono
    if (form.password) payload.password = form.password

    try {
      await updateProfile(payload)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudieron guardar los cambios')
    } finally {
      setIsSaving(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="booking-modal-overlay" onClick={onClose}>
      <div className="booking-modal-content" onClick={(e) => e.stopPropagation()}>
        <header className="booking-modal-header">
          <h2>Editar perfil</h2>
          <button type="button" className="booking-modal-close" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="booking-modal-body">
          <form className="form-grid" onSubmit={handleSubmit}>
            <label className="field">
              <span>Nombre de usuario</span>
              <input
                className="input"
                name="username"
                value={form.username}
                onChange={handleChange}
              />
            </label>
            <label className="field">
              <span>Email</span>
              <input
                className="input"
                name="email"
                type="email"
                value={form.email}
                onChange={handleChange}
              />
            </label>
            <label className="field">
              <span>Teléfono</span>
              <input
                className="input"
                name="telefono"
                type="tel"
                value={form.telefono}
                onChange={handleChange}
              />
            </label>
            <label className="field">
              <span>Nueva contraseña</span>
              <input
                className="input"
                name="password"
                type="password"
                value={form.password}
                onChange={handleChange}
                placeholder="Dejar en blanco para no cambiar"
              />
            </label>
            {error && <p className="field__error _col-full">{error}</p>}
            <div className="form-actions field--full">
              <button className="button button--ghost" type="button" onClick={onClose}>
                Cancelar
              </button>
              <button className="button" type="submit" disabled={isSaving}>
                {isSaving ? 'Guardando...' : 'Guardar cambios'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}