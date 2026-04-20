import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getAdminPayments } from '../../services/api/admin'

export function AdminPaymentsPage() {
  const { data, isLoading, error } = useApiResource(getAdminPayments)

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Tesoreria"
        title="Pagos y verificaciones"
        description="Modulo para revisar comprobantes cargados por clientes y controlar cuotas aprobadas, observadas o pendientes."
        actions={[
          { label: 'Revision masiva', variant: 'primary' },
          { label: 'Exportar movimientos', variant: 'ghost' },
        ]}
      />

      {isLoading && !data ? (
        <SectionCard title="Cargando pagos">
          <DataState
            title="Sincronizando tesoreria"
            message="Cargando pagos, montos, cuotas y verificacion administrativa."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar pagos">
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
            eyebrow="Comprobantes"
            title="Cola de verificacion"
            description="Los estados replican el flujo real del negocio: pendiente, observado y aprobado."
          >
            {data.payments.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Paciente</th>
                      <th>Operacion</th>
                      <th>Cuota</th>
                      <th>Monto</th>
                      <th>Vencimiento</th>
                      <th>Estado</th>
                      <th>Verificador</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.payments.map((payment) => (
                      <tr key={payment.id}>
                        <td>{payment.id}</td>
                        <td>
                          <strong>{payment.patient}</strong>
                          <span>{payment.submittedAt}</span>
                        </td>
                        <td>{payment.operation}</td>
                        <td>{payment.quota}</td>
                        <td>{payment.amount}</td>
                        <td>{payment.dueDate}</td>
                        <td>
                          <StatusBadge
                            tone={
                              payment.status === 'aprobado'
                                ? 'approved'
                                : payment.status === 'observado'
                                  ? 'observed'
                                  : 'pending'
                            }
                          >
                            {payment.status}
                          </StatusBadge>
                        </td>
                        <td>{payment.verifier}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <DataState
                title="Sin pagos registrados"
                message="Todavia no hay comprobantes cargados en el backend conectado."
              />
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  )
}
