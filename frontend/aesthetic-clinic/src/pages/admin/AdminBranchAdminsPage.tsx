import { useEffect, useState } from 'react'

import { createAdminBranchAdmin, getAdminBranchAdmins, toggleAdminBranchAdmin, updateAdminBranchAdmin } from '../../services/api/admin'

type AdminItem = {
  id: number
  username: string
  fullName: string
  email: string
  isActive: boolean
  branchId: number | null
  branchName: string
}

export function AdminBranchAdminsPage({ view }: { view: 'create' | 'manage' }) {
  const [rows, setRows] = useState<AdminItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ username: '', email: '', primerNombre: '', segundoNombre: '', apellidoPaterno: '', apellidoMaterno: '', password: '' })

  async function load() {
    try {
      setError(null)
      const res = await getAdminBranchAdmins()
      setRows(res.admins)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo cargar admins de sucursal')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await createAdminBranchAdmin(form)
      setForm({ username: '', email: '', primerNombre: '', segundoNombre: '', apellidoPaterno: '', apellidoMaterno: '', password: '' })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear admin de sucursal')
    } finally {
      setSaving(false)
    }
  }

  async function handleToggle(row: AdminItem) {
    setSaving(true)
    try {
      await toggleAdminBranchAdmin(row.id, !row.isActive)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo cambiar estado')
    } finally {
      setSaving(false)
    }
  }

  async function handleQuickEmailSave(row: AdminItem, email: string) {
    try {
      await updateAdminBranchAdmin(row.id, { email })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo actualizar admin')
    }
  }

  return (
    <section className="page-stack">
      <header className="page-header">
        <h1>Administradores de sucursal</h1>
        <p>Gestionados solo por administrador principal.</p>
      </header>

      {error ? <p className="error-text">{error}</p> : null}

      {view === 'create' ? (
        <form className="card" onSubmit={handleCreate}>
          <h3>Crear admin de sucursal (inactivo por defecto)</h3>
          <div className="form-grid form-grid--three">
            <input className="input" placeholder="Username" value={form.username} onChange={(e) => setForm((v) => ({ ...v, username: e.target.value }))} />
            <input className="input" placeholder="Email" value={form.email} onChange={(e) => setForm((v) => ({ ...v, email: e.target.value }))} />
            <input className="input" placeholder="Password" type="password" value={form.password} onChange={(e) => setForm((v) => ({ ...v, password: e.target.value }))} />
            <input className="input" placeholder="Primer nombre" value={form.primerNombre} onChange={(e) => setForm((v) => ({ ...v, primerNombre: e.target.value }))} />
            <input className="input" placeholder="Segundo nombre" value={form.segundoNombre} onChange={(e) => setForm((v) => ({ ...v, segundoNombre: e.target.value }))} />
            <input className="input" placeholder="Apellido paterno" value={form.apellidoPaterno} onChange={(e) => setForm((v) => ({ ...v, apellidoPaterno: e.target.value }))} />
            <input className="input" placeholder="Apellido materno" value={form.apellidoMaterno} onChange={(e) => setForm((v) => ({ ...v, apellidoMaterno: e.target.value }))} />
          </div>
          <button className="button" type="submit" disabled={saving}>Crear admin sucursal</button>
        </form>
      ) : null}

      {view === 'manage' ? (
        <div className="card">
          <h3>Gestionar admins de sucursal</h3>
          <table className="table">
            <thead><tr><th>Usuario</th><th>Nombre</th><th>Email</th><th>Sucursal</th><th>Estado</th><th>Acciones</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.username}</td>
                  <td>{row.fullName}</td>
                  <td><input className="input" defaultValue={row.email} onBlur={(e) => void handleQuickEmailSave(row, e.target.value)} /></td>
                  <td>{row.branchName}</td>
                  <td>{row.isActive ? 'Activo' : 'Inactivo'}</td>
                  <td><button className="button button--ghost" type="button" onClick={() => void handleToggle(row)}>{row.isActive ? 'Inactivar' : 'Activar'}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
