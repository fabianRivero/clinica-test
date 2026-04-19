import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { highlightedOperations } from '../../data/adminMock'

export function AdminOperationsPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Seguimiento clínico"
        title="Operaciones"
        description="Vista administrativa de tratamientos vigentes, sesiones pactadas, cuotas y citas asociadas."
        actions={[
          { label: 'Nueva operación', variant: 'primary' },
          { label: 'Filtrar por estado', variant: 'ghost' },
        ]}
      />

      <SectionCard
        eyebrow="Control operativo"
        title="Resumen de tratamientos"
        description="En esta fase dejamos el patrón visual y la jerarquía del módulo."
      >
        <div className="operation-grid">
          {highlightedOperations.map((operation) => (
            <article className="operation-card" key={operation.id}>
              <header>
                <div>
                  <strong>{operation.patient}</strong>
                  <p>{operation.procedure}</p>
                </div>
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
                <div>
                  <dt>Estado cuota</dt>
                  <dd>{operation.quotaStatus}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      </SectionCard>
    </div>
  )
}
