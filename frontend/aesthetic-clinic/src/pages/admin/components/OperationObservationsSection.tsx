import { useState } from 'react'

import { useConfirmDialog } from '../../../hooks/useConfirmDialog'
import { useNotifications } from '../../../providers/NotificationProvider'
import {
  deleteAdminOperationPhoto,
  updateAdminOperationObservaciones,
  uploadAdminOperationPhotos,
} from '../../../services/api/admin'
import type {
  ApiError,
} from '../../../services/api/apiClient'
import type {
  OperationDetailData,
  OperacionFoto,
} from '../../../types/admin'

type PhotoKind = 'antes' | 'despues'

interface OperationObservationsSectionProps {
  operacion: OperationDetailData
  /** Drives the lifecycle gate (true only for BORRADOR / EN_PROCESO). */
  editable: boolean
  /** Called after a successful mutation; the page re-fetches. */
  onSaved: () => void
}

/** Helper: read detalles_op, treating the localized placeholder as empty. */
function initDetails(operacion: OperationDetailData): string {
  return operacion.detallesOperacion === 'Sin detalles registrados.'
    ? ''
    : operacion.detallesOperacion
}

interface PhotoRowProps {
  photo: OperacionFoto
  editable: boolean
  deleting: boolean
  expanded: boolean
  onToggle: () => void
  onDelete: () => void
}

/**
 * Single photo row inside the gallery list. Renders a toggle button
 * (showing the filename), the delete button at the far right, and —
 * when toggled — the image expanded inline below the row.
 */
function PhotoRow({
  photo,
  editable,
  deleting,
  expanded,
  onToggle,
  onDelete,
}: PhotoRowProps) {
  return (
    <li className="observations-section__row">
      <div className="observations-section__row-header">
        <button
          type="button"
          className="observations-section__row-toggle button button--ghost button--compact"
          aria-expanded={expanded}
          aria-label={`${expanded ? 'Ocultar' : 'Ver'} ${photo.fileName}`}
          onClick={onToggle}
        >
          {expanded ? 'Ocultar imagen' : 'Ver imagen'}
        </button>
        <span className="observations-section__row-name">{photo.fileName}</span>
        {editable ? (
          <button
            type="button"
            className="observations-section__row-delete"
            aria-label={`Eliminar ${photo.fileName}`}
            disabled={deleting}
            onClick={onDelete}
          >
            {deleting ? '...' : '×'}
          </button>
        ) : null}
      </div>
      {expanded ? (
        <div className="observations-section__row-preview">
          <img src={photo.url} alt={photo.fileName} />
        </div>
      ) : null}
    </li>
  )
}

/**
 * "Observaciones del procedimiento" section at the bottom of the admin
 * operation detail page. Owns the textarea (bound to ``detalles_op``)
 * and two before/after photo galleries. Lifecycle-aware:
 * ``editable=false`` disables every mutation surface but keeps the
 * gallery visible.
 *
 * State reset rule (avoiding the lint warning on useEffect for
 * initialization): the local state is seeded ONCE via lazy ``useState``
 * from the first ``operacion`` snapshot. When the admin navigates to a
 * different operation, the parent remounts this component with a new
 * key in practice — the spec accepts the simpler model.
 */
export function OperationObservationsSection({
  operacion,
  editable,
  onSaved,
}: OperationObservationsSectionProps) {
  const { showNotification } = useNotifications()
  const { confirm, ConfirmDialog } = useConfirmDialog()

  const [detailsText, setDetailsText] = useState(() => initDetails(operacion))
  const [saving, setSaving] = useState(false)
  const [detailsError, setDetailsError] = useState<string | null>(null)
  const [uploading, setUploading] = useState<Record<PhotoKind, boolean>>({
    antes: false,
    despues: false,
  })
  const [photos, setPhotos] = useState<Record<PhotoKind, OperacionFoto[]>>({
    antes: [...operacion.fotosAntes],
    despues: [...operacion.fotosDespues],
  })
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [expandedPhotoId, setExpandedPhotoId] = useState<number | null>(null)

  async function handleSaveDetails() {
    setSaving(true)
    setDetailsError(null)
    try {
      await updateAdminOperationObservaciones(operacion.rawId, {
        details: detailsText,
      })
      showNotification({
        title: 'Observaciones guardadas',
        message: 'Las observaciones del procedimiento se actualizaron correctamente.',
        tone: 'success',
      })
      onSaved()
    } catch (requestError) {
      const fieldErrors = (requestError as ApiError | null)?.fieldErrors
      if (fieldErrors?.details) {
        setDetailsError(fieldErrors.details)
      } else {
        const message =
          requestError instanceof Error
            ? requestError.message
            : 'No se pudieron guardar las observaciones.'
        showNotification({
          title: 'No se pudieron guardar las observaciones',
          message,
          tone: 'danger',
        })
      }
    } finally {
      setSaving(false)
    }
  }

  async function handleUpload(kind: PhotoKind, files: File[]) {
    if (files.length === 0) return
    setUploading((current) => ({ ...current, [kind]: true }))
    try {
      const response = await uploadAdminOperationPhotos(operacion.rawId, files, kind)
      // Optimistic merge: show the freshly-saved photos immediately.
      setPhotos((current) => ({
        ...current,
        [kind]: [...current[kind], ...response.saved],
      }))
      // Surface per-file errors (oversized, unsupported format, etc.).
      const errorEntries = Object.entries(response.errors)
      if (errorEntries.length > 0) {
        showNotification({
          title: 'Algunas fotos no pudieron subirse',
          message: errorEntries.map(([key, msg]) => `${key}: ${msg}`).join('\n'),
          tone: 'warning',
        })
      } else {
        showNotification({
          title: 'Fotos guardadas',
          message:
            response.saved.length === 1
              ? 'Foto subida correctamente.'
              : `${response.saved.length} fotos subidas correctamente.`,
          tone: 'success',
        })
      }
      onSaved()
    } catch (requestError) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : 'No se pudieron subir las fotos.'
      showNotification({
        title: 'No se pudieron subir las fotos',
        message,
        tone: 'danger',
      })
    } finally {
      setUploading((current) => ({ ...current, [kind]: false }))
    }
  }

  function onFileChange(kind: PhotoKind, event: React.ChangeEvent<HTMLInputElement>) {
    const files = event.target.files ? Array.from(event.target.files) : []
    // Reset the input so the same file path can be re-picked after a failure.
    event.target.value = ''
    if (files.length > 0) {
      void handleUpload(kind, files)
    }
  }

  async function handleDelete(kind: PhotoKind, photo: OperacionFoto) {
    const accepted = await confirm({
      title: 'Eliminar foto',
      message: '¿Eliminar esta foto? Esta accion no se puede deshacer.',
      tone: 'warning',
    })
    if (!accepted) return
    setDeletingId(photo.id)
    try {
      await deleteAdminOperationPhoto(operacion.rawId, photo.id)
      setPhotos((current) => ({
        ...current,
        [kind]: current[kind].filter((p) => p.id !== photo.id),
      }))
      showNotification({
        title: 'Foto eliminada',
        message: 'La foto se elimino correctamente.',
        tone: 'success',
      })
      onSaved()
    } catch (requestError) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo eliminar la foto.'
      showNotification({
        title: 'No se pudo eliminar la foto',
        message,
        tone: 'danger',
      })
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="observations-section">
      <div className="form-grid">
        <label className="field field--full">
          <span>Observaciones del procedimiento</span>
          <textarea
            className="input textarea"
            rows={6}
            value={detailsText}
            disabled={!editable || saving}
            onChange={(event) => {
              setDetailsError(null)
              setDetailsText(event.target.value)
            }}
          />
          {detailsError ? (
            <small className="field__error">{detailsError}</small>
          ) : null}
        </label>
        {editable ? (
          <div className="form-actions field--full">
            <button
              className="button"
              type="button"
              disabled={saving}
              onClick={() => void handleSaveDetails()}
            >
              {saving ? 'Guardando...' : 'Guardar'}
            </button>
          </div>
        ) : null}
      </div>

      <div className="observations-section__kind-block">
        <div className="observations-section__kind-header">
          <strong>Fotos antes del tratamiento</strong>
          {editable ? (
            <label className="button button--ghost">
              {uploading.antes ? 'Subiendo...' : 'Seleccionar archivos'}
              <input
                type="file"
                multiple
                accept="image/*"
                disabled={uploading.antes}
                onChange={(event) => onFileChange('antes', event)}
                style={{ display: 'none' }}
              />
            </label>
          ) : null}
        </div>
        {photos.antes.length === 0 ? (
          <p className="field__hint">Sin fotos.</p>
        ) : (
          <ul className="observations-section__list">
            {photos.antes.map((photo) => (
              <PhotoRow
                key={photo.id}
                photo={photo}
                editable={editable}
                deleting={deletingId === photo.id}
                expanded={expandedPhotoId === photo.id}
                onToggle={() =>
                  setExpandedPhotoId(
                    expandedPhotoId === photo.id ? null : photo.id,
                  )
                }
                onDelete={() => void handleDelete('antes', photo)}
              />
            ))}
          </ul>
        )}
      </div>

      <div className="observations-section__kind-block">
        <div className="observations-section__kind-header">
          <strong>Fotos después del tratamiento</strong>
          {editable ? (
            <label className="button button--ghost">
              {uploading.despues ? 'Subiendo...' : 'Seleccionar archivos'}
              <input
                type="file"
                multiple
                accept="image/*"
                disabled={uploading.despues}
                onChange={(event) => onFileChange('despues', event)}
                style={{ display: 'none' }}
              />
            </label>
          ) : null}
        </div>
        {photos.despues.length === 0 ? (
          <p className="field__hint">Sin fotos.</p>
        ) : (
          <ul className="observations-section__list">
            {photos.despues.map((photo) => (
              <PhotoRow
                key={photo.id}
                photo={photo}
                editable={editable}
                deleting={deletingId === photo.id}
                expanded={expandedPhotoId === photo.id}
                onToggle={() =>
                  setExpandedPhotoId(
                    expandedPhotoId === photo.id ? null : photo.id,
                  )
                }
                onDelete={() => void handleDelete('despues', photo)}
              />
            ))}
          </ul>
        )}
      </div>

      <ConfirmDialog />
    </div>
  )
}
