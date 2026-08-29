import { useEffect, useState } from 'react'

import {
  checkAdminEspecialistasDisponibilidad,
  checkAdminMaquinariaConflicts,
  checkAdminConcurrency,
  getAdminStaff,
  getMaquinariaCatalog,
} from '../../../services/api/admin'
import type {
  AdminConcurrencyCheckResponse,
  AdminReservationExtendedPayload,
  EspecialistaDisponibilidad,
  MaquinariaConflict,
  MaquinariaDisponibilidad,
  StaffCapacityItem,
} from '../../../types/admin'
import { MaquinariaConflictList } from './MaquinariaConflictList'
import { RecursosDisponibilidadPanel } from './RecursosDisponibilidadPanel'

interface ReservationModalOption {
  id: number
  label: string
  secondaryLabel?: string
}

// `AdminReservationExtendedPayload` ya incluye `branchId` y `dateTime`;
// los demas campos son opcionales. `ReservationModalPayload` existe solo
// para que el tipo del callback `onConfirm` se lea como "payload completo"
// en las llamadas externas.
export type ReservationModalPayload = AdminReservationExtendedPayload

export interface MaquinariaOption {
  id: number
  nombre: string
  cantidadTotal: number
  marca?: string
}

export type MaquinariaRow = {
  /** Identificador local de la fila (unico). */
  rowId: string
  /** Id de la maquina seleccionada (null = sin elegir). */
  maquinariaId: number | null
  cantidad: number
}

interface ReservationModalProps {
  isOpen: boolean
  onClose: () => void
  /**
   * "create" = new reservation. "reschedule" = re-plan an existing cita
   * (date/hour editable, planning fields prepopulated from the cita).
   * The submit button label and confirmation text change accordingly.
   */
  mode?: 'create' | 'reschedule'
  /** Options for the "Procedimiento" selector. In reschedule mode the
   *  first option is auto-selected (same as create mode) and the admin
   *  does not change it. */
  reservableOperations: Array<{ id: number; rawId: number; selectLabel: string }>
  /** Sucursal del booking (la del admin/branch context). */
  branchId: number
  /**
   * In reschedule mode, prepopulate the planning fields from the cita
   * being rescheduled. Without this prop, mode reschedule behaves the
   * same as mode create (with empty planning fields).
   */
  prefillCita?: {
    duracionEstimadaMinutos?: number | null
    descripcionGeneral?: string
    notasPrevias?: string
    procedimientoPlanificado?: string
    zonaCuerpoPlanificada?: string
    especialistasPlanificados?: number[]
    maquinariaPlanificada?: Array<{ maquinariaId: number; cantidad: number }>
  }
  /** Callback que dispara la reserva. El padre arma el payload final con
   *  los IDs de operacion + branchId y dispara `createAdminClientReservation`
   *  o `rescheduleAdminAppointment` segun el `mode`. */
  onConfirm: (payload: AdminReservationExtendedPayload) => Promise<void> | void
  /** Texto de boton mientras la reserva esta en curso. */
  isBooking: boolean
}

const DURACION_DEFAULT = 60
// Carga maxima que la UI permite tipear para evitar un POST que el
// backend rechazaria (>480). La validacion de verdad vive en el server.
const DURACION_MAX = 480

/**
 * Modal de reserva de cita. Captura todos los campos planificados del
 * redesign (duracion, notas, procedimiento, zona, especialistas, maquinaria)
 * y delega en el padre el POST final. Internamente:
 *  - Carga perezosamente el catalogo de maquinaria y la lista de
 *    especialistas al abrir.
 *  - Ofrece un boton "Verificar disponibilidad" que combina el endpoint
 *    de concurrencia existente con el nuevo `check-maquinaria`.
 *  - Muestra los conflictos de maquinaria como WARN, nunca bloquea
 *    (consistente con el spec "Conflict check never blocks reservation").
 *  - Cierra con overlay, boton X, o confirmacion exitosa.
 */
export function ReservationModal({
  isOpen,
  onClose,
  mode = 'create',
  reservableOperations,
  branchId,
  prefillCita,
  onConfirm,
  isBooking,
}: ReservationModalProps) {
  // --- Local form state ---------------------------------------------------
  const [operationId, setOperationId] = useState<number | ''>('')
  const [date, setDate] = useState('')
  const [time, setTime] = useState('')
  const [duracionMinutos, setDuracionMinutos] = useState<number>(DURACION_DEFAULT)
  const [descripcionGeneral, setDescripcionGeneral] = useState('')
  const [notasPrevias, setNotasPrevias] = useState('')
  const [procedimientoPlanificado, setProcedimientoPlanificado] = useState('')
  const [zonaCuerpoPlanificada, setZonaCuerpoPlanificada] = useState('')
  const [especialistas, setEspecialistas] = useState<number[]>([])
  const [maquinariaRows, setMaquinariaRows] = useState<MaquinariaRow[]>([])

  // --- Server data (lazy) -------------------------------------------------
  const [maquinariaOptions, setMaquinariaOptions] = useState<MaquinariaOption[]>([])
  const [staffOptions, setStaffOptions] = useState<ReservationModalOption[]>([])
  const [loadingCatalog, setLoadingCatalog] = useState(false)

  // --- Availability check state -------------------------------------------
  const [concurrencyInfo, setConcurrencyInfo] = useState<AdminConcurrencyCheckResponse | null>(null)
  const [conflicts, setConflicts] = useState<MaquinariaConflict[]>([])
  const [maquinariaDisponibilidad, setMaquinariaDisponibilidad] = useState<MaquinariaDisponibilidad[]>([])
  const [especialistasDisponibilidad, setEspecialistasDisponibilidad] = useState<EspecialistaDisponibilidad[]>([])
  const [isChecking, setIsChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Becomes true after a successful check; reset to false whenever any
  // input that participates in availability changes (date, time, duration,
  // or maquinaria rows). The Confirm button stays disabled until the
  // admin runs the check again so they cannot submit with stale data.
  const [availabilityChecked, setAvailabilityChecked] = useState(false)
  // Snapshot of the inputs the last successful check was run against. Used
  // to detect when the admin has touched the form again and re-locks Confirm.
  const [checkedSnapshot, setCheckedSnapshot] = useState<{
    date: string
    time: string
    duracionMinutos: number
    maquinariaKey: string
    especialistasKey: string
  } | null>(null)

  // Reset state when the modal opens/closes.
  useEffect(() => {
    if (!isOpen) return
    // Pre-pick the first reservable operation as a convenience. The admin
    // can still change it; matches the previous inline behavior. The
    // setState-in-effect lint rule fires on the bulk reset below, so we
    // disable it just for this block — same pattern as BiometricVerifyCaptureModal.
    /* eslint-disable react-hooks/set-state-in-effect */
    setOperationId(reservableOperations[0]?.rawId ?? '')
    if (mode === 'reschedule' && prefillCita) {
      // Prepopulate planning fields from the cita being rescheduled.
      // date/time stay empty so the admin picks a new slot.
      setDate('')
      setTime('')
      setDuracionMinutos(prefillCita.duracionEstimadaMinutos ?? DURACION_DEFAULT)
      setDescripcionGeneral(prefillCita.descripcionGeneral ?? '')
      setNotasPrevias(prefillCita.notasPrevias ?? '')
      setProcedimientoPlanificado(prefillCita.procedimientoPlanificado ?? '')
      setZonaCuerpoPlanificada(prefillCita.zonaCuerpoPlanificada ?? '')
      setEspecialistas(prefillCita.especialistasPlanificados ?? [])
      setMaquinariaRows(
        (prefillCita.maquinariaPlanificada ?? []).map((item) => ({
          rowId: crypto.randomUUID(),
          maquinariaId: item.maquinariaId,
          cantidad: Math.max(1, item.cantidad),
        })),
      )
    } else {
      setDate('')
      setTime('')
      setDuracionMinutos(DURACION_DEFAULT)
      setDescripcionGeneral('')
      setNotasPrevias('')
      setProcedimientoPlanificado('')
      setZonaCuerpoPlanificada('')
      setEspecialistas([])
      setMaquinariaRows([])
    }
    setConcurrencyInfo(null)
    setConflicts([])
    setMaquinariaDisponibilidad([])
    setEspecialistasDisponibilidad([])
    setError(null)
    setAvailabilityChecked(false)
    setCheckedSnapshot(null)
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [isOpen, reservableOperations, mode, prefillCita])

  // Lazy-load the catalog + staff list once when the modal opens.
  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoadingCatalog(true)

    async function loadCatalog() {
      try {
        const [catalog, staff] = await Promise.all([
          getMaquinariaCatalog(),
          getAdminStaff(branchId),
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

        const staffOpts: ReservationModalOption[] = staff.staff
          .filter((member: StaffCapacityItem) => member.isActive)
          .map((member) => ({
            id: member.rawId,
            label: member.specialist,
            secondaryLabel: member.specialty,
          }))
        setStaffOptions(staffOpts)
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

    void loadCatalog()
    return () => {
      cancelled = true
    }
  }, [isOpen, branchId])

  // Invalidate the cached availability check whenever any input that
  // participates in availability changes. The admin must re-run
  // "Verificar disponibilidad" before Confirm unlocks again.
  const maquinariaKey = JSON.stringify(
    maquinariaRows.map((row) => ({ id: row.maquinariaId, c: row.cantidad })),
  )
  const especialistasKey = JSON.stringify([...especialistas].sort())
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!isOpen) return
    if (!checkedSnapshot) return
    const stillSame =
      checkedSnapshot.date === date &&
      checkedSnapshot.time === time &&
      checkedSnapshot.duracionMinutos === duracionMinutos &&
      checkedSnapshot.maquinariaKey === maquinariaKey &&
      checkedSnapshot.especialistasKey === especialistasKey
    if (!stillSame) {
      setAvailabilityChecked(false)
      setConcurrencyInfo(null)
      setConflicts([])
      setMaquinariaDisponibilidad([])
      setEspecialistasDisponibilidad([])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, time, duracionMinutos, maquinariaKey, especialistasKey, isOpen])
  /* eslint-enable react-hooks/set-state-in-effect */

  if (!isOpen) return null

  const totalMaquinariaSolicitada = maquinariaRows.reduce(
    (acc, row) => acc + (row.cantidad > 0 ? row.cantidad : 0),
    0,
  )

  // Per-row "is the requested cantidad above the catalog's stock?"
  // Map of rowId -> { option, cantidad, cantidadTotal }. Lets us disable
  // "Verificar disponibilidad" and surface an inline warning on the row.
  const stockByRowId = new Map<
    string,
    { option: MaquinariaOption; cantidad: number; cantidadTotal: number }
  >()
  maquinariaRows.forEach((row) => {
    if (row.maquinariaId === null) return
    const option = maquinariaOptions.find((opt) => opt.id === row.maquinariaId)
    if (!option) return
    stockByRowId.set(row.rowId, {
      option,
      cantidad: row.cantidad,
      cantidadTotal: option.cantidadTotal,
    })
  })
  const hasInsufficientStock = Array.from(stockByRowId.values()).some(
    (entry) => entry.cantidad > entry.cantidadTotal,
  )

  function addMaquinariaRow() {
    setMaquinariaRows((rows) => [
      ...rows,
      { rowId: crypto.randomUUID(), maquinariaId: null, cantidad: 1 },
    ])
  }

  function updateMaquinariaRow(rowId: string, patch: Partial<MaquinariaRow>) {
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

  async function handleCheckAvailability() {
    if (!date || !time) {
      setError('Selecciona fecha y hora.')
      return
    }
    setIsChecking(true)
    setError(null)
    try {
      const concurrency = await checkAdminConcurrency(branchId, date, time, time)
      setConcurrencyInfo(concurrency)

      // Maquinaria availability: always fetched so the panel renders even
      // when there is no over-assignment. The backend returns one entry
      // per requested maquinaría.
      const selected = maquinariaRows
        .filter((row): row is { rowId: string; maquinariaId: number; cantidad: number } =>
          row.maquinariaId !== null && row.cantidad > 0,
        )
      const selectedIds = selected.map((row) => row.maquinariaId)
      if (selectedIds.length > 0) {
        const conflictResponse = await checkAdminMaquinariaConflicts({
          sucursalId: branchId,
          fecha: date,
          hora: time,
          duracionMinutos,
          maquinariaIds: selectedIds,
          // Send the cantidad per row, aligned to maquinariaIds, so the
  // backend flags the conflict (cantidad_total=1 vs solicitud=8)
  // instead of silently defaulting to 1 per maquinaria.
          cantidades: selected.map((row) => row.cantidad),
        })
        setConflicts(conflictResponse.conflictos ?? [])
        setMaquinariaDisponibilidad(conflictResponse.disponibilidad ?? [])
      } else {
        setConflicts([])
        setMaquinariaDisponibilidad([])
      }

      // Especialistas availability: only fetched when the admin has
      // selected at least one especialista.
      if (especialistas.length > 0) {
        const espResponse = await checkAdminEspecialistasDisponibilidad({
          sucursalId: branchId,
          fecha: date,
          hora: time,
          duracionMinutos,
          especialistaIds: especialistas,
        })
        setEspecialistasDisponibilidad(espResponse.disponibilidad ?? [])
      } else {
        setEspecialistasDisponibilidad([])
      }
      // Lock in the inputs that the check was just run against. Any
      // change after this point invalidates availabilityChecked and the
      // admin must run the check again.
      setAvailabilityChecked(true)
      setCheckedSnapshot({
        date,
        time,
        duracionMinutos,
        maquinariaKey,
        especialistasKey,
      })
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo verificar la disponibilidad.',
      )
    } finally {
      setIsChecking(false)
    }
  }

  async function handleSubmit() {
    setError(null)
    if (!operationId) {
      setError('Selecciona un procedimiento.')
      return
    }
    if (!date || !time) {
      setError('Selecciona fecha y hora.')
      return
    }
    if (duracionMinutos < 1 || duracionMinutos > DURACION_MAX) {
      setError(`La duracion debe estar entre 1 y ${DURACION_MAX} minutos.`)
      return
    }

    const maquinariaPlanificada = maquinariaRows
      .filter((row) => row.maquinariaId !== null && row.cantidad > 0)
      .map((row) => ({ maquinariaId: row.maquinariaId as number, cantidad: row.cantidad }))

    const payload: AdminReservationExtendedPayload = {
      branchId,
      dateTime: `${date}T${time}:00`,
      duracionEstimadaMinutos: duracionMinutos,
      descripcionGeneral: descripcionGeneral || undefined,
      notasPrevias: notasPrevias || undefined,
      procedimientoPlanificado: procedimientoPlanificado || undefined,
      zonaCuerpoPlanificada: zonaCuerpoPlanificada || undefined,
      especialistasPlanificados: especialistas.length ? especialistas : undefined,
      maquinariaPlanificada: maquinariaPlanificada.length ? maquinariaPlanificada : undefined,
    }
    await onConfirm(payload)
  }

  return (
    <div className="booking-modal-overlay" onClick={onClose}>
      <div
        className="booking-modal-content"
        onClick={(event) => event.stopPropagation()}
        data-testid="reservation-modal"
      >
        <header className="booking-modal-header">
          <h2>{mode === 'reschedule' ? 'Reprogramar cita' : 'Reservar cita'}</h2>
          <button type="button" className="booking-modal-close" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="booking-modal-body">
          <div className="form-grid">
            <label className="field field--full">
              <span>Procedimiento</span>
              <select
                className="input"
                value={operationId === '' ? '' : String(operationId)}
                onChange={(event) =>
                  setOperationId(event.target.value === '' ? '' : Number(event.target.value))
                }
              >
                <option value="">Elegir procedimiento...</option>
                {reservableOperations.map((operation) => (
                  <option key={operation.rawId} value={operation.rawId}>
                    {operation.selectLabel}
                  </option>
                ))}
              </select>
            </label>

            <div className="_grid-2cols">
              <label className="field">
                <span>Fecha</span>
                <input
                  type="date"
                  className="input"
                  value={date}
                  onChange={(event) => setDate(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Hora de inicio</span>
                <input
                  type="time"
                  className="input"
                  value={time}
                  onChange={(event) => setTime(event.target.value)}
                />
              </label>
            </div>

            <label className="field">
              <span>Duracion estimada (minutos)</span>
              <input
                type="number"
                className="input"
                min={1}
                max={DURACION_MAX}
                value={duracionMinutos}
                onChange={(event) => setDuracionMinutos(Number(event.target.value) || 0)}
              />
            </label>

            <label className="field field--full">
              <span>Descripcion general</span>
              <textarea
                className="input textarea"
                rows={2}
                value={descripcionGeneral}
                onChange={(event) => setDescripcionGeneral(event.target.value)}
              />
            </label>

            <label className="field field--full">
              <span>Notas previas</span>
              <textarea
                className="input textarea"
                rows={2}
                value={notasPrevias}
                onChange={(event) => setNotasPrevias(event.target.value)}
              />
            </label>

            <label className="field field--full">
              <span>Procedimiento planificado</span>
              <textarea
                className="input textarea"
                rows={2}
                value={procedimientoPlanificado}
                onChange={(event) => setProcedimientoPlanificado(event.target.value)}
              />
            </label>

            <label className="field">
              <span>Zona del cuerpo planificada</span>
              <input
                type="text"
                className="input"
                value={zonaCuerpoPlanificada}
                onChange={(event) => setZonaCuerpoPlanificada(event.target.value)}
              />
            </label>

            <fieldset className="field field--full">
              <legend>Especialistas planificados</legend>
              {staffOptions.length === 0 ? (
                <small className="field__hint">No seleccionado</small>
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
              {staffOptions.length === 0 ? (
                <small className="field__hint">Cargando especialistas...</small>
              ) : null}
            </fieldset>

            <fieldset className="field field--full">
              <legend>Maquinaria planificada</legend>
              {maquinariaRows.length === 0 ? (
                <small className="field__hint">No se reservo maquinaria para esta cita.</small>
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
                            max={
                              stockByRowId.get(row.rowId)?.cantidadTotal
                            }
                            className="input"
                            value={row.cantidad}
                            onChange={(event) =>
                              updateMaquinariaRow(row.rowId, {
                                cantidad: Math.max(1, Number(event.target.value) || 1),
                              })
                            }
                          />
                          {(() => {
                            const stock = stockByRowId.get(row.rowId)
                            if (!stock) return null
                            if (stock.cantidad <= stock.cantidadTotal) return null
                            return (
                              <small className="field__error">
                                Excede el stock ({stock.cantidad} solicitados,
                                {' '}{stock.cantidadTotal} disponibles).
                              </small>
                            )
                          })()}
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
                {loadingCatalog ? (
                  <small className="field__hint _ml-sm">Cargando catalogo...</small>
                ) : null}
              </div>
            </fieldset>

            <div className="_mt-md _flex-gap-sm">
              <button
                type="button"
                className="button button--secondary"
                disabled={
                  !date || !time || isChecking || hasInsufficientStock
                }
                title={
                  hasInsufficientStock
                    ? 'Hay filas con cantidad solicitada mayor al stock disponible.'
                    : undefined
                }
                onClick={() => void handleCheckAvailability()}
              >
                {isChecking
                  ? 'Verificando...'
                  : availabilityChecked
                  ? 'Volver a verificar'
                  : 'Verificar disponibilidad'}
              </button>
              {availabilityChecked && !hasInsufficientStock ? (
                <small className="field__hint">Disponibilidad verificada</small>
              ) : null}
              {hasInsufficientStock ? (
                <small className="field__error">
                  Hay filas con cantidad superior al stock disponible.
                </small>
              ) : null}
            </div>
          </div>

          {error ? (
            <p className="field__error _mt-md" data-testid="reservation-modal-error">
              {error}
            </p>
          ) : null}

          {concurrencyInfo ? (
            <div className="_mt-md">
              <div className="_panel-card">
                <p className="_mb-sm">
                  <strong>
                    Citas simultaneas de 1 hora antes a 1 hora despues (
                    {concurrencyInfo.hora_inicio} a {concurrencyInfo.hora_fin}):
                  </strong>{' '}
                  {concurrencyInfo.concurrency}
                </p>
                {concurrencyInfo.appointments && concurrencyInfo.appointments.length > 0 ? (
                  <div
                    style={{
                      marginTop: '0.75rem',
                      paddingLeft: '0.5rem',
                      borderLeft: '2px solid var(--color-border)',
                    }}
                  >
                    <ul
                      style={{
                        fontSize: '0.82rem',
                        color: 'var(--color-text-soft)',
                        paddingLeft: '1.2rem',
                        margin: 0,
                      }}
                    >
                      {concurrencyInfo.appointments.map((apt, idx) => (
                        <li key={idx} style={{ marginBottom: '0.3rem' }}>
                          <span style={{ fontWeight: 500 }}>
                            {apt.cliente_nombre ?? 'Cliente no registrado'}
                          </span>
                          {' — '}
                          {apt.tratamiento_nombre ?? 'Sin tratamiento'}
                          {' — '}
                          {new Date(apt.hora).toLocaleTimeString('es-AR', {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p
                    style={{
                      fontSize: '0.85rem',
                      color: 'var(--color-text-soft)',
                      marginTop: '0.5rem',
                    }}
                  >
                    Sin citas simultaneas
                  </p>
                )}
                <p className="_mb-sm">
                  <strong>Especialistas en turno {concurrencyInfo.hora_seleccionada}:</strong>{' '}
                  {concurrencyInfo.presentes.length > 0
                    ? concurrencyInfo.presentes
                        .map((p) => `${p.usuario__primer_nombre} ${p.usuario__apellido_paterno}`)
                        .join(', ')
                    : 'Ninguno registrado'}
                </p>
                {concurrencyInfo.concurrency >= concurrencyInfo.presentes.length &&
                concurrencyInfo.presentes.length > 0 ? (
                  <p className="_text-danger _mt-sm _font-bold">
                    Aviso: Hay mas citas ({concurrencyInfo.concurrency}) que especialistas en
                    turno ({concurrencyInfo.presentes.length}).
                  </p>
                ) : null}
                {concurrencyInfo.presentes.length === 0 ? (
                  <p className="_text-warning _mt-sm _font-bold">
                    Aviso: No hay especialistas en turno configurados para esta sucursal a
                    esa hora.
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}

          <MaquinariaConflictList
            conflicts={conflicts}
            totalRequested={totalMaquinariaSolicitada}
          />

          <RecursosDisponibilidadPanel
            maquinaria={maquinariaDisponibilidad}
            especialistas={especialistasDisponibilidad}
          />

          <div className="_mt-lg form-actions">
            <button
              type="button"
              className="button button--primary"
              onClick={() => void handleSubmit()}
              disabled={isBooking || !availabilityChecked || hasInsufficientStock}
              title={
                hasInsufficientStock
                  ? 'Reduce la cantidad en las filas que exceden el stock.'
                  : !availabilityChecked
                  ? 'Verifica la disponibilidad antes de confirmar.'
                  : undefined
              }
              data-testid="reservation-modal-confirm"
            >
              {isBooking
                ? 'Confirmando...'
                : mode === 'reschedule'
                ? 'Confirmar reprogramacion'
                : 'Confirmar reserva'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
