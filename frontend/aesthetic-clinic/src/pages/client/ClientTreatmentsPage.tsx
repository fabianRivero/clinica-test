import { useState } from 'react'
import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getClientTreatments } from '../../services/api/client'

export function ClientTreatmentsPage() {
  const { data, isLoading, error } = useApiResource(getClientTreatments)
  const [statusFilter, setStatusFilter] = useState('')

  const operationStatuses = data ? [...new Set(data.operations.map((op) => op.status))] : []
  const filteredOperations = data
    ? statusFilter
      ? data.operations.filter((op) => op.status === statusFilter)
      : data.operations
    : []

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Historial de tratamientos"
        title="Mis tratamientos"
        description="Detalle completo de operaciones activas, cerradas, canceladas o en borrador dentro de tu cuenta."
      />

      {isLoading && !data ? (
        <SectionCard title="Cargando tratamientos">
          <DataState title="Sincronizando historial" message="Estamos cargando tu historial clinico y operativo." />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar tus tratamientos">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <>
          <SectionCard
            eyebrow="Operacion por operacion"
            title="Detalle de tratamientos"
            description="Cada tarjeta resume sesiones, recomendaciones y zona tratada."
          >
            <label className="field _mb-sm">
              <span>Filtrar por estado</span>
              <select className="input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">Todos los estados</option>
                {operationStatuses.map((status) => (
                  <option key={status} value={status}>{status}</option>
                ))}
              </select>
            </label>
            {filteredOperations.length ? (
              <div className="operation-grid">
                {filteredOperations.map((operation) => (
                  <article className="operation-card" key={operation.id}>
                    <header>
                      <div>
                        <strong>{operation.procedure}</strong>
                        <p>{operation.serviceType}</p>
                      </div>
                      <StatusBadge tone={operation.statusTone}>{operation.status}</StatusBadge>
                    </header>

                    <dl className="operation-card__details">
                      <div>
                        <dt>Sucursal</dt>
                        <dd>{operation.branch}</dd>
                      </div>
                      <div>
                        <dt>Zona</dt>
                        <dd>{operation.zone}</dd>
                      </div>
                      <div>
                        <dt>Inicio</dt>
                        <dd>{operation.startedAt}</dd>
                      </div>
                      <div>
                        <dt>Cierre</dt>
                        <dd>{operation.endedAt}</dd>
                      </div>
                      <div>
                        <dt>Próxima cita</dt>
                        <dd>{operation.nextAppointment}</dd>
                      </div>
                      <div>
                        <dt>Monto pactado</dt>
                        <dd>{operation.price}</dd>
                      </div>
                    </dl>

                    <div className="operation-card__stats">
                      <article>
                        <span>Total</span>
                        <strong>{operation.sessions.total}</strong>
                      </article>
                      <article>
                        <span>Confirmadas</span>
                        <strong>{operation.sessions.confirmed}</strong>
                      </article>
                      <article>
                        <span>Pend. verificación</span>
                        <strong>{operation.sessions.pendingBiometric}</strong>
                      </article>
                      <article>
                        <span>Libres</span>
                        <strong>{operation.sessions.available}</strong>
                      </article>
                    </div>

                    <div className="operation-card__note-grid">
                      <article>
                        <span>Reserva</span>
                        <p>{operation.reserveMessage}</p>
                      </article>
                      <article>
                        <span>Recomendaciones</span>
                        <p>{operation.recommendations}</p>
                      </article>
                      <article>
                        <span>Detalle</span>
                        <p>{operation.details}</p>
                      </article>
                      <article>
                        <span>Cuotas</span>
                        <p>{operation.quotaSummary}</p>
                      </article>
                    </div>
                  </article>
                ))}
              </div>
            ) : data.operations.length ? (
              <DataState title="Sin resultados" message="No hay tratamientos para el estado seleccionado." />
            ) : (
              <DataState title="Sin tratamientos" message="No encontramos operaciones registradas para esta cuenta." />
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  )
}
