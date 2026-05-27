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
}

export function ClientOperationList({
  operations,
  operationStatusFilter,
  operationStatuses,
  filteredOperations,
  onFilterChange,
}: ClientOperationListProps) {
  return (
    <SectionCard eyebrow="Tratamientos" title="Procedimientos del cliente" description="Resumen operativo de tratamientos activos e historicos.">
      {operations.length ? (
        <>
          <label className="field" style={{ marginBottom: 12 }}>
            <span>Filtrar por estado</span>
            <select className="input" value={operationStatusFilter} onChange={(event) => onFilterChange(event.target.value)}>
              <option value="">Todos los estados</option>
              {operationStatuses.map((status) => (
                <option key={status} value={status}>{status}</option>
              ))}
            </select>
          </label>
          {filteredOperations.length ? (
            <div className="capacity-list">
              {filteredOperations.map((operation) => (
                <article className="capacity-item" key={operation.id}>
                  <div className="capacity-item__header">
                    <div>
                      <strong>{operation.procedure}</strong>
                      <p>{operation.zone} | {operation.quotaSummary}</p>
                      <p>Establecido: {operation.startedAt || 'Fecha no registrada'}</p>
                    </div>
                    <StatusBadge tone={operation.statusTone}>{operation.status}</StatusBadge>
                  </div>
                  <div className="operation-card__stats">
                    <article><span>Totales</span><strong>{operation.sessions.total}</strong></article>
                    <article><span>Confirmadas</span><strong>{operation.sessions.confirmed}</strong></article>
                    <article><span>Reservadas</span><strong>{operation.sessions.reserved}</strong></article>
                    <article><span>Libres</span><strong>{operation.sessions.available}</strong></article>
                  </div>
                  <Link className="button button--ghost" to={`/admin/operaciones/${operation.rawId}`}>Ver operacion</Link>
                </article>
              ))}
            </div>
          ) : <DataState title="Sin resultados" message="No hay procedimientos para el estado seleccionado." />}
        </>
      ) : <DataState title="Sin procedimientos" message="No hay procedimientos asociados a este cliente." />}
    </SectionCard>
  )
}