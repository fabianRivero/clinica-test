import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'

import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getClientPayments, uploadClientPaymentReceipt } from '../../services/api/client'

export function ClientPaymentsPage() {
  const [selectedQuotaId, setSelectedQuotaId] = useState<number | null>(null)
  const [qrModalOpen, setQrModalOpen] = useState(false)
  const [paymentAmount, setPaymentAmount] = useState('')
  const [paymentDetails, setPaymentDetails] = useState('')
  const [receiptFile, setReceiptFile] = useState<File | null>(null)
  const [submitMessage, setSubmitMessage] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const { data, isLoading, error } = useApiResource(getClientPayments)
  const [pageData, setPageData] = useState(data)

  useEffect(() => {
    if (data) {
      setPageData(data)
    }
  }, [data])

  const openQuotaPayment = (quotaId: number, amountValue: string) => {
    setSelectedQuotaId(quotaId)
    setPaymentAmount(amountValue)
    setPaymentDetails('')
    setReceiptFile(null)
    setSubmitError(null)
    setSubmitMessage(null)
  }

  const closeQuotaPayment = () => {
    setSelectedQuotaId(null)
    setPaymentAmount('')
    setPaymentDetails('')
    setReceiptFile(null)
    setSubmitError(null)
  }

  const handleReceiptFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setReceiptFile(event.target.files?.[0] || null)
    setSubmitError(null)
    setSubmitMessage(null)
  }

  const handleUploadReceipt = async (event: FormEvent) => {
    event.preventDefault()
    if (!selectedQuotaId) return
    if (!receiptFile) {
      setSubmitError('Debes adjuntar el comprobante de pago antes de enviarlo.')
      return
    }

    setIsSubmitting(true)
    setSubmitError(null)
    setSubmitMessage(null)
    try {
      const response = await uploadClientPaymentReceipt(selectedQuotaId, {
        amount: paymentAmount,
        details: paymentDetails,
        receiptFile,
      })
      setPageData((current) => {
        if (!current) return current

        return {
          ...current,
          activeQuotas: current.activeQuotas.map((quota) =>
            quota.rawId === selectedQuotaId ? response.quota : quota,
          ),
          payments: [response.payment, ...current.payments],
        }
      })
      setSubmitMessage(response.detail)
      closeQuotaPayment()
    } catch (requestError) {
      setSubmitError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo enviar el comprobante.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

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

      {pageData ? (
        <>
          <section className="metrics-grid">
            {pageData.metrics.map((metric) => (
              <MetricCard key={metric.id} metric={metric} />
            ))}
          </section>

          <SectionCard
            eyebrow="Pago por QR"
            title="Escanea y paga"
            description="Usa este QR para realizar la transferencia bancaria y luego adjunta tu comprobante en la cuota correspondiente."
          >
            {pageData.paymentQrConfig.hasQr ? (
              <div className="payment-qr-grid">
                <article className="payment-qr-card">
                  <div className="payment-qr-card__header">
                    <div>
                      <span>QR bancario</span>
                      <strong>Disponible para pago</strong>
                    </div>
                  </div>
                  <img
                    alt="QR de pago bancario"
                    className="payment-qr-card__image"
                    onClick={() => setQrModalOpen(true)}
                    src={pageData.paymentQrConfig.qrImageUrl}
                  />
                  <button
                    className="button button--ghost button--compact"
                    type="button"
                    onClick={() => setQrModalOpen(true)}
                  >
                    Ver QR en grande
                  </button>
                </article>
                <article className="payment-qr-card">
                  <div className="payment-qr-card__header">
                    <div>
                      <span>Instrucciones</span>
                      <strong>Antes de subir tu comprobante</strong>
                    </div>
                  </div>
                  <p>{pageData.paymentQrConfig.instructions}</p>
                  <p>
                    Elige una cuota pendiente, realiza el pago con este QR y luego adjunta el
                    comprobante para que administracion lo revise.
                  </p>
                </article>
              </div>
            ) : (
              <DataState
                title="QR no disponible"
                message="Administracion todavia no configuró el QR bancario. Vuelve a intentar mas tarde o contacta a la clinica."
                tone="danger"
              />
            )}
          </SectionCard>

          <SectionCard
            eyebrow="Cuotas vigentes"
            title="Estado de cuotas"
            description="Resumen de montos estimados por cuota y del ultimo comprobante asociado."
          >
            {pageData.activeQuotas.length ? (
              <div className="capacity-list">
                {pageData.activeQuotas.map((quota) => (
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
                    <button
                      className="button button--ghost"
                      type="button"
                      disabled={!quota.canUploadReceipt || !pageData.paymentQrConfig.hasQr}
                      onClick={() => openQuotaPayment(quota.rawId, quota.amountValue)}
                    >
                      {quota.canUploadReceipt
                        ? pageData.paymentQrConfig.hasQr
                          ? 'Pagar por QR y subir comprobante'
                          : 'QR no disponible'
                        : 'Cuota cerrada'}
                    </button>

                    {selectedQuotaId === quota.rawId ? (
                      <form className="payment-upload-form" onSubmit={handleUploadReceipt}>
                        <div className="payment-upload-form__grid">
                          <label className="field">
                            <span>Monto pagado</span>
                            <input
                              className="input"
                              type="number"
                              min="0"
                              step="0.01"
                              value={paymentAmount}
                              onChange={(event) => setPaymentAmount(event.target.value)}
                            />
                          </label>
                          <label className="field">
                            <span>Comprobante</span>
                            <input
                              accept=".png,.jpg,.jpeg,.webp,.pdf,image/png,image/jpeg,image/webp,application/pdf"
                              className="input input--file"
                              type="file"
                              onChange={handleReceiptFileChange}
                            />
                            <small className="field__hint">
                              {receiptFile
                                ? `Archivo seleccionado: ${receiptFile.name}`
                                : 'Puedes adjuntar imagen o PDF del comprobante.'}
                            </small>
                          </label>
                          <label className="field field--full">
                            <span>Detalle adicional</span>
                            <textarea
                              className="input textarea"
                              rows={3}
                              value={paymentDetails}
                              onChange={(event) => setPaymentDetails(event.target.value)}
                              placeholder="Ejemplo: transferencia desde mi banca movil"
                            />
                          </label>
                        </div>

                        {submitError ? <div className="form-error">{submitError}</div> : null}

                        <div className="form-actions">
                          <button
                            className="button button--ghost"
                            disabled={isSubmitting}
                            type="button"
                            onClick={closeQuotaPayment}
                          >
                            Cancelar
                          </button>
                          <button className="button" disabled={isSubmitting} type="submit">
                            {isSubmitting ? 'Enviando comprobante...' : 'Enviar comprobante'}
                          </button>
                        </div>
                      </form>
                    ) : null}
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
            {submitMessage ? (
              <DataState title="Comprobante enviado" message={submitMessage} />
            ) : null}
            {pageData.payments.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Operacion</th>
                      <th>Cuota</th>
                      <th>Monto</th>
                      <th>Estado</th>
                      <th>Comprobante</th>
                      <th>Revision</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageData.payments.map((payment) => (
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
                          {payment.receiptUrl ? (
                            <a className="button button--ghost button--compact" href={payment.receiptUrl} target="_blank" rel="noreferrer">
                              Ver archivo
                            </a>
                          ) : (
                            <span>Sin archivo</span>
                          )}
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

      {pageData?.paymentQrConfig.hasQr && qrModalOpen ? (
        <div className="qr-modal" role="dialog" aria-modal="true" aria-label="QR de pago">
          <button
            aria-label="Cerrar visor de QR"
            className="qr-modal__backdrop"
            type="button"
            onClick={() => setQrModalOpen(false)}
          />
          <div className="qr-modal__content">
            <div className="qr-modal__header">
              <div>
                <span>QR de pago</span>
                <strong>Escanea este codigo para realizar la transferencia</strong>
              </div>
              <button
                className="button button--ghost button--compact"
                type="button"
                onClick={() => setQrModalOpen(false)}
              >
                Cerrar
              </button>
            </div>
            <img
              alt="QR de pago bancario ampliado"
              className="qr-modal__image"
              src={pageData.paymentQrConfig.qrImageUrl}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}
