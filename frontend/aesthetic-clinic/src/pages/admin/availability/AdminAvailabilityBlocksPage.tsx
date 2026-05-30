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
  createAdminAvailabilityException,
  deleteAdminAvailabilityException,
  getAdminAvailability,
  manageAdminGlobalAvailability,
} from '../../../services/api/admin'
import { buildEmptyExceptionForm } from './availabilityHelpers'
import { ExceptionForm } from './ExceptionForm'

const PAGE_SIZE = 10

export function AdminAvailabilityBlocksPage() {
  const { showNotification } = useNotifications()
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  const loader = useCallback(() => getAdminAvailability(branchId), [branchId])
  const { data, isLoading, error, reload } = useApiResource(loader)

  const [globalForm, setGlobalForm] = useState({ date: '', detail: '' })
  const [exceptionForm, setExceptionForm] = useState(buildEmptyExceptionForm(activeBranch?.id || 1))
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Filters for exceptions list
  const [exceptionSpecialistFilter, setExceptionSpecialistFilter] = useState<string>('')
  const [exceptionTypeFilter, setExceptionTypeFilter] = useState<string>('')

  // Pagination for exceptions
  const [exceptionPage, setExceptionPage] = useState(1)

  // Pagination for closure days
  const [closurePage, setClosurePage] = useState(1)

  // Filtrar los datos por la sucursal activa
  const branchExceptions = data?.exceptions.filter((e) => e.branchId === activeBranch?.id) || []

  useEffect(() => {
    setExceptionForm(buildEmptyExceptionForm(activeBranch?.id || 1))
    setGlobalForm({ date: '', detail: '' })
  }, [activeBranch?.id])

  // Reset pages when branch changes
  useEffect(() => {
    setExceptionPage(1)
    setClosurePage(1)
  }, [activeBranch?.id])

  // Filtered and paginated exceptions
  const filteredExceptions = branchExceptions.filter((ex) => {
    if (exceptionSpecialistFilter && ex.specialistId.toString() !== exceptionSpecialistFilter) return false
    if (exceptionTypeFilter && ex.type !== exceptionTypeFilter) return false
    return true
  })

  const totalExceptionPages = Math.ceil(filteredExceptions.length / PAGE_SIZE)
  const visibleExceptions = filteredExceptions.slice(0, exceptionPage * PAGE_SIZE)

  // Filtered and paginated closure days
  const filteredClosures = data?.globalBlocks || []

  const totalClosurePages = Math.ceil(filteredClosures.length / PAGE_SIZE)
  const visibleClosures = filteredClosures.slice(0, closurePage * PAGE_SIZE)

  function showMoreExceptions() {
    setExceptionPage((p) => Math.min(p + 1, totalExceptionPages))
  }

  function showLessExceptions() {
    setExceptionPage((p) => Math.max(1, p - 1))
  }

  function showMoreClosures() {
    setClosurePage((p) => Math.min(p + 1, totalClosurePages))
  }

  function showLessClosures() {
    setClosurePage((p) => Math.max(1, p - 1))
  }

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
    if (exceptionForm.dates.length === 0 && !exceptionForm.useDateRange) {
      showNotification({ title: 'Error', message: 'Debe agregar al menos una fecha o configurar un rango', tone: 'danger' })
      return
    }
    if (exceptionForm.useDateRange && (!exceptionForm.rangeStartDate || !exceptionForm.rangeEndDate || exceptionForm.rangeWeekdayCodes.length === 0)) {
      showNotification({ title: 'Error', message: 'Para rango debe elegir fecha inicio, fin y dias de la semana', tone: 'danger' })
      return
    }

    setIsSubmitting(true)
    try {
      await createAdminAvailabilityException({
        specialistIds: exceptionForm.specialistIds,
        branchId: activeBranch?.id || 1,
        type: exceptionForm.type,
        dates: exceptionForm.dates,
        rangeStartDate: exceptionForm.useDateRange ? exceptionForm.rangeStartDate : '',
        rangeEndDate: exceptionForm.useDateRange ? exceptionForm.rangeEndDate : '',
        weekdayCodes: exceptionForm.useDateRange ? exceptionForm.rangeWeekdayCodes : [],
        startTime: exceptionForm.isWholeDay ? '' : exceptionForm.startTime,
        endTime: exceptionForm.isWholeDay ? '' : exceptionForm.endTime,
        detail: exceptionForm.detail || (exceptionForm.type === 'BLOQUEAR' ? 'Dia libre / Bloqueo' : 'Horas extra'),
      })
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
        <div className="_flex-col _flex-gap-lg">
          {/* Forms row - side by side */}
          <div className="_grid-2cols _grid-gap-lg">
            <SectionCard title="Excepciones de Especialistas" description="Añade disponibilidad o bloquea dias para multiples especialistas a la vez.">
              <ExceptionForm
                exceptionForm={exceptionForm}
                setExceptionForm={setExceptionForm}
                specialists={data.filters.specialists}
                weekdayOptions={data.filters.weekdayOptions}
                isSubmitting={isSubmitting}
                onSubmit={handleExceptionSubmit}
              />
            </SectionCard>

            <SectionCard title={`Cierre de ${activeBranch.nombre}`} description="Bloquea dias festivos o cierres generales solo para la sucursal seleccionada.">
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
                  Bloquear dia de sucursal
                </button>
              </form>
            </SectionCard>
          </div>

          {/* Lists row - side by side */}
          <div className="_grid-2cols _grid-gap-lg">
            <SectionCard title="Excepciones Activas en Sucursal">
              {branchExceptions.length ? (
                <>
                  <div className="_flex-gap-md _mb-md _flex-wrap">
                    <select
                      className="input _min-w-dropdown"
                      value={exceptionSpecialistFilter}
                      onChange={(e) => { setExceptionSpecialistFilter(e.target.value); setExceptionPage(1) }}
                    >
                      <option value="">Todos los especialistas</option>
                      {data.filters.specialists.map((sp) => (
                        <option key={sp.id} value={sp.id.toString()}>{sp.label}</option>
                      ))}
                    </select>
                    <select
                      className="input _min-w-dropdown"
                      value={exceptionTypeFilter}
                      onChange={(e) => { setExceptionTypeFilter(e.target.value); setExceptionPage(1) }}
                    >
                      <option value="">Todos los tipos</option>
                      <option value="BLOQUEAR">Bloquear</option>
                      <option value="AGREGAR">Agregar</option>
                    </select>
                  </div>
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
                        {visibleExceptions.map((ex) => {
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
                                  className="button button--ghost button--compact _text-danger"
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
                  {filteredExceptions.length > PAGE_SIZE && (
                    <div className="_flex-center _flex-gap-md _mt-md">
                      {exceptionPage > 1 && (
                        <button className="button button--ghost" onClick={showLessExceptions}>
                          Mostrar menos
                        </button>
                      )}
                      {exceptionPage < totalExceptionPages && (
                        <button className="button button--ghost" onClick={showMoreExceptions}>
                          Mostrar mas
                        </button>
                      )}
                    </div>
                  )}
                </>
              ) : (
                <DataState title="Sin excepciones activas" message="No hay bloqueos ni horas extra para especialistas." />
              )}
            </SectionCard>

            <SectionCard title={`Dias de Cierre - ${activeBranch.nombre}`}>
              {data.globalBlocks.length ? (
                <>
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
                        {visibleClosures.map((block) => (
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
                  {filteredClosures.length > PAGE_SIZE && (
                    <div className="_flex-center _flex-gap-md _mt-md">
                      {closurePage > 1 && (
                        <button className="button button--ghost" onClick={showLessClosures}>
                          Mostrar menos
                        </button>
                      )}
                      {closurePage < totalClosurePages && (
                        <button className="button button--ghost" onClick={showMoreClosures}>
                          Mostrar mas
                        </button>
                      )}
                    </div>
                  )}
                </>
              ) : (
                <DataState title="Sin cierres de sucursal" message="Esta sucursal opera normalmente." />
              )}
            </SectionCard>
          </div>
        </div>
      ) : null}
    </div>
  )
}
