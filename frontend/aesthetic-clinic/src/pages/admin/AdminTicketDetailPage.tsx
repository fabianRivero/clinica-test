import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { closeTicket, getTicketDetail, replyTicket, reopenTicket, type Ticket, type TicketMessage } from '../../services/api/tickets'
import { useNotifications } from '../../providers/NotificationProvider'

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
  const { showNotification } = useNotifications()
  const [reply, setReply] = useState('')
  const [isReplyModalOpen, setIsReplyModalOpen] = useState(false)
  const [replyFiles, setReplyFiles] = useState<File[]>([])
  const [isSendingReply, setIsSendingReply] = useState(false)
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

      <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'flex-end' }}>
        <button className='button' type='button' disabled={ticket.status !== 'ABIERTO'} onClick={() => setIsReplyModalOpen(true)}>Responder</button>
      </div>
    </SectionCard>


    {isReplyModalOpen ? (
      <div className="booking-modal-overlay" role="dialog" aria-modal="true" aria-label="Responder ficha">
        <div className="booking-modal-content" style={{ maxWidth: '760px' }}>
          <header className="booking-modal-header">
            <div>
              <h2 style={{ margin: 0 }}>Responder ficha</h2>
              <p style={{ margin: '0.5rem 0 0', color: 'var(--c-neutral-600)' }}>Formato tipo correo interno.</p>
            </div>
            <button className="booking-modal-close" type="button" onClick={() => setIsReplyModalOpen(false)}>×</button>
          </header>
          <div className="booking-modal-body" style={{ padding: '1.5rem' }}>
            <form className="form-stack" onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault()
              if (!reply.trim()) {
                showNotification({ title: 'Mensaje requerido', message: 'Debes escribir un mensaje para responder.', tone: 'warning' })
                return
              }
              const confirmSend = window.confirm('¿Deseas enviar esta respuesta ahora?')
              if (!confirmSend) return
              setIsSendingReply(true)
              void replyTicket(ticket.id, reply.trim()).then(async () => {
                await load()
                setReply('')
                setReplyFiles([])
                setIsReplyModalOpen(false)
                showNotification({ title: 'Respuesta enviada', message: 'El mensaje se envio correctamente.', tone: 'success' })
              }).catch((error: unknown) => {
                showNotification({ title: 'No se pudo enviar', message: error instanceof Error ? error.message : 'Ocurrio un error al enviar la respuesta.', tone: 'danger' })
              }).finally(() => setIsSendingReply(false))
            }}>
              <label className="field">
                <span>Para</span>
                <input className="input" value={ticket.specialistName} readOnly />
              </label>
              <label className="field">
                <span>Asunto</span>
                <input className="input" value={`Re: ${ticket.subject}`} readOnly />
              </label>
              <label className="field">
                <span>Mensaje</span>
                <textarea className="input" rows={7} value={reply} onChange={(e) => setReply(e.target.value)} required />
              </label>
              <label className="field">
                <span>Adjuntar documentos o imagenes</span>
                <input className="input" type="file" multiple accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt" onChange={(event) => setReplyFiles(Array.from(event.target.files ?? []))} />
                {replyFiles.length > 0 ? <small style={{ color: 'var(--c-neutral-600)' }}>{replyFiles.length} archivo(s) seleccionado(s).</small> : null}
              </label>
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                <button type="button" className="button button--ghost" onClick={() => setIsReplyModalOpen(false)}>Cancelar</button>
                <button type="submit" className="button" disabled={isSendingReply}>{isSendingReply ? 'Enviando...' : 'Enviar respuesta'}</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    ) : null}

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
