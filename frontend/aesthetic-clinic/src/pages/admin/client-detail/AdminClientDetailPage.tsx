import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { AdminRelationshipTabs } from '../../../components/admin/AdminRelationshipTabs'
import { PageHeader } from '../../../components/admin/PageHeader'
import { SectionCard } from '../../../components/admin/SectionCard'
import { StatusBadge } from '../../../components/admin/StatusBadge'
import { DataState } from '../../../components/admin/DataState'
import { useNotifications } from '../../../providers/NotificationProvider'
import { useBranchContext } from '../../../providers/BranchProvider'
import { useClientDetail } from './useClientDetail'
import { ClientReservationSection } from './ClientReservationSection'
import { ClientFreeMedicalAppointmentSection } from './ClientFreeMedicalAppointmentSection'
import { ClientPaymentSection } from './ClientPaymentSection'
import { ClientOperationList } from './ClientOperationList'
import { ClientProfileModal } from './ClientProfileModal'
import { ReservationModal } from '../components/ReservationModal'
import { BiometricVerifyCaptureModal } from './BiometricVerifyCaptureModal'
import { CerrarCitaModal, type CerrarCitaPayload } from '../components/CerrarCitaModal'

const BIOMETRIC_SUSPENDED_NOTICE =
  'Verificacion por huella temporalmente suspendida. Usa la confirmacion manual para finalizar las citas pendientes.'

export function AdminClientDetailPage() {
  const { clientId = '' } = useParams()
  const { showNotification } = useNotifications()
  const {
    data,
    isLoading,
    error,
    reload,
    navigate,
    ConfirmDialogModal,

    // Reservation state
    isChecking,
    isBookingKey,
    reservableOperations,
    handleReserve,

    // Free medical appointment state
    freeSelectedDate,
    setFreeSelectedDate,
    freeSelectedTime,
    setFreeSelectedTime,
    freeConcurrencyInfo,
    setFreeConcurrencyInfo,
    isFreeBookingKey,
    handleCheckFreeConcurrency,
    handleReserveFreeMedicalAppointment,

    // Client status
    isInactivating,
    isMigrating,
    isMainAdmin,
    branches,
    handleInactivateClient,
    handleMigrateClient,

    // Payment state
    paymentActionId,
    getPaymentNote,
    handlePaymentNoteChange,
    handlePaymentStatusUpdate,

    // Pending quota state
    pendingQuotaProcedureFilter,
    pendingQuotaProcedures,
    filteredPendingQuotas,
    setPendingQuotaProcedureFilter,

    // Operation state
    operationStatusFilter,
    setOperationStatusFilter,
    operationPeriodFilter,
    setOperationPeriodFilter,
    operationStatuses,
    filteredOperations,

    // Payments pagination
    visiblePayments,
    visiblePaymentsCount,
    setVisiblePaymentsCount,
    hasMorePayments,
    hasLessPayments,

    // Sessions pagination
    visibleSessions,
    visibleSessionsCount,
    setVisibleSessionsCount,
    hasMoreSessions,
    hasLessSessions,
    sessionStatusFilter,
    setSessionStatusFilter,
    sessionStatuses,
    sessionProcedureFilter,
    setSessionProcedureFilter,
    sessionProcedures,
    filteredSessions,

    // Appointment actions
    appointmentActionId,
    handleCancelAppointment,
    handleMarkPendingBiometric,
    handleCancelFromVerification,
    handleRescheduleAppointment,
    setRescheduleAppointmentId,

    // Biometric verify modal
    verifyModalCitaId,
    openVerifyBiometric,
    closeVerifyBiometric,

    // Operations pagination
    visibleOperations,
    visibleOperationsCount,
    hasMoreOperations,
    hasLessOperations,

    // Biometric agent state
    hasAnyAgent,
    allAgentsOffline,
    biometricSuspended,
    hasBiometricEnrollment,
  } = useClientDetail(clientId)

  const { activeBranch } = useBranchContext()

  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const [rescheduleModalOpen, setRescheduleModalOpen] = useState(false)
  const [selectedSession, setSelectedSession] = useState<any>(null)
  const [closingAppointmentId, setClosingAppointmentId] = useState<number | null>(null)
  // Tracks which session's real-time panel is open in the comparison modal.
  const [realTimeOpenSessionId, setRealTimeOpenSessionId] = useState<number | null>(null)
  // Photo lightbox: opens when the admin clicks "Ver foto antes/despues"
  // inside the comparison modal. null = closed.
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null)

  function handleOpenReschedule(session: any) {
    setSelectedSession(session)
    setRescheduleAppointmentId(session.rawId)
    setRescheduleModalOpen(true)
  }

  if (isLoading && !data) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="Clientes" title="Cargando cliente" description="Estamos preparando su historial administrativo." />
        <SectionCard title="Sincronizando">
          <DataState title="Cargando información" message="Consultando citas, sesiones, pagos y procedimientos." />
        </SectionCard>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="Clientes" title="No pudimos cargar el cliente" description="Revisa la lista e intenta nuevamente." actions={[{ label: 'Volver a clientes', variant: 'ghost', to: '/cms/clientes' }]} />
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
        description={`${data.client.status} | ${data.client.phone} | Último análisis: ${data.client.lastAnalysis}`}
        actions={[
          { label: 'Volver a clientes', variant: 'ghost', to: '/cms/clientes' },
          ...(data.client.status === 'Inactivo' ? [{
            label: 'Reactivar / Nuevo tratamiento',
            onClick: () => navigate(`/cms/clientes/${clientId}/reactivar`)
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
          }] : []),
          { label: 'Ver perfil del cliente', variant: 'ghost' as const, onClick: () => setProfileModalOpen(true) }
        ]}
      />

      {biometricSuspended ? (
        <div
          className="banner banner--warning"
          data-testid="biometric-suspended-banner"
          role="status"
          aria-live="polite"
        >
          <strong>Huella biometrica suspendida.</strong>
          <span>{BIOMETRIC_SUSPENDED_NOTICE}</span>
        </div>
      ) : hasAnyAgent && allAgentsOffline ? (
        <div className="banner banner--warning" role="status" aria-live="polite">
          <strong>Lector de huellas sin conexion.</strong>
          <span>
            Ningun agente reporto heartbeat en los ultimos 5 minutos. Si necesitas confirmar la
            asistencia, usa la confirmacion manual hasta que el lector vuelva a estar disponible.
          </span>
        </div>
      ) : !hasBiometricEnrollment ? (
        <div
          className="banner banner--info"
          data-testid="biometric-enrollment-pending-banner"
          role="status"
          aria-live="polite"
        >
          <strong>Este cliente aun no tiene huella registrada.</strong>
        </div>
      ) : null}

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
                onClick={() => navigate(`/cms/clientes/${clientId}/reactivar`)}
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
              onClick={() => navigate(`/cms/clientes/${clientId}/reactivar`)}
            >
              Reactivar / Nuevo tratamiento
            </button>
          )}
        </div>
      </SectionCard>

      <section className="dashboard-grid">
        <ClientReservationSection
          effectiveOperationId={0}
          reservableOperations={reservableOperations}
          branchId={activeBranch?.id ?? null}
          onReserve={handleReserve}
          isBookingKey={isBookingKey}
        />
      </section>

      <ClientFreeMedicalAppointmentSection
        freeSelectedDate={freeSelectedDate}
        freeSelectedTime={freeSelectedTime}
        freeConcurrencyInfo={freeConcurrencyInfo}
        isChecking={isChecking}
        isFreeBookingKey={isFreeBookingKey}
        setFreeSelectedDate={setFreeSelectedDate}
        setFreeSelectedTime={setFreeSelectedTime}
        setFreeConcurrencyInfo={setFreeConcurrencyInfo}
        handleCheckFreeConcurrency={handleCheckFreeConcurrency}
        handleReserveFreeMedicalAppointment={handleReserveFreeMedicalAppointment}
      />

      <SectionCard eyebrow="Sesiones" title="Sesiones realizadas" description="Todas las sesiones del cliente.">
        {data.sessions.length ? (
          <>
            <div className="_flex _gap-sm _mb-sm">
              <label className="field">
                <span>Estado</span>
                <select className="input" value={sessionStatusFilter} onChange={(e) => setSessionStatusFilter(e.target.value)}>
                  <option value="">Todos</option>
                  {sessionStatuses.map((status) => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Procedimiento</span>
                <select className="input" value={sessionProcedureFilter} onChange={(e) => setSessionProcedureFilter(e.target.value)}>
                  <option value="">Todos</option>
                  {sessionProcedures.map((proc) => (
                    <option key={proc} value={proc}>{proc}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="capacity-list">
              {visibleSessions.map((session: any) => (
                <article className="capacity-item" key={session.id}>
                  <div className="capacity-item__header">
                    <div><strong>{session.operation}</strong><p>{session.dateTime} | {session.specialist}</p><p className="table-muted">{session.zona}</p></div>
                    <StatusBadge tone={session.statusTone}>{session.status}</StatusBadge>
                  </div>
                  <div className="capacity-item__actions">
                    {session.canMarkPendingBiometric ? (
                      <button
                        className="button button--ghost button--compact"
                        disabled={appointmentActionId !== null}
                        type="button"
                        onClick={() => void handleMarkPendingBiometric(session.rawId)}
                      >
                        {appointmentActionId === session.rawId ? 'Actualizando...' : 'Cambiar a pendiente de verificación'}
                      </button>
                    ) : null}
                    {session.canManage ? (
                      <button
                        className="button button--ghost button--compact"
                        disabled={appointmentActionId !== null}
                        type="button"
                        onClick={() => void handleCancelAppointment(session.rawId)}
                      >
                        Cancelar reserva
                      </button>
                    ) : null}
                    {session.canConfirmBiometric && !biometricSuspended ? (
                      <button
                        className="button button--ghost button--compact"
                        disabled={appointmentActionId !== null}
                        type="button"
                        onClick={() => openVerifyBiometric(session.rawId)}
                      >
                        {appointmentActionId === session.rawId ? 'Validando...' : 'Confirmar con huella'}
                      </button>
                    ) : null}
                    {session.canCancelFromVerification ? (
                      <button
                        className="button button--ghost button--compact"
                        disabled={appointmentActionId !== null}
                        type="button"
                        onClick={() => void handleCancelFromVerification(session.rawId)}
                      >
                        Cancelar
                      </button>
                    ) : null}
                    {['Programada', 'No asistio'].includes(session.status) ? (
                      <button
                        className="button button--ghost button--compact"
                        disabled={appointmentActionId !== null}
                        type="button"
                        onClick={() => handleOpenReschedule(session)}
                      >
                        Reprogramar
                      </button>
                    ) : null}
                    {session.status === 'Confirmada' ? (
                      <button
                        className="button button--primary button--compact"
                        type="button"
                        onClick={() => setClosingAppointmentId(session.rawId)}
                      >
                        Establecer datos reales
                      </button>
                    ) : null}
                    {session.hasRealTimeData ? (
                      <button
                        className="button button--ghost button--compact"
                        type="button"
                        onClick={() =>
                          setRealTimeOpenSessionId(
                            realTimeOpenSessionId === session.rawId
                              ? null
                              : session.rawId,
                          )
                        }
                        aria-expanded={realTimeOpenSessionId === session.rawId}
                      >
                        {realTimeOpenSessionId === session.rawId
                          ? 'Ocultar datos'
                          : 'Ver datos'}
                      </button>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
            {filteredSessions.length === 0 && data.sessions.length > 0 ? (
              <DataState title="Sin resultados" message="No hay sesiones para los filtros seleccionados." />
            ) : filteredSessions.length > 5 ? (
              <div className="_flex-between _mt-md">
                <span>Mostrando {visibleSessionsCount} de {filteredSessions.length} sesiones</span>
                <div>
                  {hasLessSessions && (
                    <button type="button" className="button button--ghost" onClick={() => setVisibleSessionsCount(c => c - 5)}>Ver menos</button>
                  )}
                  {hasMoreSessions && (
                    <button type="button" className="button button--secondary" onClick={() => setVisibleSessionsCount(c => c + 5)}>Ver más</button>
                  )}
                </div>
              </div>
            ) : null}
          </>
        ) : <DataState title="Sin sesiones" message="No hay sesiones registradas para este cliente." />}
      </SectionCard>

      <ClientPaymentSection
        pendingQuotas={data.pendingQuotas}
        payments={data.payments}
        paymentActionId={paymentActionId}
        getPaymentNote={getPaymentNote}
        onPaymentNoteChange={handlePaymentNoteChange}
        onUpdatePaymentStatus={handlePaymentStatusUpdate}
        pendingQuotaProcedureFilter={pendingQuotaProcedureFilter}
        pendingQuotaProcedures={pendingQuotaProcedures}
        filteredPendingQuotas={filteredPendingQuotas}
        onPendingQuotaFilterChange={setPendingQuotaProcedureFilter}
        visiblePayments={visiblePayments}
        visiblePaymentsCount={visiblePaymentsCount}
        setVisiblePaymentsCount={setVisiblePaymentsCount}
        hasMorePayments={hasMorePayments}
        hasLessPayments={hasLessPayments}
        visiblePendingQuotasCount={5}
        setVisiblePendingQuotasCount={() => {}}
        hasMorePendingQuotas={false}
        hasLessPendingQuotas={false}
      />

      <ClientOperationList
        visibleOperations={visibleOperations}
        visibleOperationsCount={visibleOperationsCount}
        hasMoreOperations={hasMoreOperations}
        hasLessOperations={hasLessOperations}
        operations={data.operations}
        operationStatusFilter={operationStatusFilter}
        operationPeriodFilter={operationPeriodFilter}
        operationStatuses={operationStatuses}
        filteredOperations={filteredOperations}
        onFilterChange={setOperationStatusFilter}
        onPeriodFilterChange={setOperationPeriodFilter}
      />

      <ConfirmDialogModal />

      <ClientProfileModal
        clientId={clientId}
        isOpen={profileModalOpen}
        onClose={() => setProfileModalOpen(false)}
      />

      <ReservationModal
        mode="reschedule"
        isOpen={rescheduleModalOpen}
        onClose={() => {
          setRescheduleModalOpen(false)
          setSelectedSession(null)
        }}
        reservableOperations={
          data?.operations?.length
            ? [
                {
                  id: data.operations[0].rawId,
                  rawId: data.operations[0].rawId,
                  selectLabel: data.operations[0].procedure,
                },
              ]
            : []
        }
        branchId={activeBranch?.id ?? 0}
        prefillCita={
          selectedSession
            ? {
                duracionEstimadaMinutos: selectedSession.duracionEstimadaMinutos,
                descripcionGeneral: selectedSession.descripcionGeneral,
                notasPrevias: selectedSession.notasPrevias,
                procedimientoPlanificado: selectedSession.procedimientoPlanificado,
                zonaCuerpoPlanificada: selectedSession.zonaCuerpoPlanificada,
                especialistasPlanificados: selectedSession.especialistasPlanificados,
                maquinariaPlanificada: selectedSession.maquinariaPlanificada,
              }
            : undefined
        }
        onConfirm={(payload) =>
          handleRescheduleAppointment(payload, () => setRescheduleModalOpen(false))
        }
        isBooking={appointmentActionId !== null}
      />

      <CerrarCitaModal
        isOpen={closingAppointmentId !== null}
        onClose={() => setClosingAppointmentId(null)}
        cita={
          closingAppointmentId !== null
            ? (data?.appointments?.find(
                (apt: any) => apt.rawId === closingAppointmentId,
              ) as CerrarCitaPayload | undefined) ?? null
            : null
        }
        branchId={activeBranch?.id ?? null}
        // CerrarCitaModal owns the POST to /cerrar/; this callback only
        // runs after a successful response, so we just close + reload here.
        onSuccess={() => {
          setClosingAppointmentId(null)
          reload()
        }}
      />

      {realTimeOpenSessionId !== null ? (
        (() => {
          const selectedSession = data?.sessions.find(
            (s: any) => s.rawId === realTimeOpenSessionId,
          )
          if (!selectedSession || !selectedSession.hasRealTimeData) return null
          return (
            <div
              className="booking-modal-overlay"
              role="dialog"
              aria-modal="true"
              aria-label="Datos reales al cierre"
              onClick={() => setRealTimeOpenSessionId(null)}
              data-testid="real-time-modal"
            >
              <div
                className="booking-modal-content"
                onClick={(event) => event.stopPropagation()}
              >
                <header className="booking-modal-header">
                  <h2 className="_m-0">Datos reales al cierre</h2>
                  <button
                    type="button"
                    className="booking-modal-close"
                    onClick={() => setRealTimeOpenSessionId(null)}
                    aria-label="Cerrar"
                  >
                    ✕
                  </button>
                </header>
                <div className="booking-modal-body">
                  <p className="_text-soft _mb-sm" style={{ fontSize: '0.85rem' }}>
                    Cita {selectedSession.dateTime} · {selectedSession.operation}
                  </p>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 1fr',
                      gap: 'var(--spacing-4)',
                    }}
                  >
                    <section
                      style={{
                        border: '1px solid var(--color-border)',
                        borderRadius: '8px',
                        padding: 'var(--spacing-3)',
                      }}
                    >
                      <h4 className="_mt-0 _mb-sm">Planificado</h4>
                      <dl className="_m-0">
                        <dt>Duración estimada</dt>
                        <dd>
                          {selectedSession.duracionEstimadaMinutos
                            ? `${selectedSession.duracionEstimadaMinutos} min`
                            : '—'}
                        </dd>
                        <dt>Descripción general</dt>
                        <dd>{selectedSession.descripcionGeneral || '—'}</dd>
                        <dt>Notas previas</dt>
                        <dd>{selectedSession.notasPrevias || '—'}</dd>
                        <dt>Procedimiento</dt>
                        <dd>{selectedSession.procedimientoPlanificado || '—'}</dd>
                        <dt>Zona</dt>
                        <dd>{selectedSession.zonaCuerpoPlanificada || '—'}</dd>
                        <dt>Especialistas</dt>
                        <dd>
                          {selectedSession.especialistasPlanificados?.length
                            ? selectedSession.especialistasPlanificados
                                .map(
                                  (e: number | { especialista_id: number }) => {
                                    if (typeof e === 'number') return `id ${e}`
                                    const esp = e as {
                                      especialista_id: number
                                      especialista__usuario__primer_nombre?: string
                                      especialista__usuario__segundo_nombre?: string
                                      especialista__usuario__apellido_paterno?: string
                                      especialista__usuario__apellido_materno?: string
                                      especialista__usuario__username?: string
                                    }
                                    return (
                                      [
                                        esp.especialista__usuario__primer_nombre,
                                        esp.especialista__usuario__segundo_nombre,
                                        esp.especialista__usuario__apellido_paterno,
                                        esp.especialista__usuario__apellido_materno,
                                      ]
                                        .filter(Boolean)
                                        .join(' ')
                                        .trim() ||
                                      esp.especialista__usuario__username ||
                                      `id ${esp.especialista_id}`
                                    )
                                  },
                                )
                                .join(', ')
                            : '—'}
                        </dd>
                        <dt>Maquinaria</dt>
                        <dd>
                          {selectedSession.maquinariaPlanificada?.length
                            ? selectedSession.maquinariaPlanificada
                                .map(
                                  (m: {
                                    maquinariaId: number
                                    cantidad: number
                                    maquinaria__nombre?: string
                                    maquinaria__marca?: string
                                  }) =>
                                    `${m.maquinaria__nombre ?? `id ${m.maquinariaId}`}${
                                      m.maquinaria__marca ? ` (${m.maquinaria__marca})` : ''
                                    } x${m.cantidad}`,
                                )
                                .join(', ')
                            : '—'}
                        </dd>
                      </dl>
                    </section>
                    <section
                      style={{
                        border: '1px solid var(--color-border)',
                        borderRadius: '8px',
                        padding: 'var(--spacing-3)',
                      }}
                    >
                      <h4 className="_mt-0 _mb-sm">Real al cierre</h4>
                      <dl className="_m-0">
                        <dt>Hora real inicio</dt>
                        <dd>{selectedSession.horaRealInicio || '—'}</dd>
                        <dt>Hora real fin</dt>
                        <dd>{selectedSession.horaRealFin || '—'}</dd>
                        <dt>Procedimiento realizado</dt>
                        <dd>{selectedSession.procedimientoRealizado || '—'}</dd>
                        <dt>Zona del cuerpo realizada</dt>
                        <dd>{selectedSession.zonaCuerpoRealizada || '—'}</dd>
                        <dt>Especialistas que atendieron</dt>
                        <dd>
                          {selectedSession.especialistasAtendieron?.length
                            ? selectedSession.especialistasAtendieron
                                .map(
                                  (e: number | { especialista_id: number }) => {
                                    if (typeof e === 'number') return `id ${e}`
                                    const esp = e as {
                                      especialista_id: number
                                      especialista__usuario__primer_nombre?: string
                                      especialista__usuario__segundo_nombre?: string
                                      especialista__usuario__apellido_paterno?: string
                                      especialista__usuario__apellido_materno?: string
                                      especialista__usuario__username?: string
                                    }
                                    return (
                                      [
                                        esp.especialista__usuario__primer_nombre,
                                        esp.especialista__usuario__segundo_nombre,
                                        esp.especialista__usuario__apellido_paterno,
                                        esp.especialista__usuario__apellido_materno,
                                      ]
                                         .filter(Boolean)
                                        .join(' ')
                                        .trim() ||
                                      esp.especialista__usuario__username ||
                                      `id ${esp.especialista_id}`
                                    )
                                  },
                                )
                                .join(', ')
                            : '—'}
                        </dd>
                        <dt>Maquinaria utilizada</dt>
                        <dd>
                          {selectedSession.maquinariaUtilizada?.length
                            ? selectedSession.maquinariaUtilizada
                                .map(
                                  (m: {
                                    maquinaria_id: number
                                    cantidad: number
                                    maquinaria__nombre?: string
                                    maquinaria__marca?: string
                                  }) =>
                                    `${m.maquinaria__nombre ?? `id ${m.maquinaria_id}`}${
                                      m.maquinaria__marca ? ` (${m.maquinaria__marca})` : ''
                                    } x${m.cantidad}`,
                                )
                                .join(', ')
                            : '—'}
                        </dd>
                        <dt>Notas post</dt>
                        <dd>{selectedSession.notasPost || '—'}</dd>
                      </dl>
                      <div
                        style={{
                          display: 'flex',
                          gap: 'var(--spacing-2)',
                          marginTop: 'var(--spacing-3)',
                          flexWrap: 'wrap',
                        }}
                      >
                        <button
                          type="button"
                          className="button button--ghost button--compact"
                          disabled={!selectedSession.fotoAntesUrl}
                          onClick={() =>
                            setPhotoPreviewUrl(
                              selectedSession.fotoAntesUrl || null,
                            )
                          }
                          aria-label="Ver foto antes"
                        >
                          Ver foto antes
                        </button>
                        <button
                          type="button"
                          className="button button--ghost button--compact"
                          disabled={!selectedSession.fotoDespuesUrl}
                          onClick={() =>
                            setPhotoPreviewUrl(
                              selectedSession.fotoDespuesUrl || null,
                            )
                          }
                          aria-label="Ver foto después"
                        >
                          Ver foto después
                        </button>
                      </div>
                    </section>
                  </div>
                </div>
              </div>
            </div>
          )
        })()
      ) : null}

      <BiometricVerifyCaptureModal
        open={!biometricSuspended && verifyModalCitaId !== null}
        citaId={verifyModalCitaId ?? 0}
        onClose={closeVerifyBiometric}
        onConfirmResult={({ matched, message, citaId: confirmedCitaId }) => {
          if (matched) {
            showNotification({
              title: 'Huella confirmada',
              message,
              tone: 'success',
            })
          } else {
            showNotification({
              title: 'Huella rechazada',
              message,
              tone: 'warning',
            })
          }
          // The modal fires onConfirmResult while the modal is still
          // mounted; the actual refetch is triggered by onAfterAttempt
          // when the operator clicks "Cerrar" on the success state.
          void confirmedCitaId
        }}
        onAfterAttempt={() => {
          // Refetch the surrounding page so the cita state reflects
          // CONFIRMADA / BIOMETRICO without a manual reload.
          reload()
        }}
      />

      {photoPreviewUrl ? (
        <div
          className="booking-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Foto de la cita"
          onClick={() => setPhotoPreviewUrl(null)}
          data-testid="photo-lightbox"
        >
          <div
            className="booking-modal-content"
            onClick={(event) => event.stopPropagation()}
            style={{ maxWidth: '40rem' }}
          >
            <header className="booking-modal-header">
              <h2 className="_m-0">Foto</h2>
              <button
                type="button"
                className="booking-modal-close"
                onClick={() => setPhotoPreviewUrl(null)}
                aria-label="Cerrar"
              >
                ✕
              </button>
            </header>
            <div
              className="booking-modal-body"
              style={{ textAlign: 'center' }}
            >
              <img
                src={photoPreviewUrl}
                alt="Foto de la cita"
                style={{
                  maxWidth: '100%',
                  maxHeight: '70vh',
                  borderRadius: '8px',
                }}
              />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
