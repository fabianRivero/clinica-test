import { useState } from 'react'
import { Link } from 'react-router-dom'
import { StatusBadge } from '../../../components/admin/StatusBadge'
import { DataState } from '../../../components/admin/DataState'
import { SectionCard } from '../../../components/admin/SectionCard'

const INITIAL_COUNT = 5
const STEP = 5

interface ClientOperationListProps {
  operations: any[]
  operationStatusFilter: string
  operationStatuses: string[]
  filteredOperations: any[]
  onFilterChange: (value: string) => void
}

export function ClientOperationList({
  operations,
  operationStatusFilter,
  operationStatuses,
  filteredOperations,
  onFilterChange,
}: ClientOperationListProps) {
  const [visibleCount, setVisibleCount] = useState(INITIAL_COUNT)

  const showMore = () => setVisibleCount((c) => c + STEP)
  const showLess = () => setVisibleCount((c) => Math.max(INITIAL_COUNT, c - STEP))

  const visibleOperations = filteredOperations.slice(0, visibleCount)
  const hasMore = filteredOperations.length > visibleCount
  const hasLess = visibleCount > INITIAL_COUNT

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
                    <Link className="button button--ghost" to={`/admin/operaciones/${operation.rawId}`}>Ver operacion</Link>
                  </article>
                ))}
              </div>
              <div className="_mt-md" style={{ display: 'flex', gap: '0.5rem' }}>
                {hasLess && (
                  <button className="button button--ghost" type="button" onClick={showLess}>
                    Ver menos
                  </button>
                )}
                {hasMore && (
                  <button className="button" type="button" onClick={showMore}>
                    Ver mas ({filteredOperations.length - visibleCount} restantes)
                  </button>
                )}
              </div>
            </>
          ) : <DataState title="Sin resultados" message="No hay procedimientos para el estado seleccionado." />}
        </>
      ) : <DataState title="Sin procedimientos" message="No hay procedimientos asociados a este cliente." />}
    </SectionCard>
  )
}