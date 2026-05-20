import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from 'react'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import { useBranchContext } from '../../providers/BranchProvider'
import {
  type AdminPaymentsFilters,
  getAdminPayments,
  updateAdminPaymentQrConfig,
  updateAdminPaymentStatus,
} from '../../services/api/admin'
import type { UpdateAdminPaymentStatusPayload } from '../../types/admin'

function toComparableDate(value?: string) {
  if (!value) return null
  const normalized = value.trim()
  const direct = new Date(normalized)
  if (!Number.isNaN(direct.getTime())) return direct
  const ddmmyyyy = normalized.match(/(\d{2})\/(\d{2})\/(\d{4})/)
  if (!ddmmyyyy) return null
  const [, dd, mm, yyyy] = ddmmyyyy
  const parsed = new Date(`${yyyy}-${mm}-${dd}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function AdminPaymentsPage() {
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  const [instructions, setInstructions] = useState('')
  const [qrFile, setQrFile] = useState<File | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [paymentNotes, setPaymentNotes] = useState<Record<number, string>>({})
  const [paymentActionId, setPaymentActionId] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState<AdminPaymentsFilters['status']>('')
  const [dateFromFilter, setDateFromFilter] = useState('')
  const [dateToFilter, setDateToFilter] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [searchFilter, setSearchFilter] = useState('')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const loader = useCallback(
    () => getAdminPayments(),
    [branchId],
  )
  const { data, isLoading, error, reload } = useApiResource(loader)
  const { showNotification } = useNotifications()

  useEffect(() => {
    if (data) {
      setInstructions(data.paymentQrConfig.instructions)
    }
  }, [data])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setSearchFilter(searchInput.trim())
    }, 400)

    return () => window.clearTimeout(timeoutId)
  }, [searchInput])

  const handleQrFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setQrFile(event.target.files?.[0] || null)
    setSubmitError(null)
  }

  const handleSubmitQrConfig = async (event: FormEvent) => {
    event.preventDefault()
    if (!qrFile) {
      setSubmitError('Debes seleccionar una imagen QR para actualizar la configuracion de pago.')
      return
    }

    setIsSubmitting(true)
    setSubmitError(null)
    try {
      const response = await updateAdminPaymentQrConfig(qrFile, instructions)
      showNotification({
        title: 'QR actualizado',
        message: response.detail,
        tone: 'success',
      })
      setQrFile(null)
      reload()
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

  const getPaymentNote = (paymentId: number, fallbackNote?: string) =>
    paymentNotes[paymentId] ?? fallbackNote ?? ''

  const handlePaymentNoteChange = (paymentId: number, note: string) => {
    setPaymentNotes((current) => ({
      ...current,
      [paymentId]: note,
    }))
  }

  const handlePaymentStatusUpdate = async (
    paymentId: number,
    status: UpdateAdminPaymentStatusPayload['status'],
    fallbackNote?: string,
  ) => {
    setPaymentActionId(paymentId)
    try {
      const note = status === 'PENDIENTE' ? '' : getPaymentNote(paymentId, fallbackNote)
      const response = await updateAdminPaymentStatus(paymentId, {
        status,
        note,
      })
      showNotification({
        title: 'Pago actualizado',
        message: response.detail,
        tone:
          status === 'APROBADO'
            ? 'success'
            : status === 'RECHAZADO' || status === 'CANCELADO'
              ? 'warning'
              : 'info',
      })
      setPaymentNotes((current) => ({
        ...current,
        [paymentId]: response.payment.note || '',
      }))
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo actualizar el pago',
        message:
          requestError instanceof Error
            ? requestError.message
            : 'Ocurrio un error al cambiar el estado del pago.',
        tone: 'danger',
      })
    } finally {
      setPaymentActionId(null)
    }
  }

  const filteredPayments = (data?.payments ?? []).filter((payment) => {
    if (statusFilter) {
      const statusMap: Record<'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO', string> = {
        PENDIENTE: 'pendiente',
        APROBADO: 'aprobado',
        RECHAZADO: 'observado',
        CANCELADO: 'cancelado',
      }
      if (statusMap[statusFilter] !== payment.status) return false
    }

    if (searchFilter) {
      const term = searchFilter.toLowerCase()
      const haystack = `${payment.patient} ${payment.operation}`.toLowerCase()
      if (!haystack.includes(term)) return false
    }

    const dueDate = toComparableDate(payment.dueDate)
    if (dateFromFilter) {
      const from = new Date(`${dateFromFilter}T00:00:00`)
      if (dueDate && dueDate < from) return false
    }
    if (dateToFilter) {
      const to = new Date(`${dateToFilter}T23:59:59`)
      if (dueDate && dueDate > to) return false
    }
    return true
  })

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
            <div className="form-grid" style={{ marginBottom: 16 }}>
              <label className="field">
                <span>Estado</span>
                <select className="input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as AdminPaymentsFilters['status'])}>
                  <option value="">Todos</option>
                  <option value="PENDIENTE">Pendiente</option>
                  <option value="APROBADO">Aprobado</option>
                  <option value="RECHAZADO">Observado</option>
                  <option value="CANCELADO">Cancelado</option>
                </select>
              </label>
              <label className="field">
                <span>Desde</span>
                <input className="input" type="date" value={dateFromFilter} onChange={(event) => setDateFromFilter(event.target.value)} />
              </label>
              <label className="field">
                <span>Hasta</span>
                <input className="input" type="date" value={dateToFilter} onChange={(event) => setDateToFilter(event.target.value)} />
              </label>
              <label className="field field--full">
                <span>Buscar paciente/procedimiento</span>
                <input className="input" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} />
              </label>
            </div>
            {filteredPayments.length ? (
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
                      <th>Comprobante / nota</th>
                      <th>Verificador</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPayments.map((payment) => (
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
                                : payment.status === 'observado' || payment.status === 'cancelado'
                                  ? 'observed'
                                  : 'pending'
                            }
                          >
                            {payment.status}
                          </StatusBadge>
                        </td>
                        <td>
                          <div className="table-cell-stack">
                            {payment.receiptUrl ? (
                              <a
                                className="button button--ghost button--compact"
                                href={payment.receiptUrl}
                                rel="noreferrer"
                                target="_blank"
                              >
                                Ver comprobante
                              </a>
                            ) : (
                              <span className="table-muted">Sin comprobante</span>
                            )}
                            <textarea
                              className="input textarea textarea--compact"
                              placeholder="Nota para aprobacion u observacion"
                              rows={3}
                              value={getPaymentNote(payment.rawId, payment.note)}
                              onChange={(event) =>
                                handlePaymentNoteChange(payment.rawId, event.target.value)
                              }
                            />
                          </div>
                        </td>
                        <td>{payment.verifier}</td>
                        <td>
                          <div className="table-actions">
                            <button
                              className="button button--success button--compact"
                              disabled={
                                paymentActionId === payment.rawId || payment.status === 'aprobado'
                              }
                              type="button"
                              onClick={() =>
                                handlePaymentStatusUpdate(
                                  payment.rawId,
                                  'APROBADO',
                                  payment.note,
                                )
                              }
                            >
                              Aprobar
                            </button>
                            <button
                              className="button button--warning button--compact"
                              disabled={
                                paymentActionId === payment.rawId || payment.status === 'observado'
                              }
                              type="button"
                              onClick={() =>
                                handlePaymentStatusUpdate(
                                  payment.rawId,
                                  'RECHAZADO',
                                  payment.note,
                                )
                              }
                            >
                              Observar
                            </button>
                            <button
                              className="button button--warning button--compact"
                              disabled={
                                paymentActionId === payment.rawId || payment.status === 'cancelado'
                              }
                              type="button"
                              onClick={() =>
                                handlePaymentStatusUpdate(
                                  payment.rawId,
                                  'CANCELADO',
                                  payment.note,
                                )
                              }
                            >
                              Cancelar
                            </button>
                            <button
                              className="button button--ghost button--compact"
                              disabled={
                                paymentActionId === payment.rawId || payment.status === 'pendiente'
                              }
                              type="button"
                              onClick={() =>
                                handlePaymentStatusUpdate(
                                  payment.rawId,
                                  'PENDIENTE',
                                  payment.note,
                                )
                              }
                            >
                              Pendiente
                            </button>
                          </div>
                        </td>
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
