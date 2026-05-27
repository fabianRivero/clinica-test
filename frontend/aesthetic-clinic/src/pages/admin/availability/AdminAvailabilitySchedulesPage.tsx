import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { AdminAvailabilityTabs } from '../../../components/admin/AdminAvailabilityTabs'
import { DataState } from '../../../components/admin/DataState'
import { PageHeader } from '../../../components/admin/PageHeader'
import { SectionCard } from '../../../components/admin/SectionCard'
import { StatusBadge } from '../../../components/admin/StatusBadge'
import { useApiResource } from '../../../hooks/useApiResource'
import { useNotifications } from '../../../providers/NotificationProvider'
import { useBranchContext } from '../../../providers/BranchProvider'
import {
  createAdminHabitualSchedule,
  deleteAdminHabitualSchedule,
  getAdminAvailability,
  updateAdminHabitualSchedule,
} from '../../../services/api/admin'
import type { UpsertAdminHabitualSchedulePayload } from '../../../types/admin'
import { buildEmptyHabitualForm } from './availabilityHelpers'
import { HabitualScheduleForm } from './HabitualScheduleForm'

export function AdminAvailabilitySchedulesPage() {
  const { showNotification } = useNotifications()
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  const loader = useCallback(() => getAdminAvailability(branchId), [branchId])
  const { data, isLoading, error, reload } = useApiResource(loader)

  const [habitualForm, setHabitualForm] = useState(buildEmptyHabitualForm(activeBranch?.id || 1))
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [editingHabitualId, setEditingHabitualId] = useState<number | null>(null)

  // Filtrar los datos por la sucursal activa
  const branchHabitualRules = data?.habitualRules.filter((r) => r.branchId === activeBranch?.id) || []

  useEffect(() => {
    setHabitualForm(buildEmptyHabitualForm(activeBranch?.id || 1))
    setEditingHabitualId(null)
  }, [activeBranch?.id])

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
          <HabitualScheduleForm
            habitualForm={habitualForm}
            setHabitualForm={setHabitualForm}
            editingHabitualId={editingHabitualId}
            setEditingHabitualId={setEditingHabitualId}
            specialists={data.filters.specialists}
            weekdayOptions={data.filters.weekdayOptions}
            activeBranch={activeBranch}
            isSubmitting={isSubmitting}
            onSubmit={handleHabitualSubmit}
          />

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