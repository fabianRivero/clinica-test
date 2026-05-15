import { useEffect, useMemo, useState } from 'react'
import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { createTicket, getTicketDetail, getTickets, replyTicket, type Ticket, type TicketMessage } from '../../services/api/tickets'

type MessageAttachment = {
  url: string
  name: string
  isImage: boolean
}

function getFileExtension(fileName: string) {
  const parts = fileName.toLowerCase().split('.')
  return parts.length > 1 ? parts[parts.length - 1] : ''
}

function getFileTypeIcon(fileName: string, isImage: boolean) {
  if (isImage) return '🖼️'
  const ext = getFileExtension(fileName)
  if (ext === 'pdf') return '📄'
  if (['doc', 'docx', 'txt', 'rtf'].includes(ext)) return '📝'
  if (['xls', 'xlsx', 'csv'].includes(ext)) return '📊'
  if (['zip', 'rar', '7z'].includes(ext)) return '🗜️'
  return '📎'
}

function getMessageAttachments(message: TicketMessage): MessageAttachment[] {
  const messageWithAttachment = message as TicketMessage & {
    attachmentUrl?: string
    attachmentName?: string
    attachments?: Array<{ url?: string; name?: string; type?: string; mimeType?: string }>
  }

  const attachments: MessageAttachment[] = []

  if (Array.isArray(messageWithAttachment.attachments)) {
    messageWithAttachment.attachments.forEach((item, index) => {
      if (!item?.url) return
      const fileName = item.name || `Adjunto ${index + 1}`
      const typeHint = (item.type || item.mimeType || '').toLowerCase()
      const isImage = typeHint.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp|svg)$/i.test(fileName)
      attachments.push({ url: item.url, name: fileName, isImage })
    })
  }

  if (messageWithAttachment.attachmentUrl) {
    const fileName = messageWithAttachment.attachmentName || 'Adjunto'
    attachments.push({
      url: messageWithAttachment.attachmentUrl,
      name: fileName,
      isImage: /\.(png|jpe?g|webp|gif|bmp|svg)$/i.test(fileName),
    })
  }

  return attachments
}

export function SpecialistMessagesPage() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [selected, setSelected] = useState<Ticket | null>(null)
  const [messages, setMessages] = useState<TicketMessage[]>([])
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [reply, setReply] = useState('')
  const [previewImage, setPreviewImage] = useState<MessageAttachment | null>(null)

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

  const messageItems = useMemo(
    () => messages.map((message) => ({ message, attachments: getMessageAttachments(message) })),
    [messages],
  )

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
      <div style={{ display: 'grid', gap: '0.85rem' }}>
        {messageItems.map(({ message: m, attachments }) => (
          <article key={m.id} style={{ border: '1px solid var(--border)', borderRadius: '12px', padding: '0.85rem 1rem', background: 'var(--bg-card)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
              <strong>{m.authorName}</strong>
              <StatusBadge tone={m.status === 'RESPONDIDO' ? 'success':'warning'}>{m.status}</StatusBadge>
            </div>
            <p>{m.body}</p>
            {attachments.length ? (
              <div style={{ marginTop: '0.75rem', display: 'grid', gap: '0.6rem' }}>
                {attachments.map((attachment) => (
                  <div key={`${m.id}-${attachment.url}`} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap', border: '1px solid var(--border)', borderRadius: '10px', padding: '0.55rem 0.65rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', minWidth: 0 }}>
                      {attachment.isImage ? (
                        <button
                          type="button"
                          onClick={() => setPreviewImage(attachment)}
                          style={{ border: '1px solid var(--border)', padding: 0, borderRadius: '8px', cursor: 'pointer', background: 'transparent' }}
                        >
                          <img src={attachment.url} alt={attachment.name} style={{ width: '56px', height: '56px', objectFit: 'cover', display: 'block', borderRadius: '8px' }} />
                        </button>
                      ) : (
                        <span style={{ fontSize: '1.3rem' }}>{getFileTypeIcon(attachment.name, attachment.isImage)}</span>
                      )}
                      <div style={{ minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <span>{getFileTypeIcon(attachment.name, attachment.isImage)}</span>
                          <strong style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'inline-block', maxWidth: '320px' }}>{attachment.name}</strong>
                        </div>
                      </div>
                    </div>
                    <a className="button button--ghost button--compact" href={attachment.url} target="_blank" rel="noreferrer" download>
                      Descargar
                    </a>
                  </div>
                ))}
              </div>
            ) : null}
          </article>
        ))}
      </div>
      {selected.status === 'ABIERTO' ? <form className="form-stack" onSubmit={(e)=>{e.preventDefault(); void replyTicket(selected.id, reply).then(()=>openTicket(selected)); setReply('')}}><textarea className="input" rows={3} value={reply} onChange={(e)=>setReply(e.target.value)} /><button className="button" type="submit">Responder</button></form> : <DataState title="Ficha cerrada" message="Solo se puede responder cuando admin la reabre." tone="warning" />}
    </SectionCard> : null}

    {previewImage ? (
      <div className="booking-modal-overlay" role="dialog" aria-modal="true" aria-label="Vista previa de imagen adjunta">
        <div className="booking-modal-content" style={{ maxWidth: '920px' }}>
          <header className="booking-modal-header">
            <div>
              <h2 style={{ margin: 0 }}>Vista previa</h2>
              <p style={{ margin: '0.5rem 0 0', color: 'var(--c-neutral-600)' }}>{previewImage.name}</p>
            </div>
            <button className="booking-modal-close" type="button" onClick={() => setPreviewImage(null)}>×</button>
          </header>
          <div className="booking-modal-body" style={{ padding: '1.5rem', textAlign: 'center' }}>
            <img src={previewImage.url} alt={previewImage.name} style={{ maxWidth: '100%', maxHeight: '70vh', borderRadius: '10px' }} />
            <div style={{ marginTop: '1rem' }}>
              <a className="button button--ghost" href={previewImage.url} target="_blank" rel="noreferrer" download>
                Descargar imagen
              </a>
            </div>
          </div>
        </div>
      </div>
    ) : null}
  </div>
}
