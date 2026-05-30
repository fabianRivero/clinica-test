import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AdminStaffTabs } from '../../components/admin/AdminStaffTabs'
import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useNotifications } from '../../providers/NotificationProvider'

import { createAdminBranchAdmin, getAdminBranchAdmins } from '../../services/api/admin'

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
  const { showNotification } = useNotifications()
  const navigate = useNavigate()
  const [rows, setRows] = useState<AdminItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [userEdited, setUserEdited] = useState({ username: false, password: false })
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    ci: '',
    username: '',
    email: '',
    telefono: '',
    primerNombre: '',
    segundoNombre: '',
    apellidoPaterno: '',
    apellidoMaterno: '',
    password: '',
    fechaNacimiento: '',
  })

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
      showNotification({ title: 'Administrador creado', message: 'El admin de sucursal se creo correctamente.', tone: 'success' })
      setUserEdited({ username: false, password: false })
      setForm({ ci: '', username: '', email: '', telefono: '', primerNombre: '', segundoNombre: '', apellidoPaterno: '', apellidoMaterno: '', password: '', fechaNacimiento: '' })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear admin de sucursal')
      showNotification({
        title: 'No se pudo crear',
        message: err instanceof Error ? err.message : 'No se pudo crear admin de sucursal.',
        tone: 'danger',
      })
    } finally {
      setSaving(false)
    }
  }


  return (
    <section className="page-stack">
      <PageHeader
        eyebrow="Equipo clinico"
        title="Administradores de sucursal"
        description="Gestionados solo por administrador principal."
      />
      <AdminStaffTabs />

      {error ? <p className="error-text">{error}</p> : null}

      {view === 'create' ? (
        <SectionCard
          eyebrow="Edicion"
          title="Crear admin de sucursal"
          description="Crea un admin de sucursal (inactivo por defecto)."
        >
        <form className="form-grid" onSubmit={handleCreate}>
            <label className="field">
              <span>CI <span style={{ color: 'var(--color-danger, #d42626)' }}>*</span></span>
              <input className="input" required value={form.ci} onChange={(e) => {
                const ci = e.target.value
                setForm((v) => ({
                  ...v,
                  ci,
                  username: userEdited.username ? v.username : ci,
                  password: userEdited.password ? v.password : ci,
                }))
              }} />
            </label>
            <label className="field">
              <span>Nombre de usuario <span style={{ color: 'var(--color-danger, #d42626)' }}>*</span></span>
              <input className="input" required value={form.username} onChange={(e) => {
                setUserEdited((v) => ({ ...v, username: true }))
                setForm((v) => ({ ...v, username: e.target.value }))
              }} />
            </label>
            <label className="field">
              <span>Email</span>
              <input className="input" type="email" value={form.email} onChange={(e) => setForm((v) => ({ ...v, email: e.target.value }))} />
            </label>
            <label className="field">
              <span>Contraseña <span style={{ color: 'var(--color-danger, #d42626)' }}>*</span></span>
              <input className="input" type="password" required               value={form.password}
              onChange={(e) => {
                setUserEdited(() => ({ username: true, password: true }))
                setForm((prev) => ({ ...prev, password: e.target.value }))
              }} />
            </label>
            <label className="field">
              <span>Primer nombre <span style={{ color: 'var(--color-danger, #d42626)' }}>*</span></span>
              <input className="input" required value={form.primerNombre} onChange={(e) => setForm((v) => ({ ...v, primerNombre: e.target.value }))} />
            </label>
            <label className="field">
              <span>Segundo nombre</span>
              <input className="input" value={form.segundoNombre} onChange={(e) => setForm((v) => ({ ...v, segundoNombre: e.target.value }))} />
            </label>
            <label className="field">
              <span>Apellido paterno <span style={{ color: 'var(--color-danger, #d42626)' }}>*</span></span>
              <input className="input" required value={form.apellidoPaterno} onChange={(e) => setForm((v) => ({ ...v, apellidoPaterno: e.target.value }))} />
            </label>
            <label className="field">
              <span>Apellido materno</span>
              <input className="input" value={form.apellidoMaterno} onChange={(e) => setForm((v) => ({ ...v, apellidoMaterno: e.target.value }))} />
            </label>
            <label className="field">
              <span>Telefono</span>
              <input className="input" type="tel" inputMode="numeric" pattern="[0-9]+" value={form.telefono} onChange={(e) => setForm((v) => ({ ...v, telefono: e.target.value }))} />
            </label>
            <label className="field">
              <span>Fecha de nacimiento <span style={{ color: 'var(--color-danger, #d42626)' }}>*</span></span>
              <input className="input" type="date" required value={form.fechaNacimiento} onChange={(e) => setForm((v) => ({ ...v, fechaNacimiento: e.target.value }))} />
            </label>
          <div className="form-actions field--full">
            <button className="button button--primary" type="submit" disabled={saving}>Crear admin sucursal</button>
          </div>
        </form>
        </SectionCard>
      ) : null}

      {view === 'manage' ? (
        <SectionCard
          eyebrow="Edicion"
          title="Admins de sucursal actuales"
          description="Seguimiento de admins creados y sucursal asignada. El estado se gestiona al asignar o retirar sucursal."
        >
          {rows.length ? (
            <div className="catalog-admin-grid">
              {rows.map((row) => (
                <article className="catalog-admin-card" key={row.id}>
                  <div className="catalog-admin-card__content">
                    <div className="catalog-admin-card__header">
                      <h3>{row.fullName}</h3>
                      <div className="table-actions">
                        <StatusBadge tone={row.isActive ? 'success' : 'neutral'}>
                          {row.isActive ? 'Activo' : 'Inactivo'}
                        </StatusBadge>
                      </div>
                    </div>

                    <div className="table-muted">Usuario: {row.username}</div>
                    <div className="table-muted">Sucursal: {row.branchName || 'Sin sucursal'}</div>

                    <div className="catalog-admin-card__actions">
                      <button className="button button--ghost button--compact" type="button" onClick={() => navigate(`/admin/equipo/admin-sucursal/${row.id}`)}>Detalles</button>
                    </div>

                  </div>
                </article>
              ))}
            </div>
          ) : (
            <DataState
              title="Sin admins de sucursal"
              message="Todavia no hay administradores de sucursal registrados en la base conectada."
            />
          )}
        </SectionCard>
      ) : null}
    </section>
  )
}
