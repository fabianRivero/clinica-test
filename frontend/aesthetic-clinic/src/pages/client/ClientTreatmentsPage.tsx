import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getClientTreatments } from '../../services/api/client'

export function ClientTreatmentsPage() {
  const { data, isLoading, error } = useApiResource(getClientTreatments)

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Historial de tratamientos"
        title="Mis tratamientos"
        description="Detalle completo de operaciones activas, cerradas, canceladas o en borrador dentro de tu cuenta."
      />

      {isLoading && !data ? (
        <SectionCard title="Cargando tratamientos">
          <DataState title="Sincronizando historial" message="Estamos cargando tu historial clinico y operativo." />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar tus tratamientos">
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

          <SectionCard
            eyebrow="Operacion por operacion"
            title="Detalle de tratamientos"
            description="Cada tarjeta resume sesiones, recomendaciones, zona tratada y disponibilidad de nuevas reservas."
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
                        <dt>Especialista</dt>
                        <dd>{operation.specialist}</dd>
                      </div>
                      <div>
                        <dt>Zona</dt>
                        <dd>{operation.zone}</dd>
                      </div>
                      <div>
                        <dt>Inicio</dt>
                        <dd>{operation.startedAt}</dd>
                      </div>
                      <div>
                        <dt>Cierre</dt>
                        <dd>{operation.endedAt}</dd>
                      </div>
                      <div>
                        <dt>Proxima cita</dt>
                        <dd>{operation.nextAppointment}</dd>
                      </div>
                      <div>
                        <dt>Monto pactado</dt>
                        <dd>{operation.price}</dd>
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
                        <span>Pend. biometria</span>
                        <strong>{operation.sessions.pendingBiometric}</strong>
                      </article>
                      <article>
                        <span>Libres</span>
                        <strong>{operation.sessions.available}</strong>
                      </article>
                    </div>

                    <div className="operation-card__note-grid">
                      <article>
                        <span>Reserva</span>
                        <p>{operation.reserveMessage}</p>
                      </article>
                      <article>
                        <span>Recomendaciones</span>
                        <p>{operation.recommendations}</p>
                      </article>
                      <article>
                        <span>Detalle</span>
                        <p>{operation.details}</p>
                      </article>
                      <article>
                        <span>Cuotas</span>
                        <p>{operation.quotaSummary}</p>
                      </article>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <DataState title="Sin tratamientos" message="No encontramos operaciones registradas para esta cuenta." />
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  )
}
