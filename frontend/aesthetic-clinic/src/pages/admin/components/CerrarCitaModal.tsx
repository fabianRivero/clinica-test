import { useEffect, useState } from 'react'

import { useNotifications } from '../../../providers/NotificationProvider'

import {
  closeAppointmentWithRealTimeData,
  getAdminStaff,
  getMaquinariaCatalog,
} from '../../../services/api/admin'
import type {
  AdminCloseExtendedPayload,
  StaffCapacityItem,
} from '../../../types/admin'

/**
 * `Cita` shape consumed by the modal. All fields are optional — the
 * backend operation detail does not (yet) embed the new planning and
 * real-time fields, so the modal gracefully falls back to empty values
 * when those fields are missing. The admin can still type and submit
 * any value; the backend persists what is sent.
 */
export interface CerrarCitaPayload {
  id?: string | number
  rawId: number
  dateTime?: string
  status?: string
  duracionEstimadaMinutos?: number | null
  procedimientoPlanificado?: string
  zonaCuerpoPlanificada?: string
  especialistasPlanificados?: number[]
  maquinariaPlanificada?: Array<{ maquinariaId: number; cantidad: number }>
}

interface CerrarCitaModalProps {
  isOpen: boolean
  onClose: () => void
  /** Cita being closed. Pass `null` to render nothing. */
  cita: CerrarCitaPayload | null
  /** Branch context used to fetch the staff list. Optional. */
  branchId?: number | null
  /** Notifies the parent of the persisted appointment id after success. */
  onSuccess?: (detail: { cita: CerrarCitaPayload | null; detail?: string }) => void
}

export interface MaquinariaUtilizadaRow {
  rowId: string
  maquinariaId: number | null
  cantidad: number
}

interface MaquinariaOption {
  id: number
  nombre: string
  cantidadTotal: number
  marca?: string
}

interface StaffOption {
  id: number
  label: string
  secondaryLabel?: string
}

const HALF = 0.5

/** Parsea `YYYY-MM-DDTHH:MM[:SS]` a minutos desde medianoche. */
function durationMinutes(start: string, end: string): number | null {
  if (!start || !end) return null
  const startDate = new Date(start)
  const endDate = new Date(end)
  const ms = endDate.getTime() - startDate.getTime()
  if (!Number.isFinite(ms) || ms <= 0) return null
  return Math.round(ms / 60000)
}

/**
 * Modal de cierre de cita. Captura los campos de "lo realmente
 * realizado" (horas reales, procedimiento, zona, especialistas que
 * atendieron, maquinaria utilizada) y los persiste via
 * `closeAppointmentWithRealTimeData` (POST /cerrar/) sobre una cita
 * que ya esta en `CONFIRMADA`. Valida en el cliente que
 * `horaRealFin > horaRealInicio` y muestra un aviso amarillo cuando
 * la duracion real difiere en mas del 50 % de la estimada, como
 * pide el spec "Duration mismatch warning".
 *
 * El nombre cambia de `CloseAppointmentModal` a `CerrarCitaModal` para
 * reflejar que la accion es de cierre post-confirmacion, no de
 * transicion de estado.
 */
export function CerrarCitaModal({
  isOpen,
  onClose,
  cita,
  branchId,
  onSuccess,
}: CerrarCitaModalProps) {
  const [horaRealInicio, setHoraRealInicio] = useState('')
  const [horaRealFin, setHoraRealFin] = useState('')
  const [procedimientoRealizado, setProcedimientoRealizado] = useState('')
  const [zonaCuerpoRealizada, setZonaCuerpoRealizada] = useState('')
  // Fecha de la reserva (auto-derivable del prop). Se muestra en los
  // inputs date de Hora real inicio/fin pero el admin no la edita — la
  // cita se cierra con la fecha programada original.
  const [scheduledDate, setScheduledDate] = useState('')
  const [fotoAntesFile, setFotoAntesFile] = useState<File | null>(null)
  const [fotoDespuesFile, setFotoDespuesFile] = useState<File | null>(null)
  const [especialistas, setEspecialistas] = useState<number[]>([])
  const [maquinariaRows, setMaquinariaRows] = useState<MaquinariaUtilizadaRow[]>([])
  const [maquinariaOptions, setMaquinariaOptions] = useState<MaquinariaOption[]>([])
  const [staffOptions, setStaffOptions] = useState<StaffOption[]>([])
  const [loadingCatalog, setLoadingCatalog] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const { showNotification } = useNotifications()

  // Reset form when the modal opens for a (different) cita.
  useEffect(() => {
    if (!isOpen || !cita) return
    /* eslint-disable react-hooks/set-state-in-effect */
    // The date inputs in Hora real inicio/fin are derived from the cita's
    // programmed date (the admin picks the slot again, so the date
    // must match the original). cita.dateTime is the display label; we
    // parse out the YYYY-MM-DD prefix.
    if (cita.dateTime) {
      const match = cita.dateTime.match(/(\d{4}-\d{2}-\d{2})/)
      if (match) {
        setScheduledDate(match[1])
      } else {
        setScheduledDate('')
      }
    } else {
      setScheduledDate('')
    }
    setHoraRealInicio('')
    setHoraRealFin('')
    setProcedimientoRealizado(cita.procedimientoPlanificado ?? '')
    setZonaCuerpoRealizada(cita.zonaCuerpoPlanificada ?? '')
    setEspecialistas(cita.especialistasPlanificados ?? [])
    setMaquinariaRows(
      (cita.maquinariaPlanificada ?? []).map((item) => ({
        rowId: crypto.randomUUID(),
        maquinariaId: item.maquinariaId,
        cantidad: Math.max(1, item.cantidad),
      })),
    )
    setFotoAntesFile(null)
    setFotoDespuesFile(null)
    setError(null)
    setSuccess(null)
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [isOpen, cita])

  // Lazy-load catalog + staff when the modal opens.
  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    setLoadingCatalog(true)
    async function load() {
      try {
        const [catalog, staff] = await Promise.all([
          getMaquinariaCatalog(),
          getAdminStaff(branchId ?? null),
        ])
        if (cancelled) return
        const options: MaquinariaOption[] = catalog.items
          .filter((item) => item.active)
          .map((item) => ({
            id: item.id,
            nombre: String(item.values.nombre ?? ''),
            cantidadTotal: Number(item.values.cantidadTotal ?? 1) || 1,
            marca: item.values.marca ? String(item.values.marca) : undefined,
          }))
          .filter((opt) => opt.cantidadTotal > 0)
        setMaquinariaOptions(options)
        const opts: StaffOption[] = staff.staff
          .filter((member: StaffCapacityItem) => member.isActive)
          .map((member) => ({
            id: member.rawId,
            label: member.specialist,
            secondaryLabel: member.specialty,
          }))
        setStaffOptions(opts)
      } catch (requestError) {
        if (!cancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : 'No se pudo cargar el catalogo de maquinaria.',
          )
        }
      } finally {
        if (!cancelled) setLoadingCatalog(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [isOpen, branchId])

  if (!isOpen || !cita) return null

  const realMinutes = durationMinutes(horaRealInicio, horaRealFin)
  const estimated = cita.duracionEstimadaMinutos ?? null
  const hasMismatch =
    realMinutes !== null && estimated !== null && estimated > 0
      ? Math.abs(realMinutes - estimated) / estimated > HALF
      : false

  function addMaquinariaRow() {
    setMaquinariaRows((rows) => [
      ...rows,
      { rowId: crypto.randomUUID(), maquinariaId: null, cantidad: 1 },
    ])
  }

  function updateMaquinariaRow(rowId: string, patch: Partial<MaquinariaUtilizadaRow>) {
    setMaquinariaRows((rows) =>
      rows.map((row) => (row.rowId === rowId ? { ...row, ...patch } : row)),
    )
  }

  function removeMaquinariaRow(rowId: string) {
    setMaquinariaRows((rows) => rows.filter((row) => row.rowId !== rowId))
  }

  function toggleEspecialista(id: number) {
    setEspecialistas((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    )
  }

  async function handleSubmit() {
    setError(null)
    setSuccess(null)
    if (!cita) {
      setError('No hay una cita seleccionada.')
      return
    }
    if (!horaRealInicio || !horaRealFin) {
      setError('Completa la hora real de inicio y fin.')
      return
    }
    if (!scheduledDate) {
      setError('No se puede determinar la fecha de la reserva.')
      return
    }
    // Combine the cita's programmed date with the admin-entered times.
    // The backend accepts ISO 8601 datetimes and validates fin > inicio.
    const horaRealInicioIso = `${scheduledDate}T${horaRealInicio}:00`
    const horaRealFinIso = `${scheduledDate}T${horaRealFin}:00`
    const inicioDate = new Date(horaRealInicioIso)
    const finDate = new Date(horaRealFinIso)
    if (Number.isNaN(inicioDate.getTime()) || Number.isNaN(finDate.getTime())) {
      setError('Hora invalida.')
      return
    }
    if (finDate.getTime() <= inicioDate.getTime()) {
      setError('La hora real de fin debe ser posterior a la de inicio.')
      return
    }

    const maquinariaUtilizada = maquinariaRows
      .filter((row) => row.maquinariaId !== null && row.cantidad > 0)
      .map((row) => ({
        maquinariaId: row.maquinariaId as number,
        cantidad: row.cantidad,
      }))

    const payload: AdminCloseExtendedPayload = {
      horaRealInicio: horaRealInicioIso,
      horaRealFin: horaRealFinIso,
      procedimientoRealizado: procedimientoRealizado || undefined,
      zonaCuerpoRealizada: zonaCuerpoRealizada || undefined,
      especialistasAtendieron: especialistas.length ? especialistas : undefined,
      maquinariaUtilizada: maquinariaUtilizada.length ? maquinariaUtilizada : undefined,
    }

    setIsSubmitting(true)
    try {
      await closeAppointmentWithRealTimeData(cita.rawId, payload)
      // If the admin attached new photos, upload them via the notes
      // endpoint. The notes endpoint accepts multipart for both text
      // and images. We only send the foto fields when files are picked.
      if (fotoAntesFile || fotoDespuesFile) {
        const services = await import('../../../services/api/admin')
        const notesForm = new FormData()
        if (fotoAntesFile) notesForm.append('fotoAntes', fotoAntesFile)
        if (fotoDespuesFile) notesForm.append('fotoDespues', fotoDespuesFile)
        try {
          // patchAppointmentNotes expects AdminAppointmentNotesPatchPayload,
          // which is the public TS shape; the actual implementation accepts
          // FormData at runtime. Cast via unknown to bridge the two.
          await services.patchAppointmentNotes(
            cita.rawId,
            notesForm as unknown as Parameters<typeof services.patchAppointmentNotes>[1],
          )
        } catch (photoError) {
          // The close-with-data already succeeded; log a soft warning
          // so the admin can retry the photo upload via the notes panel.
          setError(
            photoError instanceof Error
              ? `Datos guardados, pero las fotos no: ${photoError.message}`
              : 'Datos guardados, pero las fotos no se subieron.',
          )
        }
      }
      setSuccess('Datos reales guardados correctamente.')
      showNotification({
        title: 'Datos reales guardados',
        message: 'La cita quedo cerrada con los datos reales.',
        tone: 'success',
      })
      onSuccess?.({ cita, detail: 'Datos reales guardados correctamente.' })
      // Cerrar automaticamente despues de un pequeno delay para que
      // el admin alcance a leer el mensaje.
      setTimeout(() => {
        onClose()
      }, 600)
    } catch (requestError) {
      const errorMessage =
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo cerrar la cita.'
      setError(errorMessage)
      showNotification({
        title: 'No se pudo cerrar la cita',
        message: errorMessage,
        tone: 'danger',
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="booking-modal-overlay" onClick={onClose}>
      <div
        className="booking-modal-content"
        onClick={(event) => event.stopPropagation()}
        data-testid="close-appointment-modal"
      >
        <header className="booking-modal-header">
          <h2>Cerrar cita</h2>
          <button type="button" className="booking-modal-close" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="booking-modal-body">
          <div className="_panel-card _mb-md">
            <p>
              <strong>Cita:</strong> {cita.id ?? `#${cita.rawId}`}
            </p>
            {cita.dateTime ? (
              <p>
                <strong>Programada:</strong> {cita.dateTime}
              </p>
            ) : null}
            {cita.status ? (
              <p>
                <strong>Estado actual:</strong> {cita.status}
              </p>
            ) : null}
          </div>

          <div className="form-grid">
            <div className="_grid-2cols">
              <label className="field">
                <span>Fecha y hora real inicio</span>
                <div className="_flex _gap-sm">
                  <input
                    type="date"
                    className="input"
                    style={{ flex: '0 0 11rem' }}
                    value={scheduledDate}
                    disabled
                    aria-label="Fecha de la reserva"
                  />
                  <input
                    type="time"
                    className="input"
                    value={horaRealInicio}
                    onChange={(event) => setHoraRealInicio(event.target.value)}
                    aria-label="Hora real de inicio"
                  />
                </div>
              </label>
              <label className="field">
                <span>Fecha y hora real fin</span>
                <div className="_flex _gap-sm">
                  <input
                    type="date"
                    className="input"
                    style={{ flex: '0 0 11rem' }}
                    value={scheduledDate}
                    disabled
                    aria-label="Fecha de la reserva"
                  />
                  <input
                    type="time"
                    className="input"
                    value={horaRealFin}
                    onChange={(event) => setHoraRealFin(event.target.value)}
                    aria-label="Hora real de fin"
                  />
                </div>
              </label>
            </div>

            {hasMismatch ? (
              <p
                className="field--full"
                style={{
                  background: 'rgba(255, 209, 102, 0.18)',
                  border: '1px solid rgba(255, 209, 102, 0.6)',
                  borderRadius: '6px',
                  padding: '0.5rem 0.75rem',
                  color: 'var(--color-text)',
                  fontSize: '0.85rem',
                }}
                data-testid="close-appointment-duration-warning"
              >
                Aviso: la duracion real ({realMinutes} min) difiere en mas del 50 % de la
                estimada ({estimated} min). Confirma que sea correcto antes de cerrar.
              </p>
            ) : null}

            <label className="field field--full">
              <span>Procedimiento realizado</span>
              <textarea
                className="input textarea"
                rows={2}
                value={procedimientoRealizado}
                onChange={(event) => setProcedimientoRealizado(event.target.value)}
              />
            </label>

            <label className="field">
              <span>Zona del cuerpo realizada</span>
              <input
                type="text"
                className="input"
                maxLength={200}
                value={zonaCuerpoRealizada}
                onChange={(event) => setZonaCuerpoRealizada(event.target.value)}
              />
            </label>

            <div className="_grid-2cols field--full">
              <label className="field">
                <span>Foto antes</span>
                <input
                  type="file"
                  accept="image/*"
                  className="input"
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    setFotoAntesFile(file ?? null)
                  }}
                />
                {fotoAntesFile ? (
                  <small className="field__hint">
                    Seleccionado: {fotoAntesFile.name}
                  </small>
                ) : null}
              </label>
              <label className="field">
                <span>Foto después</span>
                <input
                  type="file"
                  accept="image/*"
                  className="input"
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    setFotoDespuesFile(file ?? null)
                  }}
                />
                {fotoDespuesFile ? (
                  <small className="field__hint">
                    Seleccionado: {fotoDespuesFile.name}
                  </small>
                ) : null}
              </label>
            </div>

            <fieldset className="field field--full">
              <legend>Especialistas que atendieron</legend>
              {staffOptions.length === 0 ? (
                <small className="field__hint">Cargando especialistas...</small>
              ) : (
                <div className="_flex _gap-sm" style={{ flexWrap: 'wrap' }}>
                  {staffOptions.map((staff) => {
                    const checked = especialistas.includes(staff.id)
                    return (
                      <label key={staff.id} className="_flex _gap-sm">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleEspecialista(staff.id)}
                        />
                        <span>{staff.label}</span>
                      </label>
                    )
                  })}
                </div>
              )}
            </fieldset>

            <fieldset className="field field--full">
              <legend>Maquinaria utilizada</legend>
              {maquinariaRows.length === 0 ? (
                <small className="field__hint">No se registro maquinaria para esta cita.</small>
              ) : (
                <div className="form-grid">
                  {maquinariaRows.map((row) => (
                    <div className="_grid-2cols _mt-sm" key={row.rowId}>
                      <label className="field">
                        <span>Maquina</span>
                        <select
                          className="input"
                          value={row.maquinariaId === null ? '' : String(row.maquinariaId)}
                          onChange={(event) =>
                            updateMaquinariaRow(row.rowId, {
                              maquinariaId:
                                event.target.value === '' ? null : Number(event.target.value),
                            })
                          }
                        >
                          <option value="">Seleccionar...</option>
                          {maquinariaOptions.map((option) => (
                            <option key={option.id} value={option.id}>
                              {option.nombre}
                              {option.marca ? ` (${option.marca})` : ''} - disp: {option.cantidadTotal}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="_flex _gap-sm">
                        <label className="field">
                          <span>Cantidad</span>
                          <input
                            type="number"
                            min={1}
                            className="input"
                            value={row.cantidad}
                            onChange={(event) =>
                              updateMaquinariaRow(row.rowId, {
                                cantidad: Math.max(1, Number(event.target.value) || 1),
                              })
                            }
                          />
                        </label>
                        <button
                          type="button"
                          className="button button--ghost"
                          onClick={() => removeMaquinariaRow(row.rowId)}
                        >
                          Quitar
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className="_mt-sm">
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={addMaquinariaRow}
                  disabled={loadingCatalog || maquinariaOptions.length === 0}
                >
                  + Agregar maquinaria
                </button>
              </div>
            </fieldset>
          </div>

          {error ? (
            <p className="field__error _mt-md" data-testid="close-appointment-error">
              {error}
            </p>
          ) : null}
          {success ? (
            <p className="field__hint _mt-md" data-testid="close-appointment-success">
              {success}
            </p>
          ) : null}

          <div className="_mt-lg form-actions">
            <button
              type="button"
              className="button button--ghost"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="button button--primary"
              onClick={() => void handleSubmit()}
              disabled={isSubmitting || loadingCatalog}
              data-testid="close-appointment-submit"
            >
              {isSubmitting ? 'Cerrando...' : 'Cerrar cita'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
