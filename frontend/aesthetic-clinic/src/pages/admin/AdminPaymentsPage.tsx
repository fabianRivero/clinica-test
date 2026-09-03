import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { AdminPaymentsTabs } from '../../components/admin/AdminPaymentsTabs'

import { DataState } from '../../components/admin/DataState'
import {
  MultiFieldSearch,
  type MultiFieldSearchField,
} from '../../components/admin/MultiFieldSearch'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import { useBranchContext } from '../../providers/BranchProvider'
import {
  type AdminPaymentsFilters,
  getAdminPayments,
  registerAdminPayment,
  updateAdminPaymentQrConfig,
  updateAdminPaymentStatus,
} from '../../services/api/admin'
import type {
  AdminPaymentQuota,
  RegisterAdminPaymentPayload,
  UpdateAdminPaymentStatusPayload,
} from '../../types/admin'
import {
  matchesFieldFilters,
  type FieldDef,
  type FieldFilters,
} from '../../utils/matchesFieldFilters'
import { formatPaymentBreakdown } from '../../utils/payments'
import { monthNames } from './expenses/expenseUtils'
import { AdminRegisterPaymentModal } from '../../components/admin/AdminRegisterPaymentModal'

export function AdminPaymentsPage({ view }: { view: 'qr' | 'pendientes' | 'cuotas' }) {
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  const now = new Date()
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [year, setYear] = useState(now.getFullYear())
  const [instructions, setInstructions] = useState('')
  const [qrFile, setQrFile] = useState<File | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [paymentNotes, setPaymentNotes] = useState<Record<number, string>>({})
  const [paymentActionId, setPaymentActionId] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState<AdminPaymentsFilters['status']>('')
  const [searchPatient, setSearchPatient] = useState('')
  const [searchOperation, setSearchOperation] = useState('')
  const [searchCodigo, setSearchCodigo] = useState('')
  const [searchId, setSearchId] = useState('')
  const [searchAmount, setSearchAmount] = useState('')
  const [quotaStatusFilter, setQuotaStatusFilter] = useState('')
  const [qrModalOpen, setQrModalOpen] = useState(false)
  const [qrModalImageUrl, setQrModalImageUrl] = useState('')
  const [showMonthPicker, setShowMonthPicker] = useState(false)
  const [pickerMonth, setPickerMonth] = useState(month)
  const [pickerYear, setPickerYear] = useState(year)
  const [registerQuota, setRegisterQuota] = useState<AdminPaymentQuota | null>(null)
  const [isRegistering, setIsRegistering] = useState(false)
  const [registerError, setRegisterError] = useState<string | null>(null)
  const viewedMonthLabel = `${monthNames[month - 1]} ${year}`
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const loader = useCallback(
    () => getAdminPayments(month, year),
    [month, year, branchId],
  )
  const { data, isLoading, error, reload } = useApiResource(loader)
  const { showNotification } = useNotifications()

  const openMonthPicker = () => {
    setPickerMonth(month)
    setPickerYear(year)
    setShowMonthPicker(true)
  }

  const applyMonthPicker = () => {
    setMonth(pickerMonth)
    setYear(pickerYear)
    setShowMonthPicker(false)
  }

  const changeMonth = (direction: -1 | 1) => {
    const currentMonth = month
    const currentYear = year
    let nextMonth = currentMonth + direction
    let nextYear = currentYear
    if (nextMonth < 1) {
      nextMonth = 12
      nextYear = currentYear - 1
    } else if (nextMonth > 12) {
      nextMonth = 1
      nextYear = currentYear + 1
    }
    setYear(nextYear)
    setMonth(nextMonth)
  }

  useEffect(() => {
    if (data) {
      setInstructions(data.paymentQrConfig.instructions)
    }
  }, [data])

  const searchFields: ReadonlyArray<MultiFieldSearchField> = [
    { key: 'patient', label: 'Paciente', placeholder: 'Ej. María López' },
    { key: 'operation', label: 'Operación', placeholder: 'Procedimiento' },
    { key: 'codigo', label: 'Código', placeholder: 'CLI-XXXXXX' },
    { key: 'id', label: 'ID', placeholder: 'PAY-0042 / 0042' },
    { key: 'amount', label: 'Monto', placeholder: 'Bs 150.00' },
  ]

  const searchValues: FieldFilters = {
    patient: searchPatient,
    operation: searchOperation,
    codigo: searchCodigo,
    id: searchId,
    amount: searchAmount,
  }

  const searchFieldsByKey: Record<string, FieldDef> = {
    patient: { key: 'patient', type: 'tokenized' },
    operation: { key: 'operation', type: 'tokenized' },
    codigo: { key: 'clienteCodigo', type: 'includes' },
    id: { key: 'id', type: 'includes' },
    amount: { key: 'amount', type: 'includes' },
  }

  function handleSearchChange(key: string, value: string) {
    if (key === 'patient') setSearchPatient(value)
    else if (key === 'operation') setSearchOperation(value)
    else if (key === 'codigo') setSearchCodigo(value)
    else if (key === 'id') setSearchId(value)
    else if (key === 'amount') setSearchAmount(value)
  }

  const handleQrFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setQrFile(event.target.files?.[0] || null)
    setSubmitError(null)
  }

  const handleSubmitQrConfig = async (event: FormEvent) => {
    event.preventDefault()
    if (!qrFile) {
      setSubmitError('Debes seleccionar una imagen QR para actualizar la configuración de pago.')
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

  const handleRegisterPayment = async (
    payload: RegisterAdminPaymentPayload,
  ) => {
    if (!registerQuota) return
    setIsRegistering(true)
    setRegisterError(null)
    try {
      const response = await registerAdminPayment(registerQuota.rawId, payload)
      showNotification({
        title: 'Pago registrado',
        message: response.detail,
        tone: 'success',
      })
      setRegisterQuota(null)
      reload()
    } catch (requestError) {
      setRegisterError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo registrar el pago.',
      )
    } finally {
      setIsRegistering(false)
    }
  }

  const closeRegisterModal = () => {
    setRegisterQuota(null)
    setRegisterError(null)
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
    return matchesFieldFilters(
      payment as unknown as Record<string, unknown>,
      searchValues,
      searchFieldsByKey,
    )
  })

  const filteredQuotas = (data?.quotas ?? []).filter((quota) => {
    if (quotaStatusFilter) {
      const normalizedStatus = quota.status.trim().toLowerCase()
      const statusTokenMap: Record<string, string[]> = {
        PENDIENTE: ['pendiente'],
        VENCIDA: ['vencida'],
        PAGADO: ['pagado'],
        NO_PAGADA: ['no pagada'],
        OBSERVADO: ['observado', 'rechazado'],
        CANCELADO: ['cancelado'],
      }
      if (!statusTokenMap[quotaStatusFilter]?.some((token) => normalizedStatus.includes(token))) return false
    }

    return matchesFieldFilters(
      quota as unknown as Record<string, unknown>,
      searchValues,
      searchFieldsByKey,
    )
  })

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Tesoreria"
        title="Pagos y verificaciones"
        description="Módulo para revisar comprobantes cargados por clientes y controlar cuotas aprobadas, observadas o pendientes."
      />

      <AdminPaymentsTabs />

      {isLoading && !data ? (
        <SectionCard title="Cargando pagos">
          <DataState
            title="Sincronizando tesoreria"
            message="Cargando pagos, montos, cuotas y verificación administrativa."
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
          {view === 'qr' ? (
          <SectionCard
            eyebrow="Pago por QR"
            title="Configuración del QR bancario"
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
                    onClick={() => {
                      setQrModalImageUrl(data.paymentQrConfig.qrImageUrl)
                      setQrModalOpen(true)
                    }}
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
          ) : null}

          {view === 'pendientes' ? (
          <SectionCard
            eyebrow="Comprobantes"
            title="Cola de verificación"
            description="Los estados replican el flujo real del negocio: pendiente, observado y aprobado."
            action={
              <div className="expense-period-controls">
                <button className="button button--ghost" type="button" onClick={() => changeMonth(-1)}>←</button>
                <div style={{ cursor: 'pointer' }} onClick={openMonthPicker}>
                  <span className="eyebrow">Mes seleccionado</span>
                  <h3 style={{ cursor: 'pointer' }}>{viewedMonthLabel}</h3>
                </div>
                <button className="button button--ghost" type="button" onClick={() => changeMonth(1)}>→</button>
              </div>
            }
          >
            <div className="_mb-md">
              <MultiFieldSearch
                fields={searchFields}
                values={searchValues}
                onChange={handleSearchChange}
              />
            </div>
            <div className="form-grid _mb-md">
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
            </div>
            {filteredPayments.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Paciente</th>
                      <th>Operación</th>
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
                            <strong>
                              <Link className="table-strong-link" to={`/cms/clientes/${payment.clientId}`}>
                                {payment.patient}
                              </Link>
                            </strong>
                            <span>{payment.submittedAt}</span>
                          </td>
                        <td>{payment.operation}</td>
                        <td>{payment.quota}</td>
<td>
                            {payment.amount}
                            {(() => {
                              const breakdown = formatPaymentBreakdown(payment)
                              return breakdown ? <small className="field__hint">{breakdown}</small> : null
                            })()}
                          </td>
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
                              placeholder="Nota para aprobación u observación"
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
          ) : null}

          {view === 'cuotas' ? (
            <SectionCard
              eyebrow="Plan de pagos"
              title={`Cuotas de ${viewedMonthLabel}`}
              description="Vista consolidada de cuotas pagadas, pendientes, vencidas, observadas o canceladas."
              action={
                <div className="expense-period-controls">
                  <button className="button button--ghost" type="button" onClick={() => changeMonth(-1)}>←</button>
                  <div style={{ cursor: 'pointer' }} onClick={openMonthPicker}>
                    <span className="eyebrow">Mes seleccionado</span>
                    <h3 style={{ cursor: 'pointer' }}>{viewedMonthLabel}</h3>
                  </div>
                  <button className="button button--ghost" type="button" onClick={() => changeMonth(1)}>→</button>
                </div>
              }
            >
              <div className="_mb-md">
                <MultiFieldSearch
                  fields={searchFields}
                  values={searchValues}
                  onChange={handleSearchChange}
                />
              </div>
              <div className="form-grid _mb-md">
                <label className="field">
                  <span>Estado</span>
                  <select className="input" value={quotaStatusFilter} onChange={(event) => setQuotaStatusFilter(event.target.value)}>
                    <option value="">Todos</option>
                    <option value="PENDIENTE">Pendiente</option>
                    <option value="VENCIDA">Vencida</option>
                    <option value="PAGADO">Pagado</option>
                    <option value="NO_PAGADA">No pagada</option>
                    <option value="OBSERVADO">Observado</option>
                    <option value="CANCELADO">Cancelado</option>
                  </select>
                </label>
              </div>
              {filteredQuotas.length ? (
                <div className="table-card">
                  <table>
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Paciente</th>
                        <th>Operación</th>
                        <th>Cuota</th>
                        <th>Monto programado</th>
                        <th>Vencimiento</th>
                        <th>Estado</th>
                        <th>Pagos registrados</th>
                        <th>Acciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredQuotas.map((quota) => (
                        <tr key={quota.id}>
                          <td>{quota.id}</td>
                          <td>
                            <Link className="table-strong-link" to={`/cms/clientes/${quota.clientId}`}>
                              {quota.patient}
                            </Link>
                          </td>
                          <td>{quota.operation}</td>
                          <td>{quota.quotaNumber}</td>
                          <td>{quota.amount}</td>
                          <td>{quota.dueDate}</td>
                          <td>
                            <StatusBadge
                              tone={
                                quota.status === 'Pagado'
                                  ? 'approved'
                                  : quota.status === 'Observado' || quota.status === 'Cancelado'
                                    ? 'observed'
                                    : 'pending'
                              }
                            >
                              {quota.status}
                            </StatusBadge>
                          </td>
                          <td>{quota.paymentsCount}</td>
                          <td>
                            <button
                              className="button button--ghost button--compact"
                              type="button"
                              onClick={() => {
                                setRegisterError(null)
                                setRegisterQuota(quota)
                              }}
                            >
                              Registrar pago
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <DataState title="Sin cuotas registradas" message="No hay cuotas en el backend conectado." />
              )}
            </SectionCard>
          ) : null}
        {qrModalOpen ? (
          <div className="qr-modal" role="dialog" aria-modal="true" aria-label="Vista previa del QR">
            <div className="qr-modal__backdrop" onClick={() => setQrModalOpen(false)} />
            <div className="qr-modal__content">
              <header className="qr-modal__header">
                <div>
                  <span>QR activo</span>
                  <strong>Vista previa ampliada</strong>
                </div>
                <button
                  className="button button--ghost button--compact"
                  type="button"
                  onClick={() => setQrModalOpen(false)}
                >
                  ×
                </button>
              </header>
              <img
                alt="QR de pago activo ampliado"
                className="qr-modal__image"
                src={qrModalImageUrl}
              />
            </div>
          </div>
        ) : null}

        {showMonthPicker ? (
          <div className="qr-modal" role="dialog" aria-modal="true" aria-label="Seleccionar mes">
            <div className="qr-modal__backdrop" onClick={() => setShowMonthPicker(false)} />
            <div className="qr-modal__content">
              <header className="qr-modal__header">
                <div>
                  <span>Seleccionar periodo</span>
                  <strong>Elige el mes y año</strong>
                </div>
                <button
                  className="button button--ghost button--compact"
                  type="button"
                  onClick={() => setShowMonthPicker(false)}
                >
                  Cerrar
                </button>
              </header>
              <div className="form-grid" style={{ marginTop: '1rem' }}>
                <label className="field">
                  <span>Mes</span>
                  <select
                    className="input"
                    value={pickerMonth}
                    onChange={(e) => setPickerMonth(parseInt(e.target.value))}
                  >
                    {monthNames.map((name, index) => (
                      <option key={name} value={index + 1}>{name}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Año</span>
                  <select
                    className="input"
                    value={pickerYear}
                    onChange={(e) => setPickerYear(parseInt(e.target.value))}
                  >
                    {[2024, 2025, 2026, 2027, 2028, 2029, 2030].map((y) => (
                      <option key={y} value={y}>{y}</option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="form-actions" style={{ marginTop: '1rem' }}>
                <button
                  className="button button--ghost"
                  type="button"
                  onClick={() => setShowMonthPicker(false)}
                >
                  Cancelar
                </button>
                <button
                  className="button"
                  type="button"
                  onClick={applyMonthPicker}
                >
                  Aplicar
                </button>
              </div>
            </div>
          </div>
        ) : null}

        <AdminRegisterPaymentModal
          quota={registerQuota}
          isOpen={registerQuota !== null}
          isSubmitting={isRegistering}
          errorMessage={registerError}
          onClose={closeRegisterModal}
          onSubmit={handleRegisterPayment}
        />
        </>
      ) : null}
    </div>
  )
}
