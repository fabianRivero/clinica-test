import { useCallback, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { AdminStaffTabs } from '../../components/admin/AdminStaffTabs'
import { DataState } from '../../components/admin/DataState'
import { FieldError } from '../../components/admin/FieldError'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useConfirmDialog } from '../../hooks/useConfirmDialog'
import { useNotifications } from '../../providers/NotificationProvider'
import {
  createAdminStaff,
  getAdminStaff,
  updateAdminStaff,
  updateAdminStaffStatus,
  changeAdminStaffBranch,
} from '../../services/api/admin'
import { useAuth } from '../../providers/AuthProvider'
import { useBranchContext } from '../../providers/BranchProvider'
import type {
  CreateAdminStaffPayload,
  StaffCapacityItem,
  StaffResponse,
  UpdateAdminStaffPayload,
} from '../../types/admin'

type StaffFormState = CreateAdminStaffPayload

function buildEmptyForm(): StaffFormState {
  return {
    username: '',
    password: '',
    email: '',
    primerNombre: '',
    segundoNombre: '',
    apellidoPaterno: '',
    apellidoMaterno: '',
    ci: '',
    telefono: '',
    observaciones: '',
    specialtyIds: [],
    fechaNacimiento: '',
  }
}

function buildFormFromStaffMember(staffMember: StaffCapacityItem): StaffFormState {
  return {
    username: staffMember.username,
    password: '',
    email: staffMember.email,
    primerNombre: staffMember.primerNombre,
    segundoNombre: staffMember.segundoNombre,
    apellidoPaterno: staffMember.apellidoPaterno,
    apellidoMaterno: staffMember.apellidoMaterno,
    ci: staffMember.ci,
    telefono: staffMember.phone ?? '',
    observaciones: staffMember.observations ?? '',
    specialtyIds: staffMember.specialtyIds,
    fechaNacimiento: staffMember.fechaNacimiento ?? '',
  }
}

function isFieldErrorShape(error: unknown): error is Error & { fieldErrors?: Record<string, string> } {
  return Boolean(error && typeof error === "object" && 'fieldErrors' in error)
}

function StaffPageShell({
  title,
  description,
  actions,
  children,
}: {
  title: string
  description: string
  actions?: Array<{
    label: string
    variant?: 'primary' | 'ghost'
    to?: string
    onClick?: () => void
  }>
  children: ReactNode
}) {
  return (
    <div className="page-stack">
      <PageHeader eyebrow="Equipo clinico" title={title} description={description} actions={actions} />
      <AdminStaffTabs />
      {children}
    </div>
  )
}

function StaffEditorForm({
  data,
  editingStaffMember,
  onEditingCancelled,
  onSaved,
}: {
  data: StaffResponse
  editingStaffMember: StaffCapacityItem | null
  onEditingCancelled: () => void
  onSaved: () => void
}) {
  const { showNotification } = useNotifications()
  const [formState, setFormState] = useState<StaffFormState>(() =>
    editingStaffMember ? buildFormFromStaffMember(editingStaffMember) : buildEmptyForm(),
  )
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  // Tracks the last CI value used to sync into username/password
  const [lastSyncedCi, setLastSyncedCi] = useState('')

  function handleChange<K extends keyof StaffFormState>(fieldName: K, value: StaffFormState[K]) {
    setFormState((current) => {
      const next = { ...current, [fieldName]: value }

      // When CI changes in create mode, sync username and password with CI
      // only if they still match the last synced CI (i.e., user hasn't manually changed them)
      if (fieldName === 'ci' && !editingStaffMember) {
        const newCi = value as string
        if (formState.username === lastSyncedCi || formState.username === '') {
          next.username = newCi
        }
        if (formState.password === lastSyncedCi || formState.password === '') {
          next.password = newCi
        }
        setLastSyncedCi(newCi)
      }

      return next
    })
    setFieldErrors((current) => {
      if (!current[fieldName]) {
        return current
      }
      const nextErrors = { ...current }
      delete nextErrors[fieldName]
      return nextErrors
    })
  }

  function resetCreateForm() {
    setFormState(buildEmptyForm())
    setFieldErrors({})
    setSubmitError(null)
    setLastSyncedCi('')
  }

  function handleCancel() {
    if (editingStaffMember) {
      onEditingCancelled()
      return
    }
    resetCreateForm()
  }

  function toggleSpecialty(specialtyId: number) {
    handleChange(
      'specialtyIds',
      formState.specialtyIds.includes(specialtyId)
        ? formState.specialtyIds.filter((item) => item !== specialtyId)
        : [...formState.specialtyIds, specialtyId].sort((left, right) => left - right),
    )
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSubmitting(true)
    setFieldErrors({})
    setSubmitError(null)

    if (formState.specialtyIds.length === 0) {
      setFieldErrors({ specialtyIds: 'Selecciona al menos una especialidad.' })
      setIsSubmitting(false)
      return
    }

    const payload: UpdateAdminStaffPayload = {
      username: formState.username.trim(),
      password: formState.password,
      email: formState.email.trim(),
      primerNombre: formState.primerNombre.trim(),
      segundoNombre: formState.segundoNombre.trim(),
      apellidoPaterno: formState.apellidoPaterno.trim(),
      apellidoMaterno: formState.apellidoMaterno.trim(),
      ci: formState.ci.trim(),
      telefono: formState.telefono.trim(),
      observaciones: formState.observaciones.trim(),
      specialtyIds: formState.specialtyIds,
      fechaNacimiento: formState.fechaNacimiento,
    }

    try {
      if (editingStaffMember) {
        await updateAdminStaff(editingStaffMember.rawId, payload)
        showNotification({
          title: 'Especialista actualizado',
          message: 'Los cambios del especialista se guardaron correctamente.',
          tone: 'success',
        })
      } else {
        await createAdminStaff(payload as CreateAdminStaffPayload)
        showNotification({
          title: 'Especialista creado',
          message: 'El nuevo especialista ya aparece dentro del equipo.',
          tone: 'success',
        })
      }
      onSaved()
    } catch (error) {
      if (isFieldErrorShape(error) && error.fieldErrors) {
        setFieldErrors(error.fieldErrors)
      }
      const message =
        error instanceof Error ? error.message : 'No se pudo guardar el especialista.'
      setSubmitError(message)
      showNotification({
        title: 'No se pudo guardar',
        message,
        tone: 'danger',
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <SectionCard
      eyebrow="Edicion"
      title={editingStaffMember ? `Editar: ${editingStaffMember.specialist}` : 'Crear especialista'}
      description="Completa los datos de acceso, contacto y especialidades del trabajador."
    >
      <form className="form-grid" onSubmit={(event) => void handleSubmit(event)}>
        <label className="field" htmlFor="staff-ci">
          <span>CI <span className="_text-danger">*</span></span>
          <input
            id="staff-ci"
            className="input"
            value={formState.ci}
            onChange={(event) => handleChange('ci', event.target.value)}
            required
          />
          <FieldError message={fieldErrors.ci} />
        </label>

        <label className="field" htmlFor="staff-password">
          <span>{editingStaffMember ? 'Nueva contrasena (opcional)' : 'Contrasena inicial'} <span className="_text-danger">*</span></span>
          <input
            id="staff-password"
            className="input"
            type="password"
            value={formState.password}
            onChange={(event) => handleChange('password', event.target.value)}
            required={!editingStaffMember}
          />
          <FieldError message={fieldErrors.password} />
        </label>

        <label className="field" htmlFor="staff-username">
          <span>Nombre de usuario <span className="_text-danger">*</span></span>
          <input
            id="staff-username"
            className="input"
            value={formState.username}
            onChange={(event) => handleChange('username', event.target.value)}
            required
          />
          <FieldError message={fieldErrors.username} />
        </label>

        <label className="field" htmlFor="staff-email">
          <span>Correo electronico</span>
          <input
            id="staff-email"
            className="input"
            type="email"
            value={formState.email}
            onChange={(event) => handleChange('email', event.target.value)}
          />
          <FieldError message={fieldErrors.email} />
        </label>

        <label className="field" htmlFor="staff-primer-nombre">
          <span>Primer nombre <span className="_text-danger">*</span></span>
          <input
            id="staff-primer-nombre"
            className="input"
            value={formState.primerNombre}
            onChange={(event) => handleChange('primerNombre', event.target.value)}
            required
          />
          <FieldError message={fieldErrors.primerNombre} />
        </label>

        <label className="field" htmlFor="staff-segundo-nombre">
          <span>Segundo nombre</span>
          <input
            id="staff-segundo-nombre"
            className="input"
            value={formState.segundoNombre}
            onChange={(event) => handleChange('segundoNombre', event.target.value)}
          />
          <FieldError message={fieldErrors.segundoNombre} />
        </label>

        <label className="field" htmlFor="staff-apellido-paterno">
          <span>Apellido paterno <span className="_text-danger">*</span></span>
          <input
            id="staff-apellido-paterno"
            className="input"
            value={formState.apellidoPaterno}
            onChange={(event) => handleChange('apellidoPaterno', event.target.value)}
            required
          />
          <FieldError message={fieldErrors.apellidoPaterno} />
        </label>

        <label className="field" htmlFor="staff-apellido-materno">
          <span>Apellido materno</span>
          <input
            id="staff-apellido-materno"
            className="input"
            value={formState.apellidoMaterno}
            onChange={(event) => handleChange('apellidoMaterno', event.target.value)}
          />
          <FieldError message={fieldErrors.apellidoMaterno} />
        </label>

        <label className="field" htmlFor="staff-telefono">
          <span>Teléfono</span>
          <input
            id="staff-telefono"
            className="input"
            value={formState.telefono}
            onChange={(event) => handleChange('telefono', event.target.value)}
          />
          <FieldError message={fieldErrors.telefono} />
        </label>

        <label className="field" htmlFor="staff-fecha-nacimiento">
          <span>Fecha de nacimiento <span className="_text-danger">*</span></span>
          <input
            id="staff-fecha-nacimiento"
            className="input"
            type="date"
            value={formState.fechaNacimiento}
            onChange={(event) => handleChange('fechaNacimiento', event.target.value)}
            required
          />
          <FieldError message={fieldErrors.fechaNacimiento} />
        </label>

        <label className="field field--full" htmlFor="staff-observaciones">
          <span>Observaciones</span>
          <textarea
            id="staff-observaciones"
            className="input textarea textarea--compact"
            value={formState.observaciones}
            onChange={(event) => handleChange('observaciones', event.target.value)}
          />
          <FieldError message={fieldErrors.observaciones} />
        </label>

        <div className="field field--full">
          <span>Especialidades <span className="_text-danger">*</span></span>
          <div className="checkbox-grid">
            {data.specialtyOptions.map((option) => (
              <label className="checkbox-pill" key={option.id}>
                <input
                  checked={formState.specialtyIds.includes(option.id)}
                  type="checkbox"
                  onChange={() => toggleSpecialty(option.id)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
          <FieldError message={fieldErrors.specialtyIds} />
        </div>

        {submitError ? <div className="form-error field--full">{submitError}</div> : null}

        <div className="form-actions field--full">
          {editingStaffMember ? (
            <button className="button button--ghost" type="button" onClick={handleCancel}>
              Cancelar edicion
            </button>
          ) : null}
          <button className="button" disabled={isSubmitting} type="submit">
            {isSubmitting
              ? 'Guardando...'
              : editingStaffMember
                ? 'Guardar cambios'
                : 'Crear especialista'}
          </button>
        </div>
      </form>
    </SectionCard>
  )
}

export function AdminStaffCreatePage() {
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  const loader = useCallback(() => getAdminStaff(branchId), [branchId])
  const { data, isLoading, error, reload } = useApiResource(loader)
  const [searchParams, setSearchParams] = useSearchParams()
  const editingStaffId = Number(searchParams.get('editar') || '') || null

  const editingStaffMember = useMemo(
    () => data?.staff.find((item) => item.rawId === editingStaffId) ?? null,
    [data, editingStaffId],
  )

  function clearEditing() {
    if (editingStaffId) {
      setSearchParams({})
    }
  }

  return (
    <StaffPageShell
      title={editingStaffMember ? `Editar: ${editingStaffMember.specialist}` : 'Crear especialista'}
      description="Crea nuevas cuentas de especialista o actualiza sus datos y especialidades."
      actions={[
        editingStaffMember
          ? { label: 'Cancelar edicion', variant: 'ghost', onClick: clearEditing }
          : { label: 'Ir a gestion', variant: 'ghost', to: '/admin/equipo/gestionar' },
      ]}
    >
      {isLoading && !data ? (
        <SectionCard title="Cargando equipo">
          <DataState
            title="Sincronizando equipo"
            message="Cargando especialidades, citas futuras y validaciones pendientes."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar el equipo">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <>
          <StaffEditorForm
            key={editingStaffMember ? `edit-${editingStaffMember.rawId}` : 'create'}
            data={data}
            editingStaffMember={editingStaffMember}
            onEditingCancelled={clearEditing}
            onSaved={() => {
              clearEditing()
              reload()
            }}
          />
        </>
      ) : null}
    </StaffPageShell>
  )
}

export function AdminStaffManagePage() {
  const { activeBranch, branches } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  const loader = useCallback(() => getAdminStaff(branchId), [branchId])
  const { data, isLoading, error, reload } = useApiResource(loader)
  const { showNotification } = useNotifications()
  const { confirm, ConfirmDialog: ConfirmDialogModal } = useConfirmDialog()
  const { user } = useAuth()
  const isMainAdmin = user?.isMainAdmin || user?.isSuperuser
  const [isChangingBranchId, setIsChangingBranchId] = useState<number | null>(null)

  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all')
  const [searchName, setSearchName] = useState('')
  const [searchCI, setSearchCI] = useState('')

  const filteredStaff = useMemo(() => {
    if (!data) return []
    return data.staff.filter(item => {
      const matchesStatus =
        statusFilter === 'all' ||
        (statusFilter === 'active' && item.isActive) ||
        (statusFilter === 'inactive' && !item.isActive)
      const nameLower = item.specialist.toLowerCase()
      const matchesName = searchName === '' || nameLower.includes(searchName.toLowerCase())
      const matchesCI = searchCI === '' || (item.ci ?? '').toLowerCase().includes(searchCI.toLowerCase())
      return matchesStatus && matchesName && matchesCI
    })
  }, [data, statusFilter, searchName, searchCI])

  async function handleChangeBranch(staffMember: StaffCapacityItem, branchId: number) {
    const branchName = branches.find(b => b.id === branchId)?.nombre || 'esta sucursal'
    const confirmed = await confirm({
      title: 'Cambiar sucursal',
      message: `¿Seguro que deseas mover a ${staffMember.specialist} a la sucursal ${branchName}?\n\n¡ATENCIÓN!: Al cambiar de sucursal, TODOS los horarios de disponibilidad y excepciones de este especialista en la sucursal actual se ELIMINARÁN automáticamente.`,
      tone: 'warning',
    })
    if (!confirmed) return

    setIsChangingBranchId(staffMember.rawId)
    try {
      const response = await changeAdminStaffBranch(staffMember.rawId, branchId)
      showNotification({ title: 'Usuario movido', message: response.detail, tone: 'success' })
      reload()
    } catch (err: any) {
      showNotification({
        title: 'Error al mover',
        message: err.message,
        tone: 'danger',
      })
    } finally {
      setIsChangingBranchId(null)
    }
  }

  async function handleToggleStatus(staffMember: StaffCapacityItem) {
    try {
      await updateAdminStaffStatus(staffMember.rawId, { active: !staffMember.isActive })
      showNotification({
        title: staffMember.isActive ? 'Especialista desactivado' : 'Especialista reactivado',
        message: staffMember.isActive
          ? 'Su disponibilidad fue eliminada y ya no podra recibir nuevas reservas.'
          : 'El especialista vuelve a estar disponible para gestion interna.',
        tone: 'success',
      })
      reload()
    } catch (error) {
      showNotification({
        title: 'No se pudo cambiar el estado',
        message:
          error instanceof Error ? error.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  return (
    <StaffPageShell
      title="Gestionar especialistas"
      description="Revisa la carga operativa del equipo y administra especialistas ya registrados."
      actions={[{ label: 'Crear especialista', to: '/admin/equipo/crear', variant: 'primary' }]}
    >
      {isLoading && !data ? (
        <SectionCard title="Cargando equipo">
          <DataState
            title="Sincronizando equipo"
            message="Cargando especialidades, citas futuras y validaciones pendientes."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar el equipo">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <>
          <SectionCard
            eyebrow="Capacidad"
            title="Especialistas actuales"
            description="Seguimiento de especialistas, agenda futura, validaciones pendientes y estado de actividad."
          >
            <div className="list-filters">
              <div className="filter-row">
                <label className="input-group">
                  <span>Estado</span>
                  <select
                    value={statusFilter}
                    onChange={e => setStatusFilter(e.target.value as typeof statusFilter)}
                    className="input"
                  >
                    <option value="all">Todos</option>
                    <option value="active">Activos</option>
                    <option value="inactive">Inactivos</option>
                  </select>
                </label>
                <label className="input-group">
                  <span>Nombre</span>
                  <input
                    type="text"
                    placeholder="Buscar por nombre..."
                    value={searchName}
                    onChange={e => setSearchName(e.target.value)}
                    className="input"
                  />
                </label>
                <label className="input-group">
                  <span>CI</span>
                  <input
                    type="text"
                    placeholder="Buscar por CI..."
                    value={searchCI}
                    onChange={e => setSearchCI(e.target.value)}
                    className="input"
                  />
                </label>
              </div>
            </div>
            {filteredStaff.length ? (
              <div className="capacity-list">
                {filteredStaff.map((item) => (
                  <article className="capacity-item" key={item.id}>
                    <div className="capacity-item__header">
                      <div>
                        <strong>{item.specialist}</strong>
                        <p>{item.specialty}</p>
                        <p>
                          @{item.username} | {item.phone || 'Sin teléfono'} | {item.activeOperations} operaciones activas |{' '}
                          {item.upcomingAppointments} citas futuras
                        </p>
                      </div>
                      <div className="table-actions">
                        <StatusBadge tone={item.isActive ? 'success' : 'neutral'}>
                          {item.status}
                        </StatusBadge>
                        <StatusBadge tone={item.pendingValidations ? 'warning' : 'success'}>
                          {item.pendingValidations
                            ? `${item.pendingValidations} pendientes`
                            : 'Sin pendientes'}
                        </StatusBadge>
                      </div>
                    </div>

                    <div className="table-muted">
                      {item.email || 'Sin correo'} | CI: {item.ci || 'Sin registrar'} | Carga: {item.load}%
                    </div>

                    {item.observations ? <div className="table-muted">{item.observations}</div> : null}

                    <div className="catalog-admin-card__actions">
                      <Link
                        className="button button--ghost button--compact"
                        to={`/admin/equipo/crear?editar=${item.rawId}`}
                      >
                        Editar
                      </Link>
                      <button
                        className={`button button--compact ${item.isActive ? 'button--warning' : 'button--success'}`}
                        type="button"
                        onClick={() => void handleToggleStatus(item)}
                      >
                        {item.isActive ? 'Desactivar' : 'Activar'}
                      </button>
                      {isMainAdmin && (
                        <button
                          className="button button--secondary button--compact"
                          type="button"
                          disabled={isChangingBranchId === item.rawId}
                          onClick={() => {
                            const targetBranchId = window.prompt(
                              `Ingresa el ID de la sucursal destino para ${item.specialist}:\n\n` +
                              branches.map(b => `[ ${b.id} ] - ${b.nombre}`).join('\n')
                            )
                            if (targetBranchId) {
                              handleChangeBranch(item, Number(targetBranchId))
                            }
                          }}
                        >
                          {isChangingBranchId === item.rawId ? 'Moviendo...' : 'Cambiar sucursal'}
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <DataState
                title="Sin especialistas"
                message={searchName || searchCI || statusFilter !== 'all'
                  ? "No hay especialistas que coincidan con los filtros seleccionados."
                  : "Todavia no hay trabajadores operativos listados en la base conectada."}
              />
            )}
          </SectionCard>
        </>
      ) : null}
      <ConfirmDialogModal />
    </StaffPageShell>
  )
}
