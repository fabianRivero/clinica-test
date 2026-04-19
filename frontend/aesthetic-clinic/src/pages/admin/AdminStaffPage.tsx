import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { staffCapacity } from '../../data/adminMock'

export function AdminStaffPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Equipo clínico"
        title="Trabajadores y especialistas"
        description="Visual base para administrar especialidades, capacidad diaria y pendientes operativos del personal."
        actions={[
          { label: 'Nuevo trabajador', variant: 'primary' },
          { label: 'Asignar especialidad', variant: 'ghost' },
        ]}
      />

      <SectionCard
        eyebrow="Capacidad"
        title="Carga operativa"
        description="Seguimiento de especialistas y validaciones pendientes."
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
    </div>
  )
}
