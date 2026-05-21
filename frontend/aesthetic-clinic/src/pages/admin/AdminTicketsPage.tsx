import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useAuth } from '../../providers/AuthProvider'
import { Link } from 'react-router-dom'
import { AdminMessagingTabs } from '../../components/admin/AdminMessagingTabs'
import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useNotifications } from '../../providers/NotificationProvider'
import { useBranchContext } from '../../providers/BranchProvider'
import {
  createTicket,
  getOpenPermissionStatus,
  getTickets,
  setSpecialistOpenPermission,
  setBranchAdminOpenPermission,
  type PermissionSummary,
  type SpecialistOpenPermission,
  type BranchAdminOpenPermission,
  type Ticket,
  type TicketStatus,
} from '../../services/api/tickets'

type TicketComposeState = {
  specialistId: number | null
  subject: string
  message: string
  files: File[]
}

const initialComposeState: TicketComposeState = {
  specialistId: null,
  subject: '',
  message: '',
  files: [],
}

export function AdminMessagingPermissionsPage() {
  const { showNotification } = useNotifications()
  const [specialists, setSpecialists] = useState<SpecialistOpenPermission[]>([])
  const [summary, setSummary] = useState<PermissionSummary>('MIXED')
  const [branchAdmins, setBranchAdmins] = useState<BranchAdminOpenPermission[]>([])
  const [mainAdmins, setMainAdmins] = useState<BranchAdminOpenPermission[]>([])
  const { user } = useAuth()
  const [isComposeOpen, setIsComposeOpen] = useState(false)
  const [composeState, setComposeState] = useState<TicketComposeState>(initialComposeState)
  const [isSending, setIsSending] = useState(false)
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null

  const loadPermissions = async () => {
    const data = await getOpenPermissionStatus()
    setSpecialists(data.specialists)
    setBranchAdmins(data.branchAdmins ?? [])
    setMainAdmins(data.mainAdmins ?? [])
    setSummary(data.summary)
  }

  useEffect(() => {
    void loadPermissions()
  }, [branchId])

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

  const onBranchAdminUpdate = async (adminUserId: number, enabled: boolean) => {
    await setBranchAdminOpenPermission(enabled, adminUserId)
    await loadPermissions()
  }

  const onBranchAdminMassUpdate = async (enabled: boolean) => {
    await setBranchAdminOpenPermission(enabled)
    await loadPermissions()
  }

  const openComposeModal = (specialistId: number, specialistName: string) => {
    setComposeState({
      specialistId,
      subject: `Nueva ficha para ${specialistName}`,
      message: '',
      files: [],
    })
    setIsComposeOpen(true)
  }

  const closeComposeModal = () => {
    setIsComposeOpen(false)
    setComposeState(initialComposeState)
  }

  const onComposeSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!composeState.specialistId) return

    const confirmSend = window.confirm('¿Deseas enviar esta ficha ahora?')
    if (!confirmSend) return

    setIsSending(true)
    try {
      await createTicket({
        specialistId: composeState.specialistId,
        subject: composeState.subject.trim(),
        message: composeState.message.trim(),
        attachment: composeState.files[0] ?? null,
      })
      closeComposeModal()
      showNotification({
        title: 'Ficha enviada',
        message: 'La ficha se envio correctamente.',
        tone: 'success',
      })
    } catch (error) {
      showNotification({
        title: 'No se pudo enviar',
        message: error instanceof Error ? error.message : 'Ocurrio un error al enviar la ficha.',
        tone: 'danger',
      })
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Administracion"
        title="Mensajeria interna"
        description="Gestiona permisos para apertura de fichas y revisa fichas existentes."
      />
      <AdminMessagingTabs />
      {user?.isMainAdmin ? (
        <SectionCard
          eyebrow="Administradores"
          title="Administradores de sucursal"
          description="Listado de administradores de sucursal con su usuario y sucursal asociada."
        >
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <button className="button" onClick={() => void onBranchAdminMassUpdate(true)}>Habilitar a todos</button>
            <button className="button button--ghost" onClick={() => void onBranchAdminMassUpdate(false)}>Bloquear a todos</button>
          </div>
          {!branchAdmins.length ? (
            <DataState title="Sin administradores" message="No hay administradores de sucursal activos." />
          ) : (
            <div className="table-card">
              <table>
                <thead><tr><th>Usuario</th><th>Sucursal</th><th>Permiso</th><th>Accion</th></tr></thead>
                <tbody>
                  {branchAdmins.map((admin) => (
                    <tr key={admin.adminId}>
                      <td>{admin.adminName}</td>
                      <td>{admin.branchName || 'Sin sucursal'}</td>
                      <td><StatusBadge tone={admin.enabled ? 'success' : 'warning'}>{admin.enabled ? 'Habilitado' : 'Bloqueado'}</StatusBadge></td>
                      <td style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                        <button className="button button--ghost button--compact" disabled={admin.enabled} onClick={() => void onBranchAdminUpdate(admin.adminId, true)}>Habilitar</button>
                        <button className="button button--ghost button--compact" disabled={!admin.enabled} onClick={() => void onBranchAdminUpdate(admin.adminId, false)}>Bloquear</button>
                        <button className="button button--compact">Crear ficha</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      ) : null}

      {user && !user.isMainAdmin ? (
        <SectionCard
          eyebrow="Comunicacion"
          title="Administradores principales"
          description="Puedes crear fichas para comunicarte con el administrador principal."
        >
          {!mainAdmins.length ? (
            <DataState title="Sin administradores principales" message="No hay administradores principales activos." />
          ) : (
            <div className="table-card">
              <table>
                <thead><tr><th>Usuario</th><th>Sucursal</th><th>Permiso</th><th>Accion</th></tr></thead>
                <tbody>
                  {mainAdmins.map((admin) => (
                    <tr key={admin.adminId}>
                      <td>{admin.adminName}</td>
                      <td>{admin.branchName || 'Global'}</td>
                      <td><StatusBadge tone={admin.enabled ? 'success' : 'warning'}>{admin.enabled ? 'Habilitado' : 'Bloqueado'}</StatusBadge></td>
                      <td><button className="button button--compact">Crear ficha</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      ) : null}

      <SectionCard
        eyebrow="Permisos"
        title="Apertura de fichas por especialistas"
        description="Control masivo e individual por especialista."
      >
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <button className="button" onClick={() => void onMassUpdate(true)}>Habilitar a todos</button>
          <button className="button button--ghost" onClick={() => void onMassUpdate(false)}>Bloquear a todos</button>
        </div>
        {summaryLabel ? <p style={{ marginTop: 0, color: 'var(--c-neutral-700)' }}>{summaryLabel}</p> : null}

        {!specialists.length ? (
          <DataState title="Sin especialistas" message="No hay especialistas activos en esta sucursal." />
        ) : (
          <div className="table-card">
            <table>
              <thead><tr><th>Especialista</th><th>Permiso</th><th>Accion</th></tr></thead>
              <tbody>
                {specialists.map((s) => (
                  <tr key={s.specialistId}>
                    <td>{s.specialistName}</td>
                    <td><StatusBadge tone={s.enabled ? 'success' : 'warning'}>{s.enabled ? 'Habilitado' : 'Bloqueado'}</StatusBadge></td>
                    <td style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                      <button className="button button--ghost button--compact" disabled={s.enabled} onClick={() => void onSingleUpdate(s.specialistId, true)}>Habilitar</button>
                      <button className="button button--ghost button--compact" disabled={!s.enabled} onClick={() => void onSingleUpdate(s.specialistId, false)}>Bloquear</button>
                      <button className="button button--compact" onClick={() => openComposeModal(s.specialistId, s.specialistName)}>Crear ficha</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {isComposeOpen ? (
        <div className="booking-modal-overlay" role="dialog" aria-modal="true" aria-label="Crear ficha">
          <div className="booking-modal-content" style={{ maxWidth: '760px' }}>
            <header className="booking-modal-header">
              <div>
                <h2 style={{ margin: 0 }}>Nueva ficha</h2>
                <p style={{ margin: '0.5rem 0 0', color: 'var(--c-neutral-600)' }}>Formato tipo correo interno.</p>
              </div>
              <button className="booking-modal-close" type="button" onClick={closeComposeModal}>×</button>
            </header>
            <div className="booking-modal-body" style={{ padding: '1.5rem' }}>
              <form className="form-stack" onSubmit={(event) => void onComposeSubmit(event)}>
                <label className="field">
                  <span>Para</span>
                  <input
                    className="input"
                    value={specialists.find((sp) => sp.specialistId === composeState.specialistId)?.specialistName ?? ''}
                    readOnly
                  />
                </label>
                <label className="field">
                  <span>Asunto</span>
                  <input
                    className="input"
                    value={composeState.subject}
                    onChange={(event) => setComposeState((current) => ({ ...current, subject: event.target.value }))}
                    required
                  />
                </label>
                <label className="field">
                  <span>Mensaje</span>
                  <textarea
                    className="input"
                    rows={7}
                    value={composeState.message}
                    onChange={(event) => setComposeState((current) => ({ ...current, message: event.target.value }))}
                    required
                  />
                </label>
                <label className="field">
                  <span>Adjuntar documentos o imagenes</span>
                  <input
                    className="input"
                    type="file"
                    multiple
                    accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt"
                    onChange={(event) => setComposeState((current) => ({ ...current, files: Array.from(event.target.files ?? []) }))}
                  />
                  {composeState.files.length > 0 ? (
                    <small style={{ color: 'var(--c-neutral-600)' }}>{composeState.files.length} archivo(s) seleccionado(s).</small>
                  ) : null}
                </label>
                <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                  <button type="button" className="button button--ghost" onClick={closeComposeModal}>Cancelar</button>
                  <button type="submit" className="button" disabled={isSending}>{isSending ? 'Enviando...' : 'Enviar ficha'}</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function AdminMessagingTicketsPage() {
  const [status, setStatus] = useState<TicketStatus | ''>('')
  const [tickets, setTickets] = useState<Ticket[]>([])
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null

  useEffect(() => {
    void getTickets(status || undefined).then((result) => setTickets(result.tickets))
  }, [status, branchId])

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Administracion"
        title="Mensajeria interna"
        description="Gestiona permisos para apertura de fichas y revisa fichas existentes."
      />
      <AdminMessagingTabs />
      <SectionCard
        eyebrow="Bandeja"
        title="Listado de fichas"
        description="Filtra y entra al detalle para responder o cerrar/reabrir."
      >
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value as TicketStatus | '')}>
          <option value="">Todos</option>
          <option value="ABIERTO">Abierto</option>
          <option value="CERRADO">Cerrado</option>
        </select>
        <div className="table-card">
          <table>
            <thead><tr><th>Estado</th><th>Asunto</th><th>Especialista</th><th>Acciones</th></tr></thead>
            <tbody>
              {tickets.map((t) => (
                <tr key={t.id}>
                  <td><StatusBadge tone={t.status === 'ABIERTO' ? 'success' : 'warning'}>{t.status}</StatusBadge></td>
                  <td>{t.subject}</td>
                  <td>{t.specialistName}</td>
                  <td>
                    <Link className="button button--ghost button--compact" to={`/admin/mensajes/${t.id}`}>
                      Ver mensajes y detalles
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  )
}
