import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { closeTicket, getTicketDetail, reopenTicket, replyTicket, type Ticket, type TicketMessage } from '../../services/api/tickets'

type MessageAttachment = {
  url: string
  name: string
  isImage: boolean
}

function formatDateTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('es-BO', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
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

export function AdminTicketDetailPage() {
  const { ticketId } = useParams()
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [messages, setMessages] = useState<TicketMessage[]>([])
  const [reply, setReply] = useState('')
  const [previewImage, setPreviewImage] = useState<MessageAttachment | null>(null)

  const load = async () => {
    if (!ticketId) return
    const data = await getTicketDetail(Number(ticketId))
    setTicket(data.ticket)
    setMessages(data.messages)
  }

  useEffect(() => {
    void load()
  }, [ticketId])

  const messageItems = useMemo(
    () => messages.map((message) => ({ message, attachments: getMessageAttachments(message) })),
    [messages],
  )

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
      <div style={{ display: 'grid', gap: '0.85rem' }}>
        {messageItems.map(({ message: m, attachments }) => (
          <article key={m.id} style={{ border: '1px solid var(--border)', borderRadius: '12px', padding: '0.85rem 1rem', background: 'var(--bg-card)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
              <strong>{m.authorName}</strong>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <small style={{ color: 'var(--c-neutral-600)' }}>{formatDateTime(m.createdAt)}</small>
                <StatusBadge tone={m.status === 'RESPONDIDO' ? 'success':'warning'}>{m.status}</StatusBadge>
              </div>
            </div>
            <p style={{ margin: '0.75rem 0 0' }}>{m.body}</p>

            {attachments.length ? (
              <div style={{ marginTop: '0.75rem', display: 'grid', gap: '0.6rem' }}>
                {attachments.map((attachment) => (
                  <div key={`${m.id}-${attachment.url}`} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                    {attachment.isImage ? (
                      <button
                        type="button"
                        onClick={() => setPreviewImage(attachment)}
                        style={{ border: '1px solid var(--border)', padding: 0, borderRadius: '8px', cursor: 'pointer', background: 'transparent' }}
                      >
                        <img src={attachment.url} alt={attachment.name} style={{ width: '72px', height: '72px', objectFit: 'cover', display: 'block', borderRadius: '8px' }} />
                      </button>
                    ) : null}
                    <a className="button button--ghost button--compact" href={attachment.url} target="_blank" rel="noreferrer" download>
                      Descargar {attachment.name}
                    </a>
                  </div>
                ))}
              </div>
            ) : null}
          </article>
        ))}
      </div>

      {ticket.status === 'ABIERTO' ? <form className='form-stack' onSubmit={(e)=>{e.preventDefault(); void replyTicket(ticket.id, reply).then(load); setReply('')}}><textarea className='input' rows={4} value={reply} onChange={(e)=>setReply(e.target.value)} /><button className='button' type='submit'>Responder</button></form> : <DataState title='Ficha cerrada' message='Reabre para permitir respuestas.' tone='warning' />}
    </SectionCard>

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
