import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { useApiResource } from '../../hooks/useApiResource'
import { getAdminCatalogs } from '../../services/api/admin'

export function AdminCatalogsPage() {
  const { data, isLoading, error } = useApiResource(getAdminCatalogs)

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Configuracion"
        title="Catalogos editables"
        description="Base visual para administrar especialidades, servicios, procedimientos, patologias y opciones clinicas."
        actions={[
          { label: 'Nuevo catalogo', variant: 'primary' },
          { label: 'Publicar cambios', variant: 'ghost' },
        ]}
      />

      {isLoading && !data ? (
        <SectionCard title="Cargando catalogos">
          <DataState
            title="Sincronizando configuracion"
            message="Estamos cargando procedimientos, servicios, campos y opciones editables."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar catalogos">
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
            eyebrow="Inventario"
            title="Estado de catalogos"
            description="Resumen real de los catalogos editables que ya existen en la base."
          >
            <div className="catalog-health">
              {data.catalogs.map((item) => (
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
        </>
      ) : null}
    </div>
  )
}
