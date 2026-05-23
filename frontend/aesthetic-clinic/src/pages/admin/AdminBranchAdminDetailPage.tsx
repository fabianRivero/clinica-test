import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AdminStaffTabs } from '../../components/admin/AdminStaffTabs'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { getAdminBranchAdminDetail, updateAdminBranchAdmin } from '../../services/api/admin'

type FormState = {username:string; email:string; telefono:string; fechaNacimiento:string; password:string}

export function AdminBranchAdminDetailPage() {
  const { userId } = useParams()
  const navigate = useNavigate()
  const [form, setForm] = useState<FormState>({ username:'', email:'', telefono:'', fechaNacimiento:'', password:'' })
  const [fullName, setFullName] = useState('')
  const [branchName, setBranchName] = useState('')
  const [isActive, setIsActive] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { void (async () => {
    if (!userId) return
    try {
      const res = await getAdminBranchAdminDetail(Number(userId))
      const a = res.admin
      setFullName(a.fullName)
      setBranchName(a.branchName || 'Sin sucursal')
      setIsActive(Boolean(a.isActive))
      setForm({ username: a.username || '', email: a.email || '', telefono: a.telefono || '', fechaNacimiento: a.fechaNacimiento || '', password: '' })
    } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo cargar detalle') }
  })() }, [userId])

  async function onSave(e: React.FormEvent) {
    e.preventDefault()
    if (!userId) return
    setSaving(true)
    setError(null)
    try {
      await updateAdminBranchAdmin(Number(userId), form)
      navigate('/admin/equipo/admin-sucursal/gestionar')
    } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo guardar') } finally { setSaving(false) }
  }

  return <section className='page-stack'>
    <PageHeader eyebrow='Equipo clinico' title='Detalle admin sucursal' description='Informacion completa y edicion permitida.' />
    <AdminStaffTabs />
    {error ? <p className='error-text'>{error}</p> : null}
    <SectionCard eyebrow='Edicion' title={fullName || 'Admin de sucursal'} description='Solo se puede editar usuario, email, contraseña (opcional) y telefono.'>
      <form className='form-grid' onSubmit={onSave}>
        <label className='field'><span>ID</span><input className='input' value={userId || ''} readOnly /></label>
        <label className='field'><span>Nombre completo</span><input className='input' value={fullName} readOnly /></label>
        <label className='field'><span>Sucursal asignada</span><input className='input' value={branchName} readOnly /></label>
        <label className='field'><span>Estado</span><input className='input' value={isActive ? 'Activo' : 'Inactivo'} readOnly /></label>
        <label className='field'><span>Nombre de usuario</span><input className='input' required value={form.username} onChange={(e)=>setForm(v=>({...v, username:e.target.value}))} /></label>
        <label className='field'><span>Email</span><input className='input' value={form.email} onChange={(e)=>setForm(v=>({...v, email:e.target.value}))} /></label>
        <label className='field'><span>Nueva contraseña (opcional)</span><input className='input' type='password' value={form.password} onChange={(e)=>setForm(v=>({...v, password:e.target.value}))} /></label>
        <label className='field'><span>Telefono</span><input className='input' value={form.telefono} onChange={(e)=>setForm(v=>({...v, telefono:e.target.value}))} /></label>
        <label className='field'><span>Fecha de nacimiento</span><input className='input' type='date' value={form.fechaNacimiento} disabled /></label>
        <div className='form-actions field--full'><button className='button button--primary' disabled={saving} type='submit'>Guardar cambios</button></div>
      </form>
    </SectionCard>
  </section>
}
