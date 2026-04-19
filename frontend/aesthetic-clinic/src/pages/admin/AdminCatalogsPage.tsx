import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { catalogHealth } from '../../data/adminMock'

export function AdminCatalogsPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Configuración"
        title="Catálogos editables"
        description="Base visual para administrar especialidades, servicios, procedimientos, patologías y opciones clínicas desde la app."
        actions={[
          { label: 'Nuevo catálogo', variant: 'primary' },
          { label: 'Publicar cambios', variant: 'ghost' },
        ]}
      />

      <SectionCard
        eyebrow="Inventario"
        title="Estado de catálogos"
        description="Pensado para reflejar el modelo editable que ya definimos en el backend."
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
    </div>
  )
}
