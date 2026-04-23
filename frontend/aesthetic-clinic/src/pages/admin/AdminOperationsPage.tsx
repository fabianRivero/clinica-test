import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getAdminOperations } from '../../services/api/admin'

export function AdminOperationsPage() {
  const { data, isLoading, error } = useApiResource(getAdminOperations)

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Seguimiento clinico"
        title="Operaciones"
        description="Vista administrativa de tratamientos vigentes, sesiones pactadas, cuotas y citas asociadas."
        actions={[
          { label: 'Configurar disponibilidad', variant: 'primary', to: '/admin/disponibilidad' },
          { label: 'Filtrar por estado', variant: 'ghost' },
        ]}
      />

      {isLoading && !data ? (
        <SectionCard title="Cargando operaciones">
          <DataState
            title="Sincronizando tratamientos"
            message="Traemos el estado actual de las operaciones desde Django."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar operaciones">
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
            eyebrow="Control operativo"
            title="Resumen de tratamientos"
            description="Lectura real de operaciones vigentes, sesiones disponibles y situacion de cuotas."
          >
            {data.operations.length ? (
              <div className="operation-grid">
                {data.operations.map((operation) => (
                  <article className="operation-card" key={operation.id}>
                    <header>
                      <div>
                        <strong>{operation.patient}</strong>
                        <p>{operation.procedure}</p>
                      </div>
                      <StatusBadge tone="primary">{operation.status || 'Sin estado'}</StatusBadge>
                    </header>
                    <dl>
                      <div>
                        <dt>Especialista</dt>
                        <dd>{operation.specialist}</dd>
                      </div>
                      <div>
                        <dt>Sesiones</dt>
                        <dd>{operation.sessions}</dd>
                      </div>
                      <div>
                        <dt>Proxima cita</dt>
                        <dd>{operation.nextAppointment}</dd>
                      </div>
                      <div>
                        <dt>Pagos</dt>
                        <dd>{operation.quotaStatus}</dd>
                      </div>
                      <div>
                        <dt>Monto pactado</dt>
                        <dd>{operation.price}</dd>
                      </div>
                    </dl>
                  </article>
                ))}
              </div>
            ) : (
              <DataState
                title="Sin operaciones"
                message="Todavia no hay tratamientos creados en la base conectada."
              />
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  )
}
