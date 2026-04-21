import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getClientPayments } from '../../services/api/client'

export function ClientPaymentsPage() {
  const { data, isLoading, error } = useApiResource(getClientPayments)

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Pagos y cuotas"
        title="Mis pagos"
        description="Consulta el estado de tus cuotas, revisa comprobantes ya enviados y detecta pagos observados."
      />

      {isLoading && !data ? (
        <SectionCard title="Cargando pagos">
          <DataState title="Sincronizando cuotas" message="Estamos trayendo pagos, comprobantes y vencimientos." />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar tus pagos">
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
            eyebrow="Cuotas vigentes"
            title="Estado de cuotas"
            description="Resumen de montos estimados por cuota y del ultimo comprobante asociado."
          >
            {data.activeQuotas.length ? (
              <div className="capacity-list">
                {data.activeQuotas.map((quota) => (
                  <article className="capacity-item" key={quota.id}>
                    <div className="capacity-item__header">
                      <div>
                        <strong>
                          {quota.operation} | {quota.quotaLabel}
                        </strong>
                        <p>
                          {quota.amount} | vence {quota.dueDate}
                        </p>
                      </div>
                      <StatusBadge tone={quota.statusTone}>{quota.status}</StatusBadge>
                    </div>
                    <div className="client-inline-meta">
                      <span>Ultimo comprobante</span>
                      <StatusBadge tone={quota.latestPaymentTone}>{quota.latestPaymentStatus}</StatusBadge>
                    </div>
                    <button className="button button--ghost" type="button" disabled={!quota.canUploadReceipt}>
                      {quota.canUploadReceipt ? 'Subir comprobante pronto' : 'Cuota cerrada'}
                    </button>
                  </article>
                ))}
              </div>
            ) : (
              <DataState title="Sin cuotas activas" message="No tienes cuotas pendientes o vencidas en este momento." />
            )}
          </SectionCard>

          <SectionCard
            eyebrow="Comprobantes"
            title="Historial de pagos"
            description="Incluye pagos pendientes, aprobados y observados, con comentarios de administracion."
          >
            {data.payments.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Operacion</th>
                      <th>Cuota</th>
                      <th>Monto</th>
                      <th>Estado</th>
                      <th>Revision</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.payments.map((payment) => (
                      <tr key={payment.id}>
                        <td>
                          <strong>{payment.operation}</strong>
                          <span>{payment.submittedAt}</span>
                        </td>
                        <td>
                          <strong>{payment.quotaLabel}</strong>
                          <span>Vence {payment.dueDate}</span>
                        </td>
                        <td>{payment.amount}</td>
                        <td>
                          <StatusBadge tone={payment.statusTone}>{payment.status}</StatusBadge>
                        </td>
                        <td>
                          <strong>{payment.verifier}</strong>
                          <span>{payment.note}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <DataState title="Sin pagos registrados" message="Aun no se registran comprobantes dentro de esta cuenta." />
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  )
}
