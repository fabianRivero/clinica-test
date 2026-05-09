import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'

import { AdminAvailabilityTabs } from '../../components/admin/AdminAvailabilityTabs'
import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import { useBranchContext } from '../../providers/BranchProvider'
import {
  createAdminAvailabilityException,
  createAdminHabitualSchedule,
  deleteAdminAvailabilityException,
  deleteAdminHabitualSchedule,
  getAdminAvailability,
  manageAdminGlobalAvailability,
  updateAdminHabitualSchedule,
} from '../../services/api/admin'
import type { UpsertAdminHabitualSchedulePayload } from '../../types/admin'

function buildEmptyHabitualForm(branchId: number) {
  return {
    specialistId: null as number | null,
    specialistIds: [] as number[],
    branchId: branchId,
    startDate: '',
    endDate: '',
    weekdayCodes: [] as number[],
    startTime: '',
    endTime: '',
    detail: '',
  }
}

function buildEmptyExceptionForm(branchId: number) {
  return {
    specialistIds: [] as number[],
    branchId: branchId,
    type: 'BLOQUEAR' as 'AGREGAR' | 'BLOQUEAR',
    dateInput: '',
    dates: [] as string[],
    startTime: '08:00',
    endTime: '18:00',
    detail: '',
    isWholeDay: true,
  }
}

function toggleSelection(current: number[], value: number) {
  return current.includes(value)
    ? current.filter((item) => item !== value)
    : [...current, value].sort((a, b) => a - b)
}

export function AdminAvailabilityVisiblePage() {
  // Redirigir a gestionar, ya no hay vista de slots individuales
  return <Navigate to="/admin/disponibilidad/gestionar" replace />
}

export function AdminAvailabilityBlocksPage() {
  const { data, isLoading, error, reload } = useApiResource(getAdminAvailability)
  const { showNotification } = useNotifications()
  const { activeBranch } = useBranchContext()

  const [globalForm, setGlobalForm] = useState({ date: '', detail: '' })
  const [exceptionForm, setExceptionForm] = useState(buildEmptyExceptionForm(activeBranch?.id || 1))
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Filtrar los datos por la sucursal activa
  const branchExceptions = data?.exceptions.filter((e) => e.branchId === activeBranch?.id) || []

  async function handleGlobalBlock(e: FormEvent) {
    e.preventDefault()
    if (!globalForm.date || !globalForm.detail) return
    setIsSubmitting(true)
    try {
      const res = await manageAdminGlobalAvailability({
        action: 'BLOQUEAR',
        date: globalForm.date,
        detail: globalForm.detail,
      })
      showNotification({ title: 'Exito', message: res.detail, tone: 'success' })
      setGlobalForm({ date: '', detail: '' })
      await reload()
    } catch (err: any) {
      showNotification({ title: 'Error', message: err.message, tone: 'danger' })
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleGlobalRestore(dateStr: string) {
    try {
      const res = await manageAdminGlobalAvailability({
        action: 'RESTAURAR',
        date: dateStr,
        detail: 'Restaurado por administrador',
      })
      showNotification({ title: 'Exito', message: res.detail, tone: 'success' })
      await reload()
    } catch (err: any) {
      showNotification({ title: 'Error', message: err.message, tone: 'danger' })
    }
  }

  async function handleExceptionSubmit(e: FormEvent) {
    e.preventDefault()
    if (exceptionForm.specialistIds.length === 0) {
      showNotification({ title: 'Error', message: 'Debe seleccionar al menos un especialista', tone: 'danger' })
      return
    }
    if (exceptionForm.dates.length === 0) {
      showNotification({ title: 'Error', message: 'Debe agregar al menos una fecha', tone: 'danger' })
      return
    }

    setIsSubmitting(true)
    try {
      await createAdminAvailabilityException({
        specialistIds: exceptionForm.specialistIds,
        branchId: activeBranch?.id || 1,
        type: exceptionForm.type,
        dates: exceptionForm.dates,
        startTime: exceptionForm.isWholeDay ? '' : exceptionForm.startTime,
        endTime: exceptionForm.isWholeDay ? '' : exceptionForm.endTime,
        detail: exceptionForm.detail || (exceptionForm.type === 'BLOQUEAR' ? 'Dia libre / Bloqueo' : 'Horas extra'),
      } as any)
      showNotification({ title: 'Exito', message: 'Excepcion(es) creada(s) correctamente', tone: 'success' })
      setExceptionForm(buildEmptyExceptionForm(activeBranch?.id || 1))
      await reload()
    } catch (err: any) {
      showNotification({ title: 'Error', message: err.message, tone: 'danger' })
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleDeleteException(exId: number) {
    if (!confirm('Eliminar esta excepcion?')) return
    try {
      await deleteAdminAvailabilityException(exId)
      showNotification({ title: 'Excepcion eliminada', message: 'La excepcion fue borrada exitosamente', tone: 'success' })
      await reload()
    } catch (err: any) {
      showNotification({ title: 'Error', message: err.message, tone: 'danger' })
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Excepciones y Cierres"
        title="Excepciones generales de horarios"
        description="Gestiona cierres globales de la clinica o excepciones especificas para uno o varios especialistas."
      >
        <AdminAvailabilityTabs />
      </PageHeader>

      {!activeBranch && (
        <SectionCard title="Atencion">
          <DataState title="Sucursal no seleccionada" message="Por favor seleccione una sucursal en la barra superior." tone="warning" />
        </SectionCard>
      )}

      {isLoading && !data && activeBranch ? <DataState title="Cargando configuracion..." message="" /> : null}
      {error && !data && activeBranch ? <DataState title="Error de conexion" message={error} tone="danger" /> : null}

      {data && activeBranch ? (
        <div className="dashboard-grid">
          <div className="form-stack">
            <SectionCard title="Excepciones de Especialistas" description="Añade disponibilidad o bloquea dias para multiples especialistas a la vez.">
              <form className="form-stack" onSubmit={(e) => void handleExceptionSubmit(e)}>
                <div className="form-group">
                  <label>Especialistas afectados</label>
                  <div className="checkbox-group" style={{ maxHeight: '150px', overflowY: 'auto', border: '1px solid var(--border)', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-card)' }}>
                    {data.filters.specialists.map((sp) => (
                      <label key={sp.id} className="checkbox-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem', cursor: 'pointer' }}>
                        <input
                          type="checkbox"
                          checked={exceptionForm.specialistIds.includes(sp.id)}
                          onChange={() => setExceptionForm({ ...exceptionForm, specialistIds: toggleSelection(exceptionForm.specialistIds, sp.id) })}
                        />
                        <span>{sp.label}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="form-group">
                  <label>Tipo de excepcion</label>
                  <select
                    className="input"
                    value={exceptionForm.type}
                    onChange={(e) => setExceptionForm({ ...exceptionForm, type: e.target.value as any })}
                    required
                  >
                    <option value="BLOQUEAR">Bloquear disponibilidad (Dia libre / Permiso)</option>
                    <option value="AGREGAR">Añadir disponibilidad extra</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="checkbox-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={exceptionForm.isWholeDay}
                      onChange={(e) => setExceptionForm({ ...exceptionForm, isWholeDay: e.target.checked })}
                    />
                    <span>Afecta a todo el dia (Sin restriccion de horas)</span>
                  </label>
                </div>

                {!exceptionForm.isWholeDay && (
                  <div className="form-group" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                    <div>
                      <label>Hora Inicio</label>
                      <input
                        type="time"
                        className="input"
                        value={exceptionForm.startTime}
                        onChange={(e) => setExceptionForm({ ...exceptionForm, startTime: e.target.value })}
                        required
                      />
                    </div>
                    <div>
                      <label>Hora Fin</label>
                      <input
                        type="time"
                        className="input"
                        value={exceptionForm.endTime}
                        onChange={(e) => setExceptionForm({ ...exceptionForm, endTime: e.target.value })}
                        required
                      />
                    </div>
                  </div>
                )}

                <div className="form-group">
                  <label>Añadir Fecha(s)</label>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <input
                      type="date"
                      className="input"
                      value={exceptionForm.dateInput}
                      onChange={(e) => setExceptionForm({ ...exceptionForm, dateInput: e.target.value })}
                    />
                    <button
                      type="button"
                      className="button button--ghost"
                      onClick={() => {
                        if (exceptionForm.dateInput && !exceptionForm.dates.includes(exceptionForm.dateInput)) {
                          setExceptionForm({
                            ...exceptionForm,
                            dates: [...exceptionForm.dates, exceptionForm.dateInput].sort(),
                            dateInput: '',
                          })
                        }
                      }}
                    >
                      Añadir
                    </button>
                  </div>
                </div>

                {exceptionForm.dates.length > 0 && (
                  <div className="form-group">
                    <label>Fechas seleccionadas</label>
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
                      {exceptionForm.dates.map((d) => (
                        <div key={d} className="status-badge status-badge--primary">
                          {d}
                          <button
                            type="button"
                            onClick={() => setExceptionForm({ ...exceptionForm, dates: exceptionForm.dates.filter((x) => x !== d) })}
                            style={{ background: 'none', border: 'none', marginLeft: '0.5rem', cursor: 'pointer', color: 'inherit' }}
                          >
                            x
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="form-group">
                  <label>Motivo / Detalle</label>
                  <input
                    type="text"
                    className="input"
                    value={exceptionForm.detail}
                    onChange={(e) => setExceptionForm({ ...exceptionForm, detail: e.target.value })}
                    placeholder="Ej. Congreso medico, Vacaciones, Hora extra feriado"
                  />
                </div>

                <button className="button button--primary" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Guardando...' : 'Aplicar excepcion'}
                </button>
              </form>
            </SectionCard>

            <SectionCard title="Cierre Global de Clinica" description="Bloquea dias festivos o cierres generales. Afecta a TODAS las sucursales.">
              <form className="form-stack" onSubmit={(e) => void handleGlobalBlock(e)}>
                <div className="form-group">
                  <label>Fecha a bloquear</label>
                  <input
                    type="date"
                    className="input"
                    value={globalForm.date}
                    onChange={(e) => setGlobalForm({ ...globalForm, date: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Motivo</label>
                  <textarea
                    className="input"
                    rows={2}
                    value={globalForm.detail}
                    onChange={(e) => setGlobalForm({ ...globalForm, detail: e.target.value })}
                    required
                  />
                </div>
                <button className="button button--secondary" type="submit" disabled={isSubmitting}>
                  Bloquear dia global
                </button>
              </form>
            </SectionCard>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <SectionCard title="Excepciones Activas en Sucursal">
              {branchExceptions.length ? (
                <div className="table-card">
                  <table>
                    <thead>
                      <tr>
                        <th>Especialista</th>
                        <th>Tipo</th>
                        <th>Fecha y Hora</th>
                        <th>Accion</th>
                      </tr>
                    </thead>
                    <tbody>
                      {branchExceptions.map((ex) => {
                        const spec = data.filters.specialists.find((s) => s.id === ex.specialistId)
                        return (
                          <tr key={ex.id}>
                            <td>{spec?.label || ex.specialistId}</td>
                            <td>
                              <StatusBadge tone={ex.type === 'BLOQUEAR' ? 'danger' : 'success'}>
                                {ex.typeLabel}
                              </StatusBadge>
                            </td>
                            <td>
                              {ex.dateLabel} | {ex.startTime === '00:00' && ex.endTime === '00:00' ? 'Todo el dia' : `${ex.startTime.slice(0, 5)} - ${ex.endTime.slice(0, 5)}`}
                            </td>
                            <td>
                              <button
                                className="button button--ghost button--compact"
                                style={{ color: 'var(--c-danger-600)' }}
                                onClick={() => void handleDeleteException(ex.id)}
                              >
                                Eliminar
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <DataState title="Sin excepciones activas" message="No hay bloqueos ni horas extra para especialistas." />
              )}
            </SectionCard>

            <SectionCard title="Dias de Cierre Global">
              {data.globalBlocks.length ? (
                <div className="table-card">
                  <table>
                    <thead>
                      <tr>
                        <th>Fecha</th>
                        <th>Motivo</th>
                        <th>Acciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.globalBlocks.map((block) => (
                        <tr key={block.id}>
                          <td><strong>{block.dateLabel}</strong></td>
                          <td>{block.detail}</td>
                          <td>
                            <button className="button button--ghost button--compact" onClick={() => void handleGlobalRestore(block.date)}>
                              Restaurar dia
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <DataState title="Sin cierres globales" message="La clinica opera normalmente." />
              )}
            </SectionCard>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function AdminAvailabilitySchedulesPage() {
  const { data, isLoading, error, reload } = useApiResource(getAdminAvailability)
  const { showNotification } = useNotifications()
  const { activeBranch } = useBranchContext()

  const [habitualForm, setHabitualForm] = useState(buildEmptyHabitualForm(activeBranch?.id || 1))
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [editingHabitualId, setEditingHabitualId] = useState<number | null>(null)

  // Filtrar los datos por la sucursal activa
  const branchHabitualRules = data?.habitualRules.filter((r) => r.branchId === activeBranch?.id) || []

  async function handleHabitualSubmit(e: FormEvent) {
    e.preventDefault()
    if (!editingHabitualId && habitualForm.specialistIds.length === 0) {
      showNotification({ title: 'Error', message: 'Debe seleccionar al menos un especialista', tone: 'danger' })
      return
    }
    if (editingHabitualId && !habitualForm.specialistId) {
      showNotification({ title: 'Error', message: 'Debe seleccionar un especialista', tone: 'danger' })
      return
    }
    if (habitualForm.weekdayCodes.length === 0) {
      showNotification({ title: 'Error', message: 'Debe seleccionar al menos un dia de la semana', tone: 'danger' })
      return
    }

    setIsSubmitting(true)
    try {
      const payload: UpsertAdminHabitualSchedulePayload = {
        specialistId: editingHabitualId ? habitualForm.specialistId : null,
        specialistIds: editingHabitualId ? [] : habitualForm.specialistIds,
        branchId: activeBranch?.id || 1,
        startDate: habitualForm.startDate,
        endDate: habitualForm.endDate || null,
        weekdayCodes: habitualForm.weekdayCodes,
        startTime: habitualForm.startTime,
        endTime: habitualForm.endTime,
        detail: habitualForm.detail || 'Agenda configurada manualmente',
      }

      if (editingHabitualId) {
        await updateAdminHabitualSchedule(editingHabitualId, payload)
        showNotification({ title: 'Exito', message: 'Agenda habitual actualizada correctamente', tone: 'success' })
      } else {
        await createAdminHabitualSchedule(payload)
        showNotification({ title: 'Exito', message: 'Agenda habitual creada correctamente', tone: 'success' })
      }

      setHabitualForm(buildEmptyHabitualForm(activeBranch?.id || 1))
      setEditingHabitualId(null)
      await reload()
    } catch (err: any) {
      showNotification({ title: 'Error', message: err.message, tone: 'danger' })
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleDeleteHabitual(ruleId: number) {
    if (!confirm('Eliminar esta agenda habitual? Esto NO eliminara las reservas ya agendadas.')) return
    try {
      await deleteAdminHabitualSchedule(ruleId)
      showNotification({ title: 'Agenda eliminada', message: 'La regla fue borrada exitosamente', tone: 'success' })
      await reload()
    } catch (err: any) {
      showNotification({ title: 'Error al eliminar', message: err.message, tone: 'danger' })
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Presencia en Sucursal"
        title="Gestion de Agendas Habituales"
        description="Configura los horarios recurrentes de entrada y salida de cada especialista para esta sucursal."
      >
        <AdminAvailabilityTabs />
      </PageHeader>

      {!activeBranch && (
        <SectionCard title="Atencion">
          <DataState title="Sucursal no seleccionada" message="Por favor seleccione una sucursal en la barra superior." tone="warning" />
        </SectionCard>
      )}

      {isLoading && !data && activeBranch ? <DataState title="Cargando agendas..." message="" /> : null}
      {error && !data && activeBranch ? <DataState title="Error de conexion" message={error} tone="danger" /> : null}

      {data && activeBranch ? (
        <div className="dashboard-grid">
          <SectionCard
            title={editingHabitualId ? 'Editar agenda habitual' : 'Nueva agenda habitual'}
            description="Configura un horario recurrente. El sistema cruzara este horario con las reservas para validar disponibilidad."
          >
            <form className="form-stack" onSubmit={(e) => void handleHabitualSubmit(e)}>
              <div className="form-group">
                <label>{editingHabitualId ? 'Especialista' : 'Especialista(s)'}</label>
                {editingHabitualId ? (
                  <select
                    className="input"
                    value={habitualForm.specialistId || ''}
                    onChange={(e) => setHabitualForm({ ...habitualForm, specialistId: Number(e.target.value) || null })}
                    required
                  >
                    <option value="">Seleccione un especialista...</option>
                    {data.filters.specialists.map((sp) => (
                      <option key={sp.id} value={sp.id}>
                        {sp.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <div
                    className="checkbox-group"
                    style={{
                      maxHeight: '150px',
                      overflowY: 'auto',
                      border: '1px solid var(--border)',
                      padding: '0.5rem',
                      borderRadius: '4px',
                      background: 'var(--bg-card)',
                    }}
                  >
                    {data.filters.specialists.map((sp) => (
                      <label
                        key={sp.id}
                        className="checkbox-label"
                        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem', cursor: 'pointer' }}
                      >
                        <input
                          type="checkbox"
                          checked={habitualForm.specialistIds.includes(sp.id)}
                          onChange={() =>
                            setHabitualForm({
                              ...habitualForm,
                              specialistIds: toggleSelection(habitualForm.specialistIds, sp.id),
                            })
                          }
                        />
                        <span>{sp.label}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              <div className="form-group" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <label>Fecha de inicio</label>
                  <input
                    type="date"
                    className="input"
                    value={habitualForm.startDate}
                    onChange={(e) => setHabitualForm({ ...habitualForm, startDate: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label>Fecha de fin (opcional)</label>
                  <input
                    type="date"
                    className="input"
                    value={habitualForm.endDate}
                    onChange={(e) => setHabitualForm({ ...habitualForm, endDate: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-group" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <label>Hora Inicio</label>
                  <input
                    type="time"
                    className="input"
                    value={habitualForm.startTime}
                    onChange={(e) => setHabitualForm({ ...habitualForm, startTime: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label>Hora Fin</label>
                  <input
                    type="time"
                    className="input"
                    value={habitualForm.endTime}
                    onChange={(e) => setHabitualForm({ ...habitualForm, endTime: e.target.value })}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Dias de atencion</label>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
                  {data.filters.weekdayOptions.map((w) => (
                    <label key={w.value} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', background: 'var(--c-neutral-100)', padding: '0.25rem 0.5rem', borderRadius: '4px' }}>
                      <input
                        type="checkbox"
                        checked={habitualForm.weekdayCodes.includes(w.value)}
                        onChange={() =>
                          setHabitualForm({ ...habitualForm, weekdayCodes: toggleSelection(habitualForm.weekdayCodes, w.value) })
                        }
                      />
                      <span style={{ fontSize: '0.875rem' }}>{w.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="form-group">
                <label>Detalle interno</label>
                <input
                  type="text"
                  className="input"
                  value={habitualForm.detail}
                  onChange={(e) => setHabitualForm({ ...habitualForm, detail: e.target.value })}
                  placeholder="Ej. Turno mañana cardiologia"
                />
              </div>

              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button type="submit" className="button button--primary" disabled={isSubmitting}>
                  {isSubmitting ? 'Guardando...' : 'Guardar agenda'}
                </button>
                {editingHabitualId && (
                  <button
                    type="button"
                    className="button button--ghost"
                    onClick={() => {
                      setEditingHabitualId(null)
                      setHabitualForm(buildEmptyHabitualForm(activeBranch?.id || 1))
                    }}
                  >
                    Cancelar
                  </button>
                )}
              </div>
            </form>
          </SectionCard>

          <SectionCard title={`Agendas Habituales - ${activeBranch.nombre}`}>
            {branchHabitualRules.length > 0 ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Especialista</th>
                      <th>Periodo</th>
                      <th>Dias</th>
                      <th>Horario</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {branchHabitualRules.map((rule) => {
                      const spec = data.filters.specialists.find((s) => s.id === rule.specialistId)
                      return (
                        <tr key={rule.id}>
                          <td>
                            <strong>{spec?.label || 'Especialista ' + rule.specialistId}</strong>
                          </td>
                          <td>
                            {rule.startDate} al {rule.endDate || 'Siempre'}
                          </td>
                          <td>
                            <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                              {rule.weekdayLabels.map((lbl) => (
                                <StatusBadge key={lbl} tone="neutral">
                                  {lbl.slice(0, 3)}
                                </StatusBadge>
                              ))}
                            </div>
                          </td>
                          <td>
                            {rule.startTime.slice(0, 5)} - {rule.endTime.slice(0, 5)}
                          </td>
                          <td>
                            <button
                              type="button"
                              className="button button--ghost button--compact"
                              onClick={() => {
                                setEditingHabitualId(rule.id)
                                setHabitualForm({
                                  specialistId: rule.specialistId,
                                  specialistIds: [rule.specialistId],
                                  branchId: activeBranch.id,
                                  startDate: rule.startDate,
                                  endDate: rule.endDate || '',
                                  weekdayCodes: rule.weekdayCodes,
                                  startTime: rule.startTime.slice(0, 5),
                                  endTime: rule.endTime.slice(0, 5),
                                  detail: rule.detail,
                                })
                              }}
                            >
                              Editar
                            </button>
                            <button
                              type="button"
                              className="button button--ghost button--compact"
                              style={{ color: 'var(--c-danger-600)' }}
                              onClick={() => void handleDeleteHabitual(rule.id)}
                            >
                              Eliminar
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <DataState title="Sin agendas habituales" message="No se han configurado horarios recurrentes en esta sucursal." />
            )}
          </SectionCard>
        </div>
      ) : null}
    </div>
  )
}
