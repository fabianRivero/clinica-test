import { useEffect, useMemo, useState } from 'react'

import { createAdminBranch, getAdminBranchDeactivationImpact, getAdminBranchesManagement, toggleAdminBranch, updateAdminBranch } from '../../services/api/admin'

type BranchRow = {
  id: number
  nombre: string
  ciudad: string
  direccion: string
  activa: boolean
  admin: { id: number; nombre: string; username: string } | null
}

export function AdminBranchesPage() {
  const [rows, setRows] = useState<BranchRow[]>([])
  const [status, setStatus] = useState<'all' | 'active' | 'inactive'>('all')
  const [city, setCity] = useState('')
  const [adminName, setAdminName] = useState('')
  const [branchId, setBranchId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [newBranch, setNewBranch] = useState({ nombre: '', ciudad: '', direccion: '' })

  const branchOptions = useMemo(() => rows.map((b) => ({ id: b.id, name: b.nombre })), [rows])

  async function load() {
    try {
      setError(null)
      const response = await getAdminBranchesManagement({ status, city: city || undefined, adminName: adminName || undefined, branchId })
      setRows(response.branches)
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

  return (
    <section className="page-stack">
      <header className="page-header">
        <h1>Gestion de sucursales</h1>
        <p>Modulo para administracion general de sucursales.</p>
      </header>

      {error ? <p className="error-text">{error}</p> : null}

      <form className="card" onSubmit={handleCreate}>
        <h3>Crear sucursal</h3>
        <div className="form-grid form-grid--three">
          <input className="input" placeholder="Nombre" value={newBranch.nombre} onChange={(e) => setNewBranch((v) => ({ ...v, nombre: e.target.value }))} />
          <input className="input" placeholder="Ciudad" value={newBranch.ciudad} onChange={(e) => setNewBranch((v) => ({ ...v, ciudad: e.target.value }))} />
          <input className="input" placeholder="Direccion" value={newBranch.direccion} onChange={(e) => setNewBranch((v) => ({ ...v, direccion: e.target.value }))} />
        </div>
        <button className="button" disabled={saving} type="submit">Crear</button>
      </form>

      <div className="card">
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
                <td><input className="input" defaultValue={row.nombre} onBlur={(e) => void updateAdminBranch(row.id, { nombre: e.target.value })} /></td>
                <td><input className="input" defaultValue={row.ciudad} onBlur={(e) => void updateAdminBranch(row.id, { ciudad: e.target.value })} /></td>
                <td><input className="input" defaultValue={row.direccion} onBlur={(e) => void updateAdminBranch(row.id, { direccion: e.target.value })} /></td>
                <td>{row.admin?.nombre || '-'}</td>
                <td>{row.activa ? 'Activa' : 'Inactiva'}</td>
                <td><button className="button button--ghost" type="button" onClick={() => void handleToggle(row)}>{row.activa ? 'Desactivar' : 'Activar'}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
