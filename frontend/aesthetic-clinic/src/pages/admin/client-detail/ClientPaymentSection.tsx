import { StatusBadge } from '../../../components/admin/StatusBadge'
import { DataState } from '../../../components/admin/DataState'
import { SectionCard } from '../../../components/admin/SectionCard'

interface ClientPaymentSectionProps {
  pendingQuotas: any[]
  payments: any[]
  paymentActionId: number | null
  getPaymentNote: (paymentId: number, fallbackNote?: string) => string
  onPaymentNoteChange: (paymentId: number, note: string) => void
  onUpdatePaymentStatus: (paymentId: number, currentStatus: string, status: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO', fallbackNote?: string) => void
  pendingQuotaProcedureFilter: string
  pendingQuotaProcedures: string[]
  filteredPendingQuotas: any[]
  onPendingQuotaFilterChange: (value: string) => void

  // Pagination props
  visiblePayments: any[]
  visiblePaymentsCount: number
  setVisiblePaymentsCount: (count: number | ((prev: number) => number)) => void
  hasMorePayments: boolean
  hasLessPayments: boolean

  visiblePendingQuotasCount: number
  setVisiblePendingQuotasCount: (count: number | ((prev: number) => number)) => void
  hasMorePendingQuotas: boolean
  hasLessPendingQuotas: boolean
}

export function ClientPaymentSection({
  pendingQuotas,
  payments,
  paymentActionId,
  getPaymentNote,
  onPaymentNoteChange,
  onUpdatePaymentStatus,
  pendingQuotaProcedureFilter,
  pendingQuotaProcedures,
  filteredPendingQuotas,
  onPendingQuotaFilterChange,

  // Pagination
  visiblePayments,
  visiblePaymentsCount,
  setVisiblePaymentsCount,
  hasMorePayments,
  hasLessPayments,

  visiblePendingQuotasCount,
  setVisiblePendingQuotasCount,
  hasMorePendingQuotas,
  hasLessPendingQuotas,
}: ClientPaymentSectionProps) {
  return (
    <>
      <SectionCard eyebrow="Pagos" title="Pagos pendientes" description="Cuotas aun no pagadas o pendientes de completar.">
        {pendingQuotas.length ? (
          <>
            <label className="field _mb-sm">
              <span>Filtrar por procedimiento</span>
              <select className="input" value={pendingQuotaProcedureFilter} onChange={(event) => onPendingQuotaFilterChange(event.target.value)}>
                <option value="">Todos los procedimientos</option>
                {pendingQuotaProcedures.map((procedure) => (
                  <option key={procedure} value={procedure}>{procedure}</option>
                ))}
              </select>
            </label>
            {filteredPendingQuotas.length ? (
              <>
                <div className="capacity-list">
                  {filteredPendingQuotas.slice(0, visiblePendingQuotasCount).map((quota) => (
                    <article className="capacity-item" key={quota.id}>
                      <div className="capacity-item__header">
                        <div><strong>{quota.operation} | {quota.quotaLabel}</strong><p>{quota.amount} | Vence: {quota.dueDate}</p></div>
                        <StatusBadge tone={quota.statusTone}>{quota.status}</StatusBadge>
                      </div>
                    </article>
                  ))}
                </div>
                {filteredPendingQuotas.length > 5 && (
                  <div className="_flex-between _mt-md">
                    <span>Mostrando {Math.min(visiblePendingQuotasCount, filteredPendingQuotas.length)} de {filteredPendingQuotas.length} pagos pendientes</span>
                    <div>
                      {hasLessPendingQuotas && (
                        <button type="button" className="button button--ghost" onClick={() => setVisiblePendingQuotasCount((c: number) => c - 5)}>Ver menos</button>
                      )}
                      {hasMorePendingQuotas && (
                        <button type="button" className="button button--secondary" onClick={() => setVisiblePendingQuotasCount((c: number) => c + 5)}>Ver más</button>
                      )}
                    </div>
                  </div>
                )}
              </>
            ) : <DataState title="Sin resultados" message="No hay pagos pendientes para el procedimiento seleccionado." />}
          </>
        ) : <DataState title="Sin pagos pendientes" message="No hay cuotas pendientes para este cliente." />}
      </SectionCard>

      <SectionCard eyebrow="Pagos" title="Pagos realizados" description="Comprobantes y pagos historicos registrados para el cliente.">
        {payments.length ? (
          <>
            <div className="table-card">
              <table>
                <thead>
                  <tr>
                    <th>Operación</th>
                    <th>Cuota</th>
                    <th>Monto</th>
                    <th>Fecha</th>
                    <th>Estado</th>
                    <th>Comprobante</th>
                    <th>Observación</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {visiblePayments.map((payment) => (
                    <tr key={payment.id}>
                      <td>{payment.operation}</td>
                      <td>{payment.quotaLabel}</td>
                      <td>{payment.amount}</td>
                      <td>{payment.submittedAt}</td>
                      <td><StatusBadge tone={payment.statusTone}>{payment.status}</StatusBadge></td>
                      <td>{payment.receiptUrl ? <a className="table-strong-link" href={payment.receiptUrl} target="_blank" rel="noreferrer">Ver</a> : 'Sin archivo'}</td>
                      <td>
                        <input
                          className="input"
                          value={getPaymentNote(payment.rawId, payment.note)}
                          onChange={(event) => onPaymentNoteChange(payment.rawId, event.target.value)}
                          placeholder="Nota para aprobación u observación"
                        />
                      </td>
                      <td>
                        <div className="table-action-list">
                          {(() => {
                            const normalizedStatus = payment.status.trim().toUpperCase()
                            const isApproved = normalizedStatus === 'APROBADO'

                            if (isApproved) {
                              return <span className="table-muted">Sin cambios</span>
                            }

                            return (
                              <>
                                <button className="button button--ghost button--compact" disabled={paymentActionId === payment.rawId || normalizedStatus === 'APROBADO'} type="button" onClick={() => void onUpdatePaymentStatus(payment.rawId, payment.status, 'APROBADO', payment.note)}>Aprobar</button>
                                <button className="button button--ghost button--compact" disabled={paymentActionId === payment.rawId || normalizedStatus === 'RECHAZADO'} type="button" onClick={() => void onUpdatePaymentStatus(payment.rawId, payment.status, 'RECHAZADO', payment.note)}>Observar</button>
                                <button className="button button--ghost button--compact" disabled={paymentActionId === payment.rawId || normalizedStatus === 'CANCELADO'} type="button" onClick={() => void onUpdatePaymentStatus(payment.rawId, payment.status, 'CANCELADO', payment.note)}>Cancelar</button>
                                <button className="button button--ghost button--compact" disabled={paymentActionId === payment.rawId || normalizedStatus === 'PENDIENTE'} type="button" onClick={() => void onUpdatePaymentStatus(payment.rawId, payment.status, 'PENDIENTE', payment.note)}>Pendiente</button>
                              </>
                            )
                          })()}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {payments.length > 5 && (
              <div className="_flex-between _mt-md">
                <span>Mostrando {visiblePaymentsCount} de {payments.length} pagos realizados</span>
                <div>
                  {hasLessPayments && (
                    <button type="button" className="button button--ghost" onClick={() => setVisiblePaymentsCount((c: number) => c - 5)}>Ver menos</button>
                  )}
                  {hasMorePayments && (
                    <button type="button" className="button button--secondary" onClick={() => setVisiblePaymentsCount((c: number) => c + 5)}>Ver más</button>
                  )}
                </div>
              </div>
            )}
          </>
        ) : <DataState title="Sin pagos registrados" message="El cliente aun no tiene pagos en su historial." />}
      </SectionCard>
    </>
  )
}