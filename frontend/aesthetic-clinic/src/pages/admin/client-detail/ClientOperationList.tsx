import { useState } from 'react'
import { Link } from 'react-router-dom'
import { StatusBadge } from '../../../components/admin/StatusBadge'
import { DataState } from '../../../components/admin/DataState'
import { SectionCard } from '../../../components/admin/SectionCard'

interface ClientOperationListProps {
  operations: any[]
  operationStatusFilter: string
  operationStatuses: string[]
  filteredOperations: any[]
  onFilterChange: (value: string) => void

  // Pagination props (optional - fall back to internal if not provided)
  visibleOperations?: any[]
  visibleOperationsCount?: number
  setVisibleOperationsCount?: (count: number) => void
  hasMoreOperations?: boolean
  hasLessOperations?: boolean
}

export function ClientOperationList({
  operations,
  operationStatusFilter,
  operationStatuses,
  filteredOperations,
  onFilterChange,

  // Pagination props
  visibleOperations: externalVisibleOperations,
  visibleOperationsCount: externalVisibleCount,
  hasMoreOperations: externalHasMore,
  hasLessOperations: externalHasLess,
}: ClientOperationListProps) {
  // Use external pagination props if provided, otherwise use internal
  const internalStep = 5

  const [internalVisibleCount, setInternalVisibleCount] = useState(5)
  const showMore = () => setInternalVisibleCount((c) => c + internalStep)
  const showLess = () => setInternalVisibleCount((c) => Math.max(5, c - internalStep))

  const visibleOperations = externalVisibleOperations ?? filteredOperations.slice(0, internalVisibleCount)
  const visibleCount = externalVisibleCount ?? internalVisibleCount
  const hasMore = externalHasMore ?? filteredOperations.length > internalVisibleCount
  const hasLess = externalHasLess ?? internalVisibleCount > 5

  const showMoreHandler = showMore
  const showLessHandler = showLess

  return (
    <SectionCard eyebrow="Tratamientos" title="Procedimientos del cliente" description="Resumen operativo de tratamientos activos e historicos.">
      {operations.length ? (
        <>
          <label className="field _mb-sm">
            <span>Filtrar por estado</span>
            <select className="input" value={operationStatusFilter} onChange={(event) => onFilterChange(event.target.value)}>
              <option value="">Todos los estados</option>
              {operationStatuses.map((status) => (
                <option key={status} value={status}>{status}</option>
              ))}
            </select>
          </label>
          {filteredOperations.length ? (
            <>
              <div className="capacity-list">
                {visibleOperations.map((operation) => (
                  <article className="capacity-item" key={operation.id}>
                    <div className="capacity-item__header">
                      <div>
                        <strong>{operation.procedure}</strong>
                        <p>ID: {operation.id} | {operation.zone} | {operation.quotaSummary}</p>
                        <p>Establecido: {operation.startedAt || 'Fecha no registrada'}</p>
                      </div>
                      <StatusBadge tone={operation.statusTone}>{operation.status}</StatusBadge>
                    </div>
                    <div className="operation-card__stats">
                      <article><span>Citas totales</span><strong>{operation.sessions.total}</strong></article>
                      <article><span>Citas confirmadas</span><strong>{operation.sessions.confirmed}</strong></article>
                      <article><span>Citas reservadas</span><strong>{operation.sessions.reserved}</strong></article>
                      <article><span>Citas libres</span><strong>{operation.sessions.available}</strong></article>
                    </div>
                    <Link className="button button--ghost" to={`/cms/operaciones/${operation.rawId}`}>Ver operación</Link>
                  </article>
                ))}
              </div>
              {filteredOperations.length > 5 && (
                <div className="_flex-between _mt-md">
                  <span>Mostrando {visibleCount} de {filteredOperations.length} procedimientos</span>
                  <div>
                    {hasLess && (
                      <button className="button button--ghost" type="button" onClick={showLessHandler}>Ver menos</button>
                    )}
                    {hasMore && (
                      <button className="button button--secondary" type="button" onClick={showMoreHandler}>Ver más</button>
                    )}
                  </div>
                </div>
              )}
            </>
          ) : <DataState title="Sin resultados" message="No hay procedimientos para el estado seleccionado." />}
        </>
      ) : <DataState title="Sin procedimientos" message="No hay procedimientos asociados a este cliente." />}
    </SectionCard>
  )
}