import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { verificationMethodLabel } from '../../constants/verification'
import { useApiResource } from '../../hooks/useApiResource'
import { getClientDashboard } from '../../services/api/client'

export function ClientDashboardPage() {
  const { data, isLoading, error } = useApiResource(getClientDashboard)

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Resumen personal"
        title="Portal del cliente"
        description="Consulta el estado de tus tratamientos, pagos, cuotas y próximas citas desde una sola vista."
      />

      {isLoading && !data ? (
        <SectionCard title="Cargando portal">
          <DataState
            title="Preparando tu información"
            message="Estamos consultando tratamientos, cuotas, pagos y citas en tiempo real."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar tu portal">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <>
          <section className="client-summary-card" style={{ display: 'flex', gap: '2rem', alignItems: 'flex-start' }}>
            <div>
              <span className="client-summary-card__eyebrow">Hola, {data.welcome.name}</span>
              <h2>Tu estado actual es {data.welcome.status.toLowerCase()}.</h2>
              <p>
                CI: {data.welcome.ci} | Teléfono: {data.welcome.phone} | Último análisis:{' '}
                {data.welcome.lastAnalysis}
              </p>
            </div>

            <div className="client-summary-card__grid" style={{ marginLeft: 'auto' }}>
              <article>
                <span>Tratamientos activos</span>
                <strong>{data.welcome.activeOperations}</strong>
              </article>
              <article>
                <span>Tratamientos totales</span>
                <strong>{data.welcome.totalOperations}</strong>
              </article>
            </div>
          </section>

          <section className="dashboard-grid">
            <SectionCard
              eyebrow="Tratamientos activos"
              title="Tus operaciones vigentes"
              description="Resumen rápido de sesiones."
            >
              {data.operations.length ? (
                <div className="operation-grid">
                  {data.operations.map((operation) => (
                    <article className="operation-card" key={operation.id}>
                      <header>
                        <div>
                          <strong>{operation.procedure}</strong>
                          <p>{operation.serviceType}</p>
                        </div>
                        <StatusBadge tone={operation.statusTone}>{operation.status}</StatusBadge>
                      </header>

                      <dl className="operation-card__details">
                        <div>
                          <dt>Sucursal</dt>
                          <dd>{operation.branch}</dd>
                        </div>
                        <div>
                          <dt>Zona</dt>
                          <dd>{operation.zone}</dd>
                        </div>
                        <div>
                          <dt>Próxima cita</dt>
                          <dd>{operation.nextAppointment}</dd>
                        </div>
                        <div>
                          <dt>Plan de pagos</dt>
                          <dd>{operation.quotaSummary}</dd>
                        </div>
                      </dl>

                      <div className="operation-card__stats">
                        <article>
                          <span>Total</span>
                          <strong>{operation.sessions.total}</strong>
                        </article>
                        <article>
                          <span>Confirmadas</span>
                          <strong>{operation.sessions.confirmed}</strong>
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
                    </article>
                  ))}
                </div>
              ) : (
                <DataState
                  title="Sin tratamientos vigentes"
                  message="Tu cuenta no registra operaciones activas en este momento."
                />
              )}
            </SectionCard>

            <SectionCard
              eyebrow="Agenda"
              title="Próximas citas"
              description="Citas ya registradas o pendientes de cierre de verificación."
            >
              {data.upcomingAppointments.length ? (
                <div className="agenda-list">
                  {data.upcomingAppointments.map((appointment) => (
                    <article className="agenda-item" key={appointment.id}>
                      <div className="agenda-item__time">
                        {appointment.dateTime.split(' ')[1] || appointment.dateTime}
                      </div>
                      <div className="agenda-item__content">
                        <strong>{appointment.operation}</strong>
                        <p>
                          método verificación:{' '}
                          {appointment.verificationMethod
                            ? verificationMethodLabel[appointment.verificationMethod]
                            : 'No especificado'}
                        </p>
                      </div>
                      <StatusBadge tone={appointment.statusTone}>{appointment.status}</StatusBadge>
                    </article>
                  ))}
                </div>
              ) : (
                <DataState
                  title="Sin citas futuras"
                  message="No tienes citas próximas registradas en el calendario."
                />
              )}
            </SectionCard>
          </section>

          <section className="dashboard-grid dashboard-grid--secondary" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <SectionCard
              eyebrow="Cuotas"
              title="Pagos por atender"
              description="Cuotas activas y último estado de tus comprobantes."
            >
              {data.pendingQuotas.length ? (
                <div className="capacity-list">
                  {data.pendingQuotas.map((quota) => (
                    <article className="capacity-item" key={quota.id}>
                      <div className="capacity-item__header">
                        <div>
                          <strong>
                            {quota.operation} | {quota.quotaLabel}
                          </strong>
                          <p>
                            {quota.amount} | vence {quota.dueDate}
                          </p>
                        </div>
                        <StatusBadge tone={quota.statusTone}>{quota.status}</StatusBadge>
                      </div>
                      <p>Último comprobante: {quota.latestPaymentStatus}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <DataState
                  title="Sin cuotas pendientes"
                  message="No tienes cuotas activas por pagar en este momento."
                />
              )}
            </SectionCard>

            <SectionCard
              eyebrow="Pagos recientes"
              title="Historial inmediato"
              description="Últimos comprobantes subidos y su estado de revisión."
            >
              {data.recentPayments.length ? (
                <div className="table-card">
                  <table>
                    <thead>
                      <tr>
                        <th>Operación</th>
                        <th>Cuota</th>
                        <th>Monto</th>
                        <th>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.recentPayments.map((payment) => (
                        <tr key={payment.id}>
                          <td>
                            <strong>{payment.operation}</strong>
                            <span>{payment.submittedAt}</span>
                          </td>
                          <td>{payment.quotaLabel}</td>
                          <td>{payment.amount}</td>
                          <td>
                            <StatusBadge tone={payment.statusTone}>{payment.status}</StatusBadge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <DataState title="Sin pagos registrados" message="Aun no existen comprobantes en tu historial." />
              )}
            </SectionCard>
          </section>
        </>
      ) : null}
    </div>
  )
}
