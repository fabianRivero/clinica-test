import { useEffect, useState } from 'react'

import {
  getAdminStaff,
  getMaquinariaCatalog,
  markAppointmentPendingBiometricExtended,
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
export interface CloseAppointmentCita {
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

interface CloseAppointmentModalProps {
  isOpen: boolean
  onClose: () => void
  /** Cita being closed. Pass `null` to render nothing. */
  cita: CloseAppointmentCita | null
  /** Branch context used to fetch the staff list. Optional. */
  branchId?: number | null
  /** Notifies the parent of the persisted appointment id after success. */
  onSuccess?: (detail: { cita: CloseAppointmentCita | null; detail?: string }) => void
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
 * atendieron, maquinaria utilizada) y delega en
 * `markAppointmentPendingBiometricExtended`. Valida en el cliente que
 * `horaRealFin > horaRealInicio` y muestra un aviso amarillo cuando
 * la duracion real difiere en mas del 50 % de la estimada, como
 * pide el spec "Duration mismatch warning".
 */
export function CloseAppointmentModal({
  isOpen,
  onClose,
  cita,
  branchId,
  onSuccess,
}: CloseAppointmentModalProps) {
  const [horaRealInicio, setHoraRealInicio] = useState('')
  const [horaRealFin, setHoraRealFin] = useState('')
  const [procedimientoRealizado, setProcedimientoRealizado] = useState('')
  const [zonaCuerpoRealizada, setZonaCuerpoRealizada] = useState('')
  const [especialistas, setEspecialistas] = useState<number[]>([])
  const [maquinariaRows, setMaquinariaRows] = useState<MaquinariaUtilizadaRow[]>([])
  const [maquinariaOptions, setMaquinariaOptions] = useState<MaquinariaOption[]>([])
  const [staffOptions, setStaffOptions] = useState<StaffOption[]>([])
  const [loadingCatalog, setLoadingCatalog] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Reset form when the modal opens for a (different) cita.
  useEffect(() => {
    if (!isOpen || !cita) return
    /* eslint-disable react-hooks/set-state-in-effect */
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
    if (realMinutes === null || realMinutes <= 0) {
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
      horaRealInicio: horaRealInicio.length === 16 ? `${horaRealInicio}:00` : horaRealInicio,
      horaRealFin: horaRealFin.length === 16 ? `${horaRealFin}:00` : horaRealFin,
      procedimientoRealizado: procedimientoRealizado || undefined,
      zonaCuerpoRealizada: zonaCuerpoRealizada || undefined,
      especialistasAtendieron: especialistas.length ? especialistas : undefined,
      maquinariaUtilizada: maquinariaUtilizada.length ? maquinariaUtilizada : undefined,
    }

    setIsSubmitting(true)
    try {
      await markAppointmentPendingBiometricExtended(cita.rawId, payload)
      setSuccess('La cita paso a pendiente de verificacion.')
      onSuccess?.({ cita, detail: 'La cita paso a pendiente de verificacion.' })
      // Cerrar automaticamente despues de un pequeno delay para que
      // el admin alcance a leer el mensaje.
      setTimeout(() => {
        onClose()
      }, 600)
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo cerrar la cita.',
      )
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
                <span>Hora real inicio</span>
                <input
                  type="datetime-local"
                  className="input"
                  value={horaRealInicio}
                  onChange={(event) => setHoraRealInicio(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Hora real fin</span>
                <input
                  type="datetime-local"
                  className="input"
                  value={horaRealFin}
                  onChange={(event) => setHoraRealFin(event.target.value)}
                />
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
