import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useBranchContext } from '../../providers/BranchProvider'
import { getAdminOperations } from '../../services/api/admin'
import { Link } from 'react-router-dom'
import { useCallback, useMemo, useState } from 'react'


const OPERATION_STATUS_ALL = 'TODOS'

export function AdminOperationsPage() {
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const loader = useCallback(() => getAdminOperations(), [branchId])
  const { data, isLoading, error } = useApiResource(loader)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState(OPERATION_STATUS_ALL)

  const statusOptions = useMemo(() => {
    const statuses = new Set((data?.operations ?? []).map((operation) => operation.status).filter(Boolean))
    return [OPERATION_STATUS_ALL, ...Array.from(statuses)]
  }, [data])

  const filteredOperations = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase()
    return (data?.operations ?? []).filter((operation) => {
      const matchesSearch = !normalizedSearch || operation.patient.toLowerCase().includes(normalizedSearch)
      const matchesStatus =
        statusFilter === OPERATION_STATUS_ALL ||
        (operation.status || '').toLowerCase() === statusFilter.toLowerCase()
      return matchesSearch && matchesStatus
    })
  }, [data, searchTerm, statusFilter])

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Seguimiento clinico"
        title="Operaciones"
        description="Vista administrativa de tratamientos vigentes, sesiones pactadas, cuotas y citas asociadas."
        actions={[
          { label: 'Configurar disponibilidad', variant: 'primary', to: '/admin/disponibilidad' },
          { label: 'Filtrar por estado', variant: 'ghost' },
        ]}
      />

      {isLoading && !data ? (
        <SectionCard title="Cargando operaciones">
          <DataState
            title="Sincronizando tratamientos"
            message="Traemos el estado actual de las operaciones desde Django."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar operaciones">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <>
          <SectionCard
            eyebrow="Control operativo"
            title="Resumen de tratamientos"
            description="Lectura real de operaciones vigentes, sesiones disponibles y situacion de cuotas."
          >
            <div className="form-grid">
              <label className="field">
                <span>Buscar cliente</span>
                <input
                  className="input"
                  placeholder="Nombre del cliente"
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
                  {statusOptions.map((status) => (
                    <option key={status} value={status}>
                      {status === OPERATION_STATUS_ALL ? 'Todos' : status}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {filteredOperations.length ? (
              <div className="operation-grid">
                {filteredOperations.map((operation) => (
                  <article className="operation-card" key={operation.id}>
                    <header>
                      <div>
                        <strong>{operation.patient}</strong>
                        <p>{operation.procedure}</p>
                      </div>
                      <StatusBadge tone="primary">{operation.status || 'Sin estado'}</StatusBadge>
                    </header>
                    <dl>
                      <div>
                        <dt>Sucursal</dt>
                        <dd>{operation.branch}</dd>
                      </div>
                      <div>
                        <dt>Sesiones</dt>
                        <dd>{operation.sessions}</dd>
                      </div>
                      <div>
                        <dt>Proxima cita</dt>
                        <dd>{operation.nextAppointment}</dd>
                      </div>
                      <div>
                        <dt>Pagos</dt>
                        <dd>{operation.quotaStatus}</dd>
                      </div>
                      <div>
                        <dt>Monto pactado</dt>
                        <dd>{operation.price}</dd>
                      </div>
                    </dl>
                    <div className="operation-card__actions">
                      {operation.rawId ? (
                        <Link className="button button--ghost button--compact" to={`/admin/operaciones/${operation.rawId}`}>
                          Ver detalle
                        </Link>
                      ) : (
                        <span className="field__hint">Sin detalle de operacion</span>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <DataState
                title={data.operations.length ? 'Sin resultados' : 'Sin operaciones'}
                message={
                  data.operations.length
                    ? 'No hay operaciones que coincidan con los filtros aplicados.'
                    : 'Todavia no hay tratamientos creados en la base conectada.'
                }
              />
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  )
}
