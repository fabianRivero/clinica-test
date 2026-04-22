import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getAdminProspects } from '../../services/api/admin'
import { Link, useLocation } from 'react-router-dom'

export function AdminProspectsPage() {
  const location = useLocation()
  const { data, isLoading, error } = useApiResource(getAdminProspects)
  const flashMessage =
    typeof location.state === 'object' && location.state && 'flashMessage' in location.state
      ? String(location.state.flashMessage)
      : null

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Relacion comercial"
        title="Prospectos y clientes"
        description="Administra prospectos pasajeros, su avance comercial y el momento en que pasan a clientes formales."
        actions={[
          { label: 'Registrar prospecto', variant: 'primary', to: '/admin/prospectos/nuevo' },
          { label: 'Importar contactos', variant: 'ghost' },
        ]}
      />

      {flashMessage ? <DataState title="Registro actualizado" message={flashMessage} /> : null}

      {isLoading && !data ? (
        <SectionCard title="Cargando relacion comercial">
          <DataState
            title="Sincronizando prospectos"
            message="Estamos trayendo prospectos, conversiones y clientes con cuenta."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar la relacion comercial">
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
            eyebrow="Seguimiento"
            title="Prospectos registrados"
            description="Registros internos que todavia no son clientes formales o ya fueron convertidos."
          >
            {data.prospects.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Telefono</th>
                      <th>Interes</th>
                      <th>Registrado por</th>
                      <th>Etapa</th>
                      <th>Estado</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.prospects.map((lead) => (
                      <tr key={lead.id}>
                        <td>
                          <strong>{lead.name}</strong>
                          <span>{lead.createdAt}</span>
                        </td>
                        <td>{lead.phone}</td>
                        <td>{lead.interest}</td>
                        <td>{lead.registeredBy}</td>
                        <td>
                          <StatusBadge tone="primary">{lead.stage}</StatusBadge>
                        </td>
                        <td>{lead.state}</td>
                        <td>
                          {lead.state === 'Pasajero' ? (
                            <Link className="button button--ghost button--compact" to={`/admin/prospectos/${lead.rawId}/convertir`}>
                              Convertir
                            </Link>
                          ) : (
                            <span>-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <DataState
                title="Sin prospectos cargados"
                message="Todavia no hay pasajeros o conversiones registradas en la base real."
              />
            )}
          </SectionCard>

          <SectionCard
            eyebrow="Clientes"
            title="Clientes con cuenta"
            description="Clientes activos e inactivos que ya pueden ingresar al portal y revisar su historial."
          >
            {data.clients.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Estado</th>
                      <th>Telefono</th>
                      <th>Operaciones activas</th>
                      <th>Historial</th>
                      <th>Ultimo analisis</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.clients.map((client) => (
                      <tr key={client.id}>
                        <td>{client.name}</td>
                        <td>
                          <StatusBadge tone={client.status === 'Activo' ? 'success' : 'neutral'}>
                            {client.status}
                          </StatusBadge>
                        </td>
                        <td>{client.phone}</td>
                        <td>{client.activeOperations}</td>
                        <td>{client.totalOperations}</td>
                        <td>{client.lastAnalysis}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <DataState
                title="Sin clientes con cuenta"
                message="No se encontraron clientes consolidados en la base conectada."
              />
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  )
}
