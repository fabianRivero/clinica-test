import { useState } from 'react'

import { useNotifications } from '../../../providers/NotificationProvider'
import { patchAppointmentNotes } from '../../../services/api/admin'
import type { AdminAppointmentNotesPatchPayload } from '../../../types/admin'

/**
 * Shape consumed by the panel. Accepts the standard appointment item plus
 * the new notes/photos fields introduced by the redesign spec.
 */
export interface AppointmentNotesCita {
  rawId: number
  descripcionGeneral?: string
  notasPrevias?: string
  notasPost?: string
  fotoAntes?: string | null
  fotoDespues?: string | null
}

interface AppointmentNotesPanelProps {
  cita: AppointmentNotesCita
  /** When true (specialist assigned) or admin can edit. */
  canEdit: boolean
  /** Optional callback after a successful save. */
  onSaved?: () => void
}

type EditableField =
  | 'descripcionGeneral'
  | 'notasPrevias'
  | 'notasPost'
  | 'fotoAntes'
  | 'fotoDespues'

const FIELD_LABELS: Record<EditableField, string> = {
  descripcionGeneral: 'Descripción general',
  notasPrevias: 'Notas previas',
  notasPost: 'Notas posteriores',
  fotoAntes: 'Foto antes',
  fotoDespues: 'Foto después',
}

export function AppointmentNotesPanel({ cita, canEdit, onSaved }: AppointmentNotesPanelProps) {
  const { showNotification } = useNotifications()
  const [editing, setEditing] = useState<EditableField | null>(null)
  const [saving, setSaving] = useState(false)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [photoFiles, setPhotoFiles] = useState<Record<string, File>>({})

  function startEdit(field: EditableField) {
    if (!canEdit) return
    setEditing(field)
    if (field in photoFiles) {
      setPhotoFiles((current) => {
        const next = { ...current }
        delete next[field]
        return next
      })
    }
    setDrafts((current) => ({ ...current, [field]: getInitialDraft(cita, field) }))
  }

  function cancelEdit(field: EditableField) {
    setEditing(null)
    setDrafts((current) => {
      const next = { ...current }
      delete next[field]
      return next
    })
    setPhotoFiles((current) => {
      const next = { ...current }
      delete next[field]
      return next
    })
  }

  async function save(field: EditableField) {
    if (!canEdit) return
    setSaving(true)
    try {
      const payload: AdminAppointmentNotesPatchPayload = {}
      if (field === 'fotoAntes' || field === 'fotoDespues') {
        const file = photoFiles[field]
        if (file) {
          payload[field] = file
        }
      } else {
        const value = drafts[field] ?? ''
        payload[field] = value
      }
      await patchAppointmentNotes(cita.rawId, payload)
      showNotification({
        title: 'Notas guardadas',
        message: `${FIELD_LABELS[field]} actualizado correctamente.`,
        tone: 'success',
      })
      setEditing(null)
      onSaved?.()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'No se pudo guardar.'
      showNotification({
        title: 'Error al guardar',
        message,
        tone: 'danger',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="_panel-card _mt-md">
      <header className="_flex-row _flex-between">
        <h3 className="_m-0">Notas y registros</h3>
        {!canEdit ? (
          <small className="_text-soft">Solo lectura</small>
        ) : null}
      </header>

      {(['descripcionGeneral', 'notasPrevias', 'notasPost'] as const).map((field) => {
        const isEditing = editing === field
        const value = isEditing ? drafts[field] ?? '' : cita[field] ?? ''
        return (
          <article className="_mt-md" key={field}>
            <header className="_flex-row _flex-between">
              <strong>{FIELD_LABELS[field]}</strong>
              {canEdit ? (
                isEditing ? (
                  <div className="_flex-gap-sm">
                    <button
                      type="button"
                      className="button button--ghost button--compact"
                      disabled={saving}
                      onClick={() => cancelEdit(field)}
                    >
                      Cancelar
                    </button>
                    <button
                      type="button"
                      className="button button--primary button--compact"
                      disabled={saving}
                      onClick={() => void save(field)}
                    >
                      {saving ? 'Guardando...' : 'Guardar'}
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="button button--ghost button--compact"
                    onClick={() => startEdit(field)}
                  >
                    Editar
                  </button>
                )
              ) : null}
            </header>
            {isEditing ? (
              <textarea
                className="input"
                rows={3}
                value={value}
                onChange={(event) => setDrafts((current) => ({ ...current, [field]: event.target.value }))}
              />
            ) : (
              <p className="_mb-0">{value || <span className="_text-soft">Sin contenido</span>}</p>
            )}
          </article>
        )
      })}

      {(['fotoAntes', 'fotoDespues'] as const).map((field) => {
        const isEditing = editing === field
        const currentUrl = cita[field]
        const file = photoFiles[field]
        return (
          <article className="_mt-md" key={field}>
            <header className="_flex-row _flex-between">
              <strong>{FIELD_LABELS[field]}</strong>
              {canEdit ? (
                isEditing ? (
                  <div className="_flex-gap-sm">
                    <button
                      type="button"
                      className="button button--ghost button--compact"
                      disabled={saving}
                      onClick={() => cancelEdit(field)}
                    >
                      Cancelar
                    </button>
                    <button
                      type="button"
                      className="button button--primary button--compact"
                      disabled={saving || !file}
                      onClick={() => void save(field)}
                    >
                      {saving ? 'Subiendo...' : 'Subir'}
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="button button--ghost button--compact"
                    onClick={() => startEdit(field)}
                  >
                    {currentUrl ? 'Reemplazar' : 'Subir'}
                  </button>
                )
              ) : null}
            </header>
            {currentUrl ? (
              <a href={currentUrl} target="_blank" rel="noreferrer">
                <img
                  src={currentUrl}
                  alt={FIELD_LABELS[field]}
                  style={{ maxWidth: '240px', borderRadius: '6px', marginTop: '0.5rem' }}
                />
              </a>
            ) : (
              <p className="_text-soft _mb-0">Sin foto</p>
            )}
            {isEditing ? (
              <input
                type="file"
                accept="image/*"
                className="input"
                style={{ marginTop: '0.5rem' }}
                onChange={(event) => {
                  const next = event.target.files?.[0]
                  if (next) {
                    setPhotoFiles((current) => ({ ...current, [field]: next }))
                  }
                }}
              />
            ) : null}
            {file ? (
              <p className="_mt-sm _text-soft">Seleccionado: {file.name}</p>
            ) : null}
          </article>
        )
      })}
    </section>
  )
}

function getInitialDraft(cita: AppointmentNotesCita, field: EditableField): string {
  if (field === 'fotoAntes' || field === 'fotoDespues') return ''
  return cita[field] ?? ''
}