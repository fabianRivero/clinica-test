import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { SpecialistMessagingTabs } from '../../components/admin/SpecialistMessagingTabs'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useConfirmDialog } from '../../hooks/useConfirmDialog'
import { useNotifications } from '../../providers/NotificationProvider'
import { createTicket, getTicketDetail, getTickets, replyTicket, type Ticket, type TicketMessage, type TicketStatus } from '../../services/api/tickets'

type MessageAttachment = { url: string; name: string; isImage: boolean }
const initialCompose = { subject: '', body: '', files: [] as File[] }

function getFileExtension(fileName: string) { const p = fileName.toLowerCase().split('.'); return p.length > 1 ? p[p.length - 1] : '' }
function getFileTypeIcon(fileName: string, isImage: boolean) {
  if (isImage) return '🖼️'; const ext = getFileExtension(fileName)
  if (ext === 'pdf') return '📄'; if (['doc', 'docx', 'txt', 'rtf'].includes(ext)) return '📝'
  if (['xls', 'xlsx', 'csv'].includes(ext)) return '📊'; if (['zip', 'rar', '7z'].includes(ext)) return '🗜️'; return '📎'
}
function formatDateTime(value: string) { const d = new Date(value); if (Number.isNaN(d.getTime())) return value; return new Intl.DateTimeFormat('es-BO', { dateStyle: 'medium', timeStyle: 'short' }).format(d) }
function getMessageAttachments(message: TicketMessage): MessageAttachment[] {
  const m = message as TicketMessage & { attachmentUrl?: string; attachmentName?: string; attachments?: Array<{ url?: string; name?: string; type?: string; mimeType?: string }> }
  const out: MessageAttachment[] = []
  if (Array.isArray(m.attachments)) m.attachments.forEach((item, i) => { if (!item?.url) return; const name = item.name || `Adjunto ${i + 1}`; const hint = (item.type || item.mimeType || '').toLowerCase(); out.push({ url: item.url, name, isImage: hint.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp|svg)$/i.test(name) }) })
  if (m.attachmentUrl) { const name = m.attachmentName || 'Adjunto'; out.push({ url: m.attachmentUrl, name, isImage: /\.(png|jpe?g|webp|gif|bmp|svg)$/i.test(name) }) }
  return out
}

function SpecialistMessagingShell({ children }: { children: React.ReactNode }) {
  return <div className="page-stack"><PageHeader eyebrow="Portal de especialista" title="Mensajeria interna" description="Gestiona tus fichas y crea nuevas comunicaciones." /><SpecialistMessagingTabs />{children}</div>
}

export function SpecialistMessagesCreatePage() {
  const { showNotification } = useNotifications()
  const { confirm, ConfirmDialog: ConfirmDialogModal } = useConfirmDialog()
  const [form, setForm] = useState(initialCompose)
  const [isSending, setIsSending] = useState(false)
  return <SpecialistMessagingShell>
    <SectionCard eyebrow="Nueva ficha" title="Abrir comunicacion" description="Crea una ficha nueva con asunto y mensaje.">
      <form className="form-stack" onSubmit={async (e) => { e.preventDefault(); const ok = await confirm({ title: 'Enviar ficha', message: '¿Deseas enviar esta ficha ahora?' }); if (!ok) return; setIsSending(true); void createTicket({ subject: form.subject, message: form.body, attachment: form.files[0] ?? null }).then(() => { setForm(initialCompose); showNotification({ title: 'Ficha enviada', message: 'La ficha se envio correctamente.', tone: 'success' }) }).catch((err: unknown) => showNotification({ title: 'Error', message: err instanceof Error ? err.message : 'No se pudo crear la ficha.', tone: 'danger' })).finally(() => setIsSending(false)) }}>
        <div className="form-group"><label>Asunto</label><input className="input" value={form.subject} onChange={(e) => setForm((c) => ({ ...c, subject: e.target.value }))} required /></div>
        <div className="form-group"><label>Mensaje</label><textarea className="input" rows={6} value={form.body} onChange={(e) => setForm((c) => ({ ...c, body: e.target.value }))} required /></div>
        <div className="form-group"><label>Adjuntar documentos o imagenes</label><input className="input" type="file" multiple accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt" onChange={(e) => setForm((c) => ({ ...c, files: Array.from(e.target.files ?? []) }))} />{form.files.length ? <small>{form.files.length} archivo(s) seleccionado(s).</small> : null}</div>
        <button className="button" type="submit" disabled={isSending}>{isSending ? 'Enviando...' : 'Crear ficha'}</button>
      </form>
    </SectionCard>
    <ConfirmDialogModal />
  </SpecialistMessagingShell>
}

export function SpecialistMessagesTicketsPage() {
  const [status, setStatus] = useState<TicketStatus | ''>('')
  const [tickets, setTickets] = useState<Ticket[]>([])
  useEffect(() => { void getTickets(status || undefined).then((r) => setTickets(r.tickets)) }, [status])
  return <SpecialistMessagingShell>
    <SectionCard eyebrow="Bandeja" title="Listado de fichas" description="Filtra y entra al detalle para responder.">
      <select className='input' value={status} onChange={(e) => setStatus(e.target.value as TicketStatus | '')}><option value=''>Todos</option><option value='ABIERTO'>Abierto</option><option value='CERRADO'>Cerrado</option></select>
      <div className='table-card'><table><thead><tr><th>Estado</th><th>Asunto</th><th>Especialista</th><th>Acciones</th></tr></thead><tbody>
      {tickets.map((t) => <tr key={t.id}><td><StatusBadge tone={t.status === 'ABIERTO' ? 'success' : 'warning'}>{t.status}</StatusBadge></td><td>{t.subject}</td><td>{t.specialistName}</td><td><Link className='button button--ghost button--compact' to={`/trabajador/mensajes/${t.id}`}>Ver mensajes y detalles</Link></td></tr>)}
      </tbody></table></div>
    </SectionCard>
  </SpecialistMessagingShell>
}

export function SpecialistMessageDetailPage() {
  const { ticketId } = useParams()
  const { showNotification } = useNotifications()
  const { confirm, ConfirmDialog: ConfirmDialogModal } = useConfirmDialog()
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [messages, setMessages] = useState<TicketMessage[]>([])
  const [previewImage, setPreviewImage] = useState<MessageAttachment | null>(null)
  const [reply, setReply] = useState('')
  const [replyFiles, setReplyFiles] = useState<File[]>([])
  const [isReplyModalOpen, setIsReplyModalOpen] = useState(false)
  const [isSendingReply, setIsSendingReply] = useState(false)
  const load = async () => { if (!ticketId) return; const d = await getTicketDetail(Number(ticketId)); setTicket(d.ticket); setMessages(d.messages) }
  useEffect(() => { void load() }, [ticketId])
  const messageItems = useMemo(() => messages.map((m) => ({ message: m, attachments: getMessageAttachments(m) })), [messages])
  if (!ticket) return null
  return <SpecialistMessagingShell>
    <SectionCard eyebrow='Detalle' title={ticket.subject} description={`Ficha ${ticket.status}`}>
      <div style={{ display: 'grid', gap: '0.85rem' }}>{messageItems.map(({ message: m, attachments }) => <article key={m.id} style={{ border: '1px solid var(--border)', borderRadius: '12px', padding: '0.85rem 1rem', background: 'var(--bg-card)' }}><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}><strong>{m.authorName}</strong><div style={{ display: 'flex', gap: '0.5rem' }}><small style={{ color: 'var(--c-neutral-600)' }}>{formatDateTime(m.createdAt)}</small><StatusBadge tone='primary'>MENSAJE</StatusBadge></div></div><p>{m.body}</p>{attachments.length ? <div style={{ marginTop: '0.75rem', display: 'grid', gap: '0.6rem' }}>{attachments.map((a) => <div key={`${m.id}-${a.url}`} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap', border: '1px solid var(--border)', borderRadius: '10px', padding: '0.55rem 0.65rem' }}><div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', minWidth: 0 }}>{a.isImage ? <button type='button' onClick={() => setPreviewImage(a)} style={{ border: '1px solid var(--border)', padding: 0, borderRadius: '8px', cursor: 'pointer', background: 'transparent' }}><img src={a.url} alt={a.name} style={{ width: '56px', height: '56px', objectFit: 'cover', display: 'block', borderRadius: '8px' }} /></button> : <span style={{ fontSize: '1.3rem' }}>{getFileTypeIcon(a.name, a.isImage)}</span>}<div><strong style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'inline-block', maxWidth: '320px' }}>{a.name}</strong></div></div><a className='button button--ghost button--compact' href={a.url} target='_blank' rel='noreferrer' download>Descargar</a></div>)}</div> : null}</article>)}</div>
      <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'flex-end' }}><button className='button' type='button' disabled={ticket.status !== 'ABIERTO'} onClick={() => setIsReplyModalOpen(true)}>Responder</button></div>
    </SectionCard>
    {isReplyModalOpen ? <div className='booking-modal-overlay' role='dialog' aria-modal='true' aria-label='Responder ficha'><div className='booking-modal-content' style={{ maxWidth: '760px' }}><header className='booking-modal-header'><div><h2 style={{ margin: 0 }}>Responder ficha</h2><p style={{ margin: '0.5rem 0 0', color: 'var(--c-neutral-600)' }}>Formato tipo correo interno.</p></div><button className='booking-modal-close' type='button' onClick={() => setIsReplyModalOpen(false)}>×</button></header><div className='booking-modal-body' style={{ padding: '1.5rem' }}><form className='form-stack' onSubmit={async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (!reply.trim()) { showNotification({ title: 'Mensaje requerido', message: 'Debes escribir un mensaje para responder.', tone: 'warning' }); return }; const ok = await confirm({ title: 'Enviar respuesta', message: '¿Deseas enviar esta respuesta ahora?' }); if (!ok) return; setIsSendingReply(true); void replyTicket(ticket.id, reply.trim(), replyFiles[0] ?? null).then(async () => { await load(); setReply(''); setReplyFiles([]); setIsReplyModalOpen(false); showNotification({ title: 'Respuesta enviada', message: 'El mensaje se envio correctamente.', tone: 'success' }) }).catch((e: unknown) => showNotification({ title: 'No se pudo enviar', message: e instanceof Error ? e.message : 'Ocurrio un error al enviar la respuesta.', tone: 'danger' })).finally(() => setIsSendingReply(false)) }}><label className='field'><span>Para</span><input className='input' value='Administracion' readOnly /></label><label className='field'><span>Asunto</span><input className='input' value={`Re: ${ticket.subject}`} readOnly /></label><label className='field'><span>Mensaje</span><textarea className='input' rows={7} value={reply} onChange={(e) => setReply(e.target.value)} required /></label><label className='field'><span>Adjuntar documentos o imagenes</span><input className='input' type='file' multiple accept='image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt' onChange={(e) => setReplyFiles(Array.from(e.target.files ?? []))} />{replyFiles.length > 0 ? <small style={{ color: 'var(--c-neutral-600)' }}>{replyFiles.length} archivo(s) seleccionado(s).</small> : null}</label><div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}><button type='button' className='button button--ghost' onClick={() => setIsReplyModalOpen(false)}>Cancelar</button><button type='submit' className='button' disabled={isSendingReply}>{isSendingReply ? 'Enviando...' : 'Enviar respuesta'}</button></div></form></div></div></div> : null}
    {previewImage ? <div className='booking-modal-overlay' role='dialog' aria-modal='true' aria-label='Vista previa de imagen adjunta'><div className='booking-modal-content' style={{ maxWidth: '920px' }}><header className='booking-modal-header'><div><h2 style={{ margin: 0 }}>Vista previa</h2><p style={{ margin: '0.5rem 0 0', color: 'var(--c-neutral-600)' }}>{previewImage.name}</p></div><button className='booking-modal-close' type='button' onClick={() => setPreviewImage(null)}>×</button></header><div className='booking-modal-body' style={{ padding: '1.5rem', textAlign: 'center' }}><img src={previewImage.url} alt={previewImage.name} style={{ maxWidth: '100%', maxHeight: '70vh', borderRadius: '10px' }} /><div style={{ marginTop: '1rem' }}><a className='button button--ghost' href={previewImage.url} target='_blank' rel='noreferrer' download>Descargar imagen</a></div></div></div></div> : null}
    <ConfirmDialogModal />
  </SpecialistMessagingShell>
}
