import { useEffect, useState } from 'react'
import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { createTicket, getTicketDetail, getTickets, replyTicket, type Ticket, type TicketMessage } from '../../services/api/tickets'

export function SpecialistMessagesPage() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [selected, setSelected] = useState<Ticket | null>(null)
  const [messages, setMessages] = useState<TicketMessage[]>([])
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [reply, setReply] = useState('')

  const load = async () => {
    const data = await getTickets()
    setTickets(data.tickets)
  }

  useEffect(() => { void load() }, [])

  const openTicket = async (ticket: Ticket) => {
    setSelected(ticket)
    const data = await getTicketDetail(ticket.id)
    setMessages(data.messages)
  }

  return <div className="page-stack">
    <PageHeader eyebrow="Portal de especialista" title="Mensajeria interna" description="Fichas con estado abierto/cerrado y mensajes enviado/respondido." />
    <SectionCard eyebrow="Nueva ficha" title="Abrir comunicacion" description="Crea una ficha nueva con asunto y mensaje.">
      <form className="form-stack" onSubmit={(e)=>{e.preventDefault(); void createTicket({ subject, message: body }).then(()=>{setSubject('');setBody('');void load()})}}>
        <div className="form-group"><label>Asunto</label><input className="input" value={subject} onChange={(e)=>setSubject(e.target.value)} /></div>
        <div className="form-group"><label>Mensaje</label><textarea className="input" rows={4} value={body} onChange={(e)=>setBody(e.target.value)} /></div>
        <button className="button" type="submit">Crear ficha</button>
      </form>
    </SectionCard>
    <SectionCard eyebrow="Bandeja" title="Mis fichas" description="Selecciona una ficha para revisar y responder.">
      {!tickets.length ? <DataState title="Sin fichas" message="Aun no creaste fichas." /> : <div className="table-card"><table><thead><tr><th>Estado</th><th>Asunto</th><th>Especialista</th><th>Accion</th></tr></thead><tbody>
      {tickets.map((t)=><tr key={t.id}><td><StatusBadge tone={t.status === 'ABIERTO' ? 'success' : 'warning'}>{t.status}</StatusBadge></td><td>{t.subject}</td><td>{t.specialistName}</td><td><button className="button button--ghost button--compact" onClick={()=>void openTicket(t)}>Ver</button></td></tr>)}
      </tbody></table></div>}
    </SectionCard>
    {selected ? <SectionCard eyebrow="Detalle" title={selected.subject} description={`Ficha ${selected.status}`}>
      {messages.map((m)=><div key={m.id}><strong>{m.authorName}</strong> · <StatusBadge tone={m.status === 'RESPONDIDO' ? 'success':'warning'}>{m.status}</StatusBadge><p>{m.body}</p></div>)}
      {selected.status === 'ABIERTO' ? <form className="form-stack" onSubmit={(e)=>{e.preventDefault(); void replyTicket(selected.id, reply).then(()=>openTicket(selected)); setReply('')}}><textarea className="input" rows={3} value={reply} onChange={(e)=>setReply(e.target.value)} /><button className="button" type="submit">Responder</button></form> : <DataState title="Ficha cerrada" message="Solo se puede responder cuando admin la reabre." tone="warning" />}
    </SectionCard> : null}
  </div>
}
