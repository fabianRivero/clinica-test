import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react'

import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getAdminPayments, updateAdminPaymentQrConfig } from '../../services/api/admin'

export function AdminPaymentsPage() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [instructions, setInstructions] = useState('')
  const [qrFile, setQrFile] = useState<File | null>(null)
  const [submitMessage, setSubmitMessage] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const loader = useMemo(() => () => getAdminPayments(), [refreshKey])
  const { data, isLoading, error } = useApiResource(loader)

  useEffect(() => {
    if (data) {
      setInstructions(data.paymentQrConfig.instructions)
    }
  }, [data])

  const handleQrFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setQrFile(event.target.files?.[0] || null)
    setSubmitError(null)
    setSubmitMessage(null)
  }

  const handleSubmitQrConfig = async (event: FormEvent) => {
    event.preventDefault()
    if (!qrFile) {
      setSubmitError('Debes seleccionar una imagen QR para actualizar la configuracion de pago.')
      return
    }

    setIsSubmitting(true)
    setSubmitError(null)
    setSubmitMessage(null)
    try {
      const response = await updateAdminPaymentQrConfig(qrFile, instructions)
      setSubmitMessage(response.detail)
      setQrFile(null)
      setRefreshKey((current) => current + 1)
    } catch (requestError) {
      setSubmitError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo actualizar el QR de pago.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

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
            eyebrow="Pago por QR"
            title="Configuracion del QR bancario"
            description="Este QR se mostrara a los clientes cuando quieran pagar una cuota desde su portal."
          >
            <div className="payment-qr-grid">
              <article className="payment-qr-card">
                <div className="payment-qr-card__header">
                  <div>
                    <span>QR activo</span>
                    <strong>
                      {data.paymentQrConfig.hasQr
                        ? 'Disponible para clientes'
                        : 'Todavia no configurado'}
                    </strong>
                  </div>
                </div>
                {data.paymentQrConfig.hasQr ? (
                  <img
                    alt="QR de pago activo"
                    className="payment-qr-card__image"
                    src={data.paymentQrConfig.qrImageUrl}
                  />
                ) : (
                  <DataState
                    title="Sin QR de pago"
                    message="Sube una imagen QR para habilitar el flujo de pagos por comprobante en el portal del cliente."
                  />
                )}
                <p>{data.paymentQrConfig.instructions}</p>
              </article>

              <form className="payment-qr-form" onSubmit={handleSubmitQrConfig}>
                <label className="field">
                  <span>Instrucciones para el cliente</span>
                  <textarea
                    className="input textarea"
                    rows={4}
                    value={instructions}
                    onChange={(event) => setInstructions(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Imagen QR</span>
                  <input
                    accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
                    className="input input--file"
                    type="file"
                    onChange={handleQrFileChange}
                  />
                  <small className="field__hint">
                    {qrFile
                      ? `Archivo seleccionado: ${qrFile.name}`
                      : 'Selecciona una imagen actualizada del QR bancario.'}
                  </small>
                </label>

                {submitError ? (
                  <div className="form-error">{submitError}</div>
                ) : null}
                {submitMessage ? (
                  <DataState title="Configuracion actualizada" message={submitMessage} />
                ) : null}

                <div className="form-actions">
                  <button className="button" disabled={isSubmitting} type="submit">
                    {isSubmitting ? 'Guardando QR...' : 'Guardar QR de pago'}
                  </button>
                </div>
              </form>
            </div>
          </SectionCard>

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
