import {
  adminAlerts,
  adminMetrics,
  catalogHealth,
  highlightedOperations,
  paymentQueue,
  prospectPipeline,
  staffCapacity,
  todayAgenda,
} from '../../data/adminMock'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'

const agendaTone = {
  programada: 'neutral',
  biometria: 'warning',
  confirmada: 'success',
} as const

export function AdminDashboardPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Vista general"
        title="Centro de control administrativo"
        description="Una lectura rápida del estado financiero, operativo y clínico de la clínica, con foco en pagos pendientes, agenda y conversión de prospectos."
        actions={[
          { label: 'Nueva operación', variant: 'primary' },
          { label: 'Exportar resumen', variant: 'ghost' },
        ]}
      />

      <section className="metrics-grid">
        {adminMetrics.map((metric) => (
          <MetricCard key={metric.id} metric={metric} />
        ))}
      </section>

      <section className="dashboard-grid">
        <SectionCard
          eyebrow="Prioridad del día"
          title="Validación de pagos"
          description="Pagos recientes subidos por clientes para revisión administrativa."
          action={<button className="button button--ghost">Ver cola completa</button>}
        >
          <div className="table-card">
            <table>
              <thead>
                <tr>
                  <th>Paciente</th>
                  <th>Operación</th>
                  <th>Monto</th>
                  <th>Banco</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {paymentQueue.map((payment) => (
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
        </SectionCard>

        <SectionCard
          eyebrow="Agenda clínica"
          title="Citas destacadas"
          description="Seguimiento operativo del día con foco en citas que todavía necesitan cierre o confirmación biométrica."
        >
          <div className="agenda-list">
            {todayAgenda.map((item) => (
              <article className="agenda-item" key={item.id}>
                <div className="agenda-item__time">{item.time}</div>
                <div className="agenda-item__content">
                  <strong>{item.patient}</strong>
                  <p>
                    {item.procedure} · {item.specialist}
                  </p>
                </div>
                <StatusBadge tone={agendaTone[item.status]}>{item.status}</StatusBadge>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          eyebrow="Atención comercial"
          title="Pipeline de prospectos"
          description="Prospectos registrados internamente por el equipo, listos para seguimiento o conversión."
        >
          <div className="pipeline-list">
            {prospectPipeline.map((lead) => (
              <article className="pipeline-item" key={lead.id}>
                <div>
                  <strong>{lead.name}</strong>
                  <p>{lead.interest}</p>
                </div>
                <div className="pipeline-item__meta">
                  <span>{lead.phone}</span>
                  <StatusBadge tone="primary">{lead.stage}</StatusBadge>
                </div>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          eyebrow="Monitoreo"
          title="Alertas críticas"
          description="Elementos que requieren intervención administrativa para no afectar reservas, pagos o experiencia del paciente."
        >
          <div className="alert-list">
            {adminAlerts.map((alert) => (
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
          eyebrow="Operaciones activas"
          title="Tratamientos destacados"
          description="Pacientes con tratamiento en curso y seguimiento operativo visible para administración."
        >
          <div className="operation-grid">
            {highlightedOperations.map((operation) => (
              <article className="operation-card" key={operation.id}>
                <header>
                  <div>
                    <strong>{operation.patient}</strong>
                    <p>{operation.procedure}</p>
                  </div>
                  <StatusBadge tone="primary">{operation.quotaStatus}</StatusBadge>
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
                    <dt>Próxima cita</dt>
                    <dd>{operation.nextAppointment}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          eyebrow="Configuración"
          title="Salud de catálogos"
          description="Estado general de los catálogos editables que alimentan la operación clínica."
        >
          <div className="catalog-health">
            {catalogHealth.map((item) => (
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
          description="Lectura rápida de especialistas, especialidades y pendientes de validación."
        >
          <div className="capacity-list">
            {staffCapacity.map((item) => (
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
                <div className="progress-bar">
                  <span style={{ width: `${item.load}%` }} />
                </div>
              </article>
            ))}
          </div>
        </SectionCard>
      </section>
    </div>
  )
}
