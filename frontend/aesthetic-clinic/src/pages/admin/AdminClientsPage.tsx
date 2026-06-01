import { DataState } from '../../components/admin/DataState'
import { AdminRelationshipTabs } from '../../components/admin/AdminRelationshipTabs'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useConfirmDialog } from '../../hooks/useConfirmDialog'
import { useNotifications } from '../../providers/NotificationProvider'
import { useBranchContext } from '../../providers/BranchProvider'
import { 
  getAdminProspects, 
  searchAdminClientsGlobal, 
  migrateAdminClient 
} from '../../services/api/admin'
import { Link } from 'react-router-dom'
import { useCallback, useMemo, useState, useEffect } from 'react'

const CLIENT_STATUS_OPTIONS = ['Activo', 'Inactivo']

export function AdminClientsPage() {
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const loader = useCallback(() => getAdminProspects(), [branchId])
  const { data, isLoading, error, reload } = useApiResource(loader)
  const { showNotification } = useNotifications()
  const { confirm, ConfirmDialog: ConfirmDialogModal } = useConfirmDialog()
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('TODOS')
  const [visibleCount, setVisibleCount] = useState(10)

  // Global search state
  const [globalSearch, setGlobalSearch] = useState('')
  const [globalResults, setGlobalResults] = useState<any[]>([])
  const [isSearchingGlobal, setIsSearchingGlobal] = useState(false)

  useEffect(() => {
    if (globalSearch.trim().length < 3) {
      setGlobalResults([])
      return
    }

    const timer = setTimeout(async () => {
      setIsSearchingGlobal(true)
      try {
        const response = await searchAdminClientsGlobal(globalSearch)
        const currentIds = (data?.clients ?? []).map((c: any) => c.rawId)
        setGlobalResults(response.clients.filter(c => !currentIds.includes(c.id)))
      } catch (err) {
        console.error('Error en busqueda global:', err)
      } finally {
        setIsSearchingGlobal(false)
      }
    }, 600)

    return () => clearTimeout(timer)
  }, [globalSearch, data?.clients])

  const handleImportClient = async (clientId: number, clientName: string) => {
    if (!branchId) return
    const confirmed = await confirm({
      title: 'Confirmar importacion',
      message: `¿Seguro que deseas importar a ${clientName} a esta sucursal?`,
    })
    if (!confirmed) return

    try {
      await migrateAdminClient(clientId, branchId)
      showNotification({
        title: 'Cliente importado',
        message: `${clientName} ahora pertenece a esta sucursal.`,
        tone: 'success'
      })
      setGlobalSearch('')
      reload()
    } catch (err: any) {
      showNotification({
        title: 'Error al importar',
        message: err.message,
        tone: 'danger'
      })
    }
  }

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

  const visibleClients = useMemo(() => {
    return filteredClients.slice(0, visibleCount)
  }, [filteredClients, visibleCount])

  function handleShowMore() {
    setVisibleCount((prev) => prev + 10)
  }

  function handleShowLess() {
    setVisibleCount((prev) => Math.max(10, prev - 10))
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Relacion comercial"
        title="Clientes"
        description="Consulta los clientes consolidados que ya tienen cuenta, historial clinico y acceso al portal para pagos y reservas."
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
          <SectionCard
            eyebrow="Red global"
            title="Buscar e importar de otra sucursal"
            description="Si el cliente ya tiene cuenta en otra sede, buscalo por CI o Nombre para importarlo a esta sucursal."
          >
            <div className="field">
              <input
                className="input"
                placeholder="Ingresa CI o Nombre para buscar globalmente..."
                value={globalSearch}
                onChange={(e) => setGlobalSearch(e.target.value)}
              />
            </div>

            {isSearchingGlobal ? (
              <p className="table-muted">Buscando en la red global...</p>
            ) : globalResults.length > 0 ? (
              <div className="table-card _mt-md">
                <table>
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>CI</th>
                      <th>Sucursal Origen</th>
                      <th>Ciudad</th>
                      <th>Accion</th>
                    </tr>
                  </thead>
                  <tbody>
                    {globalResults.map((c) => (
                      <tr key={c.id}>
                        <td>{c.name}</td>
                        <td>{c.ci}</td>
                        <td>{c.branchName}</td>
                        <td>{c.cityName}</td>
                        <td>
                          <button 
                            className="button button--compact button--secondary"
                            onClick={() => handleImportClient(c.id, c.name)}
                          >
                            Importar a esta sede
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : globalSearch.length >= 3 ? (
              <p className="table-muted _mt-md">No se encontraron clientes para importar con esos datos.</p>
            ) : null}
          </SectionCard>

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
                    {visibleClients.map((client) => (
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
                <div className="pagination-controls">
                  <span className="pagination-info">
                    Mostrando {visibleClients.length} de {filteredClients.length} clientes
                  </span>
                  <div className="pagination-buttons">
                    {visibleCount > 10 && (
                      <button
                        className="button button--secondary button--compact"
                        type="button"
                        onClick={handleShowLess}
                      >
                        Ver menos
                      </button>
                    )}
                    {visibleCount < filteredClients.length && (
                      <button
                        className="button button--secondary button--compact"
                        type="button"
                        onClick={handleShowMore}
                      >
                        Ver mas
                      </button>
                    )}
                  </div>
                </div>
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
      <ConfirmDialogModal />
    </div>
  )
}
