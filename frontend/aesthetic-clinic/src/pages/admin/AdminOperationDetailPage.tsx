import { useMemo } from 'react'
import { useParams } from 'react-router-dom'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getAdminOperationDetail } from '../../services/api/admin'

function getStatusTone(status: string) {
  const normalized = status.toLowerCase()
  if (normalized.includes('final')) return 'success'
  if (normalized.includes('cancel')) return 'danger'
  if (normalized.includes('borrador')) return 'warning'
  return 'primary'
}

export function AdminOperationDetailPage() {
  const { operationId = '' } = useParams()
  const loader = useMemo(() => () => getAdminOperationDetail(operationId), [operationId])
  const { data, isLoading, error } = useApiResource(loader)

  if (isLoading && !data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Detalle de operacion"
          title="Cargando tratamiento"
          description="Estamos recuperando la informacion clinica, financiera y documental de la operacion."
          actions={[{ label: 'Volver a operaciones', variant: 'ghost', to: '/admin/operaciones' }]}
        />
        <SectionCard title="Cargando detalle">
          <DataState
            title="Consultando operacion"
            message="Sincronizando citas, cuotas y ficha clinica desde Django."
          />
        </SectionCard>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Detalle de operacion"
          title="No pudimos cargar la operacion"
          description="Puede que la operacion no exista o que la conexion no este disponible."
          actions={[{ label: 'Volver a operaciones', variant: 'ghost', to: '/admin/operaciones' }]}
        />
        <SectionCard title="Detalle no disponible">
          <DataState
            title="Operacion no disponible"
            message={error || 'No encontramos datos suficientes para mostrar el detalle.'}
            tone="danger"
          />
        </SectionCard>
      </div>
    )
  }

  const { operation } = data

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Detalle de operacion"
        title={`${operation.procedure} · ${operation.patient}`}
        description="Aqui puedes revisar la ficha clinica, el documento escaneado, las cuotas y el seguimiento de citas."
        actions={[{ label: 'Volver a operaciones', variant: 'ghost', to: '/admin/operaciones' }]}
      />

      <SectionCard
        eyebrow="Resumen clinico"
        title="Informacion principal"
        description="Estado global del tratamiento, paciente, procedimiento y seguimiento activo."
      >
        <div className="operation-detail-grid">
          <article className="operation-detail-panel">
            <div className="operation-detail-panel__header">
              <div>
                <span>Estado actual</span>
                <strong>{operation.status}</strong>
              </div>
              <StatusBadge tone={getStatusTone(operation.status)}>{operation.status}</StatusBadge>
            </div>
            <dl className="operation-detail-list">
              <div>
                <dt>Paciente</dt>
                <dd>{operation.patient}</dd>
              </div>
              <div>
                <dt>Especialista</dt>
                <dd>{operation.specialist}</dd>
              </div>
              <div>
                <dt>Tipo de servicio</dt>
                <dd>{operation.serviceType}</dd>
              </div>
              <div>
                <dt>Tipo de procedimiento</dt>
                <dd>{operation.procedureType}</dd>
              </div>
              <div>
                <dt>Precio pactado</dt>
                <dd>{operation.price}</dd>
              </div>
              <div>
                <dt>Proxima cita</dt>
                <dd>{operation.nextAppointment}</dd>
              </div>
            </dl>
          </article>

          <article className="operation-detail-panel">
            <div className="operation-detail-panel__header">
              <div>
                <span>Datos operativos</span>
                <strong>Seguimiento del tratamiento</strong>
              </div>
            </div>
            <dl className="operation-detail-list">
              <div>
                <dt>Sesiones</dt>
                <dd>{operation.sessions}</dd>
              </div>
              <div>
                <dt>Cuotas</dt>
                <dd>{operation.quotaStatus}</dd>
              </div>
              <div>
                <dt>Inicio</dt>
                <dd>{operation.startDate}</dd>
              </div>
              <div>
                <dt>Fin</dt>
                <dd>{operation.endDate}</dd>
              </div>
              <div>
                <dt>Zona general</dt>
                <dd>{operation.zonaGeneral}</dd>
              </div>
              <div>
                <dt>Zona especifica</dt>
                <dd>{operation.zonaEspecifica}</dd>
              </div>
            </dl>
          </article>
        </div>

        <div className="operation-card__note-grid">
          <article>
            <span>Detalles de la operacion</span>
            <p>{operation.detallesOperacion}</p>
          </article>
          <article>
            <span>Recomendaciones</span>
            <p>{operation.recomendaciones}</p>
          </article>
        </div>
      </SectionCard>

      <SectionCard
        eyebrow="Ficha clinica"
        title="Documento y observaciones"
        description="Vista del PDF escaneado y de los datos generales registrados en la ficha medica."
      >
        <div className="operation-detail-grid">
          <article className="operation-detail-panel">
            <div className="operation-detail-panel__header">
              <div>
                <span>Ficha registrada</span>
                <strong>{operation.medicalRecordDate}</strong>
              </div>
            </div>
            <dl className="operation-detail-list">
              <div>
                <dt>Motivo de consulta</dt>
                <dd>{operation.medicalRecordReason}</dd>
              </div>
              <div>
                <dt>Observaciones</dt>
                <dd>{operation.medicalRecordNotes}</dd>
              </div>
              <div>
                <dt>Consentimiento</dt>
                <dd>{operation.consentAccepted ? 'Aceptado' : 'Pendiente o no registrado'}</dd>
              </div>
              <div>
                <dt>Documento PDF</dt>
                <dd>{operation.documentPdfName || 'Sin archivo adjunto'}</dd>
              </div>
            </dl>
          </article>

          <article className="operation-detail-panel">
            <div className="operation-detail-panel__header">
              <div>
                <span>Documento escaneado</span>
                <strong>{operation.documentPdfUrl ? 'Disponible para revision' : 'No adjuntado'}</strong>
              </div>
            </div>
            {operation.documentPdfUrl ? (
              <div className="document-viewer">
                <div className="document-viewer__actions">
                  <a
                    className="button button--ghost button--compact"
                    href={operation.documentPdfUrl}
                    rel="noreferrer"
                    target="_blank"
                  >
                    Ver PDF
                  </a>
                  <a
                    className="button button--compact"
                    download={operation.documentPdfName || undefined}
                    href={operation.documentPdfUrl}
                  >
                    Descargar PDF
                  </a>
                </div>
                <iframe
                  className="document-viewer__frame"
                  src={operation.documentPdfUrl}
                  title={`Documento escaneado de ${operation.id}`}
                />
              </div>
            ) : (
              <DataState
                title="Sin documento escaneado"
                message="Esta operacion todavia no tiene un PDF adjunto en la ficha clinica."
              />
            )}
          </article>
        </div>
      </SectionCard>

      <SectionCard
        eyebrow="Seguimiento"
        title="Citas y cuotas"
        description="Resumen rapido del historial de reservas y del plan de pagos asociado a la operacion."
      >
        <div className="operation-detail-grid">
          <article className="operation-detail-panel">
            <div className="operation-detail-panel__header">
              <div>
                <span>Citas medicas</span>
                <strong>{operation.appointments.length} registro(s)</strong>
              </div>
            </div>
            {operation.appointments.length ? (
              <div className="operation-detail-items">
                {operation.appointments.map((appointment) => (
                  <article className="operation-detail-item" key={appointment.id}>
                    <strong>{appointment.dateTime}</strong>
                    <p>{appointment.specialist}</p>
                    <span>{appointment.status}</span>
                    <small>Biometria: {appointment.biometricStatus}</small>
                  </article>
                ))}
              </div>
            ) : (
              <DataState
                title="Sin citas registradas"
                message="Todavia no hay citas asociadas a esta operacion."
              />
            )}
          </article>

          <article className="operation-detail-panel">
            <div className="operation-detail-panel__header">
              <div>
                <span>Plan de pagos</span>
                <strong>{operation.quotas.length} cuota(s)</strong>
              </div>
            </div>
            {operation.quotas.length ? (
              <div className="operation-detail-items">
                {operation.quotas.map((quota) => (
                  <article className="operation-detail-item" key={quota.id}>
                    <strong>Cuota {quota.number}</strong>
                    <p>Vence: {quota.dueDate}</p>
                    <span>{quota.status}</span>
                    <small>Pagos registrados: {quota.paymentsCount}</small>
                  </article>
                ))}
              </div>
            ) : (
              <DataState
                title="Sin cuotas creadas"
                message="Esta operacion no tiene cuotas registradas por el momento."
              />
            )}
          </article>
        </div>
      </SectionCard>
    </div>
  )
}
