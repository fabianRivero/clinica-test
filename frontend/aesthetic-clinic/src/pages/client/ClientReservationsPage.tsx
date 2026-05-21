import { useState } from 'react'
import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { confirmationStatusTone } from '../../constants/verification'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import { cancelClientReservation, getClientReservations } from '../../services/api/client'
import { Link, useLocation } from 'react-router-dom'

export function ClientReservationsPage() {
  const location = useLocation()
  const { showNotification } = useNotifications()
  const { data, isLoading, error, reload } = useApiResource(getClientReservations)
  const [isCancellingId, setIsCancellingId] = useState<number | null>(null)
  const flashMessage =
    typeof location.state === 'object' && location.state && 'flashMessage' in location.state
      ? String(location.state.flashMessage)
      : null

  async function handleCancelReservation(appointmentId: number) {
    const confirmed = window.confirm(
      'Esta reserva se cancelará y liberará ese espacio. ¿Deseas continuar?',
    )
    if (!confirmed) return

    setIsCancellingId(appointmentId)
    try {
      const response = await cancelClientReservation(appointmentId)
      showNotification({
        title: 'Reserva cancelada',
        message: response.detail,
        tone: 'success',
      })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo cancelar',
        message:
          requestError instanceof Error
            ? requestError.message
            : 'No pudimos cancelar la reserva seleccionada.',
        tone: 'danger',
      })
    } finally {
      setIsCancellingId(null)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Agenda y reservas"
        title="Mis reservas"
        description="Consulta citas registradas, estado de confirmacion y si tus tratamientos aun tienen sesiones disponibles."
      />

      {flashMessage ? <DataState title="Reserva registrada" message={flashMessage} /> : null}

      {isLoading && !data ? (
        <SectionCard title="Cargando reservas">
          <DataState title="Sincronizando agenda" message="Estamos cargando tus citas y cupos disponibles." />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar tus reservas">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <>
          <section className="dashboard-grid">
            <SectionCard
              eyebrow="Agenda"
              title="Citas registradas"
              description="Incluye citas futuras y tambien las que esperan confirmacion o quedaron con observaciones."
            >
              {data.appointments.length ? (
                <div className="table-card">
                  <table>
                    <thead>
                      <tr>
                        <th>Operacion</th>
                        <th>Especialista</th>
                        <th>Fecha</th>
                        <th>Estado</th>
                        <th>Confirmacion</th>
                        <th>Acciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.appointments.map((appointment) => (
                        <tr key={appointment.id}>
                          <td>
                            <strong>{appointment.operation}</strong>
                            <span>{appointment.details}</span>
                          </td>
                          <td>{appointment.specialist}</td>
                          <td>{appointment.dateTime}</td>
                          <td>
                            <StatusBadge tone={appointment.statusTone}>{appointment.status}</StatusBadge>
                          </td>
                          <td>
                            <StatusBadge
                              tone={confirmationStatusTone[appointment.confirmationStatus]}
                            >
                              {appointment.confirmationLabel}
                            </StatusBadge>
                          </td>
                          <td>
                            {appointment.canManage ? (
                              <div className="table-actions">
                                <Link
                                  className="button button--ghost button--compact"
                                  to={`/cliente/reservas/citas/${appointment.rawId}/editar`}
                                >
                                  Editar
                                </Link>
                                <button
                                  className="button button--ghost button--compact"
                                  disabled={isCancellingId === appointment.rawId}
                                  type="button"
                                  onClick={() => void handleCancelReservation(appointment.rawId)}
                                >
                                  {isCancellingId === appointment.rawId ? 'Cancelando...' : 'Cancelar'}
                                </button>
                              </div>
                            ) : (
                              <span className="table-muted">Sin cambios</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <DataState title="Sin citas registradas" message="Aun no tienes citas programadas en el sistema." />
              )}
            </SectionCard>

            <SectionCard
              eyebrow="Capacidad"
              title="Disponibilidad de reserva por tratamiento"
              description="Muestra si cada tratamiento en proceso puede recibir una nueva reserva web."
            >
              {data.operations.length ? (
                <div className="capacity-list">
                  {data.operations.map((operation) => (
                    <article className="capacity-item" key={operation.id}>
                      <div className="capacity-item__header">
                        <div>
                          <strong>{operation.procedure}</strong>
                          <p>{operation.reserveMessage}</p>
                        </div>
                        <StatusBadge tone={operation.canReserve ? 'success' : 'warning'}>
                          {operation.canReserve ? 'Con cupo' : 'Bloqueado'}
                        </StatusBadge>
                      </div>
                      <div className="operation-card__stats">
                        <article>
                          <span>1er pago</span>
                          <strong>{operation.firstPaymentVerified ? 'Verificado' : 'Pendiente'}</strong>
                        </article>
                        <article>
                          <span>Confirmadas</span>
                          <strong>{operation.sessions.confirmed}</strong>
                        </article>
                        <article>
                          <span>Pend. verificacion</span>
                          <strong>{operation.sessions.pendingBiometric}</strong>
                        </article>
                        <article>
                          <span>Reservadas</span>
                          <strong>{operation.sessions.reserved}</strong>
                        </article>
                        <article>
                          <span>Libres</span>
                          <strong>{operation.sessions.available}</strong>
                        </article>
                      </div>
                      {operation.canReserve ? (
                        <Link className="button button--ghost" to={`/cliente/reservas/${operation.rawId}/nueva`}>
                          Reservar
                        </Link>
                      ) : (
                        <button className="button button--ghost" type="button" disabled>
                          {operation.firstPaymentVerified ? 'Reserva bloqueada' : '1er pago pendiente'}
                        </button>
                      )}
                    </article>
                  ))}
                </div>
              ) : (
                <DataState
                  title="Sin tratamientos reservables"
                  message="No tienes operaciones en proceso para gestionar reservas en este momento."
                />
              )}
            </SectionCard>
          </section>
        </>
      ) : null}
    </div>
  )
}
