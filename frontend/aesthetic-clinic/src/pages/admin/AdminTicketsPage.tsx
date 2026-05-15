import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import {
  getOpenPermissionStatus,
  getTickets,
  setSpecialistOpenPermission,
  type PermissionSummary,
  type SpecialistOpenPermission,
  type Ticket,
  type TicketStatus,
} from '../../services/api/tickets'

type MessagingTab = 'PERMISOS' | 'FICHAS'

export function AdminTicketsPage() {
  const [activeTab, setActiveTab] = useState<MessagingTab>('PERMISOS')
  const [status, setStatus] = useState<TicketStatus | ''>('')
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [specialists, setSpecialists] = useState<SpecialistOpenPermission[]>([])
  const [summary, setSummary] = useState<PermissionSummary>('MIXED')

  const loadTickets = async () => setTickets((await getTickets(status || undefined)).tickets)
  const loadPermissions = async () => {
    const data = await getOpenPermissionStatus()
    setSpecialists(data.specialists)
    setSummary(data.summary)
  }

  useEffect(() => { void loadTickets() }, [status])
  useEffect(() => { void loadPermissions() }, [])

  const summaryLabel = useMemo(() => {
    if (summary === 'ALL_ENABLED') return 'Todos los especialistas estan habilitados para abrir fichas.'
    if (summary === 'ALL_BLOCKED') return 'Todos los especialistas estan bloqueados para abrir fichas.'
    return ''
  }, [summary])

  const onMassUpdate = async (enabled: boolean) => {
    const action = enabled ? 'habilitar' : 'bloquear'
    const ok = window.confirm(`¿Seguro que deseas ${action} a TODOS los especialistas para abrir nuevas fichas?`)
    if (!ok) return
    await setSpecialistOpenPermission(enabled)
    await loadPermissions()
  }

  const onSingleUpdate = async (specialistId: number, enabled: boolean) => {
    await setSpecialistOpenPermission(enabled, specialistId)
    await loadPermissions()
  }

  return <div className='page-stack'>
    <PageHeader eyebrow='Administracion' title='Fichas de mensajeria' description='Responde mensajes de especialistas y gestiona estado abierto/cerrado.' />

    <nav className='section-tabs' aria-label='Subpestañas de mensajeria'>
      <button className={`section-tabs__link ${activeTab === 'PERMISOS' ? 'is-active' : ''}`} type='button' onClick={() => setActiveTab('PERMISOS')}>
        Permisos de apertura
      </button>
      <button className={`section-tabs__link ${activeTab === 'FICHAS' ? 'is-active' : ''}`} type='button' onClick={() => setActiveTab('FICHAS')}>
        Listado de fichas
      </button>
    </nav>

    {activeTab === 'PERMISOS' ? (
      <SectionCard eyebrow='Permisos' title='Apertura de fichas por especialistas' description='Control masivo e individual por especialista.'>
        <div style={{display:'flex', gap:'0.5rem', marginBottom:'0.5rem'}}>
          <button className='button' onClick={() => void onMassUpdate(true)}>Habilitar a todos</button>
          <button className='button button--ghost' onClick={() => void onMassUpdate(false)}>Bloquear a todos</button>
        </div>
        {summaryLabel ? <p style={{marginTop:0, color:'var(--c-neutral-700)'}}>{summaryLabel}</p> : null}

        {!specialists.length ? <DataState title='Sin especialistas' message='No hay especialistas activos en esta sucursal.' /> : (
          <div className='table-card'>
            <table>
              <thead><tr><th>Especialista</th><th>Permiso</th><th>Accion</th></tr></thead>
              <tbody>
                {specialists.map((s) => (
                  <tr key={s.specialistId}>
                    <td>{s.specialistName}</td>
                    <td><StatusBadge tone={s.enabled ? 'success' : 'warning'}>{s.enabled ? 'Habilitado' : 'Bloqueado'}</StatusBadge></td>
                    <td style={{display:'flex', gap:'0.5rem'}}>
                      <button className='button button--ghost button--compact' disabled={s.enabled} onClick={() => void onSingleUpdate(s.specialistId, true)}>Habilitar</button>
                      <button className='button button--ghost button--compact' disabled={!s.enabled} onClick={() => void onSingleUpdate(s.specialistId, false)}>Bloquear</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    ) : (
      <SectionCard eyebrow='Bandeja' title='Listado de fichas' description='Filtra y entra al detalle para responder o cerrar/reabrir.'>
        <select className='input' value={status} onChange={(e)=>setStatus(e.target.value as TicketStatus | '')}><option value=''>Todos</option><option value='ABIERTO'>Abierto</option><option value='CERRADO'>Cerrado</option></select>
        <div className='table-card'><table><thead><tr><th>Estado</th><th>Asunto</th><th>Especialista</th><th></th></tr></thead><tbody>
        {tickets.map((t)=><tr key={t.id}><td><StatusBadge tone={t.status === 'ABIERTO' ? 'success':'warning'}>{t.status}</StatusBadge></td><td>{t.subject}</td><td>{t.specialistName}</td><td><Link className='button button--ghost button--compact' to={`/admin/mensajes/${t.id}`}>Abrir</Link></td></tr>)}
        </tbody></table></div>
      </SectionCard>
    )}
  </div>
}
