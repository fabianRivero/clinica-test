import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { closeTicket, getTicketDetail, replyTicket, reopenTicket, type Ticket, type TicketMessage } from '../../services/api/tickets'
import { useConfirmDialog } from '../../hooks/useConfirmDialog'
import { useNotifications } from '../../providers/NotificationProvider'
import { useBranchContext } from '../../providers/BranchProvider'
import { useAuth } from '../../providers/AuthProvider'

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

export function AdminTicketDetailPage() {
  const { ticketId } = useParams()
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [messages, setMessages] = useState<TicketMessage[]>([])
  const { showNotification } = useNotifications()
  const { confirm, ConfirmDialog: ConfirmDialogModal } = useConfirmDialog()
  const [reply, setReply] = useState('')
  const [isReplyModalOpen, setIsReplyModalOpen] = useState(false)
  const [replyFiles, setReplyFiles] = useState<File[]>([])
  const [isSendingReply, setIsSendingReply] = useState(false)
  const [previewImage, setPreviewImage] = useState<MessageAttachment | null>(null)
  const { activeBranch } = useBranchContext()
  const { user } = useAuth()
  const branchId = activeBranch?.id ?? null

  const load = async () => {
    if (!ticketId) return
    const data = await getTicketDetail(Number(ticketId))
    setTicket(data.ticket)
    setMessages(data.messages)
  }

  useEffect(() => {
    void load()
  }, [ticketId, branchId])

  const messageItems = useMemo(
    () => messages.map((message) => ({ message, attachments: getMessageAttachments(message) })),
    [messages],
  )

  if (!ticket) return null

  const isAdminToAdmin = Boolean(ticket.adminRecipientId)
  const canCloseOrReopen = isAdminToAdmin ? Boolean(user?.isMainAdmin || user?.isSuperuser) : Boolean(user?.isAdmin)

  return <div className='page-stack'>
    <PageHeader eyebrow='Administracion' title={ticket.subject} description={`Ficha ${ticket.status}`} />
    <SectionCard eyebrow='Estado' title='Gestion de ficha' description='Cerrar o reabrir segun corresponda.'>
      <div className="_flex-gap-sm">
        <StatusBadge tone={ticket.status === 'ABIERTO' ? 'success':'warning'}>{ticket.status}</StatusBadge>
        {ticket.status === 'ABIERTO' ? <button className='button button--ghost' disabled={!canCloseOrReopen} onClick={()=>void closeTicket(ticket.id).then(load)}>Cerrar ficha</button> : <button className='button' disabled={!canCloseOrReopen} onClick={()=>void reopenTicket(ticket.id).then(load)}>Reabrir ficha</button>}
      </div>
    </SectionCard>
    <SectionCard eyebrow='Mensajes' title='Hilo completo' description='Conversación completa de la ficha.'>
      <div style={{ display: 'grid', gap: '0.85rem' }}>
        {messageItems.map(({ message: m, attachments }) => (
          <article key={m.id} style={{ border: '1px solid var(--border)', borderRadius: '12px', padding: '0.85rem 1rem', background: 'var(--bg-card)' }}>
            <div className="_flex-between _flex-wrap">
              <strong>{m.authorName}</strong>
              <div className="_flex-center _flex-gap-sm">
                <small className="_text-muted">{formatDateTime(m.createdAt)}</small>
                <StatusBadge tone='primary'>MENSAJE</StatusBadge>
              </div>
            </div>
            <p className="_mt-sm">{m.body}</p>

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
                        <div>
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

      <div className="_mt-md _flex-end">
        <button className='button' type='button' disabled={ticket.status !== 'ABIERTO'} onClick={() => setIsReplyModalOpen(true)}>Responder</button>
      </div>
    </SectionCard>


    {isReplyModalOpen ? (
      <div className="booking-modal-overlay" role="dialog" aria-modal="true" aria-label="Responder ficha">
        <div className="booking-modal-content _max-w-modal-lg">
          <header className="booking-modal-header">
            <div>
            <h2 className="_m-0">Responder ficha</h2>
            <p className="_m-0 _text-muted">Formato tipo correo interno.</p>
            </div>
            <button className="booking-modal-close" type="button" onClick={() => setIsReplyModalOpen(false)}>×</button>
          </header>
          <div className="booking-modal-body _p-6">
            <form className="form-stack" onSubmit={async (event: FormEvent<HTMLFormElement>) => {
              event.preventDefault()
              if (!reply.trim()) {
                showNotification({ title: 'Mensaje requerido', message: 'Debes escribir un mensaje para responder.', tone: 'warning' })
                return
              }
              const confirmSend = await confirm({
                    title: 'Enviar respuesta',
                    message: '¿Deseas enviar esta respuesta ahora?',
                  })
                  if (!confirmSend) return
              setIsSendingReply(true)
              void replyTicket(ticket.id, reply.trim(), replyFiles[0] ?? null).then(async () => {
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
                <input className="input" value={ticket.specialistName || ticket.adminRecipientName || ''} readOnly />
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
                {replyFiles.length > 0 ? <small className="_text-muted">{replyFiles.length} archivo(s) seleccionado(s).</small> : null}
              </label>
              <div className="_flex-end _flex-gap-md">
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
        <div className="booking-modal-content _max-w-2xl">
          <header className="booking-modal-header">
            <div>
              <h2 className="_m-0">Vista previa</h2>
              <p className="_mt-sm _text-muted">{previewImage.name}</p>
            </div>
            <button className="booking-modal-close" type="button" onClick={() => setPreviewImage(null)}>×</button>
          </header>
          <div className="booking-modal-body _p-6 _text-center">
            <img src={previewImage.url} alt={previewImage.name} style={{ maxWidth: '100%', maxHeight: '70vh', borderRadius: '10px' }} />
            <div className="_mt-md">
              <a className="button button--ghost" href={previewImage.url} target="_blank" rel="noreferrer" download>
                Descargar imagen
              </a>
            </div>
          </div>
        </div>
      </div>
    ) : null}
    <ConfirmDialogModal />
  </div>
}
