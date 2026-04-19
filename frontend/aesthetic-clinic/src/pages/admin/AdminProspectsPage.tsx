import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { prospectPipeline } from '../../data/adminMock'

export function AdminProspectsPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Relación comercial"
        title="Prospectos y clientes"
        description="Administra prospectos pasajeros, su avance comercial y el momento en que pasan a convertirse en clientes formales."
        actions={[
          { label: 'Registrar prospecto', variant: 'primary' },
          { label: 'Importar contactos', variant: 'ghost' },
        ]}
      />

      <SectionCard
        eyebrow="Seguimiento"
        title="Embudo comercial"
        description="Esta vista sirve como base para el módulo que luego conectaremos con el backend."
      >
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Teléfono</th>
                <th>Interés</th>
                <th>Registrado por</th>
                <th>Etapa</th>
              </tr>
            </thead>
            <tbody>
              {prospectPipeline.map((lead) => (
                <tr key={lead.id}>
                  <td>{lead.name}</td>
                  <td>{lead.phone}</td>
                  <td>{lead.interest}</td>
                  <td>{lead.registeredBy}</td>
                  <td>
                    <StatusBadge tone="primary">{lead.stage}</StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  )
}
