import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getAdminStaff } from '../../services/api/admin'

export function AdminStaffPage() {
  const { data, isLoading, error } = useApiResource(getAdminStaff)

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Equipo clinico"
        title="Trabajadores y especialistas"
        description="Visual base para administrar especialidades, capacidad diaria y pendientes operativos del personal."
        actions={[
          { label: 'Nuevo trabajador', variant: 'primary' },
          { label: 'Asignar especialidad', variant: 'ghost' },
        ]}
      />

      {isLoading && !data ? (
        <SectionCard title="Cargando equipo">
          <DataState
            title="Sincronizando equipo"
            message="Cargando especialidades, citas futuras y validaciones pendientes."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar el equipo">
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
            eyebrow="Capacidad"
            title="Carga operativa"
            description="Seguimiento de especialistas, agenda futura y validaciones pendientes."
          >
            {data.staff.length ? (
              <div className="capacity-list">
                {data.staff.map((item) => (
                  <article className="capacity-item" key={item.id}>
                    <div className="capacity-item__header">
                      <div>
                        <strong>{item.specialist}</strong>
                        <p>{item.specialty}</p>
                        <p>
                          {item.phone} | {item.activeOperations} operaciones activas |{' '}
                          {item.upcomingAppointments} citas futuras
                        </p>
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
            ) : (
              <DataState
                title="Sin especialistas"
                message="Todavia no hay trabajadores operativos listados en la base conectada."
              />
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  )
}
