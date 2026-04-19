import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { paymentQueue } from '../../data/adminMock'

export function AdminPaymentsPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Tesorería"
        title="Pagos y verificaciones"
        description="Módulo para revisar comprobantes cargados por clientes y controlar cuotas aprobadas, observadas o pendientes."
        actions={[
          { label: 'Revisión masiva', variant: 'primary' },
          { label: 'Exportar movimientos', variant: 'ghost' },
        ]}
      />

      <SectionCard
        eyebrow="Comprobantes"
        title="Cola de verificación"
        description="Los estados replican el flujo real del negocio: pendiente, observado y aprobado."
      >
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Paciente</th>
                <th>Operación</th>
                <th>Monto</th>
                <th>Banco</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {paymentQueue.map((payment) => (
                <tr key={payment.id}>
                  <td>{payment.id}</td>
                  <td>{payment.patient}</td>
                  <td>{payment.operation}</td>
                  <td>{payment.amount}</td>
                  <td>{payment.bank}</td>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  )
}
