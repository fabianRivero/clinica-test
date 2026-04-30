import { useMemo, useState, type FormEvent, type ReactNode } from 'react'

import { AdminAvailabilityTabs } from '../../components/admin/AdminAvailabilityTabs'
import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import {
  cancelAdminAppointment,
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
  AdminMetric,
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

function normalizeSearchValue(value: string) {
  return value.trim().toLowerCase()
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
      }
    }

    return {
      specialistRules: data.habitualRules.filter((item) => item.specialistId === selectedSpecialistId),
      specialistExceptions: data.exceptions.filter((item) => item.specialistId === selectedSpecialistId),
    }
  }, [data, selectedSpecialistId])
}

function useAdminAvailabilityController() {
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
  const [slotSearchTerm, setSlotSearchTerm] = useState('')
  const [activeCoverageFilter, setActiveCoverageFilter] = useState('TODOS')
  const [activeStatusFilter, setActiveStatusFilter] = useState('TODOS')
  const [visibleSlotsState, setVisibleSlotsState] = useState({ key: '', limit: 10 })
  const loader = useMemo(() => {
    const requestVersion = refreshKey
    return () => {
      void requestVersion
      return getAdminAvailability()
    }
  }, [refreshKey])
  const { data, isLoading, error } = useApiResource(loader)
  const { showNotification } = useNotifications()

  const resolvedSelectedSpecialistId = useMemo(() => {
    if (!data?.specialistSummaries.length) {
      return null
    }
    if (
      selectedSpecialistId &&
      data.specialistSummaries.some((item) => item.id === selectedSpecialistId)
    ) {
      return selectedSpecialistId
    }
    return data.specialistSummaries[0]?.id ?? null
  }, [data, selectedSpecialistId])

  const { specialistRules, specialistExceptions } = useSpecialistScopedLists(data, resolvedSelectedSpecialistId)
  const selectedSpecialist = useMemo(
    () => data?.specialistSummaries.find((item) => item.id === resolvedSelectedSpecialistId) ?? null,
    [data, resolvedSelectedSpecialistId],
  )
  const habitualSpecialistId = useMemo(() => {
    if (!data?.specialistSummaries.length) {
      return null
    }
    if (
      habitualForm.specialistId &&
      data.specialistSummaries.some((item) => item.id === habitualForm.specialistId)
    ) {
      return habitualForm.specialistId
    }
    return resolvedSelectedSpecialistId
  }, [data, habitualForm.specialistId, resolvedSelectedSpecialistId])
  const exceptionSpecialistId = useMemo(() => {
    if (!data?.specialistSummaries.length) {
      return null
    }
    if (
      exceptionForm.specialistId &&
      data.specialistSummaries.some((item) => item.id === exceptionForm.specialistId)
    ) {
      return exceptionForm.specialistId
    }
    return resolvedSelectedSpecialistId
  }, [data, exceptionForm.specialistId, resolvedSelectedSpecialistId])
  const coverageOptions = useMemo(() => {
    if (!data) {
      return []
    }

    return Array.from(
      new Set(
        data.slots
          .flatMap((slot) => slot.coverage)
          .map((item) => item.trim())
          .filter(Boolean),
      ),
    ).sort((left, right) => left.localeCompare(right))
  }, [data])
  const statusOptions = useMemo(() => {
    if (!data) {
      return []
    }

    return Array.from(new Set(data.slots.map((slot) => slot.status))).sort((left, right) =>
      left.localeCompare(right),
    )
  }, [data])
  const resolvedCoverageFilter =
    activeCoverageFilter !== 'TODOS' && !coverageOptions.includes(activeCoverageFilter)
      ? 'TODOS'
      : activeCoverageFilter
  const resolvedStatusFilter =
    activeStatusFilter !== 'TODOS' &&
    !statusOptions.includes(activeStatusFilter as AdminAvailabilitySlot['status'])
      ? 'TODOS'
      : activeStatusFilter
  const visibleSlotsFilterKey = `${slotSearchTerm}::${resolvedCoverageFilter}::${resolvedStatusFilter}`
  const visibleSlotsLimit =
    visibleSlotsState.key === visibleSlotsFilterKey ? visibleSlotsState.limit : 10
  const filteredVisibleSlots = useMemo(() => {
    if (!data) {
      return []
    }

    const normalizedSearch = normalizeSearchValue(slotSearchTerm)

    return data.slots.filter((slot) => {
      const matchesCoverage =
        resolvedCoverageFilter === 'TODOS' || slot.coverage.includes(resolvedCoverageFilter)
      const matchesStatus = resolvedStatusFilter === 'TODOS' || slot.status === resolvedStatusFilter
      const haystack = normalizeSearchValue(
        [
          slot.dateTime,
          slot.date,
          slot.timeRange,
          slot.specialist,
          slot.detail,
          slot.patient,
          slot.operation,
          ...slot.coverage,
        ].join(' '),
      )
      const matchesSearch = !normalizedSearch || haystack.includes(normalizedSearch)

      return matchesCoverage && matchesStatus && matchesSearch
    })
  }, [data, resolvedCoverageFilter, resolvedStatusFilter, slotSearchTerm])
  const paginatedVisibleSlots = useMemo(
    () => filteredVisibleSlots.slice(0, visibleSlotsLimit),
    [filteredVisibleSlots, visibleSlotsLimit],
  )

  function refreshAvailability() {
    setRefreshKey((current) => current + 1)
  }

  function handleSelectSpecialist(nextSpecialistId: number | null) {
    setSelectedSpecialistId(nextSpecialistId)
    setHabitualForm((current) => ({ ...current, specialistId: nextSpecialistId }))
    setExceptionForm((current) => ({ ...current, specialistId: nextSpecialistId }))
  }

  function handleVisibleSlotsLimitChange(nextValue: number | ((current: number) => number)) {
    setVisibleSlotsState((current) => {
      const currentLimit = current.key === visibleSlotsFilterKey ? current.limit : 10
      return {
        key: visibleSlotsFilterKey,
        limit: typeof nextValue === 'function' ? nextValue(currentLimit) : nextValue,
      }
    })
  }

  function resetTimeSlotForm() {
    setEditingTimeSlotId(null)
    setTimeSlotForm(buildEmptyTimeSlotForm())
  }

  function resetHabitualForm() {
    setEditingHabitualId(null)
    setHabitualForm({
      ...buildEmptyHabitualForm(),
      specialistId: resolvedSelectedSpecialistId,
    })
  }

  function resetExceptionForm() {
    setExceptionForm({
      ...buildEmptyExceptionForm(),
      specialistId: resolvedSelectedSpecialistId,
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
    handleSelectSpecialist(rule.specialistId)
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
      refreshAvailability()
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
      refreshAvailability()
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
        ? await updateAdminHabitualSchedule(editingHabitualId, {
            ...habitualForm,
            specialistId: habitualSpecialistId,
          })
        : await createAdminHabitualSchedule({
            ...habitualForm,
            specialistId: habitualSpecialistId,
          })
      showNotification({
        title: editingHabitualId ? 'Horario habitual actualizado' : 'Horario habitual creado',
        message: response.detail,
        tone: 'success',
      })
      resetHabitualForm()
      refreshAvailability()
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
      refreshAvailability()
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
        specialistId: exceptionSpecialistId,
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
      refreshAvailability()
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
      refreshAvailability()
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
      refreshAvailability()
    } catch (requestError) {
      setSubmitError(
        requestError instanceof Error ? requestError.message : 'No se pudo aplicar el cambio global.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleCancelReservedAppointment(appointmentId: number) {
    const shouldCancel = window.confirm(
      'Se cancelara la cita programada y el cupo volvera a quedar disponible para nuevas reservas. ¿Deseas continuar?',
    )
    if (!shouldCancel) {
      return
    }

    setSubmitError(null)
    setIsSubmitting(true)
    try {
      const response = await cancelAdminAppointment(appointmentId)
      showNotification({
        title: 'Cita cancelada',
        message: response.detail,
        tone: 'success',
      })
      refreshAvailability()
    } catch (requestError) {
      setSubmitError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo cancelar la cita programada.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return {
    data,
    error,
    isLoading,
    submitError,
    isSubmitting,
    selectedSpecialistId: resolvedSelectedSpecialistId,
    selectedSpecialist,
    specialistRules,
    specialistExceptions,
    timeSlotForm,
    habitualForm,
    exceptionForm,
    globalDate,
    globalDetail,
    editingTimeSlotId,
    editingHabitualId,
    slotSearchTerm,
    activeCoverageFilter: resolvedCoverageFilter,
    activeStatusFilter: resolvedStatusFilter,
    coverageOptions,
    statusOptions,
    filteredVisibleSlots,
    paginatedVisibleSlots,
    setSelectedSpecialistId: handleSelectSpecialist,
    setTimeSlotForm,
    setHabitualForm,
    setExceptionForm,
    setGlobalDate,
    setGlobalDetail,
    setSlotSearchTerm,
    setActiveCoverageFilter,
    setActiveStatusFilter,
    setVisibleSlotsLimit: handleVisibleSlotsLimitChange,
    habitualSpecialistId,
    exceptionSpecialistId,
    refreshAvailability,
    resetTimeSlotForm,
    resetHabitualForm,
    resetExceptionForm,
    addExceptionDate,
    loadTimeSlotForEdit,
    loadHabitualForEdit,
    handleTimeSlotSubmit,
    handleDeleteTimeSlot,
    handleHabitualSubmit,
    handleDeleteHabitual,
    handleExceptionSubmit,
    handleDeleteException,
    handleGlobalAction,
    handleCancelReservedAppointment,
  }
}

type AvailabilityController = ReturnType<typeof useAdminAvailabilityController>

function AvailabilityPageShell({
  eyebrow,
  title,
  description,
  controller,
  metrics,
  children,
}: {
  eyebrow: string
  title: string
  description: string
  controller: AvailabilityController
  metrics?: AdminMetric[]
  children: ReactNode
}) {
  if (controller.isLoading && !controller.data) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="Agenda configurable" title={title} description="Cargando configuracion de agenda." />
        <SectionCard title="Cargando agenda">
          <DataState
            title="Sincronizando agenda"
            message="Estamos preparando horarios base, agendas habituales y excepciones puntuales."
          />
        </SectionCard>
      </div>
    )
  }

  if (controller.error || !controller.data) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="Agenda configurable" title={title} description="No pudimos cargar la configuracion de agenda." />
        <SectionCard title="Agenda no disponible">
          <DataState
            title="Conexion no disponible"
            message={controller.error || 'No se pudo cargar la agenda.'}
            tone="danger"
          />
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={eyebrow}
        title={title}
        description={description}
        actions={[
          {
            label: 'Actualizar vista',
            variant: 'ghost',
            onClick: controller.refreshAvailability,
          },
        ]}
      />

      <AdminAvailabilityTabs />

      {controller.submitError ? (
        <DataState title="No pudimos completar el cambio" message={controller.submitError} tone="danger" />
      ) : null}

      <section className="metrics-grid metrics-grid--compact">
        {(metrics ?? controller.data.metrics).map((metric) => (
          <MetricCard key={metric.id} metric={metric} />
        ))}
      </section>

      {children}
    </div>
  )
}

function VisibleAvailabilitySection({ controller }: { controller: AvailabilityController }) {
  return (
    <SectionCard
      eyebrow="Vista publicada"
      title="Dias y horarios visibles"
      description="Esta lista muestra la agenda concreta que hoy esta disponible o publicada para reservas. Puedes explorarla por fecha y por servicio."
    >
      <div className="availability-visible-toolbar">
        <label className="field availability-visible-toolbar__search">
          <span>Buscar por fecha o servicio</span>
          <input
            className="input"
            type="search"
            value={controller.slotSearchTerm}
            onChange={(event) => controller.setSlotSearchTerm(event.target.value)}
            placeholder="Ej. 2026-05-12, Consulta, Laser"
          />
        </label>

        <div className="availability-visible-toolbar__filters">
          <span className="availability-visible-toolbar__label">Filtrar por servicio</span>
          <div className="filter-chip-row">
            <button
              className={`filter-chip ${controller.activeCoverageFilter === 'TODOS' ? 'is-active' : ''}`}
              type="button"
              onClick={() => controller.setActiveCoverageFilter('TODOS')}
            >
              Todos
            </button>
            {controller.coverageOptions.map((coverage) => (
              <button
                key={coverage}
                className={`filter-chip ${controller.activeCoverageFilter === coverage ? 'is-active' : ''}`}
                type="button"
                onClick={() => controller.setActiveCoverageFilter(coverage)}
              >
                {coverage}
              </button>
              ))}
          </div>
        </div>

        <div className="availability-visible-toolbar__filters">
          <span className="availability-visible-toolbar__label">Filtrar por estado</span>
          <div className="filter-chip-row">
            <button
              className={`filter-chip ${controller.activeStatusFilter === 'TODOS' ? 'is-active' : ''}`}
              type="button"
              onClick={() => controller.setActiveStatusFilter('TODOS')}
            >
              Todos
            </button>
            {controller.statusOptions.map((status) => (
              <button
                key={status}
                className={`filter-chip ${controller.activeStatusFilter === status ? 'is-active' : ''}`}
                type="button"
                onClick={() => controller.setActiveStatusFilter(status)}
              >
                {status}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="availability-visible-summary">
        <strong>
          Mostrando {controller.paginatedVisibleSlots.length} de {controller.filteredVisibleSlots.length} horario(s)
        </strong>
        <span>
          {controller.activeCoverageFilter === 'TODOS'
            ? 'Sin filtro de servicio activo.'
            : `Servicio filtrado: ${controller.activeCoverageFilter}`}
        </span>
        <span>
          {controller.activeStatusFilter === 'TODOS'
            ? 'Sin filtro de estado activo.'
            : `Estado filtrado: ${controller.activeStatusFilter}`}
        </span>
      </div>

      {controller.paginatedVisibleSlots.length ? (
        <>
          <div className="availability-slot-list">
            {controller.paginatedVisibleSlots.map((slot) => (
              <VisibleSlotCard
                key={slot.id}
                slot={slot}
                onCancelAppointment={controller.handleCancelReservedAppointment}
              />
            ))}
          </div>

          {controller.filteredVisibleSlots.length > controller.paginatedVisibleSlots.length ? (
            <div className="form-actions form-actions--start">
              <button
                className="button button--ghost"
                type="button"
                onClick={() => controller.setVisibleSlotsLimit(controller.paginatedVisibleSlots.length + 10)}
              >
                Ver 10 mas
              </button>
            </div>
          ) : null}
        </>
      ) : (
        <DataState
          title="Sin horarios visibles"
          message="No encontramos cupos publicados con los filtros actuales."
        />
      )}
    </SectionCard>
  )
}

function VisibleSlotCard({
  slot,
  onCancelAppointment,
}: {
  slot: AdminAvailabilitySlot
  onCancelAppointment: (appointmentId: number) => Promise<void>
}) {
  return (
    <article className="availability-slot-card">
      <header>
        <div>
          <strong>{slot.dateTime}</strong>
          <p>{slot.timeRange}</p>
        </div>
        <StatusBadge tone={slotTone[slot.status]}>{slot.status}</StatusBadge>
      </header>
      <div className="availability-slot-card__meta">
        <span>Especialista: {slot.specialist}</span>
        <p>{slot.detail || 'Sin detalle adicional.'}</p>
        {slot.patient ? (
          <p>
            Reservado por {slot.patient} | {slot.operation} | {slot.reservationState}
          </p>
        ) : (
          <p>{slot.active ? 'Publicado para reserva' : 'Inactivo para clientes'}</p>
        )}
      </div>
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
      {slot.appointmentCanCancel && slot.appointmentId ? (
        <div className="catalog-admin-card__actions">
          <button
            className="button button--ghost button--compact"
            type="button"
            onClick={() => void onCancelAppointment(slot.appointmentId as number)}
          >
            Cancelar cita
          </button>
        </div>
      ) : null}
    </article>
  )
}

function BlocksAvailabilitySection({ controller }: { controller: AvailabilityController }) {
  const { data } = controller
  if (!data) return null

  return (
    <div className="availability-workspace-grid">
      <SectionCard
        eyebrow="Bloques de horario"
        title={controller.editingTimeSlotId ? 'Editar bloque de horario' : 'Crear bloque de horario'}
        description="Estos rangos horarios se aplican a todos los dias y luego se asignan a los especialistas en sus horarios habituales."
      >
        <form className="availability-admin-form" onSubmit={(event) => void controller.handleTimeSlotSubmit(event)}>
          <div className="form-grid">
            <label className="field">
              <span>Hora inicio</span>
              <input
                className="input"
                type="time"
                value={controller.timeSlotForm.startTime}
                onChange={(event) =>
                  controller.setTimeSlotForm((current) => ({ ...current, startTime: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>Hora fin</span>
              <input
                className="input"
                type="time"
                value={controller.timeSlotForm.endTime}
                onChange={(event) =>
                  controller.setTimeSlotForm((current) => ({ ...current, endTime: event.target.value }))
                }
              />
            </label>
            <label className="field field--full">
              <span>Detalle opcional</span>
              <input
                className="input"
                type="text"
                value={controller.timeSlotForm.detail}
                onChange={(event) =>
                  controller.setTimeSlotForm((current) => ({ ...current, detail: event.target.value }))
                }
                placeholder="Ej. Bloque matutino principal"
              />
            </label>
          </div>

          {controller.editingTimeSlotId ? (
            <label className="field field--inline">
              <input
                checked={controller.timeSlotForm.active}
                type="checkbox"
                onChange={(event) =>
                  controller.setTimeSlotForm((current) => ({ ...current, active: event.target.checked }))
                }
              />
              <span>Bloque activo</span>
            </label>
          ) : null}

          <div className="form-actions">
            <button className="button" disabled={controller.isSubmitting} type="submit">
              {controller.editingTimeSlotId ? 'Actualizar bloque' : 'Crear bloque'}
            </button>
            {controller.editingTimeSlotId ? (
              <button className="button button--ghost" type="button" onClick={controller.resetTimeSlotForm}>
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
                <button className="button button--ghost button--compact" type="button" onClick={() => controller.loadTimeSlotForEdit(slot.id)}>
                  Editar
                </button>
                <button
                  className="button button--ghost button--compact"
                  type="button"
                  onClick={() => void controller.handleDeleteTimeSlot(slot.id)}
                >
                  Eliminar
                </button>
              </div>
            </article>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        eyebrow="Dias globales"
        title="Restaurar dia activo o dia libre"
        description="Bloquea una fecha completa para todos los especialistas o restaurala para que vuelvan sus horarios habituales."
      >
        <form
          className="availability-admin-form"
          onSubmit={(event) => {
            event.preventDefault()
            void controller.handleGlobalAction('BLOQUEAR')
          }}
        >
          <div className="form-grid">
            <label className="field">
              <span>Fecha</span>
              <input
                className="input"
                type="date"
                value={controller.globalDate}
                onChange={(event) => controller.setGlobalDate(event.target.value)}
              />
            </label>
            <label className="field field--full">
              <span>Motivo o nota</span>
              <input
                className="input"
                type="text"
                value={controller.globalDetail}
                onChange={(event) => controller.setGlobalDetail(event.target.value)}
                placeholder="Ej. Feriado clinico o mantenimiento general"
              />
            </label>
          </div>
          <div className="form-actions">
            <button className="button" disabled={controller.isSubmitting} type="submit">
              Marcar dia libre para todos
            </button>
            <button
              className="button button--ghost"
              disabled={controller.isSubmitting}
              type="button"
              onClick={() => void controller.handleGlobalAction('RESTAURAR')}
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
                        controller.setGlobalDate(item.date)
                        controller.setGlobalDetail(item.detail)
                        void controller.handleGlobalAction('RESTAURAR', {
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
    </div>
  )
}

function SchedulesAvailabilitySection({ controller }: { controller: AvailabilityController }) {
  const { data } = controller
  if (!data) return null

  return (
    <SectionCard
      eyebrow="Especialistas"
      title="Gestionar horarios"
      description="Selecciona un especialista para asignarle sus horarios habituales y sus excepciones puntuales."
    >
      <div className="specialist-agenda">
        <aside className="specialist-agenda__sidebar">
          {data.specialistSummaries.map((item) => (
            <button
              key={item.id}
              className={`specialist-agenda__summary ${controller.selectedSpecialistId === item.id ? 'is-active' : ''}`}
              type="button"
              onClick={() => controller.setSelectedSpecialistId(item.id)}
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
          {controller.selectedSpecialist ? (
            <>
              <div className="specialist-agenda__hero">
                <div>
                  <span className="specialist-agenda__eyebrow">Especialista seleccionado</span>
                  <h3>{controller.selectedSpecialist.label}</h3>
                  <p>{controller.selectedSpecialist.secondaryLabel}</p>
                </div>
                <div className="specialist-agenda__hero-metrics">
                  <article>
                    <span>Proximo cupo</span>
                    <strong>{controller.selectedSpecialist.nextSlot}</strong>
                  </article>
                  <article>
                    <span>Reglas habituales</span>
                    <strong>{controller.selectedSpecialist.habitualRules}</strong>
                  </article>
                  <article>
                    <span>Excepciones</span>
                    <strong>{controller.selectedSpecialist.exceptions}</strong>
                  </article>
                </div>
              </div>

              <section className="dashboard-grid">
                <SectionCard
                  eyebrow="Horario habitual"
                  title={controller.editingHabitualId ? 'Editar regla habitual' : 'Asignar horario habitual'}
                  description="Este es el patron base del especialista. Luego puedes quitar dias o agregar otros con excepciones puntuales."
                >
                  <form className="availability-admin-form" onSubmit={(event) => void controller.handleHabitualSubmit(event)}>
                    <div className="form-grid">
                      <label className="field">
                        <span>Especialista</span>
                        <select
                          className="input"
                          value={controller.habitualSpecialistId ?? ''}
                          onChange={(event) =>
                            controller.setHabitualForm((current) => ({
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
                          value={controller.habitualForm.startDate}
                          onChange={(event) =>
                            controller.setHabitualForm((current) => ({ ...current, startDate: event.target.value }))
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Hasta</span>
                        <input
                          className="input"
                          type="date"
                          value={controller.habitualForm.endDate}
                          onChange={(event) =>
                            controller.setHabitualForm((current) => ({ ...current, endDate: event.target.value }))
                          }
                        />
                      </label>
                      <label className="field field--full">
                        <span>Detalle</span>
                        <input
                          className="input"
                          type="text"
                          value={controller.habitualForm.detail}
                          onChange={(event) =>
                            controller.setHabitualForm((current) => ({ ...current, detail: event.target.value }))
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
                              checked={controller.habitualForm.weekdayCodes.includes(option.value)}
                              type="checkbox"
                              onChange={() =>
                                controller.setHabitualForm((current) => ({
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
                      <strong>Bloques de horario</strong>
                      <div className="choice-grid">
                        {data.filters.timeSlots
                          .filter((slot) => slot.active)
                          .map((slot) => (
                            <label className="choice-card" key={slot.id}>
                              <input
                                checked={controller.habitualForm.timeSlotIds.includes(slot.id)}
                                type="checkbox"
                                onChange={() =>
                                  controller.setHabitualForm((current) => ({
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
                                checked={controller.habitualForm.serviceTypeIds.includes(option.id)}
                                type="checkbox"
                                onChange={() =>
                                  controller.setHabitualForm((current) => ({
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
                                checked={controller.habitualForm.procedureTypeIds.includes(option.id)}
                                type="checkbox"
                                onChange={() =>
                                  controller.setHabitualForm((current) => ({
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
                                checked={controller.habitualForm.procedureIds.includes(option.id)}
                                type="checkbox"
                                onChange={() =>
                                  controller.setHabitualForm((current) => ({
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
                      <button className="button" disabled={controller.isSubmitting} type="submit">
                        {controller.editingHabitualId ? 'Actualizar horario habitual' : 'Crear horario habitual'}
                      </button>
                      {controller.editingHabitualId ? (
                        <button className="button button--ghost" type="button" onClick={controller.resetHabitualForm}>
                          Cancelar edicion
                        </button>
                      ) : null}
                    </div>
                  </form>

                  <div className="availability-admin-list">
                    {controller.specialistRules.length ? (
                      controller.specialistRules.map((rule) => (
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
                            <button
                              className="button button--ghost button--compact"
                              type="button"
                              onClick={() => controller.loadHabitualForEdit(rule)}
                            >
                              Editar
                            </button>
                            <button
                              className="button button--ghost button--compact"
                              type="button"
                              onClick={() => void controller.handleDeleteHabitual(rule.id)}
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
                  <form className="availability-admin-form" onSubmit={(event) => void controller.handleExceptionSubmit(event)}>
                    <div className="form-grid">
                      <label className="field">
                        <span>Especialista</span>
                        <select
                          className="input"
                          value={controller.exceptionSpecialistId ?? ''}
                          onChange={(event) =>
                            controller.setExceptionForm((current) => ({
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
                          value={controller.exceptionForm.type}
                          onChange={(event) =>
                            controller.setExceptionForm((current) => ({
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
                          value={controller.exceptionForm.detail}
                          onChange={(event) =>
                            controller.setExceptionForm((current) => ({ ...current, detail: event.target.value }))
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
                          value={controller.exceptionForm.dateInput}
                          onChange={(event) =>
                            controller.setExceptionForm((current) => ({ ...current, dateInput: event.target.value }))
                          }
                        />
                        <button className="button button--ghost button--compact" type="button" onClick={controller.addExceptionDate}>
                          Agregar fecha
                        </button>
                      </div>
                      <div className="chip-list">
                        {controller.exceptionForm.dates.length ? (
                          controller.exceptionForm.dates.map((item) => (
                            <button
                              key={item}
                              className="chip-list__item"
                              type="button"
                              onClick={() =>
                                controller.setExceptionForm((current) => ({
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
                                checked={controller.exceptionForm.timeSlotIds.includes(slot.id)}
                                type="checkbox"
                                onChange={() =>
                                  controller.setExceptionForm((current) => ({
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

                    {controller.exceptionForm.type === 'AGREGAR' ? (
                      <div className="availability-form__scope">
                        <article className="availability-form__panel">
                          <strong>Tipos de servicio</strong>
                          <div className="choice-grid">
                            {data.filters.serviceTypes.map((option) => (
                              <label className="choice-card" key={option.id}>
                                <input
                                  checked={controller.exceptionForm.serviceTypeIds.includes(option.id)}
                                  type="checkbox"
                                  onChange={() =>
                                    controller.setExceptionForm((current) => ({
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
                                  checked={controller.exceptionForm.procedureTypeIds.includes(option.id)}
                                  type="checkbox"
                                  onChange={() =>
                                    controller.setExceptionForm((current) => ({
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
                                  checked={controller.exceptionForm.procedureIds.includes(option.id)}
                                  type="checkbox"
                                  onChange={() =>
                                    controller.setExceptionForm((current) => ({
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
                      <button className="button" disabled={controller.isSubmitting} type="submit">
                        {controller.exceptionForm.type === 'AGREGAR' ? 'Agregar dia puntual' : 'Quitar dia puntual'}
                      </button>
                      <button className="button button--ghost" type="button" onClick={controller.resetExceptionForm}>
                        Limpiar formulario
                      </button>
                    </div>
                  </form>

                  <div className="availability-admin-list">
                    {controller.specialistExceptions.length ? (
                      controller.specialistExceptions.map((item) => (
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
                              onClick={() => void controller.handleDeleteException(item.id)}
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
            </>
          ) : (
            <DataState
              title="Selecciona un especialista"
              message="Elige un especialista para darle sus horarios habituales y gestionar sus cambios puntuales."
            />
          )}
        </div>
      </div>
    </SectionCard>
  )
}

function useCurrentMonthAvailabilityMetrics(controller: AvailabilityController) {
  return useMemo(() => {
    if (!controller.data) {
      return []
    }

    const now = new Date()
    const currentMonthPublishedSlots = controller.data.slots.filter((slot) => {
      if (!slot.active) {
        return false
      }

      const slotDate = new Date(`${slot.date}T00:00:00`)
      return (
        slotDate.getFullYear() === now.getFullYear() &&
        slotDate.getMonth() === now.getMonth()
      )
    })

    return controller.data.metrics.map((metric) =>
      metric.id === 'availability-open'
        ? {
            ...metric,
            value: String(currentMonthPublishedSlots.length),
            delta: 'Cupos activos del mes actual',
          }
        : metric,
    )
  }, [controller.data])
}

export function AdminAvailabilityVisiblePage() {
  const controller = useAdminAvailabilityController()
  const currentMonthMetrics = useCurrentMonthAvailabilityMetrics(controller)

  return (
    <AvailabilityPageShell
      eyebrow="Agenda publicada"
      title="Dias y horarios visibles"
      description="Revisa la agenda concreta que hoy esta visible para clientes, con buscador por fecha y filtros por servicio."
      controller={controller}
      metrics={currentMonthMetrics}
    >
      <VisibleAvailabilitySection controller={controller} />
    </AvailabilityPageShell>
  )
}

export function AdminAvailabilityBlocksPage() {
  const controller = useAdminAvailabilityController()
  const currentMonthMetrics = useCurrentMonthAvailabilityMetrics(controller)

  return (
    <AvailabilityPageShell
      eyebrow="Bloques y dias globales"
      title="Bloques de horarios"
      description="Crea, edita y borra bloques de horario, y controla fechas globales como dias libres o dias restaurados."
      controller={controller}
      metrics={currentMonthMetrics}
    >
      <BlocksAvailabilitySection controller={controller} />
    </AvailabilityPageShell>
  )
}

export function AdminAvailabilitySchedulesPage() {
  const controller = useAdminAvailabilityController()
  const currentMonthMetrics = useCurrentMonthAvailabilityMetrics(controller)

  return (
    <AvailabilityPageShell
      eyebrow="Horarios por especialista"
      title="Gestionar horarios"
      description="Asigna horarios habituales a especialistas y aplica excepciones puntuales cuando haga falta."
      controller={controller}
      metrics={currentMonthMetrics}
    >
      <SchedulesAvailabilitySection controller={controller} />
    </AvailabilityPageShell>
  )
}
