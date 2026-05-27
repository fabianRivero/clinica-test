import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { AdminBranchTabs } from '../../components/admin/AdminBranchTabs'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { changeAdminBranchManager, finalizeAdminBranchWizard, getAdminBranchAdmins, getAdminBranchAuditLogs, getAdminBranchDeactivationImpact, getAdminBranchesManagement, initializeAdminBranchWizard, saveAdminBranchWizardStep1, saveAdminBranchWizardStep2CreateNew, toggleAdminBranch, updateAdminBranch } from '../../services/api/admin'
import { useAuth } from '../../providers/AuthProvider'
import { useConfirmDialog } from '../../hooks/useConfirmDialog'
import { useNotifications } from '../../providers/NotificationProvider'

type BranchRow = {
  id: number
  nombre: string
  ciudad: string
  direccion: string
  activa: boolean
  admin: { id: number; nombre: string; username: string } | null
}

export function AdminBranchesPage({ view = 'edit' }: { view?: 'edit' | 'create' }) {
  const { logout, user } = useAuth()
  const { confirm, ConfirmDialog: ConfirmDialogModal } = useConfirmDialog()
  const navigate = useNavigate()
  const { showNotification } = useNotifications()
  const [rows, setRows] = useState<BranchRow[]>([])
  const [status, setStatus] = useState<'all' | 'active' | 'inactive'>('all')
  const [city, setCity] = useState('')
  const [adminName, setAdminName] = useState('')
  const [branchId, setBranchId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [newBranch, setNewBranch] = useState({ nombre: '', ciudad: '', direccion: '' })
  const [wizardStep, setWizardStep] = useState<1 | 2 | 3>(1)
  const [wizardStep1Completed, setWizardStep1Completed] = useState(false)
  const [wizardStep2Completed, setWizardStep2Completed] = useState(false)
  const [wizardNewAdmin, setWizardNewAdmin] = useState({ username: '', email: '', primerNombre: '', apellidoPaterno: '', ci: '', password: '' })
  const [wizardTablet, setWizardTablet] = useState({ nombre: '', clave: '' })
  const [branchAdmins, setBranchAdmins] = useState<Array<{ id: number; username: string; fullName: string; isActive: boolean; branchId: number | null; branchName: string }>>([])
  const [editingBranch, setEditingBranch] = useState<BranchRow | null>(null)
  const [editForm, setEditForm] = useState({ nombre: '', ciudad: '', direccion: '' })
  const [changingAdminBranch, setChangingAdminBranch] = useState<BranchRow | null>(null)
  const [newAdminUserId, setNewAdminUserId] = useState('')
  const [changeNotice, setChangeNotice] = useState<{ message: string; requiresLogout: boolean } | null>(null)
  const [auditRows, setAuditRows] = useState<Array<{ id: number; createdAt: string; action: string; detail: string; branchName: string; actor: string }>>([])
  const recentAuditRows = useMemo(() => auditRows.slice(0, 5), [auditRows])
  const logoutTimerRef = useRef<number | null>(null)

  const branchOptions = useMemo(() => rows.map((b) => ({ id: b.id, name: b.nombre })), [rows])

  async function load() {
    try {
      setError(null)
      const response = await getAdminBranchesManagement({ status, city: city || undefined, adminName: adminName || undefined, branchId })
      setRows(response.branches)
      const audit = await getAdminBranchAuditLogs(branchId)
      setAuditRows(audit.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo cargar sucursales')
    }
  }

  useEffect(() => {
    void load()
  }, [status, city, adminName, branchId])

  useEffect(() => {
    if (view !== 'create') return
    void initializeAdminBranchWizard().catch(() => undefined)
    void getAdminBranchAdmins().then((r) => setBranchAdmins(r.admins)).catch(() => undefined)
  }, [view])

  useEffect(() => {
    if (!changeNotice?.requiresLogout) return undefined

    if (logoutTimerRef.current) {
      window.clearTimeout(logoutTimerRef.current)
    }

    logoutTimerRef.current = window.setTimeout(() => {
      void logout().finally(() => {
        window.location.href = '/login'
      })
    }, 3500)

    return () => {
      if (logoutTimerRef.current) {
        window.clearTimeout(logoutTimerRef.current)
        logoutTimerRef.current = null
      }
    }
  }, [changeNotice, logout])

  async function handleWizardStep1(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await saveAdminBranchWizardStep1(newBranch)
      setWizardStep1Completed(true)
      setWizardStep(2)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar paso 1')
    } finally {
      setSaving(false)
    }
  }

  async function handleWizardStep2(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await saveAdminBranchWizardStep2CreateNew(wizardNewAdmin)
      setWizardStep2Completed(true)
      setWizardStep(3)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar paso 2')
    } finally {
      setSaving(false)
    }
  }

  async function handleWizardStep3(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await finalizeAdminBranchWizard(wizardTablet)
      showNotification({
        title: 'Sucursal creada',
        message: 'La sucursal se creó correctamente.',
        tone: 'success',
      })
      setWizardStep(1)
      setWizardStep1Completed(false)
      setWizardStep2Completed(false)
      setNewBranch({ nombre: '', ciudad: '', direccion: '' })
      setWizardTablet({ nombre: '', clave: '' })
      navigate('/admin/sucursales/editar')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo finalizar creación')
      showNotification({
        title: 'Error al crear sucursal',
        message: err instanceof Error ? err.message : 'No se pudo finalizar la creación de la sucursal.',
        tone: 'danger',
      })
    } finally {
      setSaving(false)
    }
  }

  async function handleCancelWizard() {
    const ok = await confirm({
      title: 'Cancelar creacion',
      message: '¿Seguro que deseas cancelar la creación de sucursal? Se perderán los cambios no finalizados.',
      tone: 'danger',
    })
    if (!ok) return
    setWizardStep(1)
    setWizardStep1Completed(false)
    setWizardStep2Completed(false)
    setNewBranch({ nombre: '', ciudad: '', direccion: '' })
    setWizardNewAdmin({ username: '', email: '', primerNombre: '', apellidoPaterno: '', ci: '', password: '' })
    setWizardTablet({ nombre: '', clave: '' })
    void initializeAdminBranchWizard().catch(() => undefined)
  }

  async function handleToggle(row: BranchRow) {
    try {
      if (row.activa) {
        const impact = await getAdminBranchDeactivationImpact(row.id)
        const p = impact.impact
        const hasPending = p.appointments_pending + p.payments_pending + p.processes_pending > 0
        if (hasPending) {
          const ok = await confirm({
            title: 'Desactivar sucursal',
            message: `Hay pendientes en la sucursal:\n- Citas: ${p.appointments_pending}\n- Pagos: ${p.payments_pending}\n- Procesos: ${p.processes_pending}\n\n¿Deseas desactivar de todas formas?`,
            tone: 'warning',
          })
          if (!ok) return
          await toggleAdminBranch(row.id, false, true)
        } else {
          await toggleAdminBranch(row.id, false)
        }
      } else {
        await toggleAdminBranch(row.id, true)
      }
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo actualizar estado')
    }
  }

  function openEditModal(row: BranchRow) {
    setEditingBranch(row)
    setEditForm({ nombre: row.nombre, ciudad: row.ciudad, direccion: row.direccion })
  }

  async function handleSaveEdit() {
    if (!editingBranch) return
    setSaving(true)
    try {
      await updateAdminBranch(editingBranch.id, editForm)
      setEditingBranch(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo actualizar la sucursal')
    } finally {
      setSaving(false)
    }
  }

  function openChangeAdminModal(row: BranchRow) {
    setChangingAdminBranch(row)
    setNewAdminUserId('')
    setChangeNotice(null)
    void getAdminBranchAdmins().then((r) => setBranchAdmins(r.admins)).catch(() => undefined)
  }

  async function handleConfirmAdminChange() {
    if (!changingAdminBranch) return
    const parsedId = Number(newAdminUserId)
    if (!parsedId || Number.isNaN(parsedId)) {
      setError('Debes ingresar un ID de administrador valido.')
      return
    }
    setSaving(true)
    try {
      const result = await changeAdminBranchManager(changingAdminBranch.id, parsedId)
      setChangingAdminBranch(null)
      setNewAdminUserId('')
      if (result.mode === 'swap_with_main_admin') {
        setError(null)
        setChangeNotice({
          message: 'El cambio se realizó correctamente. Tu sesión se cerrará en unos segundos para proteger el acceso a la sucursal anterior.',
          requiresLogout: true,
        })
        return
      }
      await load()
      setError(null)
      setChangeNotice({
        message: 'El cambio se realizó correctamente.',
        requiresLogout: false,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo cambiar el administrador')
    } finally {
      setSaving(false)
    }
  }

  function handleCloseChangeNotice() {
    if (changeNotice?.requiresLogout) return
    setChangeNotice(null)
  }

  async function handleLogoutNow() {
    if (logoutTimerRef.current) {
      window.clearTimeout(logoutTimerRef.current)
      logoutTimerRef.current = null
    }
    await logout().finally(() => {
      window.location.href = '/login'
    })
  }

  return (
    <section className="page-stack">
      <PageHeader
        eyebrow="Administracion"
        title="Gestion de sucursales"
        description="Modulo para administracion general de sucursales."
      />

      <AdminBranchTabs />

      {error ? <p className="error-text">{error}</p> : null}

      {changeNotice ? <div className="booking-modal-overlay" role="dialog" aria-modal="true" aria-label="Aviso de cambio de administrador">
        <div className="booking-modal-content" style={{ maxWidth: '640px' }}>
          <header className="booking-modal-header">
            <h2 style={{ margin: 0 }}>Cambio realizado</h2>
          </header>
          <div className="booking-modal-body" style={{ padding: '1rem 1.5rem' }}>
            <p style={{ marginTop: 0 }}>{changeNotice.message}</p>
            {changeNotice.requiresLogout ? <p style={{ color: 'var(--c-neutral-600)' }}>Puedes cerrar sesión ahora o esperar unos segundos.</p> : null}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              {changeNotice.requiresLogout ? <button className="button" type="button" onClick={() => void handleLogoutNow()}>Cerrar sesión ahora</button> : <button className="button" type="button" onClick={() => void handleCloseChangeNotice()}>Aceptar</button>}
            </div>
          </div>
        </div>
      </div> : null}

      {view === 'create' ? <SectionCard title="Crear sucursal" description="Completa el wizard para registrar una nueva sucursal, su administrador y su tablet.">
        <section className="wizard-summary">
          <p className="wizard-summary__title">Wizard de creacion</p>
          <p className="wizard-summary__description">Avanza paso a paso y valida los datos antes de finalizar.</p>
        </section>

        <div className="stepper">
          <button className={`stepper__item ${wizardStep === 1 ? 'is-active' : ''}`} type="button" onClick={() => setWizardStep(1)}>
            <span className="stepper__index">Paso 1</span><span className="stepper__label">Datos de sucursal</span>
          </button>
          <button className={`stepper__item ${wizardStep === 2 ? 'is-active' : ''}`} type="button" onClick={() => setWizardStep(2)} disabled={!wizardStep1Completed}>
            <span className="stepper__index">Paso 2</span><span className="stepper__label">Administrador</span>
          </button>
          <button className={`stepper__item ${wizardStep === 3 ? 'is-active' : ''}`} type="button" onClick={() => setWizardStep(3)} disabled={!wizardStep1Completed || !wizardStep2Completed}>
            <span className="stepper__index">Paso 3</span><span className="stepper__label">Tablet</span>
          </button>
        </div>
        {wizardStep === 1 ? <form onSubmit={handleWizardStep1}><div className="form-grid form-grid--three">
          <label className="field"><span>Nombre de sucursal</span><input className="input" value={newBranch.nombre} onChange={(e) => setNewBranch((v) => ({ ...v, nombre: e.target.value }))} /></label>
          <label className="field"><span>Ciudad</span><input className="input" value={newBranch.ciudad} onChange={(e) => setNewBranch((v) => ({ ...v, ciudad: e.target.value }))} /></label>
          <label className="field"><span>Dirección</span><input className="input" value={newBranch.direccion} onChange={(e) => setNewBranch((v) => ({ ...v, direccion: e.target.value }))} /></label>
        </div><div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem' }}><button className="button button--ghost" type="button" onClick={handleCancelWizard}>Cancelar</button><button className="button" disabled={saving} type="submit">Continuar</button></div></form> : null}
        {wizardStep === 2 ? <form onSubmit={handleWizardStep2}>
          <p style={{ marginBottom: '0.75rem', color: 'var(--c-neutral-600)' }}>
            En este paso siempre se crea un administrador nuevo. El usuario se registra como inactivo y sin sucursal por defecto.
          </p>
          <div className="form-grid form-grid--three">
            <label className="field"><span>Username</span><input className="input" value={wizardNewAdmin.username} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, username: e.target.value }))} /></label>
            <label className="field"><span>Primer nombre</span><input className="input" value={wizardNewAdmin.primerNombre} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, primerNombre: e.target.value }))} /></label>
            <label className="field"><span>Apellido paterno</span><input className="input" value={wizardNewAdmin.apellidoPaterno} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, apellidoPaterno: e.target.value }))} /></label>
            <label className="field"><span>CI</span><input className="input" value={wizardNewAdmin.ci} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, ci: e.target.value }))} /></label>
            <label className="field"><span>Email</span><input className="input" value={wizardNewAdmin.email} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, email: e.target.value }))} /></label>
            <label className="field"><span>Contraseña</span><input className="input" type="password" value={wizardNewAdmin.password} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, password: e.target.value }))} /></label>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem' }}><button className="button button--ghost" type="button" onClick={handleCancelWizard}>Cancelar</button><div style={{ display: 'flex', gap: '0.5rem' }}><button className="button button--ghost" type="button" onClick={() => setWizardStep(1)}>Volver</button><button className="button" disabled={saving} type="submit">Continuar</button></div></div>
        </form> : null}
        {wizardStep === 3 ? <form onSubmit={handleWizardStep3}><div className="form-grid form-grid--three">
          <label className="field"><span>Nombre tablet <span style={{ color: "#dc2626" }}>*</span></span><input className="input" value={wizardTablet.nombre} onChange={(e) => setWizardTablet((v) => ({ ...v, nombre: e.target.value }))} /></label>
          <label className="field"><span>Clave tablet <span style={{ color: "#dc2626" }}>*</span></span><input className="input" type="password" value={wizardTablet.clave} onChange={(e) => setWizardTablet((v) => ({ ...v, clave: e.target.value }))} /></label>
        </div><div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem' }}><button className="button button--ghost" type="button" onClick={handleCancelWizard}>Cancelar</button><div style={{ display: 'flex', gap: '0.5rem' }}><button className="button button--ghost" type="button" onClick={() => setWizardStep(2)}>Volver</button><button className="button" disabled={saving} type="submit">Finalizar</button></div></div></form> : null}
      </SectionCard> : null}

      {view === 'edit' ? <><div className="card">
        <h3>Filtros</h3>
        <div className="form-grid form-grid--four">
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value as 'all' | 'active' | 'inactive')}>
            <option value="all">Todos</option>
            <option value="active">Activas</option>
            <option value="inactive">Inactivas</option>
          </select>
          <input className="input" placeholder="Ciudad" value={city} onChange={(e) => setCity(e.target.value)} />
          <input className="input" placeholder="Admin" value={adminName} onChange={(e) => setAdminName(e.target.value)} />
          <select className="input" value={branchId ?? ''} onChange={(e) => setBranchId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">Todas las sucursales</option>
            {branchOptions.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </div>
      </div>

      <div className="branch-management-panels">
        <div className="section-card branch-management-panel">
          <h3>Lista de sucursales</h3>
          <div className="table-card">
            <table>
          <thead><tr><th>Nombre</th><th>Ciudad</th><th>Direccion</th><th>Admin</th><th>Estado</th><th>Acciones</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.nombre}</td>
                <td>{row.ciudad}</td>
                <td>{row.direccion}</td>
                <td>{row.admin?.nombre || '-'}</td>
                <td>{row.activa ? 'Activa' : 'Inactiva'}</td>
                <td style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <button className="button button--ghost" type="button" onClick={() => openEditModal(row)}>Editar informacion</button>
                  <button className="button button--ghost" type="button" onClick={() => openChangeAdminModal(row)}>Cambiar administrador</button>
                  {(!user?.branchId || row.id !== user.branchId) && (
                    <button className="button button--ghost" type="button" onClick={() => void handleToggle(row)}>{row.activa ? 'Desactivar' : 'Activar'}</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
            </table>
          </div>
        </div>

        <div className="section-card branch-management-panel">
          <h3>Historial de cambios</h3>
          <div className="table-card">
            <table>
          <thead><tr><th>Fecha</th><th>Sucursal</th><th>Accion</th><th>Detalle</th><th>Actor</th></tr></thead>
          <tbody>
            {recentAuditRows.map((row) => (
              <tr key={row.id}>
                <td>{new Date(row.createdAt).toLocaleString()}</td>
                <td>{row.branchName}</td>
                <td>{row.action}</td>
                <td>{row.detail}</td>
                <td>{row.actor}</td>
              </tr>
            ))}
          </tbody>
            </table>
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '0.75rem' }}>
              <Link className="button button--ghost" to="/admin/sucursales/historial">
                Ver todo el historial
              </Link>
            </div>
          </div>
        </div>
      </div>

      {editingBranch ? <div className="booking-modal-overlay" role="dialog" aria-modal="true" aria-label="Editar sucursal">
        <div className="booking-modal-content" style={{ maxWidth: '720px' }}>
          <header className="booking-modal-header">
            <h2 style={{ margin: 0 }}>Editar información de sucursal</h2>
            <button className="booking-modal-close" type="button" onClick={() => setEditingBranch(null)}>×</button>
          </header>
          <div className="booking-modal-body" style={{ padding: '1rem 1.5rem' }}>
            <div className="form-grid form-grid--three">
              <input className="input" placeholder="Nombre" value={editForm.nombre} onChange={(e) => setEditForm((v) => ({ ...v, nombre: e.target.value }))} />
              <input className="input" placeholder="Ciudad" value={editForm.ciudad} onChange={(e) => setEditForm((v) => ({ ...v, ciudad: e.target.value }))} />
              <input className="input" placeholder="Direccion" value={editForm.direccion} onChange={(e) => setEditForm((v) => ({ ...v, direccion: e.target.value }))} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
              <button className="button button--ghost" type="button" onClick={() => setEditingBranch(null)}>Cancelar</button>
              <button className="button" type="button" onClick={() => void handleSaveEdit()} disabled={saving}>Guardar cambios</button>
            </div>
          </div>
        </div>
      </div> : null}

      {changingAdminBranch ? <div className="booking-modal-overlay" role="dialog" aria-modal="true" aria-label="Cambiar administrador">
        <div className="booking-modal-content" style={{ maxWidth: '760px' }}>
          <header className="booking-modal-header">
            <h2 style={{ margin: 0 }}>Cambiar administrador de sucursal</h2>
            <button className="booking-modal-close" type="button" onClick={() => { setChangingAdminBranch(null); setNewAdminUserId('') }}>×</button>
          </header>
          <div className="booking-modal-body" style={{ padding: '1rem 1.5rem' }}>
            <p>Selecciona el administrador de sucursal para {changingAdminBranch.nombre}.</p>
            <select className="input" value={newAdminUserId} onChange={(e) => setNewAdminUserId(e.target.value)}>
              <option value="">Seleccionar admin</option>
              {branchAdmins
                .filter((a) => {
                  // Si la sucursal está bajo admin principal (no hay admin de sucursal activo en la fila),
                  // el backend solo permite intercambio con admin de sucursal activo y con sucursal.
                  if (!changingAdminBranch?.admin) return a.isActive && a.branchId !== null
                  // Si ya existe admin de sucursal, se excluye al actual para que no aparezca como opción.
                  return a.id !== changingAdminBranch.admin!.id
                })
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.fullName} ({a.username}) - {a.isActive ? 'Activo' : 'Inactivo'} - {a.branchName}
                  </option>
                ))}
            </select>
            <p style={{ marginTop: '0.75rem', color: 'var(--c-neutral-600)' }}>
              Aviso: si el admin elegido está activo en otra sucursal, se hará intercambio; si está inactivo y sin sucursal, se activará y el admin actual quedará inactivo.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button className="button button--ghost" type="button" onClick={() => { setChangingAdminBranch(null); setNewAdminUserId('') }}>Cancelar</button>
              <button className="button" type="button" onClick={() => void handleConfirmAdminChange()} disabled={saving}>Confirmar cambio</button>
            </div>
          </div>
        </div>
      </div> : null}
      </> : null}
      <ConfirmDialogModal />
    </section>
  )
}
