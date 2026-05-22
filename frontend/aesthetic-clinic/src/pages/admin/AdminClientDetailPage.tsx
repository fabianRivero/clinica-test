import { useCallback, useMemo, useState } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'

import { DataState } from '../../components/admin/DataState'
import { AdminRelationshipTabs } from '../../components/admin/AdminRelationshipTabs'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { verificationStatusLabel } from '../../constants/verification'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import {
  cancelAdminAppointment,
  checkAdminConcurrency,
  createAdminClientFreeMedicalAppointment,
  confirmAdminAppointmentBiometric,
  createAdminClientReservation,
  getAdminClientDetail,
  inactivateAdminClient,
  markAdminAppointmentPendingBiometric,
  rescheduleAdminAppointment,
  updateAdminPaymentStatus,
} from '../../services/api/admin'
import { verifyMockFingerprint } from '../../services/fingerprint/mockFingerprint'
import type {
  AdminConcurrencyCheckResponse,
} from '../../types/admin'
import { useBranchContext } from '../../providers/BranchProvider'
import { migrateAdminClient } from '../../services/api/admin'
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
  const [rescheduleAppointmentId, setRescheduleAppointmentId] = useState<number | null>(null)
  const [rescheduleDate, setRescheduleDate] = useState('')
  const [rescheduleTime, setRescheduleTime] = useState('')
  const [rescheduleCheck, setRescheduleCheck] = useState<AdminConcurrencyCheckResponse | null>(null)
  const [isCheckingReschedule, setIsCheckingReschedule] = useState(false)
  const [paymentNotes, setPaymentNotes] = useState<Record<number, string>>({})
  const [paymentActionId, setPaymentActionId] = useState<number | null>(null)
  const [operationStatusFilter, setOperationStatusFilter] = useState<string>('')
  const [pendingQuotaProcedureFilter, setPendingQuotaProcedureFilter] = useState<string>('')
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
        title: 'Cita pendiente de verificacion',
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

  async function handleCheckRescheduleAvailability() {
    if (!activeBranch || !rescheduleDate || !rescheduleTime) {
      showNotification({ title: 'Atencion', message: 'Selecciona fecha y hora.', tone: 'warning' })
      return
    }
    setIsCheckingReschedule(true)
    try {
      const info = await checkAdminConcurrency(activeBranch.id, rescheduleDate, rescheduleTime, rescheduleTime)
      setRescheduleCheck(info)
    } catch (err: any) {
      showNotification({ title: 'Error', message: err.message, tone: 'danger' })
    } finally {
      setIsCheckingReschedule(false)
    }
  }

  async function handleRescheduleAppointment() {
    if (!rescheduleAppointmentId || !rescheduleCheck) return
    setAppointmentActionId(rescheduleAppointmentId)
    try {
      const response = await rescheduleAdminAppointment(rescheduleAppointmentId, {
        dateTime: `${rescheduleDate}T${rescheduleTime}:00`,
      })
      showNotification({ title: 'Reserva reprogramada', message: response.detail, tone: 'success' })
      setRescheduleAppointmentId(null)
      setRescheduleDate('')
      setRescheduleTime('')
      setRescheduleCheck(null)
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo reprogramar',
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


  const getPaymentNote = (paymentId: number, fallbackNote?: string) =>
    paymentNotes[paymentId] ?? fallbackNote ?? ''

  const handlePaymentNoteChange = (paymentId: number, note: string) => {
    setPaymentNotes((current) => ({
      ...current,
      [paymentId]: note,
    }))
  }

  async function handlePaymentStatusUpdate(
    paymentId: number,
    currentStatus: string,
    status: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO',
    fallbackNote?: string,
  ) {
    const normalizedCurrentStatus = currentStatus.trim().toUpperCase()
    if (normalizedCurrentStatus === 'APROBADO') {
      showNotification({
        title: 'Pago bloqueado',
        message: 'Los pagos aprobados ya no se pueden modificar.',
        tone: 'warning',
      })
      return
    }
    setPaymentActionId(paymentId)
    try {
      const note = status === 'PENDIENTE' ? '' : getPaymentNote(paymentId, fallbackNote)
      const response = await updateAdminPaymentStatus(paymentId, { status, note })
      showNotification({
        title: 'Pago actualizado',
        message: response.detail,
        tone:
          status === 'APROBADO'
            ? 'success'
            : status === 'RECHAZADO' || status === 'CANCELADO'
              ? 'warning'
              : 'info',
      })
      setPaymentNotes((current) => ({ ...current, [paymentId]: response.payment.note || '' }))
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo actualizar el pago',
        message: requestError instanceof Error ? requestError.message : 'Ocurrio un error al cambiar el estado del pago.',
        tone: 'danger',
      })
    } finally {
      setPaymentActionId(null)
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

  const operationStatuses = Array.from(new Set(data.operations.map((operation) => operation.status)))
  const filteredOperations = data.operations.filter((operation) =>
    operationStatusFilter ? operation.status === operationStatusFilter : true,
  )
  const pendingQuotaProcedures = Array.from(new Set(data.pendingQuotas.map((quota) => quota.operation)))
  const filteredPendingQuotas = data.pendingQuotas.filter((quota) =>
    pendingQuotaProcedureFilter ? quota.operation === pendingQuotaProcedureFilter : true,
  )

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
                branches.filter((branch) => branch.id !== currentBranchId).map((branch) => `[ ${branch.id} ] - ${branch.nombre}`).join('\n')
              )
              if (targetBranchId) {
                handleMigrateClient(Number(targetBranchId))
              }
            }
          }] : [])
        ]}
      />

      <AdminRelationshipTabs />

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

      <SectionCard eyebrow="Agenda" title="Todas las citas del cliente" description="Historial completo de reservas, sesiones realizadas, cancelaciones y pendientes de verificacion.">
        {data.appointments.length ? (
          <div className="table-card">
            <table>
              <thead>
                <tr>
                  <th>Operacion</th>
                  <th>Especialista</th>
                  <th>Fecha</th>
                  <th>Estado</th>
                  <th>Verificacion</th>
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
                    <td>{verificationStatusLabel[appointment.verificationStatus]}</td>
                    <td>
                      <div className="table-action-list">
                        {appointment.canMarkPendingBiometric ? (
                          <button
                            className="button button--ghost button--compact"
                            disabled={appointmentActionId !== null}
                            type="button"
                            onClick={() => void handleMarkPendingBiometric(appointment.rawId)}
                          >
                            {appointmentActionId === appointment.rawId ? 'Actualizando...' : 'Cambiar a pendiente de verificacion'}
                          </button>
                        ) : null}
                        {['programada', 'no asistio'].includes(appointment.status?.toLowerCase?.() ?? '') ? (
                          <button
                            className="button button--ghost button--compact"
                            disabled={appointmentActionId !== null}
                            type="button"
                            onClick={() => {
                              setRescheduleAppointmentId(appointment.rawId)
                              setRescheduleCheck(null)
                            }}
                          >
                            Reprogramar reserva
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
        {rescheduleAppointmentId ? (
          <div style={{ marginTop: '1rem', padding: '1rem', background: 'var(--c-neutral-100)', borderRadius: '8px' }}>
            <p style={{ marginBottom: '1rem' }}><strong>Reprogramar cita seleccionada</strong></p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <label className="field">
                <span>Nueva fecha</span>
                <input type="date" className="input" value={rescheduleDate} onChange={(e) => { setRescheduleDate(e.target.value); setRescheduleCheck(null) }} />
              </label>
              <label className="field">
                <span>Nueva hora</span>
                <input type="time" className="input" value={rescheduleTime} onChange={(e) => { setRescheduleTime(e.target.value); setRescheduleCheck(null) }} />
              </label>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
              <button type="button" className="button button--secondary" disabled={!rescheduleDate || !rescheduleTime || isCheckingReschedule} onClick={() => void handleCheckRescheduleAvailability()}>
                {isCheckingReschedule ? 'Verificando...' : 'Verificar disponibilidad'}
              </button>
              <button type="button" className="button button--primary" disabled={!rescheduleCheck || appointmentActionId !== null} onClick={() => void handleRescheduleAppointment()}>
                {appointmentActionId === rescheduleAppointmentId ? 'Confirmando...' : 'Confirmar reprogramacion en esta hora'}
              </button>
              <button type="button" className="button button--ghost" onClick={() => { setRescheduleAppointmentId(null); setRescheduleCheck(null) }}>
                Cancelar
              </button>
            </div>
            {rescheduleCheck ? (
              <p style={{ marginTop: '0.75rem' }}>
                Citas simultaneas de 1 hora antes a 1 hora despues ({rescheduleCheck.hora_inicio} a {rescheduleCheck.hora_fin}): {rescheduleCheck.concurrency}. Especialistas en turno {rescheduleCheck.hora_seleccionada}: {rescheduleCheck.presentes.length > 0 ? rescheduleCheck.presentes.map((p) => p.usuario__primer_nombre).join(', ') : 'Ninguno registrado'}.
              </p>
            ) : null}
          </div>
        ) : null}
      </SectionCard>

      <section className="dashboard-grid">
        <SectionCard eyebrow="Sesiones" title="Sesiones realizadas" description="Citas confirmadas con verificacion registrada.">
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
          ) : <DataState title="Sin sesiones realizadas" message="Todavia no hay sesiones confirmadas con verificacion." />}
        </SectionCard>

        <SectionCard eyebrow="Pagos" title="Pagos pendientes" description="Cuotas aun no pagadas o pendientes de completar.">
          {data.pendingQuotas.length ? (
            <>
              <label className="field" style={{ marginBottom: 12 }}>
                <span>Filtrar por procedimiento</span>
                <select className="input" value={pendingQuotaProcedureFilter} onChange={(event) => setPendingQuotaProcedureFilter(event.target.value)}>
                  <option value="">Todos los procedimientos</option>
                  {pendingQuotaProcedures.map((procedure) => (
                    <option key={procedure} value={procedure}>{procedure}</option>
                  ))}
                </select>
              </label>
              {filteredPendingQuotas.length ? (
                <div className="capacity-list">
              {filteredPendingQuotas.map((quota) => (
                <article className="capacity-item" key={quota.id}>
                  <div className="capacity-item__header">
                    <div><strong>{quota.operation} | {quota.quotaLabel}</strong><p>{quota.amount} | Vence: {quota.dueDate}</p></div>
                    <StatusBadge tone={quota.statusTone}>{quota.status}</StatusBadge>
                  </div>
                </article>
              ))}
            </div>
              ) : <DataState title="Sin resultados" message="No hay pagos pendientes para el procedimiento seleccionado." />}
            </>
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
                  <th>Observacion</th>
                  <th>Acciones</th>
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
                    <td>
                      <input
                        className="input"
                        value={getPaymentNote(payment.rawId, payment.note)}
                        onChange={(event) => handlePaymentNoteChange(payment.rawId, event.target.value)}
                        placeholder="Nota para aprobacion u observacion"
                      />
                    </td>
                    <td>
                      <div className="table-action-list">
                        {(() => {
                          const normalizedStatus = payment.status.trim().toUpperCase()
                          const isApproved = normalizedStatus === 'APROBADO'

                          if (isApproved) {
                            return <span className="table-muted">Sin cambios</span>
                          }

                          return (
                            <>
                              <button className="button button--ghost button--compact" disabled={paymentActionId === payment.rawId || normalizedStatus === 'APROBADO'} type="button" onClick={() => void handlePaymentStatusUpdate(payment.rawId, payment.status, 'APROBADO', payment.note)}>Aprobar</button>
                              <button className="button button--ghost button--compact" disabled={paymentActionId === payment.rawId || normalizedStatus === 'RECHAZADO'} type="button" onClick={() => void handlePaymentStatusUpdate(payment.rawId, payment.status, 'RECHAZADO', payment.note)}>Observar</button>
                              <button className="button button--ghost button--compact" disabled={paymentActionId === payment.rawId || normalizedStatus === 'CANCELADO'} type="button" onClick={() => void handlePaymentStatusUpdate(payment.rawId, payment.status, 'CANCELADO', payment.note)}>Cancelar</button>
                              <button className="button button--ghost button--compact" disabled={paymentActionId === payment.rawId || normalizedStatus === 'PENDIENTE'} type="button" onClick={() => void handlePaymentStatusUpdate(payment.rawId, payment.status, 'PENDIENTE', payment.note)}>Pendiente</button>
                            </>
                          )
                        })()}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <DataState title="Sin pagos registrados" message="El cliente aun no tiene pagos en su historial." />}
      </SectionCard>

      <SectionCard eyebrow="Tratamientos" title="Procedimientos del cliente" description="Resumen operativo de tratamientos activos e historicos.">
        {data.operations.length ? (
          <>
            <label className="field" style={{ marginBottom: 12 }}>
              <span>Filtrar por estado</span>
              <select className="input" value={operationStatusFilter} onChange={(event) => setOperationStatusFilter(event.target.value)}>
                <option value="">Todos los estados</option>
                {operationStatuses.map((status) => (
                  <option key={status} value={status}>{status}</option>
                ))}
              </select>
            </label>
            {filteredOperations.length ? (
              <div className="capacity-list">
            {filteredOperations.map((operation) => (
              <article className="capacity-item" key={operation.id}>
                <div className="capacity-item__header">
                  <div>
                    <strong>{operation.procedure}</strong>
                    <p>{operation.zone} | {operation.quotaSummary}</p>
                    <p>Establecido: {operation.startedAt || 'Fecha no registrada'}</p>
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
            ) : <DataState title="Sin resultados" message="No hay procedimientos para el estado seleccionado." />}
          </>
        ) : <DataState title="Sin procedimientos" message="No hay procedimientos asociados a este cliente." />}
      </SectionCard>
    </div>
  )
}
