import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { closeTicket, getTicketDetail, reopenTicket, replyTicket, type Ticket, type TicketMessage } from '../../services/api/tickets'

export function AdminTicketDetailPage() {
  const { ticketId } = useParams()
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [messages, setMessages] = useState<TicketMessage[]>([])
  const [reply, setReply] = useState('')
  const load = async () => {
    if (!ticketId) return
    const data = await getTicketDetail(Number(ticketId))
    setTicket(data.ticket)
    setMessages(data.messages)
  }
  useEffect(() => { void load() }, [ticketId])
  if (!ticket) return null
  return <div className='page-stack'>
    <PageHeader eyebrow='Administracion' title={ticket.subject} description={`Ficha ${ticket.status}`} />
    <SectionCard eyebrow='Estado' title='Gestion de ficha' description='Cerrar o reabrir segun corresponda.'>
      <div style={{display:'flex', gap:'0.5rem'}}>
        <StatusBadge tone={ticket.status === 'ABIERTO' ? 'success':'warning'}>{ticket.status}</StatusBadge>
        {ticket.status === 'ABIERTO' ? <button className='button button--ghost' onClick={()=>void closeTicket(ticket.id).then(load)}>Cerrar ficha</button> : <button className='button' onClick={()=>void reopenTicket(ticket.id).then(load)}>Reabrir ficha</button>}
      </div>
    </SectionCard>
    <SectionCard eyebrow='Mensajes' title='Hilo completo' description='Estado de mensajes ENVIADO/RESPONDIDO.'>
      {messages.map((m)=><div key={m.id}><strong>{m.authorName}</strong> <StatusBadge tone={m.status === 'RESPONDIDO' ? 'success':'warning'}>{m.status}</StatusBadge><p>{m.body}</p></div>)}
      {ticket.status === 'ABIERTO' ? <form className='form-stack' onSubmit={(e)=>{e.preventDefault(); void replyTicket(ticket.id, reply).then(load); setReply('')}}><textarea className='input' rows={4} value={reply} onChange={(e)=>setReply(e.target.value)} /><button className='button' type='submit'>Responder</button></form> : <DataState title='Ficha cerrada' message='Reabre para permitir respuestas.' tone='warning' />}
    </SectionCard>
  </div>
}
