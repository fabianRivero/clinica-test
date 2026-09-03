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
const MIN_GLOBAL_QUERY_LENGTH = 3

function matchesTokens(filter: string, target: string | undefined | null): boolean {
  const trimmed = filter.trim().toLowerCase()
  if (!trimmed) return true
  const tokens = trimmed.split(/\s+/).filter(Boolean)
  const haystack = (target ?? '').toLowerCase()
  return tokens.every((token) => haystack.includes(token))
}

export function AdminClientsPage() {
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const loader = useCallback(() => getAdminProspects(), [branchId])
  const { data, isLoading, error, reload } = useApiResource(loader)
  const { showNotification } = useNotifications()
  const { confirm, ConfirmDialog: ConfirmDialogModal } = useConfirmDialog()

  // Local filter state — 5 inputs + status
  const [nameFilter, setNameFilter] = useState('')
  const [ciFilter, setCiFilter] = useState('')
  const [phoneFilter, setPhoneFilter] = useState('')
  const [emailFilter, setEmailFilter] = useState('')
  const [codeFilter, setCodeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('TODOS')
  const [visibleCount, setVisibleCount] = useState(10)

  // Global search state — 5 inputs mirrored locally, debounced search
  const [globalName, setGlobalName] = useState('')
  const [globalCi, setGlobalCi] = useState('')
  const [globalPhone, setGlobalPhone] = useState('')
  const [globalEmail, setGlobalEmail] = useState('')
  const [globalCode, setGlobalCode] = useState('')
  const [globalResults, setGlobalResults] = useState<any[]>([])
  const [isSearchingGlobal, setIsSearchingGlobal] = useState(false)

  const hasAnyGlobalFilter = useMemo(() => {
    return (
      globalName.trim().length >= MIN_GLOBAL_QUERY_LENGTH ||
      globalCi.trim().length >= MIN_GLOBAL_QUERY_LENGTH ||
      globalPhone.trim().length >= MIN_GLOBAL_QUERY_LENGTH ||
      globalEmail.trim().length >= MIN_GLOBAL_QUERY_LENGTH ||
      globalCode.trim().length >= MIN_GLOBAL_QUERY_LENGTH
    )
  }, [globalName, globalCi, globalPhone, globalEmail, globalCode])

  const hasAnyLocalFilter = useMemo(() => {
    return Boolean(
      nameFilter.trim() || ciFilter.trim() || phoneFilter.trim() || emailFilter.trim() || codeFilter.trim(),
    )
  }, [nameFilter, ciFilter, phoneFilter, emailFilter, codeFilter])

  useEffect(() => {
    if (!hasAnyGlobalFilter) {
      setGlobalResults([])
      return
    }

    const timer = setTimeout(async () => {
      setIsSearchingGlobal(true)
      try {
        const response = await searchAdminClientsGlobal({
          name: globalName || undefined,
          ci: globalCi || undefined,
          phone: globalPhone || undefined,
          email: globalEmail || undefined,
          code: globalCode || undefined,
        })
        const currentIds = (data?.clients ?? []).map((c: any) => c.rawId)
        setGlobalResults(response.clients.filter((c: any) => !currentIds.includes(c.id)))
      } catch (err) {
        console.error('Error en busqueda global:', err)
      } finally {
        setIsSearchingGlobal(false)
      }
    }, 600)

    return () => clearTimeout(timer)
  }, [globalName, globalCi, globalPhone, globalEmail, globalCode, hasAnyGlobalFilter, data?.clients])

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
      setGlobalName('')
      setGlobalCi('')
      setGlobalPhone('')
      setGlobalEmail('')
      setGlobalCode('')
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
    return (data?.clients ?? []).filter((client) => {
      const matchesName = matchesTokens(nameFilter, client.name)
      const matchesCi = matchesTokens(ciFilter, client.ci)
      const matchesPhone = matchesTokens(phoneFilter, client.phone)
      const matchesEmail = matchesTokens(emailFilter, client.email)
      const matchesCode = matchesTokens(codeFilter, client.clienteCodigo)
      const matchesStatus = statusFilter === 'TODOS' || client.status === statusFilter
      return matchesName && matchesCi && matchesPhone && matchesEmail && matchesCode && matchesStatus
    })
  }, [data, nameFilter, ciFilter, phoneFilter, emailFilter, codeFilter, statusFilter])

  const visibleClients = useMemo(() => {
    return filteredClients.slice(0, visibleCount)
  }, [filteredClients, visibleCount])

  function handleShowMore() {
    setVisibleCount((prev) => prev + 10)
  }

  function handleShowLess() {
    setVisibleCount((prev) => Math.max(10, prev - 10))
  }

  function handleClearLocalFilters() {
    setNameFilter('')
    setCiFilter('')
    setPhoneFilter('')
    setEmailFilter('')
    setCodeFilter('')
  }

  function handleClearGlobalFilters() {
    setGlobalName('')
    setGlobalCi('')
    setGlobalPhone('')
    setGlobalEmail('')
    setGlobalCode('')
  }

  const localCodeZeroHits =
    codeFilter.trim().length > 0 && filteredClients.length === 0 && data && data.clients.length > 0
  const globalZeroHits =
    hasAnyGlobalFilter && globalResults.length === 0 && !isSearchingGlobal

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Relacion comercial"
        title="Clientes"
        description="Consulta los clientes consolidados que ya tienen cuenta, historial clinico y acceso al portal para pagos y reservas."
        actions={[
          { label: 'Crear cliente directo', variant: 'primary', to: '/cms/clientes/nuevo' },
        ]}
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
            description="Si el cliente ya tiene cuenta en otra sede, búscalo por cualquiera de los datos que recuerdes para importarlo a esta sucursal."
          >
            <div className="form-grid form-grid--five">
              <label className="field">
                <span>Nombre</span>
                <input
                  className="input"
                  placeholder="Buscar por nombre..."
                  value={globalName}
                  onChange={(e) => setGlobalName(e.target.value)}
                />
              </label>
              <label className="field">
                <span>CI</span>
                <input
                  className="input"
                  placeholder="Buscar por CI..."
                  value={globalCi}
                  onChange={(e) => setGlobalCi(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Teléfono</span>
                <input
                  className="input"
                  placeholder="Buscar por teléfono..."
                  value={globalPhone}
                  onChange={(e) => setGlobalPhone(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Email</span>
                <input
                  className="input"
                  placeholder="Buscar por email..."
                  value={globalEmail}
                  onChange={(e) => setGlobalEmail(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Código</span>
                <input
                  className="input"
                  placeholder="Buscar por código (CLI-...)"
                  value={globalCode}
                  onChange={(e) => setGlobalCode(e.target.value)}
                />
              </label>
            </div>

            {hasAnyGlobalFilter && (
              <div className="form-actions form-actions--start">
                <button
                  type="button"
                  className="button button--ghost button--compact"
                  onClick={handleClearGlobalFilters}
                >
                  Limpiar filtros
                </button>
              </div>
            )}

            {isSearchingGlobal ? (
              <p className="table-muted">Buscando en la red global...</p>
            ) : globalResults.length > 0 ? (
              <div className="table-card _mt-md">
                <table>
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Código</th>
                      <th>CI</th>
                      <th>Teléfono</th>
                      <th>Email</th>
                      <th>Sucursal Origen</th>
                      <th>Ciudad</th>
                      <th>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {globalResults.map((c: any) => (
                      <tr key={c.id}>
                        <td>{c.name}</td>
                        <td>{c.clienteCodigo || <span className="table-muted">—</span>}</td>
                        <td>{c.ci}</td>
                        <td>{c.phone || <span className="table-muted">—</span>}</td>
                        <td>{c.email || <span className="table-muted">—</span>}</td>
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
            ) : globalZeroHits ? (
              <p className="table-muted _mt-md">
                No se encontraron clientes para importar con esos datos. Verificá que los hayas escrito bien o probá con otro filtro.
              </p>
            ) : null}
          </SectionCard>

          <SectionCard
            eyebrow="Clientes"
            title="Clientes con cuenta"
            description="Clientes activos e inactivos que ya pueden ingresar al portal y revisar su historial."
          >
            <div className="form-grid form-grid--five">
              <label className="field">
                <span>Nombre</span>
                <input
                  className="input"
                  placeholder="Buscar por nombre..."
                  value={nameFilter}
                  onChange={(event) => setNameFilter(event.target.value)}
                />
              </label>
              <label className="field">
                <span>CI</span>
                <input
                  className="input"
                  placeholder="Buscar por CI..."
                  value={ciFilter}
                  onChange={(event) => setCiFilter(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Teléfono</span>
                <input
                  className="input"
                  placeholder="Buscar por teléfono..."
                  value={phoneFilter}
                  onChange={(event) => setPhoneFilter(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Email</span>
                <input
                  className="input"
                  placeholder="Buscar por email..."
                  value={emailFilter}
                  onChange={(event) => setEmailFilter(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Código</span>
                <input
                  className="input"
                  placeholder="Buscar por código (CLI-...)"
                  value={codeFilter}
                  onChange={(event) => setCodeFilter(event.target.value)}
                />
              </label>
            </div>

            <div className="form-grid">
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

            {hasAnyLocalFilter && (
              <div className="form-actions form-actions--start">
                <button
                  type="button"
                  className="button button--ghost button--compact"
                  onClick={handleClearLocalFilters}
                >
                  Limpiar filtros
                </button>
              </div>
            )}

            {filteredClients.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Código</th>
                      <th>Estado</th>
                      <th>CI</th>
                      <th>Teléfono</th>
                      <th>Email</th>
                      <th>Operaciones activas</th>
                      <th>Historial</th>
                      <th>Último análisis</th>
                      <th>Citas programadas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleClients.map((client) => (
                      <tr key={client.id}>
                        <td>
                          <Link className="table-strong-link" to={`/cms/clientes/${client.rawId}`}>
                            {client.name}
                          </Link>
                        </td>
                        <td>{client.clienteCodigo || <span className="table-muted">—</span>}</td>
                        <td>
                          <StatusBadge tone={client.status === 'Activo' ? 'success' : 'neutral'}>
                            {client.status}
                          </StatusBadge>
                        </td>
                        <td>{client.ci}</td>
                        <td>{client.phone || <span className="table-muted">—</span>}</td>
                        <td>{client.email || <span className="table-muted">—</span>}</td>
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
                        Ver más
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ) : localCodeZeroHits ? (
              <DataState
                title="Sin resultados"
                message="No se encontraron clientes con ese código. Verificá que lo hayas escrito bien."
              />
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
