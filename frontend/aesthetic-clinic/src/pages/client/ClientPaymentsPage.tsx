import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import { getClientPayments, uploadClientPaymentReceipt } from '../../services/api/client'
import { formatPaymentBreakdown } from '../../utils/payments'

const PAGE_SIZE = 10

const ALL_FILTERS = {
  pagos: [
    { value: '', label: 'Todos los estados' },
    { value: 'pendiente', label: 'Pendiente' },
    { value: 'aprobado', label: 'Aprobado' },
    { value: 'observado', label: 'Observado' },
    { value: 'cancelado', label: 'Cancelado' },
  ],
  cuotas: [
    { value: '', label: 'Todos los estados' },
    { value: 'Pendiente', label: 'Pendiente' },
    { value: 'Vencida', label: 'Vencida' },
    { value: 'Pagado', label: 'Pagado' },
    { value: 'No pagada', label: 'No pagada' },
  ],
}

export function ClientPaymentsPage() {
  const [selectedQuotaId, setSelectedQuotaId] = useState<number | null>(null)
  const [qrModalOpen, setQrModalOpen] = useState(false)
  const [paymentAmount, setPaymentAmount] = useState('')
  const [paymentDetails, setPaymentDetails] = useState('')
  const [receiptFile, setReceiptFile] = useState<File | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [paymentStatusFilter, setPaymentStatusFilter] = useState('')
  const [paymentsVisibleCount, setPaymentsVisibleCount] = useState(PAGE_SIZE)
  const [quotaStatusFilter, setQuotaStatusFilter] = useState('')
  const [quotasVisibleCount, setQuotasVisibleCount] = useState(PAGE_SIZE)
  const { data, isLoading, error } = useApiResource(getClientPayments)
  const [pageData, setPageData] = useState(data)
  const { showNotification } = useNotifications()

  useEffect(() => {
    if (data) {
      setPageData(data)
    }
  }, [data])

  // Filter helpers: status match is case-insensitive trimmed contains so that
  // small backend label changes don't silently break the filter.
  const filteredPayments = (pageData?.payments ?? []).filter((payment) => {
    if (!paymentStatusFilter) return true
    return payment.status.trim().toLowerCase() === paymentStatusFilter.toLowerCase()
  })

  const filteredQuotas = (pageData?.activeQuotas ?? []).filter((quota) => {
    if (!quotaStatusFilter) return true
    return quota.status.trim().toLowerCase() === quotaStatusFilter.toLowerCase()
  })

  const visiblePayments = filteredPayments.slice(0, paymentsVisibleCount)
  const visibleQuotas = filteredQuotas.slice(0, quotasVisibleCount)

  const handlePaymentStatusFilterChange = (value: string) => {
    setPaymentStatusFilter(value)
    setPaymentsVisibleCount(PAGE_SIZE)
  }

  const handleQuotaStatusFilterChange = (value: string) => {
    setQuotaStatusFilter(value)
    setQuotasVisibleCount(PAGE_SIZE)
  }

  const handleShowMorePayments = () => {
    setPaymentsVisibleCount((current) => current + PAGE_SIZE)
  }

  const handleShowLessPayments = () => {
    setPaymentsVisibleCount((current) => Math.max(current - PAGE_SIZE, PAGE_SIZE))
  }

  const handleShowMoreQuotas = () => {
    setQuotasVisibleCount((current) => current + PAGE_SIZE)
  }

  const handleShowLessQuotas = () => {
    setQuotasVisibleCount((current) => Math.max(current - PAGE_SIZE, PAGE_SIZE))
  }

  const openQuotaPayment = (quotaId: number, amountValue: string) => {
    setSelectedQuotaId(quotaId)
    setPaymentAmount(amountValue)
    setPaymentDetails('')
    setReceiptFile(null)
    setSubmitError(null)
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
  }

  const handleUploadReceipt = async (event: FormEvent) => {
    event.preventDefault()
    if (!selectedQuotaId) return
    // Client portal is VIRTUAL-only — receipt is mandatory.
    if (!receiptFile) {
      setSubmitError('Debes adjuntar el comprobante de pago antes de enviarlo.')
      return
    }

    setIsSubmitting(true)
    setSubmitError(null)
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
      showNotification({
        title: 'Comprobante enviado',
        message: response.detail,
        tone: 'success',
      })
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
                    comprobante para que administración lo revise.
                  </p>
                </article>
              </div>
            ) : (
              <DataState
                title="QR no disponible"
                message="Administración todavía no configuró el QR bancario. Vuelve a intentar más tarde o contacta a la clínica."
                tone="danger"
              />
            )}
          </SectionCard>

          <SectionCard
            eyebrow="Cuotas vigentes"
            title="Estado de cuotas"
            description="Resumen de montos estimados por cuota y del último comprobante asociado."
            action={
              <label className="field" style={{ minWidth: '12rem' }}>
                <span className="visually-hidden">Estado de la cuota</span>
                <select
                  className="input"
                  value={quotaStatusFilter}
                  onChange={(event) => handleQuotaStatusFilterChange(event.target.value)}
                >
                  {ALL_FILTERS.cuotas.map((option) => (
                    <option key={option.value || 'all'} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            }
          >
            {filteredQuotas.length === 0 ? (
              <DataState
                title="Sin cuotas para mostrar"
                message={
                  quotaStatusFilter
                    ? `No hay cuotas en estado "${quotaStatusFilter}" en este momento.`
                    : 'No tienes cuotas pendientes o vencidas en este momento.'
                }
              />
            ) : (
              <div className="capacity-list">
                {visibleQuotas.map((quota) => (
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
                      <span>Último comprobante</span>
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
                          ? quota.uploadActionLabel
                          : 'QR no disponible'
                        : 'Cuota cerrada'}
                    </button>

                    {selectedQuotaId === quota.rawId ? (
                      <form className="payment-upload-form" onSubmit={handleUploadReceipt}>
                        <div className="payment-upload-form__grid">
                          <label className="field">
                            <span>Monto a pagar</span>
                            <input
                              className="input"
                              type="number"
                              min="0"
                              step="0.01"
                              value={paymentAmount}
                              readOnly
                              aria-readonly="true"
                            />
                          </label>
                          <label className="field">
                            <span>Metodo de pago</span>
                            <input
                              className="input"
                              type="text"
                              value="Virtual (QR + comprobante)"
                              readOnly
                              aria-readonly="true"
                            />
                            <small className="field__hint">
                              Los pagos en caja (efectivo o mixto) se registran en
                              consultorio; desde el portal solo puedes enviar
                              comprobantes de transferencias QR.
                            </small>
                          </label>
                          <label className="field">
                            <span>Comprobante</span>
                            <input
                              accept=".png,.jpg,.jpeg,.webp,.pdf,image/png,image/jpeg,image/webp,application/pdf"
                              className="input input--file"
                              type="file"
                              onChange={handleReceiptFileChange}
                              required
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
            )}
            {filteredQuotas.length > PAGE_SIZE ? (
              <div className="_mt-md" style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem' }}>
                <button
                  className="button button--ghost"
                  type="button"
                  onClick={handleShowLessQuotas}
                  disabled={quotasVisibleCount <= PAGE_SIZE}
                >
                  Ver menos
                </button>
                <button
                  className="button button--secondary"
                  type="button"
                  onClick={handleShowMoreQuotas}
                  disabled={quotasVisibleCount >= filteredQuotas.length}
                >
                  Ver más
                </button>
              </div>
            ) : null}
          </SectionCard>

          <SectionCard
            eyebrow="Comprobantes"
            title="Historial de pagos"
            description="Incluye pagos pendientes, aprobados y observados, con comentarios de administración."
            action={
              <label className="field" style={{ minWidth: '12rem' }}>
                <span className="visually-hidden">Estado del pago</span>
                <select
                  className="input"
                  value={paymentStatusFilter}
                  onChange={(event) => handlePaymentStatusFilterChange(event.target.value)}
                >
                  {ALL_FILTERS.pagos.map((option) => (
                    <option key={option.value || 'all'} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            }
          >
            {filteredPayments.length === 0 ? (
              <DataState
                title="Sin pagos para mostrar"
                message={
                  paymentStatusFilter
                    ? `No hay pagos en estado "${paymentStatusFilter}" en este momento.`
                    : 'Aun no se registran comprobantes dentro de esta cuenta.'
                }
              />
            ) : (
              <>
                <div className="table-card">
                  <table>
                    <thead>
                      <tr>
                        <th>Operación</th>
                        <th>Cuota</th>
                        <th>Monto</th>
                        <th>Estado</th>
                        <th>Comprobante</th>
                        <th>Revisión</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visiblePayments.map((payment) => (
                        <tr key={payment.id}>
                          <td>
                            <strong>{payment.operation}</strong>
                            <span>{payment.submittedAt}</span>
                          </td>
                          <td>
                            <strong>{payment.quotaLabel}</strong>
                            <span>Vence {payment.dueDate}</span>
                          </td>
                          <td>
                            {payment.amount}
                            {(() => {
                              const breakdown = formatPaymentBreakdown(payment)
                              return breakdown ? <small className="field__hint">{breakdown}</small> : null
                            })()}
                          </td>
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
                {filteredPayments.length > PAGE_SIZE ? (
                  <div className="_mt-md" style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem' }}>
                    <button
                      className="button button--ghost"
                      type="button"
                      onClick={handleShowLessPayments}
                      disabled={paymentsVisibleCount <= PAGE_SIZE}
                    >
                      Ver menos
                    </button>
                    <button
                      className="button button--secondary"
                      type="button"
                      onClick={handleShowMorePayments}
                      disabled={paymentsVisibleCount >= filteredPayments.length}
                    >
                      Ver más
                    </button>
                  </div>
                ) : null}
                <div className="_mt-md" style={{ textAlign: 'center' }}>
                  <Link className="button button--secondary" to="/cliente/pagos/historial">
                    Ver todo el historial
                  </Link>
                </div>
              </>
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
