import { type ChangeEvent, type FormEvent, useEffect, useState } from 'react'

import { useNotifications } from '../../../providers/NotificationProvider'
import {
  getAdminClientReactivation,
  patchAdminClientProfile,
} from '../../../services/api/admin'
import type {
  AdminClientProfilePatchPayload,
  ProspectConversionUserData,
} from '../../../types/prospectConversion'

type Props = {
  clientId: string
  isOpen: boolean
  onClose: () => void
}

export function ClientProfileModal({ clientId, isOpen, onClose }: Props) {
  const { showNotification } = useNotifications()
  const [form, setForm] = useState<ProspectConversionUserData | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [_fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    if (isOpen && clientId) {
      setIsLoading(true)
      setError(null)
      getAdminClientReactivation(clientId)
        .then((res) => {
          setForm(res.draft.userData)
        })
        .catch(() => {
          setError('No se pudieron cargar los datos del cliente')
        })
        .finally(() => setIsLoading(false))
    }
  }, [isOpen, clientId])

  const handleChange = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (!form) return
    const { name, value } = event.target
    setForm((prev) => ({ ...prev!, [name]: value }))
    setFieldErrors((current) => ({ ...current, [name]: '' }))
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!form) return
    setIsSaving(true)
    setError(null)
    try {
      // Build the strict 13-field payload: the live endpoint rejects
      // `codBiometrico` and unknown fields, so we map the form state
      // down before sending.
      const payload: AdminClientProfilePatchPayload = {
        primerNombre: form.primerNombre,
        segundoNombre: form.segundoNombre,
        apellidoPaterno: form.apellidoPaterno,
        apellidoMaterno: form.apellidoMaterno,
        ci: form.ci,
        username: form.username,
        email: form.email,
        telefono: form.telefono,
        fechaNacimiento: form.fechaNacimiento,
        nroHijos: form.nroHijos,
        ocupacion: form.ocupacion,
        direccionDomicilio: form.direccionDomicilio,
        observacionesCliente: form.observacionesCliente,
      }
      const response = await patchAdminClientProfile(clientId, payload)
      // response.client is the server snapshot of the live profile,
      // matching ProspectConversionUserData (minus codBiometrico).
      // Re-hydrate the form so the modal closes with the truth on disk;
      // we keep the existing codBiometrico since the live endpoint does
      // not surface it.
      setForm({ codBiometrico: form.codBiometrico, ...response.client })
      showNotification({
        title: 'Perfil actualizado',
        message: 'Los cambios del perfil se guardaron correctamente.',
        tone: 'success',
      })
      onClose()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'No se pudo guardar el perfil.'
      setError(message)
      showNotification({
        title: 'No se pudo guardar el perfil',
        message,
        tone: 'danger',
      })
    } finally {
      setIsSaving(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="booking-modal-overlay" onClick={onClose}>
      <div className="booking-modal-content" onClick={(e) => e.stopPropagation()}>
        <header className="booking-modal-header">
          <h2>Perfil del cliente</h2>
          <button type="button" className="booking-modal-close" onClick={onClose}>✕</button>
        </header>
        <div className="booking-modal-body">
          {isLoading ? (
            <p>Cargando...</p>
          ) : error && !form ? (
            <p className="_text-danger">{error}</p>
          ) : form ? (
            <form className="form-grid" onSubmit={handleSubmit}>
              <label className="field">
                <span>Primer nombre</span>
                <input className="input" name="primerNombre" value={form.primerNombre} onChange={handleChange} />
              </label>
              <label className="field">
                <span>Segundo nombre</span>
                <input className="input" name="segundoNombre" value={form.segundoNombre} onChange={handleChange} />
              </label>
              <label className="field">
                <span>Apellido paterno</span>
                <input className="input" name="apellidoPaterno" value={form.apellidoPaterno} onChange={handleChange} />
              </label>
              <label className="field">
                <span>Apellido materno</span>
                <input className="input" name="apellidoMaterno" value={form.apellidoMaterno} onChange={handleChange} />
              </label>
              <label className="field">
                <span>CI</span>
                <input className="input" name="ci" value={form.ci} onChange={handleChange} />
              </label>
              <label className="field">
                <span>Nombre de usuario</span>
                <input className="input" name="username" value={form.username} onChange={handleChange} />
              </label>
              <label className="field">
                <span>Email</span>
                <input className="input" name="email" type="email" value={form.email} onChange={handleChange} />
              </label>
              <label className="field">
                <span>Teléfono</span>
                <input className="input" name="telefono" type="tel" value={form.telefono} onChange={handleChange} />
              </label>
              <label className="field">
                <span>Fecha de nacimiento</span>
                <input className="input" name="fechaNacimiento" type="date" value={form.fechaNacimiento} onChange={handleChange} />
              </label>
              <label className="field">
                <span>Nro. hijos</span>
                <input className="input" name="nroHijos" type="number" min="0" value={form.nroHijos} onChange={handleChange} />
              </label>
              <label className="field">
                <span>Ocupación</span>
                <input className="input" name="ocupacion" value={form.ocupacion} onChange={handleChange} />
              </label>
              <label className="field field--full">
                <span>Dirección</span>
                <input className="input" name="direccionDomicilio" value={form.direccionDomicilio} onChange={handleChange} />
              </label>
              <label className="field field--full">
                <span>Observaciones del cliente</span>
                <textarea className="input textarea" name="observacionesCliente" rows={3} value={form.observacionesCliente} onChange={handleChange} />
              </label>
              {error && <p className="field__error _col-full">{error}</p>}
              <div className="form-actions field--full">
                <button className="button button--ghost" type="button" onClick={onClose}>Cancelar</button>
                <button className="button" type="submit" disabled={isSaving}>{isSaving ? 'Guardando...' : 'Guardar cambios'}</button>
              </div>
            </form>
          ) : null}
        </div>
      </div>
    </div>
  )
}
