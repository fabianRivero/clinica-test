import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { AdminRelationshipTabs } from '../../../components/admin/AdminRelationshipTabs'
import { PageHeader } from '../../../components/admin/PageHeader'
import { SectionCard } from '../../../components/admin/SectionCard'
import { StatusBadge } from '../../../components/admin/StatusBadge'
import { DataState } from '../../../components/admin/DataState'
import { useClientDetail } from './useClientDetail'
import { ClientReservationSection } from './ClientReservationSection'
import { ClientFreeMedicalAppointmentSection } from './ClientFreeMedicalAppointmentSection'
import { ClientPaymentSection } from './ClientPaymentSection'
import { ClientOperationList } from './ClientOperationList'
import { ClientProfileModal } from './ClientProfileModal'
import { RescheduleModal } from './RescheduleModal'

export function AdminClientDetailPage() {
  const { clientId = '' } = useParams()
  const {
    data,
    isLoading,
    error,
    navigate,
    ConfirmDialogModal,

    // Reservation state
    setSelectedOperationId,
    selectedDate,
    setSelectedDate,
    selectedTime,
    setSelectedTime,
    concurrencyInfo,
    setConcurrencyInfo,
    isChecking,
    isBookingKey,
    effectiveOperationId,
    reservableOperations,
    handleCheckConcurrency,
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
    operationStatuses,
    filteredOperations,
    setOperationStatusFilter,

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
    handleConfirmBiometric,
    handleCancelFromVerification,
    handleCheckRescheduleAvailability,
    handleRescheduleAppointment,
    rescheduleAppointmentId,
    setRescheduleAppointmentId,
    rescheduleDate,
    setRescheduleDate,
    rescheduleTime,
    setRescheduleTime,
    rescheduleCheck,
    setRescheduleCheck,
    isCheckingReschedule,

    // Operations pagination
    visibleOperations,
    visibleOperationsCount,
    hasMoreOperations,
    hasLessOperations,
  } = useClientDetail(clientId)

  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const [rescheduleModalOpen, setRescheduleModalOpen] = useState(false)
  const [selectedSession, setSelectedSession] = useState<any>(null)

  function handleOpenReschedule(session: any) {
    setSelectedSession(session)
    setRescheduleAppointmentId(session.rawId)
    setRescheduleModalOpen(true)
  }

  function handleCloseReschedule() {
    setRescheduleModalOpen(false)
    setSelectedSession(null)
    setRescheduleDate('')
    setRescheduleTime('')
    setRescheduleCheck(null)
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
          effectiveOperationId={effectiveOperationId}
          reservableOperations={reservableOperations}
          selectedDate={selectedDate}
          selectedTime={selectedTime}
          concurrencyInfo={concurrencyInfo}
          isChecking={isChecking}
          isBookingKey={isBookingKey}
          onOperationChange={setSelectedOperationId}
          onDateChange={(v) => { setSelectedDate(v); setConcurrencyInfo(null) }}
          onTimeChange={(v) => { setSelectedTime(v); setConcurrencyInfo(null) }}
          onCheckConcurrency={handleCheckConcurrency}
          onReserve={handleReserve}
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
                    {session.canConfirmBiometric ? (
                      <button
                        className="button button--ghost button--compact"
                        disabled={appointmentActionId !== null}
                        type="button"
                        onClick={() => void handleConfirmBiometric(session.rawId, session.biometricMockTemplate)}
                      >
                        {appointmentActionId === session.rawId ? 'Validando...' : 'Confirmar huella mock'}
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
                    {!session.canManage && !session.canMarkPendingBiometric && !session.canConfirmBiometric && !session.canCancelFromVerification && !['Programada', 'No asistio'].includes(session.status) ? (
                      <span className="table-muted">Sin cambios</span>
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
        operationStatuses={operationStatuses}
        filteredOperations={filteredOperations}
        onFilterChange={setOperationStatusFilter}
      />

      <ConfirmDialogModal />

      <ClientProfileModal
        clientId={clientId}
        isOpen={profileModalOpen}
        onClose={() => setProfileModalOpen(false)}
      />

      <RescheduleModal
        isOpen={rescheduleModalOpen}
        onClose={handleCloseReschedule}
        session={selectedSession}
        rescheduleDate={rescheduleDate}
        setRescheduleDate={setRescheduleDate}
        rescheduleTime={rescheduleTime}
        setRescheduleTime={setRescheduleTime}
        concurrencyInfo={rescheduleCheck}
        isChecking={isCheckingReschedule}
        onCheckAvailability={handleCheckRescheduleAvailability}
        onConfirm={() => handleRescheduleAppointment(() => setRescheduleModalOpen(false))}
        isBookingKey={appointmentActionId ? 'reprogramming' : null}
      />
    </div>
  )
}
