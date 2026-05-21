import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { verificationStatusLabel, verificationStatusTone } from '../../constants/verification'
import { useApiResource } from '../../hooks/useApiResource'
import { getClientReservations } from '../../services/api/client'
import { useLocation } from 'react-router-dom'

export function ClientReservationsPage() {
  const location = useLocation()
  const { data, isLoading, error } = useApiResource(getClientReservations)
  const flashMessage =
    typeof location.state === 'object' && location.state && 'flashMessage' in location.state
      ? String(location.state.flashMessage)
      : null

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Agenda y reservas"
        title="Mis reservas"
        description="Consulta citas registradas y su estado de confirmacion."
      />

      {flashMessage ? <DataState title="Reserva registrada" message={flashMessage} /> : null}

      {isLoading && !data ? (
        <SectionCard title="Cargando reservas">
          <DataState title="Sincronizando agenda" message="Estamos cargando tus citas y cupos disponibles." />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar tus reservas">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <section className="dashboard-grid">
          <SectionCard
            eyebrow="Agenda"
            title="Citas registradas"
            description="Incluye citas futuras y tambien las que esperan confirmacion o quedaron con observaciones."
          >
            {data.appointments.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Operacion</th>
                      <th>Especialista</th>
                      <th>Fecha</th>
                      <th>Estado</th>
                      <th>Confirmacion</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.appointments.map((appointment) => (
                      <tr key={appointment.id}>
                        <td>
                          <strong>{appointment.operation}</strong>
                          <span>{appointment.details}</span>
                        </td>
                        <td>{appointment.specialist}</td>
                        <td>{appointment.dateTime}</td>
                        <td>
                          <StatusBadge tone={appointment.statusTone}>{appointment.status}</StatusBadge>
                        </td>
                        <td>
                          <StatusBadge tone={verificationStatusTone[appointment.verificationStatus ?? 'pendiente']}>
                            {verificationStatusLabel[appointment.verificationStatus ?? 'pendiente']}
                          </StatusBadge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <DataState title="Sin citas registradas" message="Aun no tienes citas programadas en el sistema." />
            )}
          </SectionCard>
        </section>
      ) : null}
    </div>
  )
}
