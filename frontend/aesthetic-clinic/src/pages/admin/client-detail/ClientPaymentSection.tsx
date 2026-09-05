import { useMemo, useState } from 'react'

import { StatusBadge } from '../../../components/admin/StatusBadge'
import { DataState } from '../../../components/admin/DataState'
import { SectionCard } from '../../../components/admin/SectionCard'
import { AdminRegisterPaymentModal } from '../../../components/admin/AdminRegisterPaymentModal'
import { useNotifications } from '../../../providers/NotificationProvider'
import { registerAdminPayment } from '../../../services/api/admin'
import type {
  AdminPaymentQuota,
  RegisterAdminPaymentPayload,
} from '../../../types/admin'

const PAGE_SIZE = 5

const PAYMENT_STATUS_FILTER_OPTIONS = [
  { value: '', label: 'Todos los estados' },
  { value: 'PENDIENTE', label: 'Pendiente' },
  { value: 'APROBADO', label: 'Aprobado' },
  { value: 'RECHAZADO', label: 'Observado' },
  { value: 'CANCELADO', label: 'Cancelado' },
]

interface ClientPaymentSectionProps {
  clientId: number
  clientName: string
  pendingQuotas: any[]
  payments: any[]
  paymentActionId: number | null
  getPaymentNote: (paymentId: number, fallbackNote?: string) => string
  onPaymentNoteChange: (paymentId: number, note: string) => void
  onUpdatePaymentStatus: (paymentId: number, currentStatus: string, status: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO', fallbackNote?: string) => void
  onPaymentRegistered: () => void
  pendingQuotaProcedureFilter: string
  pendingQuotaProcedures: string[]
  filteredPendingQuotas: any[]
  onPendingQuotaFilterChange: (value: string) => void

  // Pagination props
  visiblePayments: any[]
  visiblePaymentsCount: number
  setVisiblePaymentsCount: (count: number | ((prev: number) => number)) => void
  hasMorePayments: boolean
  hasLessPayments: boolean

  visiblePendingQuotasCount: number
  setVisiblePendingQuotasCount: (count: number | ((prev: number) => number)) => void
  hasMorePendingQuotas: boolean
  hasLessPendingQuotas: boolean
}

interface PaymentRowProps {
  payment: any
  paymentActionId: number | null
  getPaymentNote: (paymentId: number, fallbackNote?: string) => string
  onPaymentNoteChange: (paymentId: number, note: string) => void
  onUpdatePaymentStatus: (paymentId: number, currentStatus: string, status: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO', fallbackNote?: string) => void
  /** When true, the row shows Aprobar / Observar / Cancelar / Pendiente.
   *  When false (APROBADO rows), only the read-only observation input
   *  and the status badge are shown. */
  showActions: boolean
}

function PaymentRow({
  payment,
  paymentActionId,
  getPaymentNote,
  onPaymentNoteChange,
  onUpdatePaymentStatus,
  showActions,
}: PaymentRowProps) {
  const normalizedStatus = payment.status.trim().toUpperCase()
  return (
    <tr key={payment.id}>
      <td>{payment.operation}</td>
      <td>{payment.quotaLabel}</td>
      <td>{payment.amount}</td>
      <td>{payment.submittedAt}</td>
      <td><StatusBadge tone={payment.statusTone}>{payment.status}</StatusBadge></td>
      <td>
        {payment.receiptUrl
          ? <a className="table-strong-link" href={payment.receiptUrl} target="_blank" rel="noreferrer">Ver</a>
          : 'Sin archivo'}
      </td>
      <td>
        <input
          className="input"
          value={getPaymentNote(payment.rawId, payment.note)}
          onChange={(event) => onPaymentNoteChange(payment.rawId, event.target.value)}
          placeholder="Nota para aprobación u observación"
        />
      </td>
      <td>
        {showActions ? (
          <div className="table-action-list">
            <button
              className="button button--ghost button--compact"
              disabled={paymentActionId === payment.rawId || normalizedStatus === 'APROBADO'}
              type="button"
              onClick={() => void onUpdatePaymentStatus(payment.rawId, payment.status, 'APROBADO', payment.note)}
            >
              Aprobar
            </button>
            <button
              className="button button--ghost button--compact"
              disabled={paymentActionId === payment.rawId || normalizedStatus === 'RECHAZADO'}
              type="button"
              onClick={() => void onUpdatePaymentStatus(payment.rawId, payment.status, 'RECHAZADO', payment.note)}
            >
              Observar
            </button>
            <button
              className="button button--ghost button--compact"
              disabled={paymentActionId === payment.rawId || normalizedStatus === 'CANCELADO'}
              type="button"
              onClick={() => void onUpdatePaymentStatus(payment.rawId, payment.status, 'CANCELADO', payment.note)}
            >
              Cancelar
            </button>
            <button
              className="button button--ghost button--compact"
              disabled={paymentActionId === payment.rawId || normalizedStatus === 'PENDIENTE'}
              type="button"
              onClick={() => void onUpdatePaymentStatus(payment.rawId, payment.status, 'PENDIENTE', payment.note)}
            >
              Pendiente
            </button>
          </div>
        ) : (
          <span className="admin-client-payment__final">
            Verificado por {payment.verifier || 'administración'}
          </span>
        )}
      </td>
    </tr>
  )
}

interface PaymentListCardProps {
  title: string
  description: string
  emptyTitle: string
  emptyMessage: string
  rows: any[]
  showActions: boolean
  paymentActionId: number | null
  getPaymentNote: (paymentId: number, fallbackNote?: string) => string
  onPaymentNoteChange: (paymentId: number, note: string) => void
  onUpdatePaymentStatus: (
    paymentId: number,
    currentStatus: string,
    status: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO',
    fallbackNote?: string,
  ) => void
}

function PaymentListCard({
  title,
  description,
  emptyTitle,
  emptyMessage,
  rows,
  showActions,
  paymentActionId,
  getPaymentNote,
  onPaymentNoteChange,
  onUpdatePaymentStatus,
}: PaymentListCardProps) {
  const [procedureFilter, setProcedureFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)

  const procedures = useMemo(
    () => Array.from(new Set(rows.map((row) => row.operation))).sort(),
    [rows],
  )

  const filtered = useMemo(() => {
    return rows.filter((row) => {
      if (procedureFilter && row.operation !== procedureFilter) return false
      if (statusFilter && row.status.trim().toUpperCase() !== statusFilter) return false
      const iso = row.createdAt ? String(row.createdAt) : ''
      const isoDate = iso.slice(0, 10)
      if (dateFrom && isoDate && isoDate < dateFrom) return false
      if (dateTo && isoDate && isoDate > dateTo) return false
      return true
    })
  }, [rows, procedureFilter, statusFilter, dateFrom, dateTo])

  const visible = filtered.slice(0, visibleCount)
  const hasMore = visibleCount < filtered.length
  const hasLess = visibleCount > PAGE_SIZE

  return (
    <SectionCard eyebrow="Pagos" title={title} description={description}>
      {rows.length ? (
        <>
          <div className="admin-client-payment__filters">
            <label className="field">
              <span>Procedimiento</span>
              <select
                className="input"
                value={procedureFilter}
                onChange={(event) => {
                  setProcedureFilter(event.target.value)
                  setVisibleCount(PAGE_SIZE)
                }}
              >
                <option value="">Todos los procedimientos</option>
                {procedures.map((procedure) => (
                  <option key={procedure} value={procedure}>
                    {procedure}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Estado</span>
              <select
                className="input"
                value={statusFilter}
                onChange={(event) => {
                  setStatusFilter(event.target.value)
                  setVisibleCount(PAGE_SIZE)
                }}
              >
                {PAYMENT_STATUS_FILTER_OPTIONS.map((option) => (
                  <option key={option.value || 'all'} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Desde</span>
              <input
                className="input"
                type="date"
                value={dateFrom}
                onChange={(event) => {
                  setDateFrom(event.target.value)
                  setVisibleCount(PAGE_SIZE)
                }}
              />
            </label>
            <label className="field">
              <span>Hasta</span>
              <input
                className="input"
                type="date"
                value={dateTo}
                onChange={(event) => {
                  setDateTo(event.target.value)
                  setVisibleCount(PAGE_SIZE)
                }}
              />
            </label>
          </div>

          {filtered.length ? (
            <>
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Operación</th>
                      <th>Cuota</th>
                      <th>Monto</th>
                      <th>Fecha</th>
                      <th>Estado</th>
                      <th>Comprobante</th>
                      <th>Observación</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((payment) => (
                      <PaymentRow
                        key={payment.id}
                        payment={payment}
                        paymentActionId={paymentActionId}
                        getPaymentNote={getPaymentNote}
                        onPaymentNoteChange={onPaymentNoteChange}
                        onUpdatePaymentStatus={onUpdatePaymentStatus}
                        showActions={showActions}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
              {filtered.length > PAGE_SIZE && (
                <div className="_flex-between _mt-md">
                  <span>Mostrando {Math.min(visibleCount, filtered.length)} de {filtered.length}</span>
                  <div>
                    {hasLess && (
                      <button
                        type="button"
                        className="button button--ghost"
                        onClick={() => setVisibleCount((current) => Math.max(current - PAGE_SIZE, PAGE_SIZE))}
                      >
                        Ver menos
                      </button>
                    )}
                    {hasMore && (
                      <button
                        type="button"
                        className="button button--secondary"
                        onClick={() => setVisibleCount((current) => current + PAGE_SIZE)}
                      >
                        Ver más
                      </button>
                    )}
                  </div>
                </div>
              )}
            </>
          ) : (
            <DataState
              title="Sin resultados"
              message="No hay pagos que coincidan con los filtros seleccionados."
            />
          )}
        </>
      ) : (
        <DataState title={emptyTitle} message={emptyMessage} />
      )}
    </SectionCard>
  )
}

export function ClientPaymentSection({
  clientId,
  clientName,
  pendingQuotas,
  payments,
  paymentActionId,
  getPaymentNote,
  onPaymentNoteChange,
  onUpdatePaymentStatus,
  onPaymentRegistered,
  pendingQuotaProcedureFilter,
  pendingQuotaProcedures,
  filteredPendingQuotas,
  onPendingQuotaFilterChange,

  // Pagination (kept for API compatibility — no longer used here, the
  // two payment blocks manage their own pagination internally).
 
}: ClientPaymentSectionProps) {
  // Estado del modal `AdminRegisterPaymentModal` reusado para que el
  // admin registre pagos en nombre del cliente desde "Cuotas
  // pendientes" sin tener que abrir el flujo global de pagos/cuotas.
  const [registerQuota, setRegisterQuota] = useState<AdminPaymentQuota | null>(null)
  const [isRegistering, setIsRegistering] = useState(false)
  const [registerError, setRegisterError] = useState<string | null>(null)
  const { showNotification } = useNotifications()

  const closeRegisterModal = () => {
    setRegisterQuota(null)
    setRegisterError(null)
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
      onPaymentRegistered()
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

  const openRegisterModalForQuota = (quota: any) => {
    const quotaMatch = /(\d+)/.exec(quota.quotaLabel ?? '')
    const quotaNumber = quotaMatch ? Number(quotaMatch[1]) : 0
    setRegisterError(null)
    setRegisterQuota({
      id: quota.id,
      rawId: quota.rawId,
      clientId,
      patient: clientName,
      operation: quota.operation,
      quotaNumber,
      amount: quota.amountValue ?? quota.amount,
      paidAmount: quota.paidAmountValue,
      dueDate: quota.dueDate,
      status: quota.status,
      paymentsCount: 0,
    })
  }

  // Split the payments collection by verification state. PENDIENTE /
  // RECHAZADO / CANCELADO go to the "verification" block (the admin
  // still needs to act on them or audit the rejection); APROBADO is
  // the final, read-only record.
  const verificationPayments = useMemo(
    () => payments.filter((payment) => payment.status.trim().toUpperCase() !== 'APROBADO'),
    [payments],
  )
  const completedPayments = useMemo(
    () => payments.filter((payment) => payment.status.trim().toUpperCase() === 'APROBADO'),
    [payments],
  )

  return (
    <>
      <SectionCard
        eyebrow="Pagos"
        title="Cuotas pendientes"
        description="Cuotas aun no cubiertas. Usa 'Registrar pago' para cobrar en caja."
      >
        {pendingQuotas.length ? (
          <>
            <label className="field _mb-sm">
              <span>Filtrar por procedimiento</span>
              <select className="input" value={pendingQuotaProcedureFilter} onChange={(event) => onPendingQuotaFilterChange(event.target.value)}>
                <option value="">Todos los procedimientos</option>
                {pendingQuotaProcedures.map((procedure) => (
                  <option key={procedure} value={procedure}>{procedure}</option>
                ))}
              </select>
            </label>
            {filteredPendingQuotas.length ? (
              <>
                <div className="capacity-list">
                  {filteredPendingQuotas.slice(0, PAGE_SIZE).map((quota) => (
                    <article className="capacity-item" key={quota.id}>
                      <div className="capacity-item__header">
                        <div><strong>{quota.operation} | {quota.quotaLabel}</strong><p>{quota.amount} | Vence: {quota.dueDate}</p></div>
                        <StatusBadge tone={quota.statusTone}>{quota.status}</StatusBadge>
                      </div>
                      <div className="capacity-item__actions">
                        <button
                          className="button button--ghost button--compact"
                          type="button"
                          disabled={isRegistering}
                          onClick={() => openRegisterModalForQuota(quota)}
                          aria-label={`Registrar pago de ${quota.quotaLabel}`}
                        >
                          {isRegistering && registerQuota?.rawId === quota.rawId
                            ? 'Registrando...'
                            : 'Registrar pago'}
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
                {filteredPendingQuotas.length > PAGE_SIZE && (
                  <DataState
                    title="Mostrando solo las primeras 5 cuotas"
                    message={`Hay ${filteredPendingQuotas.length - PAGE_SIZE} cuotas adicionales. Ajusta el filtro de procedimiento para acotar la lista.`}
                  />
                )}
              </>
            ) : <DataState title="Sin resultados" message="No hay cuotas pendientes para el procedimiento seleccionado." />}
          </>
        ) : <DataState title="Sin cuotas pendientes" message="Todas las cuotas tienen un pago registrado o estan pagadas." />}
      </SectionCard>

      <PaymentListCard
        title="Pagos pendientes de verificación"
        description="Pagos realizados por un cliente desde su perfil. Necesitan ser verificados antes de aprobarlos."
        emptyTitle="Sin pagos por verificar"
        emptyMessage="No hay pagos esperando revisión para este cliente."
        rows={verificationPayments}
        showActions
        paymentActionId={paymentActionId}
        getPaymentNote={getPaymentNote}
        onPaymentNoteChange={onPaymentNoteChange}
        onUpdatePaymentStatus={onUpdatePaymentStatus}
      />

      <PaymentListCard
        title="Pagos realizados"
        description="Historial de pagos aprobados. Lista de solo lectura."
        emptyTitle="Sin pagos aprobados"
        emptyMessage="El cliente aun no tiene pagos aprobados en su historial."
        rows={completedPayments}
        showActions={false}
        paymentActionId={paymentActionId}
        getPaymentNote={getPaymentNote}
        onPaymentNoteChange={onPaymentNoteChange}
        onUpdatePaymentStatus={onUpdatePaymentStatus}
      />

      <AdminRegisterPaymentModal
        quota={registerQuota}
        isOpen={registerQuota !== null}
        isSubmitting={isRegistering}
        errorMessage={registerError}
        onClose={closeRegisterModal}
        onSubmit={handleRegisterPayment}
      />
    </>
  )
}
