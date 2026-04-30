import { DataState } from '../../components/admin/DataState'
import { AdminRelationshipTabs } from '../../components/admin/AdminRelationshipTabs'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import { cancelAdminAppointment, getAdminProspects } from '../../services/api/admin'

export function AdminClientsPage() {
  const { data, isLoading, error, reload } = useApiResource(getAdminProspects)
  const { showNotification } = useNotifications()

  async function handleCancelAppointment(appointmentId: number) {
    const shouldCancel = window.confirm(
      'Se cancelara la cita programada del cliente y el cupo volvera a quedar disponible. ¿Deseas continuar?',
    )
    if (!shouldCancel) {
      return
    }

    try {
      const response = await cancelAdminAppointment(appointmentId)
      showNotification({
        title: 'Cita cancelada',
        message: response.detail,
        tone: 'success',
      })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo cancelar la cita',
        message:
          requestError instanceof Error
            ? requestError.message
            : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Relacion comercial"
        title="Clientes"
        description="Consulta los clientes consolidados que ya tienen cuenta, historial clinico y acceso al portal para pagos y reservas."
        actions={[{ label: 'Exportar clientes', variant: 'ghost' }]}
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
          <section className="metrics-grid metrics-grid--compact">
            {data.metrics.slice(2).map((metric) => (
              <MetricCard key={metric.id} metric={metric} />
            ))}
          </section>

          <SectionCard
            eyebrow="Clientes"
            title="Clientes con cuenta"
            description="Clientes activos e inactivos que ya pueden ingresar al portal y revisar su historial."
          >
            {data.clients.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Estado</th>
                      <th>Telefono</th>
                      <th>Operaciones activas</th>
                      <th>Historial</th>
                      <th>Ultimo analisis</th>
                      <th>Citas programadas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.clients.map((client) => (
                      <tr key={client.id}>
                        <td>{client.name}</td>
                        <td>
                          <StatusBadge tone={client.status === 'Activo' ? 'success' : 'neutral'}>
                            {client.status}
                          </StatusBadge>
                        </td>
                        <td>{client.phone}</td>
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
                                  <button
                                    className="button button--ghost button--compact"
                                    type="button"
                                    onClick={() => void handleCancelAppointment(appointment.rawId)}
                                  >
                                    Cancelar cita
                                  </button>
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
              </div>
            ) : (
              <DataState
                title="Sin clientes con cuenta"
                message="No se encontraron clientes consolidados en la base conectada."
              />
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  )
}
