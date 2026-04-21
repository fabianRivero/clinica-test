import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getAdminDashboard } from '../../services/api/admin'

const agendaTone = {
  programada: 'neutral',
  biometria: 'warning',
  confirmada: 'success',
} as const

export function AdminDashboardPage() {
  const { data, isLoading, error } = useApiResource(getAdminDashboard)

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Vista general"
        title="Centro de control administrativo"
        description="Una lectura rapida del estado financiero, operativo y clinico de la clinica."
        actions={[
          { label: 'Registrar prospecto', variant: 'primary', to: '/admin/prospectos/nuevo' },
          { label: 'Exportar resumen', variant: 'ghost' },
        ]}
      />

      {isLoading && !data ? (
        <SectionCard title="Cargando panel" description="Consultando la API real de administracion.">
          <DataState
            title="Sincronizando informacion"
            message="Cargando pagos, agenda, prospectos, operaciones, catalogos y equipo."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar el panel">
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
              eyebrow="Prioridad del dia"
              title="Validacion de pagos"
              description="Pagos recientes subidos por clientes para revision administrativa."
              action={<button className="button button--ghost">Ver cola completa</button>}
            >
              {data.payments.length ? (
                <div className="table-card">
                  <table>
                    <thead>
                      <tr>
                        <th>Paciente</th>
                        <th>Operacion</th>
                        <th>Monto</th>
                        <th>Canal</th>
                        <th>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.payments.map((payment) => (
                        <tr key={payment.id}>
                          <td>
                            <strong>{payment.patient}</strong>
                            <span>{payment.submittedAt}</span>
                          </td>
                          <td>{payment.operation}</td>
                          <td>{payment.amount}</td>
                          <td>{payment.bank}</td>
                          <td>
                            <StatusBadge
                              tone={
                                payment.status === 'aprobado'
                                  ? 'approved'
                                  : payment.status === 'observado'
                                    ? 'observed'
                                    : 'pending'
                              }
                            >
                              {payment.status}
                            </StatusBadge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <DataState
                  title="Sin pagos recientes"
                  message="Todavia no hay comprobantes registrados en la cola administrativa."
                />
              )}
            </SectionCard>

            <SectionCard
              eyebrow="Agenda clinica"
              title="Citas destacadas"
              description="Seguimiento operativo del dia con foco en citas que necesitan cierre o biometria."
            >
              {data.agenda.length ? (
                <div className="agenda-list">
                  {data.agenda.map((item) => (
                    <article className="agenda-item" key={item.id}>
                      <div className="agenda-item__time">{item.time}</div>
                      <div className="agenda-item__content">
                        <strong>{item.patient}</strong>
                        <p>
                          {item.procedure} | {item.specialist}
                        </p>
                      </div>
                      <StatusBadge tone={agendaTone[item.status]}>{item.status}</StatusBadge>
                    </article>
                  ))}
                </div>
              ) : (
                <DataState
                  title="Sin citas visibles"
                  message="No encontramos citas futuras o recientes para mostrar en el tablero."
                />
              )}
            </SectionCard>

            <SectionCard
              eyebrow="Monitoreo"
              title="Alertas criticas"
              description="Elementos que requieren intervencion administrativa."
            >
              <div className="alert-list">
                {data.alerts.map((alert) => (
                  <article className={`alert-card alert-card--${alert.severity}`} key={alert.id}>
                    <div>
                      <strong>{alert.title}</strong>
                      <p>{alert.description}</p>
                    </div>
                    <button className="button button--ghost" type="button">
                      {alert.action}
                    </button>
                  </article>
                ))}
              </div>
            </SectionCard>
          </section>

          <section className="dashboard-grid dashboard-grid--secondary">

            <SectionCard
              eyebrow="Configuracion"
              title="Salud de catalogos"
              description="Estado general de los catalogos editables que alimentan la operacion clinica."
            >
              <div className="catalog-health">
                {data.catalogHealth.map((item) => (
                  <article className="catalog-health__item" key={item.id}>
                    <div>
                      <strong>{item.name}</strong>
                      <p>{item.note}</p>
                    </div>
                    <span>{item.count}</span>
                  </article>
                ))}
              </div>
            </SectionCard>

            <SectionCard
              eyebrow="Capacidad"
              title="Carga del equipo"
              description="Lectura rapida de especialistas, especialidades y pendientes de validacion."
            >
              <div className="capacity-list">
                {data.staffCapacity.map((item) => (
                  <article className="capacity-item" key={item.id}>
                    <div className="capacity-item__header">
                      <div>
                        <strong>{item.specialist}</strong>
                        <p>{item.specialty}</p>
                      </div>
                      <StatusBadge tone={item.pendingValidations ? 'warning' : 'success'}>
                        {item.pendingValidations
                          ? `${item.pendingValidations} pendientes`
                          : 'Sin pendientes'}
                      </StatusBadge>
                    </div>
                  </article>
                ))}
              </div>
            </SectionCard>
          </section>
        </>
      ) : null}
    </div>
  )
}
