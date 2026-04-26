import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import {
  createAdminAvailabilityException,
  createAdminHabitualSchedule,
  createAdminTimeSlot,
  deleteAdminAvailabilityException,
  deleteAdminHabitualSchedule,
  deleteAdminTimeSlot,
  getAdminAvailability,
  manageAdminGlobalAvailability,
  updateAdminHabitualSchedule,
  updateAdminTimeSlot,
} from '../../services/api/admin'
import type {
  AdminAvailabilityResponse,
  AdminAvailabilitySlot,
  AdminHabitualSchedule,
  AdminSpecialistAvailabilityException,
} from '../../types/admin'

const slotTone = {
  disponible: 'success',
  reservado: 'primary',
  expirado: 'warning',
  inactivo: 'neutral',
} as const

function buildEmptyTimeSlotForm() {
  return {
    startTime: '',
    endTime: '',
    detail: '',
    active: true,
  }
}

function buildEmptyHabitualForm() {
  return {
    specialistId: null as number | null,
    startDate: '',
    endDate: '',
    weekdayCodes: [] as number[],
    timeSlotIds: [] as number[],
    serviceTypeIds: [] as number[],
    procedureTypeIds: [] as number[],
    procedureIds: [] as number[],
    detail: '',
  }
}

function buildEmptyExceptionForm() {
  return {
    specialistId: null as number | null,
    type: 'BLOQUEAR' as 'AGREGAR' | 'BLOQUEAR',
    dateInput: '',
    dates: [] as string[],
    timeSlotIds: [] as number[],
    serviceTypeIds: [] as number[],
    procedureTypeIds: [] as number[],
    procedureIds: [] as number[],
    detail: '',
  }
}

function toggleSelection(current: number[], value: number) {
  return current.includes(value)
    ? current.filter((item) => item !== value)
    : [...current, value].sort((a, b) => a - b)
}

function normalizeDate(value: string) {
  return value.trim()
}

function useSpecialistScopedLists(
  data: AdminAvailabilityResponse | null,
  selectedSpecialistId: number | null,
) {
  return useMemo(() => {
    if (!data || !selectedSpecialistId) {
      return {
        specialistRules: [] as AdminHabitualSchedule[],
        specialistExceptions: [] as AdminSpecialistAvailabilityException[],
        specialistSlots: [] as AdminAvailabilitySlot[],
      }
    }

    return {
      specialistRules: data.habitualRules.filter((item) => item.specialistId === selectedSpecialistId),
      specialistExceptions: data.exceptions.filter((item) => item.specialistId === selectedSpecialistId),
      specialistSlots: data.slots.filter((item) => item.specialistId === selectedSpecialistId),
    }
  }, [data, selectedSpecialistId])
}

export function AdminAvailabilityPage() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [selectedSpecialistId, setSelectedSpecialistId] = useState<number | null>(null)
  const [editingTimeSlotId, setEditingTimeSlotId] = useState<number | null>(null)
  const [editingHabitualId, setEditingHabitualId] = useState<number | null>(null)
  const [timeSlotForm, setTimeSlotForm] = useState(buildEmptyTimeSlotForm())
  const [habitualForm, setHabitualForm] = useState(buildEmptyHabitualForm())
  const [exceptionForm, setExceptionForm] = useState(buildEmptyExceptionForm())
  const [globalDate, setGlobalDate] = useState('')
  const [globalDetail, setGlobalDetail] = useState('')
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const loader = useMemo(() => () => getAdminAvailability(), [refreshKey])
  const { data, isLoading, error } = useApiResource(loader)
  const { showNotification } = useNotifications()

  useEffect(() => {
    if (!data?.specialistSummaries.length) {
      setSelectedSpecialistId(null)
      return
    }
    if (!selectedSpecialistId || !data.specialistSummaries.some((item) => item.id === selectedSpecialistId)) {
      const firstSpecialistId = data.specialistSummaries[0]?.id ?? null
      setSelectedSpecialistId(firstSpecialistId)
      setHabitualForm((current) => ({ ...current, specialistId: firstSpecialistId }))
      setExceptionForm((current) => ({ ...current, specialistId: firstSpecialistId }))
    }
  }, [data, selectedSpecialistId])

  const { specialistRules, specialistExceptions, specialistSlots } = useSpecialistScopedLists(
    data,
    selectedSpecialistId,
  )
  const selectedSpecialist = useMemo(
    () => data?.specialistSummaries.find((item) => item.id === selectedSpecialistId) ?? null,
    [data, selectedSpecialistId],
  )

  function resetTimeSlotForm() {
    setEditingTimeSlotId(null)
    setTimeSlotForm(buildEmptyTimeSlotForm())
  }

  function resetHabitualForm() {
    setEditingHabitualId(null)
    setHabitualForm({
      ...buildEmptyHabitualForm(),
      specialistId: selectedSpecialistId,
    })
  }

  function resetExceptionForm() {
    setExceptionForm({
      ...buildEmptyExceptionForm(),
      specialistId: selectedSpecialistId,
    })
  }

  function addExceptionDate() {
    const normalized = normalizeDate(exceptionForm.dateInput)
    if (!normalized) {
      return
    }
    setExceptionForm((current) => ({
      ...current,
      dateInput: '',
      dates: current.dates.includes(normalized)
        ? current.dates
        : [...current.dates, normalized].sort(),
    }))
  }

  function loadTimeSlotForEdit(slotId: number) {
    const slot = data?.filters.timeSlots.find((item) => item.id === slotId)
    if (!slot) {
      return
    }
    setEditingTimeSlotId(slotId)
    setTimeSlotForm({
      startTime: slot.startTime,
      endTime: slot.endTime,
      detail: slot.detail,
      active: slot.active,
    })
    setSubmitError(null)
  }

  function loadHabitualForEdit(rule: AdminHabitualSchedule) {
    setEditingHabitualId(rule.id)
    setSelectedSpecialistId(rule.specialistId)
    setHabitualForm({
      specialistId: rule.specialistId,
      startDate: rule.startDate,
      endDate: rule.endDate,
      weekdayCodes: [...rule.weekdayCodes],
      timeSlotIds: [...rule.timeSlotIds],
      serviceTypeIds: [...rule.serviceTypeIds],
      procedureTypeIds: [...rule.procedureTypeIds],
      procedureIds: [...rule.procedureIds],
      detail: rule.detail,
    })
    setSubmitError(null)
  }

  async function handleTimeSlotSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    console.log('[AdminAvailability] handleTimeSlotSubmit:start', {
      editingTimeSlotId,
      payload: timeSlotForm,
      at: new Date().toISOString(),
    })
    setSubmitError(null)
    setIsSubmitting(true)
    try {
      console.log('[AdminAvailability] handleTimeSlotSubmit:beforeRequest', {
        mode: editingTimeSlotId ? 'update' : 'create',
      })
      const response = editingTimeSlotId
        ? await updateAdminTimeSlot(editingTimeSlotId, timeSlotForm)
        : await createAdminTimeSlot(timeSlotForm)
      console.log('[AdminAvailability] handleTimeSlotSubmit:afterResponse', {
        response,
        at: new Date().toISOString(),
      })
      showNotification({
        title: editingTimeSlotId ? 'Horario actualizado' : 'Horario creado',
        message: response.detail,
        tone: 'success',
      })
      resetTimeSlotForm()
      setRefreshKey((current) => current + 1)
    } catch (requestError) {
      console.error('[AdminAvailability] handleTimeSlotSubmit:error', requestError)
      setSubmitError(
        requestError instanceof Error ? requestError.message : 'No se pudo guardar el horario base.',
      )
    } finally {
      console.log('[AdminAvailability] handleTimeSlotSubmit:finally', {
        at: new Date().toISOString(),
      })
      setIsSubmitting(false)
    }
  }

  async function handleDeleteTimeSlot(slotId: number) {
    const confirmed = window.confirm(
      'Se eliminara el horario base seleccionado. Los cupos futuros sin reserva dejaran de publicarse. ¿Continuar?',
    )
    if (!confirmed) {
      return
    }

    setSubmitError(null)
    setIsSubmitting(true)
    try {
      const response = await deleteAdminTimeSlot(slotId)
      showNotification({
        title: 'Horario eliminado',
        message: response.detail,
        tone: 'success',
      })
      if (editingTimeSlotId === slotId) {
        resetTimeSlotForm()
      }
      setRefreshKey((current) => current + 1)
    } catch (requestError) {
      setSubmitError(
        requestError instanceof Error ? requestError.message : 'No se pudo eliminar el horario base.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleHabitualSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitError(null)
    setIsSubmitting(true)
    try {
      const response = editingHabitualId
        ? await updateAdminHabitualSchedule(editingHabitualId, habitualForm)
        : await createAdminHabitualSchedule(habitualForm)
      showNotification({
        title: editingHabitualId ? 'Horario habitual actualizado' : 'Horario habitual creado',
        message: response.detail,
        tone: 'success',
      })
      resetHabitualForm()
      setRefreshKey((current) => current + 1)
    } catch (requestError) {
      setSubmitError(
        requestError instanceof Error ? requestError.message : 'No se pudo guardar el horario habitual.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleDeleteHabitual(ruleId: number) {
    const confirmed = window.confirm(
      'Se eliminara esta regla habitual. Las reservas futuras ya tomadas se conservaran, pero los cupos libres dejaran de publicarse. ¿Continuar?',
    )
    if (!confirmed) {
      return
    }

    setSubmitError(null)
    setIsSubmitting(true)
    try {
      const response = await deleteAdminHabitualSchedule(ruleId)
      showNotification({
        title: 'Horario habitual eliminado',
        message: response.detail,
        tone: 'success',
      })
      if (editingHabitualId === ruleId) {
        resetHabitualForm()
      }
      setRefreshKey((current) => current + 1)
    } catch (requestError) {
      setSubmitError(
        requestError instanceof Error ? requestError.message : 'No se pudo eliminar el horario habitual.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleExceptionSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitError(null)
    setIsSubmitting(true)
    try {
      const response = await createAdminAvailabilityException({
        specialistId: exceptionForm.specialistId,
        type: exceptionForm.type,
        dates: exceptionForm.dates,
        timeSlotIds: exceptionForm.timeSlotIds,
        serviceTypeIds: exceptionForm.serviceTypeIds,
        procedureTypeIds: exceptionForm.procedureTypeIds,
        procedureIds: exceptionForm.procedureIds,
        detail: exceptionForm.detail,
      })
      showNotification({
        title:
          exceptionForm.type === 'AGREGAR'
            ? 'Dia adicional publicado'
            : 'Bloque puntual suspendido',
        message: response.detail,
        tone: 'success',
      })
      resetExceptionForm()
      setRefreshKey((current) => current + 1)
    } catch (requestError) {
      setSubmitError(
        requestError instanceof Error ? requestError.message : 'No se pudo guardar la excepcion.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleDeleteException(exceptionId: number) {
    const confirmed = window.confirm(
      'Se eliminara esta excepcion y volvera a aplicarse la agenda habitual correspondiente. ¿Continuar?',
    )
    if (!confirmed) {
      return
    }

    setSubmitError(null)
    setIsSubmitting(true)
    try {
      const response = await deleteAdminAvailabilityException(exceptionId)
      showNotification({
        title: 'Excepcion eliminada',
        message: response.detail,
        tone: 'success',
      })
      setRefreshKey((current) => current + 1)
    } catch (requestError) {
      setSubmitError(
        requestError instanceof Error ? requestError.message : 'No se pudo eliminar la excepcion.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleGlobalAction(
    action: 'BLOQUEAR' | 'RESTAURAR',
    overrides?: { date?: string; detail?: string },
  ) {
    setSubmitError(null)
    setIsSubmitting(true)
    try {
      const response = await manageAdminGlobalAvailability({
        action,
        date: overrides?.date ?? globalDate,
        detail: overrides?.detail ?? globalDetail,
      })
      showNotification({
        title: action === 'BLOQUEAR' ? 'Dia libre global aplicado' : 'Dia restaurado',
        message: response.detail,
        tone: 'success',
      })
      if (action === 'RESTAURAR') {
        setGlobalDetail('')
      }
      setRefreshKey((current) => current + 1)
    } catch (requestError) {
      setSubmitError(
        requestError instanceof Error ? requestError.message : 'No se pudo aplicar el cambio global.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading && !data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Agenda configurable"
          title="Disponibilidad de citas"
          description="Cargando horarios base, especialistas y cupos ya publicados."
        />
        <SectionCard title="Cargando agenda">
          <DataState
            title="Sincronizando agenda"
            message="Estamos preparando horarios base, agendas habituales y excepciones puntuales."
          />
        </SectionCard>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Agenda configurable"
          title="Disponibilidad de citas"
          description="No pudimos cargar la configuracion de agenda."
        />
        <SectionCard title="Agenda no disponible">
          <DataState title="Conexion no disponible" message={error || 'No se pudo cargar la agenda.'} tone="danger" />
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Agenda configurable"
        title="Disponibilidad de citas"
        description="Define horarios base para toda la clinica, establece horarios habituales por especialista y aplica cambios puntuales o globales sin rehacer todo el calendario."
        actions={[
          {
            label: 'Actualizar vista',
            variant: 'ghost',
            onClick: () => setRefreshKey((current) => current + 1),
          },
        ]}
      />

      {submitError ? (
        <DataState title="No pudimos completar el cambio" message={submitError} tone="danger" />
      ) : null}

      <section className="metrics-grid">
        {data.metrics.map((metric) => (
          <MetricCard key={metric.id} metric={metric} />
        ))}
      </section>

      <section className="dashboard-grid">
        <SectionCard
          eyebrow="Horarios base"
          title="Bloques reutilizables"
          description="Estos rangos horarios se aplican a todos los dias. Luego puedes asignarlos a especialistas dentro de sus periodos habituales."
        >
          <form className="availability-admin-form" onSubmit={(event) => void handleTimeSlotSubmit(event)}>
            <div className="form-grid">
              <label className="field">
                <span>Hora inicio</span>
                <input
                  className="input"
                  type="time"
                  value={timeSlotForm.startTime}
                  onChange={(event) => setTimeSlotForm((current) => ({ ...current, startTime: event.target.value }))}
                />
              </label>
              <label className="field">
                <span>Hora fin</span>
                <input
                  className="input"
                  type="time"
                  value={timeSlotForm.endTime}
                  onChange={(event) => setTimeSlotForm((current) => ({ ...current, endTime: event.target.value }))}
                />
              </label>
              <label className="field field--full">
                <span>Detalle opcional</span>
                <input
                  className="input"
                  type="text"
                  value={timeSlotForm.detail}
                  onChange={(event) => setTimeSlotForm((current) => ({ ...current, detail: event.target.value }))}
                  placeholder="Ej. Bloque matutino principal"
                />
              </label>
            </div>

            {editingTimeSlotId ? (
              <label className="field field--inline">
                <input
                  checked={timeSlotForm.active}
                  type="checkbox"
                  onChange={(event) => setTimeSlotForm((current) => ({ ...current, active: event.target.checked }))}
                />
                <span>Horario base activo</span>
              </label>
            ) : null}

            <div className="form-actions">
              <button className="button" disabled={isSubmitting} type="submit">
                {editingTimeSlotId ? 'Actualizar horario' : 'Crear horario'}
              </button>
              {editingTimeSlotId ? (
                <button className="button button--ghost" type="button" onClick={resetTimeSlotForm}>
                  Cancelar edicion
                </button>
              ) : null}
            </div>
          </form>

          <div className="availability-admin-list">
            {data.filters.timeSlots.map((slot) => (
              <article className="availability-admin-card" key={slot.id}>
                <div>
                  <strong>{slot.label}</strong>
                  <p>
                    {slot.futureSlots} cupo(s) futuro(s) | {slot.reservedFutureSlots} con reserva
                  </p>
                </div>
                <div className="availability-admin-card__actions">
                  <StatusBadge tone={slot.active ? 'success' : 'neutral'}>
                    {slot.active ? 'Activo' : 'Inactivo'}
                  </StatusBadge>
                  <button className="button button--ghost button--compact" type="button" onClick={() => loadTimeSlotForEdit(slot.id)}>
                    Editar
                  </button>
                  <button
                    className="button button--ghost button--compact"
                    type="button"
                    onClick={() => void handleDeleteTimeSlot(slot.id)}
                  >
                    Eliminar
                  </button>
                </div>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          eyebrow="Cambios globales"
          title="Dias libres o restaurados para todos"
          description="Bloquea una fecha completa para todos los especialistas o restáurala para que vuelvan sus horarios habituales."
        >
          <form
            className="availability-admin-form"
            onSubmit={(event) => {
              event.preventDefault()
              void handleGlobalAction('BLOQUEAR')
            }}
          >
            <div className="form-grid">
              <label className="field">
                <span>Fecha</span>
                <input
                  className="input"
                  type="date"
                  value={globalDate}
                  onChange={(event) => setGlobalDate(event.target.value)}
                />
              </label>
              <label className="field field--full">
                <span>Motivo o nota</span>
                <input
                  className="input"
                  type="text"
                  value={globalDetail}
                  onChange={(event) => setGlobalDetail(event.target.value)}
                  placeholder="Ej. Feriado clinico o mantenimiento general"
                />
              </label>
            </div>
            <div className="form-actions">
              <button className="button" disabled={isSubmitting} type="submit">
                Marcar dia libre para todos
              </button>
              <button
                className="button button--ghost"
                disabled={isSubmitting}
                type="button"
                onClick={() => void handleGlobalAction('RESTAURAR')}
              >
                Restaurar fecha
              </button>
            </div>
          </form>

          <div className="availability-admin-list">
            {data.globalBlocks.length ? (
              data.globalBlocks.map((item) => (
                <article className="availability-admin-card" key={item.id}>
                  <div>
                    <strong>{item.dateLabel}</strong>
                    <p>{item.detail || 'Sin detalle adicional.'}</p>
                  </div>
                  <div className="availability-admin-card__actions">
                    <StatusBadge tone={item.active ? 'warning' : 'neutral'}>
                      {item.active ? 'Bloqueado' : 'Restaurado'}
                    </StatusBadge>
                    {item.active ? (
                      <button
                        className="button button--ghost button--compact"
                        type="button"
                        onClick={() => {
                          setGlobalDate(item.date)
                          setGlobalDetail(item.detail)
                          void handleGlobalAction('RESTAURAR', {
                            date: item.date,
                            detail: item.detail,
                          })
                        }}
                      >
                        Restaurar
                      </button>
                    ) : null}
                  </div>
                </article>
              ))
            ) : (
              <DataState
                title="Sin bloqueos globales"
                message="Todavia no se definieron dias libres para toda la clinica."
              />
            )}
          </div>
        </SectionCard>
      </section>

      <SectionCard
        eyebrow="Especialistas"
        title="Agenda habitual y ajustes puntuales"
        description="Selecciona un especialista para ver sus horarios habituales, aplicar excepciones por fecha y revisar los cupos concretos que hoy se publican."
      >
        <div className="specialist-agenda">
          <aside className="specialist-agenda__sidebar">
            {data.specialistSummaries.map((item) => (
              <button
                key={item.id}
                className={`specialist-agenda__summary ${selectedSpecialistId === item.id ? 'is-active' : ''}`}
                type="button"
                onClick={() => {
                  setSelectedSpecialistId(item.id)
                  setHabitualForm((current) => ({ ...current, specialistId: item.id }))
                  setExceptionForm((current) => ({ ...current, specialistId: item.id }))
                }}
              >
                <strong>{item.label}</strong>
                <p>{item.secondaryLabel}</p>
                <div className="specialist-agenda__summary-meta">
                  <span>{item.futureSlots} cupos</span>
                  <span>{item.habitualRules} reglas</span>
                  <span>{item.exceptions} excepciones</span>
                </div>
                <small>{item.nextSlot}</small>
              </button>
            ))}
          </aside>

          <div className="specialist-agenda__content">
            {selectedSpecialist ? (
              <>
                <div className="specialist-agenda__hero">
                  <div>
                    <span className="specialist-agenda__eyebrow">Especialista seleccionado</span>
                    <h3>{selectedSpecialist.label}</h3>
                    <p>{selectedSpecialist.secondaryLabel}</p>
                  </div>
                  <div className="specialist-agenda__hero-metrics">
                    <article>
                      <span>Proximo cupo</span>
                      <strong>{selectedSpecialist.nextSlot}</strong>
                    </article>
                    <article>
                      <span>Reglas habituales</span>
                      <strong>{selectedSpecialist.habitualRules}</strong>
                    </article>
                    <article>
                      <span>Excepciones</span>
                      <strong>{selectedSpecialist.exceptions}</strong>
                    </article>
                  </div>
                </div>

                <section className="dashboard-grid">
                  <SectionCard
                    eyebrow="Horario habitual"
                    title={editingHabitualId ? 'Editar regla habitual' : 'Crear horario habitual'}
                    description="Este es el patron base del especialista. Luego puedes quitar dias o agregar otros con excepciones puntuales."
                  >
                    <form className="availability-admin-form" onSubmit={(event) => void handleHabitualSubmit(event)}>
                      <div className="form-grid">
                        <label className="field">
                          <span>Especialista</span>
                          <select
                            className="input"
                            value={habitualForm.specialistId ?? ''}
                            onChange={(event) =>
                              setHabitualForm((current) => ({
                                ...current,
                                specialistId: event.target.value ? Number(event.target.value) : null,
                              }))
                            }
                          >
                            <option value="">Selecciona un especialista</option>
                            {data.filters.specialists.map((option) => (
                              <option key={option.id} value={option.id}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="field">
                          <span>Desde</span>
                          <input
                            className="input"
                            type="date"
                            value={habitualForm.startDate}
                            onChange={(event) =>
                              setHabitualForm((current) => ({ ...current, startDate: event.target.value }))
                            }
                          />
                        </label>
                        <label className="field">
                          <span>Hasta</span>
                          <input
                            className="input"
                            type="date"
                            value={habitualForm.endDate}
                            onChange={(event) =>
                              setHabitualForm((current) => ({ ...current, endDate: event.target.value }))
                            }
                          />
                        </label>
                        <label className="field field--full">
                          <span>Detalle</span>
                          <input
                            className="input"
                            type="text"
                            value={habitualForm.detail}
                            onChange={(event) =>
                              setHabitualForm((current) => ({ ...current, detail: event.target.value }))
                            }
                            placeholder="Ej. Horario habitual de depilacion laser"
                          />
                        </label>
                      </div>

                      <article className="availability-form__panel">
                        <strong>Dias habituales</strong>
                        <div className="choice-grid choice-grid--compact">
                          {data.filters.weekdayOptions.map((option) => (
                            <label className="choice-card" key={option.value}>
                              <input
                                checked={habitualForm.weekdayCodes.includes(option.value)}
                                type="checkbox"
                                onChange={() =>
                                  setHabitualForm((current) => ({
                                    ...current,
                                    weekdayCodes: toggleSelection(current.weekdayCodes, option.value),
                                  }))
                                }
                              />
                              <span>{option.label}</span>
                            </label>
                          ))}
                        </div>
                      </article>

                      <article className="availability-form__panel">
                        <strong>Horarios base</strong>
                        <div className="choice-grid">
                          {data.filters.timeSlots
                            .filter((slot) => slot.active)
                            .map((slot) => (
                              <label className="choice-card" key={slot.id}>
                                <input
                                  checked={habitualForm.timeSlotIds.includes(slot.id)}
                                  type="checkbox"
                                  onChange={() =>
                                    setHabitualForm((current) => ({
                                      ...current,
                                      timeSlotIds: toggleSelection(current.timeSlotIds, slot.id),
                                    }))
                                  }
                                />
                                <span>{slot.label}</span>
                              </label>
                            ))}
                        </div>
                      </article>

                      <div className="availability-form__scope">
                        <article className="availability-form__panel">
                          <strong>Tipos de servicio</strong>
                          <div className="choice-grid">
                            {data.filters.serviceTypes.map((option) => (
                              <label className="choice-card" key={option.id}>
                                <input
                                  checked={habitualForm.serviceTypeIds.includes(option.id)}
                                  type="checkbox"
                                  onChange={() =>
                                    setHabitualForm((current) => ({
                                      ...current,
                                      serviceTypeIds: toggleSelection(current.serviceTypeIds, option.id),
                                    }))
                                  }
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
                                  checked={habitualForm.procedureTypeIds.includes(option.id)}
                                  type="checkbox"
                                  onChange={() =>
                                    setHabitualForm((current) => ({
                                      ...current,
                                      procedureTypeIds: toggleSelection(current.procedureTypeIds, option.id),
                                    }))
                                  }
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
                                  checked={habitualForm.procedureIds.includes(option.id)}
                                  type="checkbox"
                                  onChange={() =>
                                    setHabitualForm((current) => ({
                                      ...current,
                                      procedureIds: toggleSelection(current.procedureIds, option.id),
                                    }))
                                  }
                                />
                                <span>{option.label}</span>
                                {option.secondaryLabel ? <small>{option.secondaryLabel}</small> : null}
                              </label>
                            ))}
                          </div>
                        </article>
                      </div>

                      <div className="form-actions">
                        <button className="button" disabled={isSubmitting} type="submit">
                          {editingHabitualId ? 'Actualizar horario habitual' : 'Crear horario habitual'}
                        </button>
                        {editingHabitualId ? (
                          <button className="button button--ghost" type="button" onClick={resetHabitualForm}>
                            Cancelar edicion
                          </button>
                        ) : null}
                      </div>
                    </form>

                    <div className="availability-admin-list">
                      {specialistRules.length ? (
                        specialistRules.map((rule) => (
                          <article className="availability-admin-card" key={rule.id}>
                            <div>
                              <strong>
                                {rule.weekdayLabels.join(', ')} | {rule.timeSlotLabels.join(', ')}
                              </strong>
                              <p>
                                {rule.startDate} a {rule.endDate}
                              </p>
                              <div className="chip-list chip-list--static">
                                {rule.scope.map((item) => (
                                  <span key={`${rule.id}-${item}`} className="chip-list__item chip-list__item--static">
                                    {item}
                                  </span>
                                ))}
                              </div>
                            </div>
                            <div className="availability-admin-card__actions">
                              <button className="button button--ghost button--compact" type="button" onClick={() => loadHabitualForEdit(rule)}>
                                Editar
                              </button>
                              <button
                                className="button button--ghost button--compact"
                                type="button"
                                onClick={() => void handleDeleteHabitual(rule.id)}
                              >
                                Eliminar
                              </button>
                            </div>
                          </article>
                        ))
                      ) : (
                        <DataState
                          title="Sin horarios habituales"
                          message="Todavia no definiste el patron base de este especialista."
                        />
                      )}
                    </div>
                  </SectionCard>

                  <SectionCard
                    eyebrow="Excepciones"
                    title="Agregar o quitar dias puntuales"
                    description="Usa este bloque para cubrir imprevistos: quitar un dia, sumar otro o asignarlo a un alcance distinto solo en una fecha concreta."
                  >
                    <form className="availability-admin-form" onSubmit={(event) => void handleExceptionSubmit(event)}>
                      <div className="form-grid">
                        <label className="field">
                          <span>Especialista</span>
                          <select
                            className="input"
                            value={exceptionForm.specialistId ?? ''}
                            onChange={(event) =>
                              setExceptionForm((current) => ({
                                ...current,
                                specialistId: event.target.value ? Number(event.target.value) : null,
                              }))
                            }
                          >
                            <option value="">Selecciona un especialista</option>
                            {data.filters.specialists.map((option) => (
                              <option key={option.id} value={option.id}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="field">
                          <span>Tipo de cambio</span>
                          <select
                            className="input"
                            value={exceptionForm.type}
                            onChange={(event) =>
                              setExceptionForm((current) => ({
                                ...current,
                                type: event.target.value as 'AGREGAR' | 'BLOQUEAR',
                              }))
                            }
                          >
                            <option value="BLOQUEAR">Quitar disponibilidad puntual</option>
                            <option value="AGREGAR">Agregar disponibilidad puntual</option>
                          </select>
                        </label>
                        <label className="field field--full">
                          <span>Detalle</span>
                          <input
                            className="input"
                            type="text"
                            value={exceptionForm.detail}
                            onChange={(event) =>
                              setExceptionForm((current) => ({ ...current, detail: event.target.value }))
                            }
                            placeholder="Ej. Cambio por incapacidad o cobertura extraordinaria"
                          />
                        </label>
                      </div>

                      <article className="availability-form__panel">
                        <strong>Fechas puntuales</strong>
                        <div className="selection-row">
                          <input
                            className="input"
                            type="date"
                            value={exceptionForm.dateInput}
                            onChange={(event) =>
                              setExceptionForm((current) => ({ ...current, dateInput: event.target.value }))
                            }
                          />
                          <button className="button button--ghost button--compact" type="button" onClick={addExceptionDate}>
                            Agregar fecha
                          </button>
                        </div>
                        <div className="chip-list">
                          {exceptionForm.dates.length ? (
                            exceptionForm.dates.map((item) => (
                              <button
                                key={item}
                                className="chip-list__item"
                                type="button"
                                onClick={() =>
                                  setExceptionForm((current) => ({
                                    ...current,
                                    dates: current.dates.filter((value) => value !== item),
                                  }))
                                }
                              >
                                {item}
                              </button>
                            ))
                          ) : (
                            <span className="availability-form__empty">Todavia no agregaste fechas.</span>
                          )}
                        </div>
                      </article>

                      <article className="availability-form__panel">
                        <strong>Horarios afectados</strong>
                        <div className="choice-grid">
                          {data.filters.timeSlots
                            .filter((slot) => slot.active)
                            .map((slot) => (
                              <label className="choice-card" key={slot.id}>
                                <input
                                  checked={exceptionForm.timeSlotIds.includes(slot.id)}
                                  type="checkbox"
                                  onChange={() =>
                                    setExceptionForm((current) => ({
                                      ...current,
                                      timeSlotIds: toggleSelection(current.timeSlotIds, slot.id),
                                    }))
                                  }
                                />
                                <span>{slot.label}</span>
                              </label>
                            ))}
                        </div>
                      </article>

                      {exceptionForm.type === 'AGREGAR' ? (
                        <div className="availability-form__scope">
                          <article className="availability-form__panel">
                            <strong>Tipos de servicio</strong>
                            <div className="choice-grid">
                              {data.filters.serviceTypes.map((option) => (
                                <label className="choice-card" key={option.id}>
                                  <input
                                    checked={exceptionForm.serviceTypeIds.includes(option.id)}
                                    type="checkbox"
                                    onChange={() =>
                                      setExceptionForm((current) => ({
                                        ...current,
                                        serviceTypeIds: toggleSelection(current.serviceTypeIds, option.id),
                                      }))
                                    }
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
                                    checked={exceptionForm.procedureTypeIds.includes(option.id)}
                                    type="checkbox"
                                    onChange={() =>
                                      setExceptionForm((current) => ({
                                        ...current,
                                        procedureTypeIds: toggleSelection(current.procedureTypeIds, option.id),
                                      }))
                                    }
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
                                    checked={exceptionForm.procedureIds.includes(option.id)}
                                    type="checkbox"
                                    onChange={() =>
                                      setExceptionForm((current) => ({
                                        ...current,
                                        procedureIds: toggleSelection(current.procedureIds, option.id),
                                      }))
                                    }
                                  />
                                  <span>{option.label}</span>
                                  {option.secondaryLabel ? <small>{option.secondaryLabel}</small> : null}
                                </label>
                              ))}
                            </div>
                          </article>
                        </div>
                      ) : null}

                      <div className="form-actions">
                        <button className="button" disabled={isSubmitting} type="submit">
                          {exceptionForm.type === 'AGREGAR' ? 'Agregar dia puntual' : 'Quitar dia puntual'}
                        </button>
                        <button className="button button--ghost" type="button" onClick={resetExceptionForm}>
                          Limpiar formulario
                        </button>
                      </div>
                    </form>

                    <div className="availability-admin-list">
                      {specialistExceptions.length ? (
                        specialistExceptions.map((item) => (
                          <article className="availability-admin-card" key={item.id}>
                            <div>
                              <strong>
                                {item.dateLabel} | {item.typeLabel}
                              </strong>
                              <p>{item.timeSlotLabels.join(', ')}</p>
                              {item.scope.length ? (
                                <div className="chip-list chip-list--static">
                                  {item.scope.map((scopeItem) => (
                                    <span
                                      key={`${item.id}-${scopeItem}`}
                                      className="chip-list__item chip-list__item--static"
                                    >
                                      {scopeItem}
                                    </span>
                                  ))}
                                </div>
                              ) : null}
                              {item.detail ? <small>{item.detail}</small> : null}
                            </div>
                            <div className="availability-admin-card__actions">
                              <StatusBadge tone={item.type === 'AGREGAR' ? 'success' : 'warning'}>
                                {item.type === 'AGREGAR' ? 'Extra' : 'Bloqueado'}
                              </StatusBadge>
                              <button
                                className="button button--ghost button--compact"
                                type="button"
                                onClick={() => void handleDeleteException(item.id)}
                              >
                                Eliminar
                              </button>
                            </div>
                          </article>
                        ))
                      ) : (
                        <DataState
                          title="Sin excepciones"
                          message="Este especialista todavia no tiene cambios puntuales cargados."
                        />
                      )}
                    </div>
                  </SectionCard>
                </section>

                <SectionCard
                  eyebrow="Vista publicada"
                  title="Dias y horarios hoy visibles"
                  description="Esta lista muestra el resultado concreto que ve el cliente para este especialista, incluyendo reservas ya tomadas."
                >
                  {specialistSlots.length ? (
                    <div className="availability-slot-list">
                      {specialistSlots.map((slot) => (
                        <article className="availability-slot-card" key={slot.id}>
                          <header>
                            <div>
                              <strong>{slot.dateTime}</strong>
                              <p>{slot.timeRange}</p>
                            </div>
                            <StatusBadge tone={slotTone[slot.status]}>{slot.status}</StatusBadge>
                          </header>
                          <div className="chip-list chip-list--static">
                            {slot.coverage.length ? (
                              slot.coverage.map((item) => (
                                <span key={`${slot.id}-${item}`} className="chip-list__item chip-list__item--static">
                                  {item}
                                </span>
                              ))
                            ) : (
                              <span className="availability-form__empty">Sin alcance configurado.</span>
                            )}
                          </div>
                          <div className="availability-slot-card__meta">
                            <span>{slot.detail || 'Sin detalle adicional.'}</span>
                            {slot.patient ? (
                              <p>
                                Reservado por {slot.patient} | {slot.operation} | {slot.reservationState}
                              </p>
                            ) : (
                              <p>{slot.active ? 'Publicado para reserva' : 'Inactivo para clientes'}</p>
                            )}
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <DataState
                      title="Sin cupos concretos"
                      message="Aun no hay dias y horarios publicados para este especialista."
                    />
                  )}
                </SectionCard>
              </>
            ) : (
              <DataState
                title="Selecciona un especialista"
                message="Elige un especialista para configurar sus horarios base, sus excepciones y revisar sus cupos publicados."
              />
            )}
          </div>
        </div>
      </SectionCard>
    </div>
  )
}
