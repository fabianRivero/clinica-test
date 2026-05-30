import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { AdminBranchTabs } from '../../components/admin/AdminBranchTabs'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { WizardSubTabs } from '../../components/admin/WizardSubTabs'
import { changeAdminBranchManager, finalizeAdminBranchWizard, getAdminBranchAdmins, getAdminBranchAuditLogs, getAdminBranchDeactivationImpact, getAdminBranchesManagement, initializeAdminBranchWizard, saveAdminBranchWizardStep1, saveAdminBranchWizardStep2CreateNew, saveAdminBranchWizardStep2ExistingInactive, toggleAdminBranch, updateAdminBranch } from '../../services/api/admin'
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
  const [step1Submitted, setStep1Submitted] = useState(false)
  const [wizardStep, setWizardStep] = useState<1 | 2 | 3>(1)
  const [wizardStep1Completed, setWizardStep1Completed] = useState(false)
  const [wizardStep2Completed, setWizardStep2Completed] = useState(false)
  const [wizardNewAdmin, setWizardNewAdmin] = useState({ username: '', ci: '', email: '', primerNombre: '', segundoNombre: '', apellidoPaterno: '', apellidoMaterno: '', telefono: '', fechaNacimiento: '', password: '' })
  const [step2Submitted, setStep2Submitted] = useState(false)
  const [step2SubTab, setStep2SubTab] = useState<'create' | 'select'>('create')
  const [selectedInactiveAdminId, setSelectedInactiveAdminId] = useState<number | null>(null)
  const [wizardTablet, setWizardTablet] = useState({ nombre: '', clave: '' })
  const [showWizardConfirmModal, setShowWizardConfirmModal] = useState(false)
  const [createdBranchInfo, setCreatedBranchInfo] = useState<{ branchName: string; tabletCode: string; tabletClave: string } | null>(null)
  const [branchAdmins, setBranchAdmins] = useState<Array<{ id: number; username: string; fullName: string; isActive: boolean; branchId: number | null; branchName: string }>>([])
  const [editingBranch, setEditingBranch] = useState<BranchRow | null>(null)
  const [editForm, setEditForm] = useState({ nombre: '', ciudad: '', direccion: '' })
  const [changingAdminBranch, setChangingAdminBranch] = useState<BranchRow | null>(null)
  const [newAdminUserId, setNewAdminUserId] = useState('')
  const [changeNotice, setChangeNotice] = useState<{ message: string; requiresLogout: boolean } | null>(null)
  const [auditRows, setAuditRows] = useState<Array<{ id: number; createdAt: string; action: string; detail: string; branchName: string; actor: string }>>([])
  const recentAuditRows = useMemo(() => auditRows.slice(0, 5), [auditRows])
  const logoutTimerRef = useRef<number | null>(null)
  const [activatingBranch, setActivatingBranch] = useState<BranchRow | null>(null)
  const [selectedActivatingAdminId, setSelectedActivatingAdminId] = useState<number | null>(null)

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
    setStep1Submitted(true)
    if (!newBranch.nombre.trim() || !newBranch.ciudad.trim() || !newBranch.direccion.trim()) {
      return
    }
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
    setStep2Submitted(true)
    if (!wizardNewAdmin.username.trim() || !wizardNewAdmin.ci.trim() || !wizardNewAdmin.primerNombre.trim() || !wizardNewAdmin.apellidoPaterno.trim() || !wizardNewAdmin.password.trim() || !wizardNewAdmin.fechaNacimiento.trim()) {
      return
    }
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

  async function handleWizardStep2SelectExisting() {
    if (!selectedInactiveAdminId) return
    setStep2Submitted(true)
    setSaving(true)
    setError(null)
    try {
      await saveAdminBranchWizardStep2ExistingInactive(selectedInactiveAdminId)
      setWizardStep2Completed(true)
      setWizardStep(3)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo asignar el administrador')
    } finally {
      setSaving(false)
    }
  }

  async function handleWizardStep3(e: React.FormEvent) {
    e.preventDefault()
    setShowWizardConfirmModal(true)
  }

  async function handleWizardSubmit() {
    setSaving(true)
    setShowWizardConfirmModal(false)
    setError(null)
    try {
      const result = await finalizeAdminBranchWizard(wizardTablet)
      setCreatedBranchInfo({
        branchName: newBranch.nombre,
        tabletCode: result.tabletKioskCode,
        tabletClave: wizardTablet.clave,
      })
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
    setStep1Submitted(false)
    setStep2Submitted(false)
    setStep2SubTab('create')
    setSelectedInactiveAdminId(null)
    setNewBranch({ nombre: '', ciudad: '', direccion: '' })
    setWizardNewAdmin({ username: '', ci: '', email: '', primerNombre: '', segundoNombre: '', apellidoPaterno: '', apellidoMaterno: '', telefono: '', fechaNacimiento: '', password: '' })
    setWizardTablet({ nombre: '', clave: '' })
    void initializeAdminBranchWizard().catch(() => undefined)
  }

  async function handleToggle(row: BranchRow) {
    try {
      if (!row.activa) {
        const impact = await getAdminBranchDeactivationImpact(row.id)
        const p = impact.impact
        const hasPending = p.appointments_pending + p.payments_pending + p.processes_pending > 0
        if (hasPending) {
          showNotification({
            title: 'No se puede activar',
            message: `Esta sucursal tiene citas, pagos o procedimientos activos que deben completarse o cancelarse antes.`,
            tone: 'warning',
          })
          return
        }
        const adminsResp = await getAdminBranchAdmins()
        const availableAdmins = adminsResp.admins.filter((a: any) => !a.isActive && a.branchId === null)
        if (availableAdmins.length === 0) {
          showNotification({
            title: 'No se puede activar',
            message: 'No hay administradores inactivos sin sucursal disponibles para asignar.',
            tone: 'warning',
          })
          return
        }
        setActivatingBranch(row)
        setSelectedActivatingAdminId(null)
        void getAdminBranchAdmins().then((r) => setBranchAdmins(r.admins)).catch(() => undefined)
        return
      }
      const impact = await getAdminBranchDeactivationImpact(row.id)
      const p = impact.impact
      const hasPending = p.appointments_pending + p.payments_pending + p.processes_pending > 0
      if (hasPending) {
        showNotification({
          title: 'No se puede desactivar',
          message: `Esta sucursal tiene pendientes que deben completarse primero:\n\n- Citas activas: ${p.appointments_pending}\n- Pagos pendientes de verificación: ${p.payments_pending}\n- Procedimientos en proceso: ${p.processes_pending}\n\nCompleta o cancela todos los pendientes antes de desactivar.`,
          tone: 'warning',
        })
        return
      }
      const ok = await confirm({
        title: 'Desactivar sucursal',
        message: `¿Estás seguro de que deseas desactivar "${row.nombre}"? Su administrador también quedará inactivo y sin sucursal asignada.`,
        tone: 'warning',
      })
      if (!ok) return
      await toggleAdminBranch(row.id, false)
      await load()
      showNotification({
        title: 'Sucursal desactivada',
        message: 'La sucursal fue desactivada correctamente. Su administrador también fue desactivado y desasignado.',
        tone: 'success',
      })
    } catch (err) {
      const msg = err instanceof Error ? err.message : ''
      if (msg.includes('pendientes operativos')) {
        showNotification({
          title: 'No se puede desactivar',
          message: 'Esta sucursal tiene citas, pagos o procedimientos pendientes. Completa o cancela todos los pendientes antes de desactivar.',
          tone: 'warning',
        })
      } else if (msg.includes('sin administrador')) {
        showNotification({
          title: 'No se puede activar',
          message: 'Esta sucursal no tiene un administrador asignado. Asigna uno primero antes de activar.',
          tone: 'warning',
        })
      } else {
        setError(err instanceof Error ? err.message : 'No se pudo actualizar estado')
      }
    }
  }

  function openEditModal(row: BranchRow) {
    setEditingBranch(row)
    setEditForm({ nombre: row.nombre, ciudad: row.ciudad, direccion: row.direccion })
  }

  async function handleConfirmActivation() {
    if (!activatingBranch || !selectedActivatingAdminId) return
    setSaving(true)
    try {
      await changeAdminBranchManager(activatingBranch.id, selectedActivatingAdminId)
      await toggleAdminBranch(activatingBranch.id, true)
      setActivatingBranch(null)
      setSelectedActivatingAdminId(null)
      await load()
      showNotification({
        title: 'Sucursal activada',
        message: 'La sucursal fue activada correctamente con su administrador asignado.',
        tone: 'success',
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo activar la sucursal')
    } finally {
      setSaving(false)
    }
  }

  async function handleCancelActivation() {
    setActivatingBranch(null)
    setSelectedActivatingAdminId(null)
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
          <label className="field"><span>Nombre de sucursal <span style={{ color: "#dc2626" }}>*</span></span><input className="input" value={newBranch.nombre} onChange={(e) => setNewBranch((v) => ({ ...v, nombre: e.target.value }))} />{step1Submitted && !newBranch.nombre.trim() && <span style={{ color: "#dc2626", fontSize: "0.75rem" }}>Campo obligatorio</span>}</label>
          <label className="field"><span>Ciudad <span style={{ color: "#dc2626" }}>*</span></span><input className="input" value={newBranch.ciudad} onChange={(e) => setNewBranch((v) => ({ ...v, ciudad: e.target.value }))} />{step1Submitted && !newBranch.ciudad.trim() && <span style={{ color: "#dc2626", fontSize: "0.75rem" }}>Campo obligatorio</span>}</label>
          <label className="field"><span>Dirección <span style={{ color: "#dc2626" }}>*</span></span><input className="input" value={newBranch.direccion} onChange={(e) => setNewBranch((v) => ({ ...v, direccion: e.target.value }))} />{step1Submitted && !newBranch.direccion.trim() && <span style={{ color: "#dc2626", fontSize: "0.75rem" }}>Campo obligatorio</span>}</label>
        </div><div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem' }}><button className="button button--ghost" type="button" onClick={handleCancelWizard}>Cancelar</button><button className="button" disabled={saving} type="submit">Continuar</button></div></form> : null}
        {wizardStep === 2 ? <div>
          <p style={{ marginBottom: '0.75rem', color: 'var(--c-neutral-600)' }}>
            En este paso puedes crear un nuevo administrador o seleccionar uno inactivo existente.
          </p>
          <WizardSubTabs
            tabs={[
              { id: 'create', label: 'Crear nuevo admin' },
              { id: 'select', label: 'Seleccionar admin existente' },
            ]}
            activeTab={step2SubTab}
            onTabChange={(id) => { setStep2SubTab(id as 'create' | 'select'); setStep2Submitted(false) }}
          />

          {step2SubTab === 'create' ? (
            <form onSubmit={handleWizardStep2}>
              <div className="form-grid form-grid--three">
                <label className="field"><span>CI <span style={{ color: "#dc2626" }}>*</span></span><input className="input" value={wizardNewAdmin.ci} onChange={(e) => { const val = e.target.value; setWizardNewAdmin((v) => ({ ...v, ci: val, username: val, password: val })) }} />{step2Submitted && !wizardNewAdmin.ci.trim() && <span style={{ color: "#dc2626", fontSize: "0.75rem" }}>Campo obligatorio</span>}</label>
                <label className="field"><span>Nombre de usuario <span style={{ color: "#dc2626" }}>*</span></span><input className="input" value={wizardNewAdmin.username} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, username: e.target.value }))} />{step2Submitted && !wizardNewAdmin.username.trim() && <span style={{ color: "#dc2626", fontSize: "0.75rem" }}>Campo obligatorio</span>}</label>
                <label className="field"><span>Contraseña <span style={{ color: "#dc2626" }}>*</span></span><input className="input" type="password" value={wizardNewAdmin.password} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, password: e.target.value }))} />{step2Submitted && !wizardNewAdmin.password.trim() && <span style={{ color: "#dc2626", fontSize: "0.75rem" }}>Campo obligatorio</span>}</label>
                <label className="field"><span>Email</span><input className="input" value={wizardNewAdmin.email} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, email: e.target.value }))} /></label>
                <label className="field"><span>Primer nombre <span style={{ color: "#dc2626" }}>*</span></span><input className="input" value={wizardNewAdmin.primerNombre} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, primerNombre: e.target.value }))} />{step2Submitted && !wizardNewAdmin.primerNombre.trim() && <span style={{ color: "#dc2626", fontSize: "0.75rem" }}>Campo obligatorio</span>}</label>
                <label className="field"><span>Segundo nombre</span><input className="input" value={wizardNewAdmin.segundoNombre} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, segundoNombre: e.target.value }))} /></label>
                <label className="field"><span>Apellido paterno <span style={{ color: "#dc2626" }}>*</span></span><input className="input" value={wizardNewAdmin.apellidoPaterno} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, apellidoPaterno: e.target.value }))} />{step2Submitted && !wizardNewAdmin.apellidoPaterno.trim() && <span style={{ color: "#dc2626", fontSize: "0.75rem" }}>Campo obligatorio</span>}</label>
                <label className="field"><span>Apellido materno</span><input className="input" value={wizardNewAdmin.apellidoMaterno} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, apellidoMaterno: e.target.value }))} /></label>
                <label className="field"><span>Telefono</span><input className="input" value={wizardNewAdmin.telefono} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, telefono: e.target.value }))} /></label>
                <label className="field"><span>Fecha de nacimiento <span style={{ color: "#dc2626" }}>*</span></span><input className="input" type="date" value={wizardNewAdmin.fechaNacimiento} onChange={(e) => setWizardNewAdmin((v) => ({ ...v, fechaNacimiento: e.target.value }))} />{step2Submitted && !wizardNewAdmin.fechaNacimiento.trim() && <span style={{ color: "#dc2626", fontSize: "0.75rem" }}>Campo obligatorio</span>}</label>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem' }}><button className="button button--ghost" type="button" onClick={handleCancelWizard}>Cancelar</button><div style={{ display: 'flex', gap: '0.5rem' }}><button className="button button--ghost" type="button" onClick={() => setWizardStep(1)}>Volver</button><button className="button" disabled={saving} type="submit">Continuar</button></div></div>
            </form>
          ) : (
            <div>
              <p style={{ color: 'var(--c-neutral-600)', marginBottom: '1rem' }}>
                Selecciona un administrador inactivo que no tenga sucursal asignada.
              </p>
              <div style={{ maxHeight: '320px', overflowY: 'auto', border: '1px solid var(--c-neutral-200)', borderRadius: '8px', marginBottom: '1rem' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead style={{ position: 'sticky', top: 0, background: 'var(--c-neutral-50)', zIndex: 1 }}>
                    <tr>
                      <th style={{ padding: '0.75rem', textAlign: 'left', fontSize: '0.75rem', color: 'var(--c-neutral-500)', fontWeight: 500 }}>Nombre</th>
                      <th style={{ padding: '0.75rem', textAlign: 'left', fontSize: '0.75rem', color: 'var(--c-neutral-500)', fontWeight: 500 }}>Usuario</th>
                      <th style={{ padding: '0.75rem', textAlign: 'left', fontSize: '0.75rem', color: 'var(--c-neutral-500)', fontWeight: 500 }}>Email</th>
                      <th style={{ padding: '0.75rem', textAlign: 'center', fontSize: '0.75rem', color: 'var(--c-neutral-500)', fontWeight: 500, width: '60px' }}>Seleccionar</th>
                    </tr>
                  </thead>
                  <tbody>
                    {branchAdmins.filter((a) => !a.isActive && a.branchId === null).length === 0 ? (
                      <tr>
                        <td colSpan={4} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--c-neutral-500)' }}>
                          No hay admins inactivos disponibles
                        </td>
                      </tr>
                    ) : (
                      branchAdmins
                        .filter((a) => !a.isActive && a.branchId === null)
                        .map((a) => (
                          <tr key={a.id} style={{ background: selectedInactiveAdminId === a.id ? 'var(--c-primary-50)' : undefined }}>
                            <td style={{ padding: '0.75rem', borderBottom: '1px solid var(--c-neutral-100)' }}>{a.fullName}</td>
                            <td style={{ padding: '0.75rem', borderBottom: '1px solid var(--c-neutral-100)' }}>{a.username}</td>
                            <td style={{ padding: '0.75rem', borderBottom: '1px solid var(--c-neutral-100)' }}>{a.email || '-'}</td>
                            <td style={{ padding: '0.75rem', borderBottom: '1px solid var(--c-neutral-100)', textAlign: 'center' }}>
                              <input
                                type="radio"
                                name="inactiveAdmin"
                                value={a.id}
                                checked={selectedInactiveAdminId === a.id}
                                onChange={() => setSelectedInactiveAdminId(a.id)}
                                style={{ cursor: 'pointer' }}
                              />
                            </td>
                          </tr>
                        ))
                    )}
                  </tbody>
                </table>
              </div>
              {step2Submitted && !selectedInactiveAdminId && (
                <span style={{ color: "#dc2626", fontSize: "0.75rem", display: 'block', marginBottom: '0.75rem' }}>Debes seleccionar un administrador</span>
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem' }}><button className="button button--ghost" type="button" onClick={handleCancelWizard}>Cancelar</button><div style={{ display: 'flex', gap: '0.5rem' }}><button className="button button--ghost" type="button" onClick={() => setWizardStep(1)}>Volver</button><button className="button" disabled={saving} type="button" onClick={() => void handleWizardStep2SelectExisting()}>Continuar</button></div></div>
            </div>
          )}
        </div> : null}
        {wizardStep === 3 ? <form onSubmit={(e) => { e.preventDefault(); setShowWizardConfirmModal(true) }}><div className="form-grid form-grid--three">
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

      {activatingBranch ? <div className="booking-modal-overlay" role="dialog" aria-modal="true" aria-label="Activar sucursal">
        <div className="booking-modal-content" style={{ maxWidth: '720px' }}>
          <header className="booking-modal-header">
            <h2 style={{ margin: 0 }}>Activar sucursal</h2>
            <button className="booking-modal-close" type="button" onClick={() => void handleCancelActivation()}>×</button>
          </header>
          <div className="booking-modal-body" style={{ padding: '1rem 1.5rem' }}>
            <p>Para activar la sucursal <strong>{activatingBranch.nombre}</strong>, seleccioná un administrador de sucursal inactivo que no tenga sucursal asignada.</p>
            <div style={{ maxHeight: '320px', overflowY: 'auto', border: '1px solid var(--c-neutral-200)', borderRadius: '8px', marginBottom: '1rem' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead style={{ position: 'sticky', top: 0, background: 'var(--c-neutral-50)', zIndex: 1 }}>
                  <tr>
                    <th style={{ padding: '0.75rem', textAlign: 'left', fontSize: '0.75rem', color: 'var(--c-neutral-500)', fontWeight: 500 }}>Nombre</th>
                    <th style={{ padding: '0.75rem', textAlign: 'left', fontSize: '0.75rem', color: 'var(--c-neutral-500)', fontWeight: 500 }}>Usuario</th>
                    <th style={{ padding: '0.75rem', textAlign: 'left', fontSize: '0.75rem', color: 'var(--c-neutral-500)', fontWeight: 500 }}>Email</th>
                    <th style={{ padding: '0.75rem', textAlign: 'center', fontSize: '0.75rem', color: 'var(--c-neutral-500)', fontWeight: 500, width: '60px' }}>Seleccionar</th>
                  </tr>
                </thead>
                <tbody>
                  {branchAdmins.filter((a) => !a.isActive && a.branchId === null).length === 0 ? (
                    <tr>
                      <td colSpan={4} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--c-neutral-500)' }}>
                        No hay admins inactivos disponibles
                      </td>
                    </tr>
                  ) : (
                    branchAdmins
                      .filter((a) => !a.isActive && a.branchId === null)
                      .map((a) => (
                        <tr key={a.id} style={{ background: selectedActivatingAdminId === a.id ? 'var(--c-primary-50)' : undefined }}>
                          <td style={{ padding: '0.75rem', borderBottom: '1px solid var(--c-neutral-100)' }}>{a.fullName}</td>
                          <td style={{ padding: '0.75rem', borderBottom: '1px solid var(--c-neutral-100)' }}>{a.username}</td>
                          <td style={{ padding: '0.75rem', borderBottom: '1px solid var(--c-neutral-100)' }}>{a.email || '-'}</td>
                          <td style={{ padding: '0.75rem', borderBottom: '1px solid var(--c-neutral-100)', textAlign: 'center' }}>
                            <input
                              type="radio"
                              name="activatingAdmin"
                              value={a.id}
                              checked={selectedActivatingAdminId === a.id}
                              onChange={() => setSelectedActivatingAdminId(a.id)}
                              style={{ cursor: 'pointer' }}
                            />
                          </td>
                        </tr>
                      ))
                  )}
                </tbody>
              </table>
            </div>
            {selectedActivatingAdminId === null && (
              <span style={{ color: "#dc2626", fontSize: "0.75rem", display: 'block', marginBottom: '0.75rem' }}>Debes seleccionar un administrador</span>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button className="button button--ghost" type="button" onClick={() => void handleCancelActivation()}>Cancelar</button>
              <button className="button" type="button" onClick={() => void handleConfirmActivation()} disabled={saving || selectedActivatingAdminId === null}>Confirmar</button>
            </div>
          </div>
        </div>
      </div> : null}
      </> : null}

      {showWizardConfirmModal ? (
        <div
          className="booking-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Confirmar creación de sucursal"
        >
          <div className="booking-modal-content" style={{ maxWidth: '640px' }}>
            <header className="booking-modal-header">
              <h2 style={{ margin: 0 }}>Confirmar creación de sucursal</h2>
              <button
                className="booking-modal-close"
                type="button"
                onClick={() => setShowWizardConfirmModal(false)}
              >
                ×
              </button>
            </header>
            <div className="booking-modal-body" style={{ padding: '1rem 1.5rem' }}>
              <p style={{ marginTop: 0, color: 'var(--c-neutral-600)' }}>
                Revisa los datos antes de confirmar.
              </p>

              <div style={{ marginBottom: '1rem' }}>
                <h3
                  style={{
                    fontSize: '0.875rem',
                    fontWeight: 600,
                    marginBottom: '0.5rem',
                    color: 'var(--c-neutral-600)',
                  }}
                >
                  Sucursal
                </h3>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '0.5rem',
                    background: 'var(--c-neutral-50)',
                    padding: '0.75rem',
                    borderRadius: '8px',
                  }}
                >
                  <div>
                    <strong>Nombre:</strong> {newBranch.nombre}
                  </div>
                  <div>
                    <strong>Ciudad:</strong> {newBranch.ciudad}
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <strong>Dirección:</strong> {newBranch.direccion}
                  </div>
                </div>
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <h3
                  style={{
                    fontSize: '0.875rem',
                    fontWeight: 600,
                    marginBottom: '0.5rem',
                    color: 'var(--c-neutral-600)',
                  }}
                >
                  Administrador
                </h3>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '0.5rem',
                    background: 'var(--c-neutral-50)',
                    padding: '0.75rem',
                    borderRadius: '8px',
                  }}
                >
                  <div>
                    <strong>Usuario:</strong> {wizardNewAdmin.username}
                  </div>
                  <div>
                    <strong>CI:</strong> {wizardNewAdmin.ci}
                  </div>
                  <div>
                    <strong>Nombre:</strong> {wizardNewAdmin.primerNombre}{' '}
                    {wizardNewAdmin.segundoNombre} {wizardNewAdmin.apellidoPaterno}
                  </div>
                  <div>
                    <strong>Email:</strong> {wizardNewAdmin.email || '-'}
                  </div>
                </div>
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <h3
                  style={{
                    fontSize: '0.875rem',
                    fontWeight: 600,
                    marginBottom: '0.5rem',
                    color: 'var(--c-neutral-600)',
                  }}
                >
                  Tablet
                </h3>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '0.5rem',
                    background: 'var(--c-neutral-50)',
                    padding: '0.75rem',
                    borderRadius: '8px',
                  }}
                >
                  <div>
                    <strong>Nombre:</strong> {wizardTablet.nombre}
                  </div>
                  <div>
                    <strong>Clave:</strong> {wizardTablet.clave}
                  </div>
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: '0.75rem',
                  marginTop: '1.5rem',
                }}
              >
                <button
                  className="button button--ghost"
                  type="button"
                  onClick={() => setShowWizardConfirmModal(false)}
                >
                  Cancelar
                </button>
                <button
                  className="button"
                  type="button"
                  onClick={() => void handleWizardSubmit()}
                  disabled={saving}
                >
                  Confirmar y crear
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {createdBranchInfo ? (
        <div className="booking-modal-overlay" role="dialog" aria-modal="true" aria-label="Sucursal creada">
          <div className="booking-modal-content" style={{ maxWidth: '520px' }}>
            <header className="booking-modal-header">
              <h2 style={{ margin: 0 }}>Sucursal creada exitosamente</h2>
            </header>
            <div className="booking-modal-body" style={{ padding: '1.5rem' }}>
              <p style={{ marginTop: 0, color: 'var(--c-neutral-600)' }}>
                La sucursal <strong>{createdBranchInfo.branchName}</strong> fue creada. Anota las credenciales del tablet antes de continuar.
              </p>

              <div
                style={{
                  background: 'var(--c-neutral-50)',
                  padding: '1rem',
                  borderRadius: '8px',
                  marginBottom: '1rem',
                }}
              >
                <div style={{ marginBottom: '0.5rem' }}>
                  <strong>Código tablet:</strong>
                </div>
                <div
                  style={{
                    fontSize: '1.25rem',
                    fontWeight: 700,
                    fontFamily: 'monospace',
                    background: '#fff',
                    padding: '0.5rem 0.75rem',
                    borderRadius: '6px',
                    border: '1px solid var(--c-neutral-200)',
                    marginBottom: '1rem',
                    wordBreak: 'break-all',
                  }}
                >
                  {createdBranchInfo.tabletCode}
                </div>
                <div style={{ marginBottom: '0.5rem' }}>
                  <strong>Clave tablet:</strong>
                </div>
                <div
                  style={{
                    fontSize: '1.25rem',
                    fontWeight: 700,
                    fontFamily: 'monospace',
                    background: '#fff',
                    padding: '0.5rem 0.75rem',
                    borderRadius: '6px',
                    border: '1px solid var(--c-neutral-200)',
                    wordBreak: 'break-all',
                  }}
                >
                  {createdBranchInfo.tabletClave}
                </div>
              </div>

              <p style={{ fontSize: '0.875rem', color: 'var(--c-neutral-500)', marginBottom: '1rem' }}>
                Con estas credenciales el tablet podrá iniciar sesión. Se recomienda anotar estas credenciales.
              </p>

              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  className="button"
                  type="button"
                  onClick={() => {
                    setCreatedBranchInfo(null)
                    setWizardStep(1)
                    setWizardStep1Completed(false)
                    setWizardStep2Completed(false)
                    setStep1Submitted(false)
                    setStep2Submitted(false)
                    setNewBranch({ nombre: '', ciudad: '', direccion: '' })
                    setWizardTablet({ nombre: '', clave: '' })
                    navigate('/admin/sucursales/editar')
                  }}
                >
                  Continuar
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <ConfirmDialogModal />
    </section>
  )
}
