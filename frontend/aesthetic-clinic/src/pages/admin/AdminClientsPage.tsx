import { DataState } from '../../components/admin/DataState'
import { AdminRelationshipTabs } from '../../components/admin/AdminRelationshipTabs'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import { useBranchContext } from '../../providers/BranchProvider'
import { cancelAdminAppointment, getAdminProspects } from '../../services/api/admin'
import { Link } from 'react-router-dom'
import { useCallback, useMemo, useState } from 'react'

const CLIENT_STATUS_OPTIONS = ['Activo', 'Inactivo']

export function AdminClientsPage() {
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const loader = useCallback(() => getAdminProspects(), [branchId])
  const { data, isLoading, error, reload } = useApiResource(loader)
  const { showNotification } = useNotifications()
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('TODOS')

  const filteredClients = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase()
    return (data?.clients ?? []).filter((client) => {
      const matchesSearch =
        !normalizedSearch ||
        client.name.toLowerCase().includes(normalizedSearch) ||
        client.ci.toLowerCase().includes(normalizedSearch)
      const matchesStatus = statusFilter === 'TODOS' || client.status === statusFilter
      return matchesSearch && matchesStatus
    })
  }, [data, searchTerm, statusFilter])


  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Relacion comercial"
        title="Clientes"
        description="Consulta los clientes consolidados que ya tienen cuenta, historial clinico y acceso al portal para pagos y reservas."
        actions={[{ label: 'Exportar clientes', variant: 'ghost' }]}
      />

      <AdminRelationshipTabs />

      {isLoading && !data ? (
        <SectionCard title="Cargando clientes">
          <DataState
            title="Sincronizando clientes"
            message="Estamos trayendo clientes activos, clientes inactivos y su historial operativo."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar clientes">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <>
          <section className="metrics-grid metrics-grid--compact">
            {data.metrics.slice(2).map((metric) => (
              <MetricCard key={metric.id} metric={metric} />
            ))}
          </section>

          <SectionCard
            eyebrow="Clientes"
            title="Clientes con cuenta"
            description="Clientes activos e inactivos que ya pueden ingresar al portal y revisar su historial."
          >
            <div className="form-grid">
              <label className="field">
                <span>Buscar cliente</span>
                <input
                  className="input"
                  placeholder="Nombre o CI"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Estado</span>
                <select
                  className="input"
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                >
                  <option value="TODOS">Todos</option>
                  {CLIENT_STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {filteredClients.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Estado</th>
                      <th>CI</th>
                      <th>Operaciones activas</th>
                      <th>Historial</th>
                      <th>Ultimo analisis</th>
                      <th>Citas programadas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredClients.map((client) => (
                      <tr key={client.id}>
                        <td>
                          <Link className="table-strong-link" to={`/admin/clientes/${client.rawId}`}>
                            {client.name}
                          </Link>
                        </td>
                        <td>
                          <StatusBadge tone={client.status === 'Activo' ? 'success' : 'neutral'}>
                            {client.status}
                          </StatusBadge>
                        </td>
                        <td>{client.ci}</td>
                        <td>{client.activeOperations}</td>
                        <td>{client.totalOperations}</td>
                        <td>{client.lastAnalysis}</td>
                        <td>
                          {client.scheduledAppointments.length ? (
                            <div className="table-action-list">
                              {client.scheduledAppointments.map((appointment) => (
                                <div key={appointment.id} className="table-action-list__item">
                                  <div>
                                    <strong>{appointment.dateTime}</strong>
                                    <span>
                                      {appointment.operation} · {appointment.specialist}
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <span>Sin citas programadas</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <DataState
                title={data.clients.length ? 'Sin resultados' : 'Sin clientes con cuenta'}
                message={
                  data.clients.length
                    ? 'No hay clientes que coincidan con la busqueda o el filtro seleccionado.'
                    : 'No se encontraron clientes consolidados en la base conectada.'
                }
              />
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  )
}
