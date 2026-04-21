import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getClientReservations } from '../../services/api/client'

export function ClientReservationsPage() {
  const { data, isLoading, error } = useApiResource(getClientReservations)

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Agenda y reservas"
        title="Mis reservas"
        description="Consulta citas registradas, estado biometrico y si tus tratamientos aun tienen sesiones disponibles."
      />

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
          <section className="metrics-grid">
            {data.metrics.map((metric) => (
              <MetricCard key={metric.id} metric={metric} />
            ))}
          </section>

          <section className="dashboard-grid">
            <SectionCard
              eyebrow="Agenda"
              title="Citas registradas"
              description="Incluye citas futuras y tambien las que esperan cierre biometrico o quedaron con observaciones."
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
                        <th>Biometria</th>
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
                          <td>{appointment.biometric}</td>
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
                          {operation.canReserve ? 'Con cupo' : 'Sin cupo'}
                        </StatusBadge>
                      </div>
                      <div className="operation-card__stats">
                        <article>
                          <span>Confirmadas</span>
                          <strong>{operation.sessions.confirmed}</strong>
                        </article>
                        <article>
                          <span>Pend. biometria</span>
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
                      <button className="button button--ghost" type="button" disabled={!operation.canReserve}>
                        {operation.canReserve ? 'Reserva web disponible pronto' : 'No disponible'}
                      </button>
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
