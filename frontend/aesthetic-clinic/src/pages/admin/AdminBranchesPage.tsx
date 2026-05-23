import { useEffect, useMemo, useState } from 'react'

import { AdminBranchTabs } from '../../components/admin/AdminBranchTabs'
import { changeAdminBranchManager, createAdminBranch, getAdminBranchAuditLogs, getAdminBranchDeactivationImpact, getAdminBranchesManagement, toggleAdminBranch, updateAdminBranch } from '../../services/api/admin'

type BranchRow = {
  id: number
  nombre: string
  ciudad: string
  direccion: string
  activa: boolean
  admin: { id: number; nombre: string; username: string } | null
}

export function AdminBranchesPage({ view = 'edit' }: { view?: 'edit' | 'create' }) {
  const [rows, setRows] = useState<BranchRow[]>([])
  const [status, setStatus] = useState<'all' | 'active' | 'inactive'>('all')
  const [city, setCity] = useState('')
  const [adminName, setAdminName] = useState('')
  const [branchId, setBranchId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [newBranch, setNewBranch] = useState({ nombre: '', ciudad: '', direccion: '' })
  const [editingBranch, setEditingBranch] = useState<BranchRow | null>(null)
  const [editForm, setEditForm] = useState({ nombre: '', ciudad: '', direccion: '' })
  const [changingAdminBranch, setChangingAdminBranch] = useState<BranchRow | null>(null)
  const [changeAdminStep, setChangeAdminStep] = useState<1 | 2>(1)
  const [newAdminUserId, setNewAdminUserId] = useState('')
  const [auditRows, setAuditRows] = useState<Array<{ id: number; createdAt: string; action: string; detail: string; branchName: string; actor: string }>>([])

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

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await createAdminBranch(newBranch)
      setNewBranch({ nombre: '', ciudad: '', direccion: '' })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear la sucursal')
    } finally {
      setSaving(false)
    }
  }

  async function handleToggle(row: BranchRow) {
    try {
      if (row.activa) {
        const impact = await getAdminBranchDeactivationImpact(row.id)
        const p = impact.impact
        const hasPending = p.appointments_pending + p.payments_pending + p.processes_pending > 0
        if (hasPending) {
          const ok = window.confirm(
            `Hay pendientes en la sucursal:\n- Citas: ${p.appointments_pending}\n- Pagos: ${p.payments_pending}\n- Procesos: ${p.processes_pending}\n\n¿Deseas desactivar de todas formas?`,
          )
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
    setChangeAdminStep(1)
    setNewAdminUserId('')
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
      await changeAdminBranchManager(changingAdminBranch.id, parsedId)
      setChangingAdminBranch(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo cambiar el administrador')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="page-stack">
      <header className="page-header">
        <h1>Gestion de sucursales</h1>
        <p>Modulo para administracion general de sucursales.</p>
      </header>

      <AdminBranchTabs />

      {error ? <p className="error-text">{error}</p> : null}

      {view === 'create' ? <form className="card" onSubmit={handleCreate}>
        <h3>Crear sucursal</h3>
        <div className="form-grid form-grid--three">
          <input className="input" placeholder="Nombre" value={newBranch.nombre} onChange={(e) => setNewBranch((v) => ({ ...v, nombre: e.target.value }))} />
          <input className="input" placeholder="Ciudad" value={newBranch.ciudad} onChange={(e) => setNewBranch((v) => ({ ...v, ciudad: e.target.value }))} />
          <input className="input" placeholder="Direccion" value={newBranch.direccion} onChange={(e) => setNewBranch((v) => ({ ...v, direccion: e.target.value }))} />
        </div>
        <button className="button" disabled={saving} type="submit">Crear</button>
      </form> : null}

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

      <div className="card">
        <table className="table">
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
                  <button className="button button--ghost" type="button" onClick={() => void handleToggle(row)}>{row.activa ? 'Desactivar' : 'Activar'}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Historial de cambios</h3>
        <table className="table">
          <thead><tr><th>Fecha</th><th>Sucursal</th><th>Accion</th><th>Detalle</th><th>Actor</th></tr></thead>
          <tbody>
            {auditRows.map((row) => (
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
            <button className="booking-modal-close" type="button" onClick={() => setChangingAdminBranch(null)}>×</button>
          </header>
          <div className="booking-modal-body" style={{ padding: '1rem 1.5rem' }}>
            {changeAdminStep === 1 ? <>
              <p><strong>Paso 1:</strong> Sucursal seleccionada: {changingAdminBranch.nombre}</p>
              <p style={{ color: 'var(--c-neutral-600)' }}>Pasa al Paso 2 para ingresar el ID del administrador de sucursal a asignar.</p>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button className="button button--ghost" type="button" onClick={() => setChangingAdminBranch(null)}>Cancelar</button>
                <button className="button" type="button" onClick={() => setChangeAdminStep(2)}>Siguiente</button>
              </div>
            </> : <>
              <p><strong>Paso 2:</strong> Ingresa el <code>rawId</code> del administrador de sucursal.</p>
              <input className="input" placeholder="ID admin sucursal (rawId)" value={newAdminUserId} onChange={(e) => setNewAdminUserId(e.target.value)} />
              <p style={{ marginTop: '0.75rem', color: 'var(--c-neutral-600)' }}>
                Aviso: si el admin elegido está activo en otra sucursal, se hará intercambio; si está inactivo y sin sucursal, se activará y el admin actual quedará inactivo.
              </p>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem' }}>
                <button className="button button--ghost" type="button" onClick={() => setChangeAdminStep(1)}>Volver</button>
                <button className="button" type="button" onClick={() => void handleConfirmAdminChange()} disabled={saving}>Confirmar cambio</button>
              </div>
            </>}
          </div>
        </div>
      </div> : null}
      </> : null}
    </section>
  )
}
