import { useCallback, useMemo, useState } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'

import { DataState } from '../../components/admin/DataState'
import { AdminRelationshipTabs } from '../../components/admin/AdminRelationshipTabs'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import {
  cancelAdminAppointment,
  createAdminClientFreeMedicalAppointment,
  confirmAdminAppointmentBiometric,
  createAdminClientReservation,
  getAdminClientDetail,
  inactivateAdminClient,
  markAdminAppointmentPendingBiometric,
} from '../../services/api/admin'
import { verifyMockFingerprint } from '../../services/fingerprint/mockFingerprint'
import type {
  AdminConcurrencyCheckResponse,
} from '../../types/admin'
import { useBranchContext } from '../../providers/BranchProvider'
import { checkAdminConcurrency, migrateAdminClient } from '../../services/api/admin'
import { useAuth } from '../../providers/AuthProvider'

export function AdminClientDetailPage() {
  const navigate = useNavigate()
  const { clientId = '' } = useParams()
  const { showNotification } = useNotifications()
  const loader = useCallback(() => getAdminClientDetail(clientId), [clientId])
  const { data, isLoading, error, reload } = useApiResource(loader)
  const [selectedOperationId, setSelectedOperationId] = useState<number | ''>('')
  const { activeBranch } = useBranchContext()
  const [selectedDate, setSelectedDate] = useState('')
  const [selectedTime, setSelectedTime] = useState('')
  const [concurrencyInfo, setConcurrencyInfo] = useState<AdminConcurrencyCheckResponse | null>(null)
  
  const [freeSelectedDate, setFreeSelectedDate] = useState('')
  const [freeSelectedTime, setFreeSelectedTime] = useState('')
  const [freeConcurrencyInfo, setFreeConcurrencyInfo] = useState<AdminConcurrencyCheckResponse | null>(null)

  const [isChecking, setIsChecking] = useState(false)
  const [isBookingKey, setIsBookingKey] = useState<string | null>(null)
  const [isFreeBookingKey, setIsFreeBookingKey] = useState<string | null>(null)
  const [isInactivating, setIsInactivating] = useState(false)
  const [appointmentActionId, setAppointmentActionId] = useState<number | null>(null)
  const [isMigrating, setIsMigrating] = useState(false)
  const { user } = useAuth()
  const isMainAdmin = user?.isMainAdmin || user?.isSuperuser
  const { branches } = useBranchContext()

  const reservableOperations = useMemo(
    () => data?.operations.filter((operation: any) => operation.status === 'En proceso') ?? [],
    [data],
  )
  const effectiveOperationId = selectedOperationId || reservableOperations[0]?.rawId || ''





  async function handleCancelAppointment(appointmentId: number) {
    const shouldCancel = window.confirm('Se cancelara esta reserva y el cupo volvera a quedar disponible. ¿Deseas continuar?')
    if (!shouldCancel) return

    try {
      const response = await cancelAdminAppointment(appointmentId)
      showNotification({ title: 'Cita cancelada', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo cancelar la cita',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  async function handleMarkPendingBiometric(appointmentId: number) {
    const confirmed = window.confirm('Solo se debe cambiar a este estado cuando el cliente asiste al tratamiento. ¿Deseas continuar?')
    if (!confirmed) return

    setAppointmentActionId(appointmentId)
    try {
      const response = await markAdminAppointmentPendingBiometric(appointmentId)
      showNotification({
        title: 'Cita pendiente de biometria',
        message: response.detail,
        tone: 'success',
      })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo actualizar la cita',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    } finally {
      setAppointmentActionId(null)
    }
  }

  async function handleConfirmBiometric(appointmentId: number, biometricMockTemplate: string) {
    if (!biometricMockTemplate) {
      showNotification({
        title: 'Sin huella registrada',
        message: 'Este cliente no tiene una huella mock disponible para comparar.',
        tone: 'danger',
      })
      return
    }

    setAppointmentActionId(appointmentId)
    try {
      const capture = await verifyMockFingerprint(biometricMockTemplate)
      const response = await confirmAdminAppointmentBiometric(appointmentId, {
        provider: capture.provider,
        template: capture.template,
        quality: capture.quality,
        deviceSerial: capture.deviceSerial,
      })
      showNotification({
        title: 'Huella confirmada',
        message: 'La cita fue confirmada con la huella biometrica simulada.',
        tone: 'success',
      })
      reload()
      void response
    } catch (requestError) {
      showNotification({
        title: 'No se pudo confirmar la huella',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    } finally {
      setAppointmentActionId(null)
    }
  }

  async function handleCheckConcurrency() {
    if (!activeBranch || !selectedDate || !selectedTime) {
      showNotification({ title: 'Atencion', message: 'Selecciona fecha y hora.', tone: 'warning' })
      return
    }
    setIsChecking(true)
    try {
      const info = await checkAdminConcurrency(activeBranch.id, selectedDate, selectedTime, selectedTime)
      setConcurrencyInfo(info)
    } catch (err: any) {
      showNotification({ title: 'Error', message: err.message, tone: 'danger' })
    } finally {
      setIsChecking(false)
    }
  }

  async function handleCheckFreeConcurrency() {
    if (!activeBranch || !freeSelectedDate || !freeSelectedTime) {
      showNotification({ title: 'Atencion', message: 'Selecciona fecha y hora.', tone: 'warning' })
      return
    }
    setIsChecking(true)
    try {
      const info = await checkAdminConcurrency(activeBranch.id, freeSelectedDate, freeSelectedTime, freeSelectedTime)
      setFreeConcurrencyInfo(info)
    } catch (err: any) {
      showNotification({ title: 'Error', message: err.message, tone: 'danger' })
    } finally {
      setIsChecking(false)
    }
  }


  async function handleReserve() {
    if (!data || !effectiveOperationId || !activeBranch) return
    setIsBookingKey('booking')

    try {
      const response = await createAdminClientReservation(data.client.rawId, effectiveOperationId, {
        branchId: activeBranch.id,
        dateTime: `${selectedDate}T${selectedTime}:00`
      } as any)
      showNotification({ title: 'Reserva registrada', message: response.detail, tone: 'success' })
      reload()
      setSelectedOperationId('')
      setSelectedDate('')
      setSelectedTime('')
      setConcurrencyInfo(null)
    } catch (requestError: any) {
      showNotification({
        title: 'No se pudo reservar',
        message: requestError.message,
        tone: 'danger',
      })
    } finally {
      setIsBookingKey(null)
    }
  }

  async function handleReserveFreeMedicalAppointment() {
    if (!data || !activeBranch) return
    setIsFreeBookingKey('booking')

    try {
      const response = await createAdminClientFreeMedicalAppointment(data.client.rawId, {
        branchId: activeBranch.id,
        dateTime: `${freeSelectedDate}T${freeSelectedTime}:00`
      } as any)
      showNotification({ title: 'Cita medica registrada', message: response.detail, tone: 'success' })
      reload()
      setFreeSelectedDate('')
      setFreeSelectedTime('')
      setFreeConcurrencyInfo(null)
    } catch (requestError: any) {
      showNotification({
        title: 'No se pudo reservar',
        message: requestError.message,
        tone: 'danger',
      })
    } finally {
      setIsFreeBookingKey(null)
    }
  }

  async function handleInactivateClient() {
    if (!data) return
    const activeOperations = data.operations.filter((operation) => operation.status === 'En proceso')
    const pendingSessions = activeOperations.reduce(
      (total, operation) =>
        total + Math.max(operation.sessions.total - operation.sessions.confirmed, 0),
      0,
    )
    const pendingQuotas = data.pendingQuotas.length
    const warningDetail =
      pendingSessions || pendingQuotas
        ? `Advertencia: este cliente aun tiene ${pendingSessions} sesion(es) y ${pendingQuotas} cuota(s) pendiente(s). `
        : ''
    const confirmed = window.confirm(
      `${warningDetail}El cliente pasara a inactivo, se cancelaran sus procedimientos en proceso y sus citas programadas. ¿Deseas continuar?`,
    )
    if (!confirmed) return

    setIsInactivating(true)
    try {
      const response = await inactivateAdminClient(data.client.rawId)
      showNotification({ title: 'Cliente inactivo', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo inactivar',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    } finally {
      setIsInactivating(false)
    }
  }

  async function handleMigrateClient(branchId: number) {
    if (!data) return
    const branchName = branches.find(b => b.id === branchId)?.nombre || 'esta sucursal'
    const confirmed = window.confirm(`¿Seguro que deseas migrar este cliente a la sucursal ${branchName}? Podra ser gestionado por los administradores de esa sucursal.`)
    if (!confirmed) return

    setIsMigrating(true)
    try {
      const response = await migrateAdminClient(data.client.rawId, branchId)
      showNotification({ title: 'Cliente migrado', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError: any) {
      showNotification({
        title: 'Error al migrar',
        message: requestError.message,
        tone: 'danger',
      })
    } finally {
      setIsMigrating(false)
    }
  }

  if (isLoading && !data) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="Clientes" title="Cargando cliente" description="Estamos preparando su historial administrativo." />
        <SectionCard title="Sincronizando">
          <DataState title="Cargando informacion" message="Consultando citas, sesiones, pagos y procedimientos." />
        </SectionCard>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="Clientes" title="No pudimos cargar el cliente" description="Revisa la lista e intenta nuevamente." actions={[{ label: 'Volver a clientes', variant: 'ghost', to: '/admin/clientes' }]} />
        <SectionCard title="Cliente no disponible">
          <DataState title="Conexion no disponible" message={error || 'No encontramos el cliente solicitado.'} tone="danger" />
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Administrador de cliente"
        title={data.client.name}
        description={`${data.client.status} | ${data.client.phone} | Ultimo analisis: ${data.client.lastAnalysis}`}
        actions={[
          { label: 'Volver a clientes', variant: 'ghost', to: '/admin/clientes' },
          ...(data.client.status === 'Inactivo' ? [{
            label: 'Reactivar / Nuevo tratamiento',
            onClick: () => navigate(`/admin/clientes/${clientId}/reactivar`)
          }] : []),
          ...(isMainAdmin ? [{
            label: isMigrating ? 'Migrando...' : 'Migrar sucursal',
            variant: 'secondary' as const,
            disabled: isMigrating,
            onClick: () => {
              const currentBranchId = data.client.branchId || data.client.sucursalId
              const targetBranchId = window.prompt(
                `Ingresa el ID de la sucursal destino:\n\n` +
                branches.filter(b => b.id !== currentBranchId).map(b => `[ \${b.id} ] - \${b.nombre}`).join('\n')
              )
              if (targetBranchId) {
                handleMigrateClient(Number(targetBranchId))
              }
            }
          }] : [])
        ]}
      />

      <AdminRelationshipTabs />

      <section className="metrics-grid metrics-grid--compact">
        {data.metrics.map((metric) => (
          <MetricCard key={metric.id} metric={metric} />
        ))}
      </section>

      <SectionCard eyebrow="Estado" title="Gestion del cliente" description="Permite retirar al cliente de sus procedimientos vigentes cuando corresponde.">
        <div className="client-inline-meta">
          <StatusBadge tone={data.client.status === 'Activo' ? 'success' : 'neutral'}>{data.client.status}</StatusBadge>
          <span>{data.client.activeOperations} procedimiento(s) activo(s)</span>
          {data.client.status === 'Activo' ? (
            <>
              <button
                className="button"
                type="button"
                onClick={() => navigate(`/admin/clientes/${clientId}/reactivar`)}
              >
                Añadir procedimiento
              </button>
              <button
                className="button button--ghost"
                disabled={isInactivating}
                type="button"
                onClick={() => void handleInactivateClient()}
              >
                {isInactivating ? 'Inactivando...' : 'Convertir a inactivo'}
              </button>
            </>
          ) : (
            <button
              className="button button--primary"
              type="button"
              onClick={() => navigate(`/admin/clientes/${clientId}/reactivar`)}
            >
              Reactivar / Nuevo tratamiento
            </button>
          )}
        </div>
      </SectionCard>

      <section className="dashboard-grid">
        <SectionCard eyebrow="Reservas" title="Hacer reserva para este cliente" description="Agendar hora libre (Agenda abierta).">
          {reservableOperations.length ? (
            <div className="form-grid">
              <label className="field field--full">
                <span>Procedimiento</span>
                <select className="input" value={effectiveOperationId} onChange={(event) => setSelectedOperationId(Number(event.target.value))}>
                  {reservableOperations.map((operation: any) => (
                    <option key={operation.id} value={operation.rawId}>
                      {operation.procedure} | {operation.reserveMessage}
                    </option>
                  ))}
                </select>
              </label>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <label className="field">
                  <span>Fecha</span>
                  <input type="date" className="input" value={selectedDate} onChange={e => { setSelectedDate(e.target.value); setConcurrencyInfo(null); }} />
                </label>
                <label className="field">
                  <span>Hora de Inicio</span>
                  <input type="time" className="input" value={selectedTime} onChange={e => { setSelectedTime(e.target.value); setConcurrencyInfo(null); }} />
                </label>
              </div>
              
              <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
                <button type="button" className="button button--secondary" disabled={!selectedDate || !selectedTime || isChecking} onClick={() => void handleCheckConcurrency()}>
                  {isChecking ? 'Verificando...' : 'Verificar Disponibilidad'}
                </button>
              </div>
            </div>
          ) : (
            <DataState title="Sin procedimientos en proceso" message="Este cliente no tiene tratamientos activos para nuevas reservas." />
          )}
        </SectionCard>

        {concurrencyInfo && (
          <SectionCard title="Resultados de disponibilidad">
            <div style={{ padding: '1rem', background: 'var(--c-neutral-100)', borderRadius: '8px' }}>
              <p style={{ marginBottom: '0.5rem' }}>
                <strong>Citas simultaneas de 1 hora antes a 1 hora despues ({concurrencyInfo.hora_inicio} a {concurrencyInfo.hora_fin}):</strong> {concurrencyInfo.concurrency}
              </p>
              <p style={{ marginBottom: '0.5rem' }}>
                <strong>Especialistas en turno {concurrencyInfo.hora_seleccionada}:</strong> {concurrencyInfo.presentes.length > 0 ? concurrencyInfo.presentes.map(p => p.usuario__primer_nombre).join(', ') : 'Ninguno registrado'}
              </p>
              {concurrencyInfo.concurrency >= concurrencyInfo.presentes.length && concurrencyInfo.presentes.length > 0 && (
                <p style={{ color: 'var(--c-danger-600)', marginTop: '0.5rem', fontWeight: 600 }}>
                  Aviso: Hay mas citas ({concurrencyInfo.concurrency}) que especialistas en turno ({concurrencyInfo.presentes.length}).
                </p>
              )}
              {concurrencyInfo.presentes.length === 0 && (
                <p style={{ color: 'var(--c-warning-600)', marginTop: '0.5rem', fontWeight: 600 }}>
                  Aviso: No hay especialistas en turno configurados para esta sucursal a esa hora.
                </p>
              )}
              <div style={{ marginTop: '1.5rem' }}>
                 <button type="button" className="button button--primary" onClick={() => void handleReserve()} disabled={Boolean(isBookingKey)}>
                   {isBookingKey ? 'Confirmando...' : 'Confirmar Reserva en esta Hora'}
                 </button>
              </div>
            </div>
          </SectionCard>
        )}
      </section>

      <section className="dashboard-grid">
        <SectionCard eyebrow="Cita medica" title="Reservar cita medica libre" description="Agenda una consulta sin asociarla a un tratamiento activo. Disponible tambien para clientes inactivos.">
          <div className="form-grid">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <label className="field">
                <span>Fecha</span>
                <input type="date" className="input" value={freeSelectedDate} onChange={e => { setFreeSelectedDate(e.target.value); setFreeConcurrencyInfo(null); }} />
              </label>
              <label className="field">
                <span>Hora de Inicio</span>
                <input type="time" className="input" value={freeSelectedTime} onChange={e => { setFreeSelectedTime(e.target.value); setFreeConcurrencyInfo(null); }} />
              </label>
            </div>
            
            <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="button button--secondary" disabled={!freeSelectedDate || !freeSelectedTime || isChecking} onClick={() => void handleCheckFreeConcurrency()}>
                {isChecking ? 'Verificando...' : 'Verificar Disponibilidad'}
              </button>
            </div>
          </div>
        </SectionCard>

        {freeConcurrencyInfo && (
          <SectionCard title="Resultados de disponibilidad">
            <div style={{ padding: '1rem', background: 'var(--c-neutral-100)', borderRadius: '8px' }}>
              <p style={{ marginBottom: '0.5rem' }}>
                <strong>Citas simultaneas de 1 hora antes a 1 hora despues ({freeConcurrencyInfo.hora_inicio} a {freeConcurrencyInfo.hora_fin}):</strong> {freeConcurrencyInfo.concurrency}
              </p>
              <p style={{ marginBottom: '0.5rem' }}>
                <strong>Especialistas en turno {freeConcurrencyInfo.hora_seleccionada}:</strong> {freeConcurrencyInfo.presentes.length > 0 ? freeConcurrencyInfo.presentes.map(p => p.usuario__primer_nombre).join(', ') : 'Ninguno registrado'}
              </p>
              <div style={{ marginTop: '1.5rem' }}>
                 <button type="button" className="button button--primary" onClick={() => void handleReserveFreeMedicalAppointment()} disabled={Boolean(isFreeBookingKey)}>
                   {isFreeBookingKey ? 'Confirmando...' : 'Confirmar Cita Medica'}
                 </button>
              </div>
            </div>
          </SectionCard>
        )}
      </section>

      <SectionCard eyebrow="Agenda" title="Todas las citas del cliente" description="Historial completo de reservas, sesiones realizadas, cancelaciones y pendientes de biometria.">
        {data.appointments.length ? (
          <div className="table-card">
            <table>
              <thead>
                <tr>
                  <th>Operacion</th>
                  <th>Especialista</th>
                  <th>Fecha</th>
                  <th>Estado</th>
                  <th>Biometria</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {data.appointments.map((appointment) => (
                  <tr key={appointment.id}>
                    <td><strong>{appointment.operation}</strong><span>{appointment.details}</span></td>
                    <td>{appointment.specialist}</td>
                    <td>{appointment.dateTime}</td>
                    <td><StatusBadge tone={appointment.statusTone}>{appointment.status}</StatusBadge></td>
                    <td>{appointment.biometric}</td>
                    <td>
                      <div className="table-action-list">
                        {appointment.canMarkPendingBiometric ? (
                          <button
                            className="button button--ghost button--compact"
                            disabled={appointmentActionId !== null}
                            type="button"
                            onClick={() => void handleMarkPendingBiometric(appointment.rawId)}
                          >
                            {appointmentActionId === appointment.rawId ? 'Actualizando...' : 'Cambiar a pendiente de biometria'}
                          </button>
                        ) : null}
                        {appointment.canManage ? (
                          <button
                            className="button button--ghost button--compact"
                            disabled={appointmentActionId !== null}
                            type="button"
                            onClick={() => void handleCancelAppointment(appointment.rawId)}
                          >
                            Cancelar reserva
                          </button>
                        ) : null}
                        {appointment.canConfirmBiometric ? (
                          <button
                            className="button button--ghost button--compact"
                            disabled={appointmentActionId !== null}
                            type="button"
                            onClick={() => void handleConfirmBiometric(appointment.rawId, appointment.biometricMockTemplate)}
                          >
                            {appointmentActionId === appointment.rawId ? 'Validando...' : 'Confirmar huella mock'}
                          </button>
                        ) : null}
                        {!appointment.canManage && !appointment.canMarkPendingBiometric && !appointment.canConfirmBiometric ? (
                          <span className="table-muted">Sin cambios</span>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <DataState title="Sin citas registradas" message="El cliente aun no tiene citas asociadas." />}
      </SectionCard>

      <section className="dashboard-grid">
        <SectionCard eyebrow="Sesiones" title="Sesiones realizadas" description="Citas confirmadas con validacion biometrica.">
          {data.sessions.length ? (
            <div className="capacity-list">
              {data.sessions.map((session) => (
                <article className="capacity-item" key={session.id}>
                  <div className="capacity-item__header">
                    <div><strong>{session.operation}</strong><p>{session.dateTime} | {session.specialist}</p></div>
                    <StatusBadge tone={session.statusTone}>{session.status}</StatusBadge>
                  </div>
                </article>
              ))}
            </div>
          ) : <DataState title="Sin sesiones realizadas" message="Todavia no hay sesiones confirmadas con biometria." />}
        </SectionCard>

        <SectionCard eyebrow="Pagos" title="Pagos pendientes" description="Cuotas aun no pagadas o pendientes de completar.">
          {data.pendingQuotas.length ? (
            <div className="capacity-list">
              {data.pendingQuotas.map((quota) => (
                <article className="capacity-item" key={quota.id}>
                  <div className="capacity-item__header">
                    <div><strong>{quota.operation} | {quota.quotaLabel}</strong><p>{quota.amount} | Vence: {quota.dueDate}</p></div>
                    <StatusBadge tone={quota.statusTone}>{quota.status}</StatusBadge>
                  </div>
                </article>
              ))}
            </div>
          ) : <DataState title="Sin pagos pendientes" message="No hay cuotas pendientes para este cliente." />}
        </SectionCard>
      </section>

      <SectionCard eyebrow="Pagos" title="Pagos realizados" description="Comprobantes y pagos historicos registrados para el cliente.">
        {data.payments.length ? (
          <div className="table-card">
            <table>
              <thead>
                <tr>
                  <th>Operacion</th>
                  <th>Cuota</th>
                  <th>Monto</th>
                  <th>Fecha</th>
                  <th>Estado</th>
                  <th>Comprobante</th>
                </tr>
              </thead>
              <tbody>
                {data.payments.map((payment) => (
                  <tr key={payment.id}>
                    <td>{payment.operation}</td>
                    <td>{payment.quotaLabel}</td>
                    <td>{payment.amount}</td>
                    <td>{payment.submittedAt}</td>
                    <td><StatusBadge tone={payment.statusTone}>{payment.status}</StatusBadge></td>
                    <td>{payment.receiptUrl ? <a className="table-strong-link" href={payment.receiptUrl} target="_blank" rel="noreferrer">Ver</a> : 'Sin archivo'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <DataState title="Sin pagos registrados" message="El cliente aun no tiene pagos en su historial." />}
      </SectionCard>

      <SectionCard eyebrow="Tratamientos" title="Procedimientos del cliente" description="Resumen operativo de tratamientos activos e historicos.">
        {data.operations.length ? (
          <div className="capacity-list">
            {data.operations.map((operation) => (
              <article className="capacity-item" key={operation.id}>
                <div className="capacity-item__header">
                  <div>
                    <strong>{operation.procedure}</strong>
                    <p>{operation.zone} | {operation.quotaSummary}</p>
                  </div>
                  <StatusBadge tone={operation.statusTone}>{operation.status}</StatusBadge>
                </div>
                <div className="operation-card__stats">
                  <article><span>Totales</span><strong>{operation.sessions.total}</strong></article>
                  <article><span>Confirmadas</span><strong>{operation.sessions.confirmed}</strong></article>
                  <article><span>Reservadas</span><strong>{operation.sessions.reserved}</strong></article>
                  <article><span>Libres</span><strong>{operation.sessions.available}</strong></article>
                </div>
                <Link className="button button--ghost" to={`/admin/operaciones/${operation.rawId}`}>Ver operacion</Link>
              </article>
            ))}
          </div>
        ) : <DataState title="Sin procedimientos" message="No hay procedimientos asociados a este cliente." />}
      </SectionCard>
    </div>
  )
}
