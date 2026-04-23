import { useCallback, useMemo, useState, type FormEvent } from 'react'

import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import {
  createAdminAvailability,
  getAdminAvailability,
} from '../../services/api/admin'

const slotTone = {
  disponible: 'success',
  reservado: 'primary',
  expirado: 'warning',
  inactivo: 'neutral',
} as const

const WEEKDAY_OPTIONS = [
  { label: 'Lunes', value: 1 },
  { label: 'Martes', value: 2 },
  { label: 'Miercoles', value: 3 },
  { label: 'Jueves', value: 4 },
  { label: 'Viernes', value: 5 },
  { label: 'Sabado', value: 6 },
  { label: 'Domingo', value: 0 },
] as const

const WEEKDAY_PRESETS = {
  weekdays: [1, 2, 3, 4, 5],
  monWedFri: [1, 3, 5],
  allWeek: [0, 1, 2, 3, 4, 5, 6],
} as const

function toDateKey(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function normalizeDate(value: string) {
  return value.trim()
}

function normalizeTime(value: string) {
  return value.trim().slice(0, 5)
}

function buildDateRange(startDate: string, endDate: string, weekdays: number[], excludedDates: string[]) {
  if (!startDate || !endDate) {
    return []
  }

  const start = new Date(`${startDate}T00:00:00`)
  const end = new Date(`${endDate}T00:00:00`)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) {
    return []
  }

  const selectedWeekdays = new Set(weekdays)
  const excluded = new Set(excludedDates)
  const dates: string[] = []
  const current = new Date(start)

  while (current <= end) {
    const dateKey = toDateKey(current)
    if (selectedWeekdays.has(current.getDay()) && !excluded.has(dateKey)) {
      dates.push(dateKey)
    }
    current.setDate(current.getDate() + 1)
  }

  return dates
}

export function AdminAvailabilityPage() {
  const [refreshToken, setRefreshToken] = useState(0)
  const [dateMode, setDateMode] = useState<'single' | 'range'>('single')
  const [specialistId, setSpecialistId] = useState<number | null>(null)
  const [dateInput, setDateInput] = useState('')
  const [timeInput, setTimeInput] = useState('')
  const [selectedDates, setSelectedDates] = useState<string[]>([])
  const [selectedTimes, setSelectedTimes] = useState<string[]>([])
  const [rangeStart, setRangeStart] = useState('')
  const [rangeEnd, setRangeEnd] = useState('')
  const [rangeWeekdays, setRangeWeekdays] = useState<number[]>([1, 2, 3, 4, 5])
  const [excludeDateInput, setExcludeDateInput] = useState('')
  const [excludedDates, setExcludedDates] = useState<string[]>([])
  const [serviceTypeIds, setServiceTypeIds] = useState<number[]>([])
  const [procedureTypeIds, setProcedureTypeIds] = useState<number[]>([])
  const [procedureIds, setProcedureIds] = useState<number[]>([])
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [rangeError, setRangeError] = useState<string | null>(null)

  const loader = useCallback(() => getAdminAvailability(), [refreshToken])
  const { data, isLoading, error } = useApiResource(loader)

  const totalBlocks = useMemo(
    () => selectedDates.length * selectedTimes.length,
    [selectedDates.length, selectedTimes.length],
  )

  function toggleSelection(list: number[], value: number) {
    return list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
  }

  function addDate() {
    const normalized = normalizeDate(dateInput)
    if (!normalized) return
    setSelectedDates((current) =>
      current.includes(normalized) ? current : [...current, normalized].sort(),
    )
    setDateInput('')
  }

  function switchDateMode(mode: 'single' | 'range') {
    setDateMode(mode)
    setSelectedDates([])
    setDateInput('')
    setRangeStart('')
    setRangeEnd('')
    setExcludedDates([])
    setExcludeDateInput('')
    setRangeError(null)
  }

  function addTime() {
    const normalized = normalizeTime(timeInput)
    if (!normalized) return
    setSelectedTimes((current) =>
      current.includes(normalized) ? current : [...current, normalized].sort(),
    )
    setTimeInput('')
  }

  function setWeekdayPreset(preset: readonly number[]) {
    setRangeWeekdays([...preset].sort((a, b) => a - b))
  }

  function toggleWeekday(day: number) {
    setRangeWeekdays((current) =>
      current.includes(day)
        ? current.filter((item) => item !== day).sort((a, b) => a - b)
        : [...current, day].sort((a, b) => a - b),
    )
  }

  function addExcludedDate() {
    const normalized = normalizeDate(excludeDateInput)
    if (!normalized) return
    setExcludedDates((current) =>
      current.includes(normalized) ? current : [...current, normalized].sort(),
    )
    setExcludeDateInput('')
  }

  function applyRange() {
    setRangeError(null)

    if (!rangeStart || !rangeEnd) {
      setRangeError('Debes indicar fecha inicial y fecha final para generar el rango.')
      return
    }

    if (!rangeWeekdays.length) {
      setRangeError('Debes seleccionar al menos un dia de la semana para el rango.')
      return
    }

    const generatedDates = buildDateRange(rangeStart, rangeEnd, rangeWeekdays, excludedDates)
    if (!generatedDates.length) {
      setRangeError('El rango no genero fechas validas con la configuracion actual.')
      return
    }

    setSelectedDates((current) => Array.from(new Set([...current, ...generatedDates])).sort())
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitError(null)
    setSubmitSuccess(null)
    setIsSubmitting(true)

    try {
      const response = await createAdminAvailability({
        specialistId,
        dates: selectedDates,
        times: selectedTimes,
        serviceTypeIds,
        procedureTypeIds,
        procedureIds,
      })
      setSubmitSuccess(response.detail)
      setSelectedDates([])
      setSelectedTimes([])
      setDateInput('')
      setTimeInput('')
      setRangeStart('')
      setRangeEnd('')
      setExcludedDates([])
      setExcludeDateInput('')
      setRangeWeekdays([1, 2, 3, 4, 5])
      setRefreshToken((value) => value + 1)
    } catch (requestError) {
      setSubmitError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo guardar la disponibilidad.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Agenda configurable"
        title="Disponibilidad de citas"
        description="Publica horarios reales por especialista y define para que servicios o procedimientos quedaran abiertos en el portal del cliente."
        actions={[
          {
            label: 'Actualizar vista',
            variant: 'ghost',
            onClick: () => setRefreshToken((value) => value + 1),
          },
        ]}
      />

      {submitSuccess ? <DataState title="Disponibilidad guardada" message={submitSuccess} /> : null}
      {submitError ? <DataState title="No pudimos guardar los horarios" message={submitError} tone="danger" /> : null}
      {rangeError ? <DataState title="No pudimos generar el rango" message={rangeError} tone="danger" /> : null}

      {isLoading && !data ? (
        <SectionCard title="Cargando disponibilidad">
          <DataState
            title="Consultando agenda publicada"
            message="Estamos trayendo especialistas, catalogos y horarios ya establecidos para reservas."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar la disponibilidad">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <>
          <section className="metrics-grid">
            {data.metrics.map((metric) => (
              <MetricCard key={metric.id} metric={metric} />
            ))}
          </section>

          <SectionCard
            eyebrow="Publicacion"
            title="Crear horarios disponibles"
            description="Selecciona el especialista, agrega dias y horas, y define para que alcance de servicio quedaran visibles estos cupos."
          >
            <form className="availability-form" onSubmit={(event) => void handleSubmit(event)}>
              <div className="form-grid">
                <label className="field field--full">
                  <span>Especialista disponible</span>
                  <select
                    className="input"
                    value={specialistId ?? ''}
                    onChange={(event) =>
                      setSpecialistId(event.target.value ? Number(event.target.value) : null)
                    }
                  >
                    <option value="">Selecciona un especialista</option>
                    {data.filters.specialists.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                        {option.secondaryLabel ? ` | ${option.secondaryLabel}` : ''}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="availability-form__mode-switch" role="tablist" aria-label="Modo de fechas">
                <button
                  className={`availability-form__mode-button ${dateMode === 'single' ? 'is-active' : ''}`}
                  type="button"
                  onClick={() => switchDateMode('single')}
                >
                  Fecha puntual
                </button>
                <button
                  className={`availability-form__mode-button ${dateMode === 'range' ? 'is-active' : ''}`}
                  type="button"
                  onClick={() => switchDateMode('range')}
                >
                  Rango de fechas
                </button>
              </div>

              <div className="availability-form__grid">
                {dateMode === 'single' ? (
                  <div className="availability-form__panel availability-form__panel--wide">
                    <strong>Fecha puntual</strong>
                    <div className="selection-row">
                      <input
                        className="input"
                        type="date"
                        value={dateInput}
                        onChange={(event) => setDateInput(event.target.value)}
                      />
                      <button className="button button--ghost button--compact" type="button" onClick={addDate}>
                        Agregar dia
                      </button>
                    </div>
                    <div className="chip-list">
                      {selectedDates.length ? (
                        selectedDates.map((item) => (
                          <button
                            key={item}
                            className="chip-list__item"
                            type="button"
                            onClick={() => setSelectedDates((current) => current.filter((value) => value !== item))}
                          >
                            {item}
                          </button>
                        ))
                      ) : (
                        <span className="availability-form__empty">Todavia no agregaste fechas puntuales.</span>
                      )}
                    </div>
                    <p className="availability-form__hint">
                      Usa este modo para uno o varios dias sueltos cargados manualmente.
                    </p>
                  </div>
                ) : (
                  <div className="availability-form__panel availability-form__panel--wide">
                    <strong>Rango de fechas</strong>
                    <div className="form-grid">
                      <label className="field">
                        <span>Desde</span>
                        <input
                          className="input"
                          type="date"
                          value={rangeStart}
                          onChange={(event) => setRangeStart(event.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>Hasta</span>
                        <input
                          className="input"
                          type="date"
                          value={rangeEnd}
                          onChange={(event) => setRangeEnd(event.target.value)}
                        />
                      </label>
                    </div>

                    <div className="availability-form__preset-row">
                      <button className="button button--ghost button--compact" type="button" onClick={() => setWeekdayPreset(WEEKDAY_PRESETS.weekdays)}>
                        Lunes a viernes
                      </button>
                      <button className="button button--ghost button--compact" type="button" onClick={() => setWeekdayPreset(WEEKDAY_PRESETS.monWedFri)}>
                        Lunes, miercoles y viernes
                      </button>
                      <button className="button button--ghost button--compact" type="button" onClick={() => setWeekdayPreset(WEEKDAY_PRESETS.allWeek)}>
                        Toda la semana
                      </button>
                    </div>

                    <div className="choice-grid choice-grid--compact">
                      {WEEKDAY_OPTIONS.map((option) => (
                        <label className="choice-card" key={option.value}>
                          <input
                            type="checkbox"
                            checked={rangeWeekdays.includes(option.value)}
                            onChange={() => toggleWeekday(option.value)}
                          />
                          <span>{option.label}</span>
                        </label>
                      ))}
                    </div>

                    <div className="selection-row">
                      <input
                        className="input"
                        type="date"
                        value={excludeDateInput}
                        onChange={(event) => setExcludeDateInput(event.target.value)}
                      />
                      <button className="button button--ghost button--compact" type="button" onClick={addExcludedDate}>
                        Excluir fecha
                      </button>
                    </div>
                    <div className="chip-list">
                      {excludedDates.length ? (
                        excludedDates.map((item) => (
                          <button
                            key={item}
                            className="chip-list__item"
                            type="button"
                            onClick={() => setExcludedDates((current) => current.filter((value) => value !== item))}
                          >
                            {item}
                          </button>
                        ))
                      ) : (
                        <span className="availability-form__empty">Sin excepciones especificas.</span>
                      )}
                    </div>
                    <div className="chip-list">
                      {selectedDates.length ? (
                        selectedDates.map((item) => (
                          <button
                            key={item}
                            className="chip-list__item"
                            type="button"
                            onClick={() => setSelectedDates((current) => current.filter((value) => value !== item))}
                          >
                            {item}
                          </button>
                        ))
                      ) : (
                        <span className="availability-form__empty">Todavia no generaste fechas desde el rango.</span>
                      )}
                    </div>
                    <button className="button button--ghost" type="button" onClick={applyRange}>
                      Generar fechas del rango
                    </button>
                    <p className="availability-form__hint">
                      Usa este modo para bloques como lunes a viernes, lunes-miercoles-viernes u otras combinaciones.
                    </p>
                  </div>
                )}

                <div className="availability-form__panel">
                  <strong>Horas</strong>
                  <div className="selection-row">
                    <input
                      className="input"
                      type="time"
                      value={timeInput}
                      onChange={(event) => setTimeInput(event.target.value)}
                    />
                    <button className="button button--ghost button--compact" type="button" onClick={addTime}>
                      Agregar hora
                    </button>
                  </div>
                  <div className="chip-list">
                    {selectedTimes.length ? (
                      selectedTimes.map((item) => (
                        <button
                          key={item}
                          className="chip-list__item"
                          type="button"
                          onClick={() => setSelectedTimes((current) => current.filter((value) => value !== item))}
                        >
                          {item}
                        </button>
                      ))
                    ) : (
                      <span className="availability-form__empty">Todavia no agregaste horas.</span>
                    )}
                  </div>
                  <p className="availability-form__hint">
                    Puedes dejar una hora para todos los dias o varias horas para publicar varios turnos por fecha.
                  </p>
                </div>
              </div>

              <div className="availability-form__scope">
                <article className="availability-form__panel">
                  <strong>Tipos de servicio</strong>
                  <div className="choice-grid">
                    {data.filters.serviceTypes.map((option) => (
                      <label className="choice-card" key={option.id}>
                        <input
                          type="checkbox"
                          checked={serviceTypeIds.includes(option.id)}
                          onChange={() => setServiceTypeIds((current) => toggleSelection(current, option.id))}
                        />
                        <span>{option.label}</span>
                      </label>
                    ))}
                  </div>
                </article>

                <article className="availability-form__panel">
                  <strong>Tipos de procedimiento estetico</strong>
                  <div className="choice-grid">
                    {data.filters.procedureTypes.map((option) => (
                      <label className="choice-card" key={option.id}>
                        <input
                          type="checkbox"
                          checked={procedureTypeIds.includes(option.id)}
                          onChange={() => setProcedureTypeIds((current) => toggleSelection(current, option.id))}
                        />
                        <span>{option.label}</span>
                      </label>
                    ))}
                  </div>
                </article>

                <article className="availability-form__panel">
                  <strong>Procedimientos especificos</strong>
                  <div className="choice-grid">
                    {data.filters.procedures.map((option) => (
                      <label className="choice-card" key={option.id}>
                        <input
                          type="checkbox"
                          checked={procedureIds.includes(option.id)}
                          onChange={() => setProcedureIds((current) => toggleSelection(current, option.id))}
                        />
                        <span>{option.label}</span>
                        {option.secondaryLabel ? <small>{option.secondaryLabel}</small> : null}
                      </label>
                    ))}
                  </div>
                </article>
              </div>

              <div className="availability-form__summary">
                <span>
                  Se crearan o actualizaran <strong>{totalBlocks}</strong> bloque(s) a partir de la combinacion actual.
                </span>
              </div>

              <div className="form-actions">
                <button className="button" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Guardando...' : 'Guardar disponibilidad'}
                </button>
              </div>
            </form>
          </SectionCard>

          <SectionCard
            eyebrow="Vista publicada"
            title="Horarios registrados"
            description="Estos son los bloques que hoy controlan la disponibilidad que el cliente ve en su calendario."
          >
            {data.slots.length ? (
              <div className="availability-slot-list">
                {data.slots.map((slot) => (
                  <article className="availability-slot-card" key={slot.id}>
                    <header>
                      <div>
                        <strong>{slot.dateTime}</strong>
                        <p>{slot.specialist}</p>
                      </div>
                      <StatusBadge tone={slotTone[slot.status]}>{slot.status}</StatusBadge>
                    </header>

                    <div className="chip-list chip-list--static">
                      {slot.coverage.length ? (
                        slot.coverage.map((item) => <span key={`${slot.id}-${item}`} className="chip-list__item chip-list__item--static">{item}</span>)
                      ) : (
                        <span className="availability-form__empty">Sin alcance configurado.</span>
                      )}
                    </div>

                    {slot.patient ? (
                      <div className="availability-slot-card__meta">
                        <span>Reservado por</span>
                        <strong>{slot.patient}</strong>
                        <p>
                          {slot.operation} | {slot.reservationState}
                        </p>
                      </div>
                    ) : (
                      <div className="availability-slot-card__meta">
                        <span>Estado actual</span>
                        <strong>{slot.active ? 'Publicado' : 'Inactivo'}</strong>
                        <p>Esperando reserva desde el portal del cliente.</p>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            ) : (
              <DataState
                title="Sin disponibilidad publicada"
                message="Todavia no hay bloques de horario creados para que el cliente pueda reservar."
              />
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  )
}
