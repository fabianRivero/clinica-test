import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { getTickets, setSpecialistOpenPermission, type Ticket, type TicketStatus } from '../../services/api/tickets'

export function AdminTicketsPage() {
  const [status, setStatus] = useState<TicketStatus | ''>('')
  const [tickets, setTickets] = useState<Ticket[]>([])

  const load = async () => setTickets((await getTickets(status || undefined)).tickets)
  useEffect(() => { void load() }, [status])

  return <div className='page-stack'>
    <PageHeader eyebrow='Administracion' title='Fichas de mensajeria' description='Responde mensajes de especialistas y gestiona estado abierto/cerrado.' />
    <SectionCard eyebrow='Permisos' title='Apertura de fichas por especialistas' description='Habilita o bloquea abrir nuevas fichas en esta sucursal.'>
      <div style={{display:'flex', gap:'0.5rem'}}><button className='button' onClick={()=>void setSpecialistOpenPermission(true)}>Habilitar</button><button className='button button--ghost' onClick={()=>void setSpecialistOpenPermission(false)}>Bloquear</button></div>
    </SectionCard>
    <SectionCard eyebrow='Bandeja' title='Listado de fichas' description='Filtra y entra al detalle para responder o cerrar/reabrir.'>
      <select className='input' value={status} onChange={(e)=>setStatus(e.target.value as TicketStatus | '')}><option value=''>Todos</option><option value='ABIERTO'>Abierto</option><option value='CERRADO'>Cerrado</option></select>
      <div className='table-card'><table><thead><tr><th>Estado</th><th>Asunto</th><th>Especialista</th><th></th></tr></thead><tbody>
      {tickets.map((t)=><tr key={t.id}><td><StatusBadge tone={t.status === 'ABIERTO' ? 'success':'warning'}>{t.status}</StatusBadge></td><td>{t.subject}</td><td>{t.specialistName}</td><td><Link className='button button--ghost button--compact' to={`/admin/mensajes/${t.id}`}>Abrir</Link></td></tr>)}
      </tbody></table></div>
    </SectionCard>
  </div>
}
