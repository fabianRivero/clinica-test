import type { OperationClosurePreconditionsReport } from '../../../types/admin'

/**
 * Pure helper that derives the same precondition shape the backend
 * would return from a GET on the operation detail. The frontend mirrors
 * it client-side so the "Finalizar" button can be disabled (and the
 * confirmation modal populated) without a follow-up round-trip.
 *
 * IMPORTANT: keep this in sync with ``Operacion.puede_cerrar`` on the
 * backend (``backend/operations/models.py``). If the two drift, the
 * server remains authoritative — see ``OperationClosureActions`` in
 * ``AdminOperationDetailPage.tsx`` for the 409 re-render path.
 */
export type OperationSesionRow = {
  status: string
}

export type OperationCuotaRow = {
  number: number
  status: string
  amountValue?: string
}

export type OperationClosureDeriveInput = {
  sesionesTotales: number
  appointments: OperationSesionRow[]
  quotas: OperationCuotaRow[]
  /**
   * Decimal-strings coming from the backend `_operation_item`
   * helper (e.g. ``"Bs 1,200.00"`` or ``"1200.00"``). The helper
   * normalises them so the comparison is currency-precise.
   */
  precioTotalLabel: string
}

const _TWO_PLACES = (value: string | number): string => {
  if (typeof value !== 'string') return Number(value).toFixed(2)
  // Strip "Bs", currency symbols, and thousands separators, keep dot.
  const cleaned = value.replace(/[^0-9.-]/g, '')
  const num = Number(cleaned)
  return Number.isFinite(num) ? num.toFixed(2) : '0.00'
}

const _toFixed = (n: number): string => {
  if (!Number.isFinite(n)) return '0.00'
  return n.toFixed(2)
}

const _diff = (a: string, b: string): string => {
  const aa = Number(a)
  const bb = Number(b)
  if (!Number.isFinite(aa) || !Number.isFinite(bb)) return '0.00'
  return (aa - bb).toFixed(2)
}

export function deriveOperationClosurePreconditions(
  input: OperationClosureDeriveInput,
): OperationClosurePreconditionsReport {
  const sesionesTotales = Math.max(
    0,
    Math.floor(Number(input.sesionesTotales) || 0),
  )

  let confirmed = 0
  let reserved = 0
  let pending = 0
  for (const apt of input.appointments) {
    const s = (apt.status ?? '').toLowerCase()
    if (s === 'confirmada') confirmed++
    else if (s === 'programada') reserved++
    else if (s.includes('realizada pendiente')) pending++
  }
  // Only CONFIRMADA counts as a realized session. PROGRAMADA and
  // REALIZADA_PENDIENTE_VERIFICACION both BLOCK closure (the former
  // is just a reservation, the latter is awaiting client approval in
  // /tablet). ``reserved`` and ``pending`` stay in the report as
  // diagnostic counts so the modal can show what's pending.
  const consumed = confirmed
  const missing = Math.max(sesionesTotales - consumed, 0)
  const sesionesOk = missing === 0 && sesionesTotales > 0

  const cuotasPending = (input.quotas || [])
    .filter((quota) => {
      const s = (quota.status ?? '').toLowerCase()
      return s !== 'pagado' && s !== 'no pagada'
    })
    .map((quota) => ({ nroCuota: quota.number, estado: quota.status }))
  const cuotasOk = cuotasPending.length === 0

  const precioTotal = _TWO_PLACES(input.precioTotalLabel)
  let suma = 0
  for (const quota of input.quotas || []) {
    suma += Number(quota.amountValue) || 0
  }
  const sumaMonto = _toFixed(suma)
  const diff = _diff(precioTotal, sumaMonto)
  const montoOk = diff === '0.00'

  return {
    ok: sesionesOk && cuotasOk && montoOk,
    sesiones: {
      ok: sesionesOk,
      expected: sesionesTotales,
      confirmed,
      reserved,
      pending,
      missing,
    },
    cuotas: {
      ok: cuotasOk,
      pending: cuotasPending,
    },
    monto: {
      ok: montoOk,
      precioTotal,
      sumaMontoProgramado: sumaMonto,
      diff,
    },
  }
}

interface OperationClosureConfirmModalProps {
  open: boolean
  mode: 'finalizar' | 'suspender'
  /**
   * Pre-populated by the page on open. Replaced wholesale with the
   * server's structured 409 payload if the request fails — server is
   * always authoritative.
   */
  report: OperationClosurePreconditionsReport
  operationLabel: string
  /** Source-state error from the server (409 without preconditions). */
  sourceStateError?: string | null
  isSubmitting: boolean
  onClose: () => void
  onConfirm: () => void
}

/**
 * Confirmation modal for the manual closure flow on the operation
 * detail page. Lists each precondition with pass/fail chips so the
 * admin sees exactly what would block finalize before clicking.
 *
 * Mode semantics:
 *   - ``finalizar``: "Confirmar" disabled while ``report.ok === false``.
 *   - ``suspender``: preconditions are irrelevant; "Confirmar" always
 *     enabled (the admin explicitly chose to suspend).
 */
export function OperationClosureConfirmModal({
  open,
  mode,
  report,
  operationLabel,
  sourceStateError,
  isSubmitting,
  onClose,
  onConfirm,
}: OperationClosureConfirmModalProps) {
  if (!open) return null

  const title = mode === 'finalizar' ? 'Finalizar operacion' : 'Suspender operacion'
  const confirmLabel =
    mode === 'finalizar' ? 'Finalizar operacion' : 'Suspender operacion'
  const intro =
    mode === 'finalizar'
      ? `Confirma el cierre definitivo del tratamiento "${operationLabel}". Esta accion no se puede deshacer.`
      : `Vas a suspender el tratamiento "${operationLabel}". El sistema bloquea nuevas reservas y cuotas; las existentes se conservan.`

  const sesionesTone = report.sesiones.ok ? 'success' : 'warning'
  // Prefer the most actionable reason first: missing > reserved > pending.
  const sesionesLabel = report.sesiones.ok
    ? 'Sesiones realizadas'
    : report.sesiones.missing > 0
      ? `Faltan ${report.sesiones.missing} sesion(es) por realizar`
      : report.sesiones.reserved > 0
        ? `${report.sesiones.reserved} cita(s) reservada(s) pendiente(s)`
        : `${report.sesiones.pending} cita(s) esperando aprobacion del cliente`

  const cuotasTone = report.cuotas.ok ? 'success' : 'warning'
  const cuotasLabel = report.cuotas.ok
    ? 'Plan de pagos cerrado'
    : `${report.cuotas.pending.length} cuota(s) pendiente(s)`

  const montoTone = report.monto.ok ? 'success' : 'warning'
  const montoLabel = report.monto.ok
    ? 'Monto programado = precio total'
    : `Diferencia Bs ${report.monto.diff} entre precio y monto programado`

  const confirmDisabled = mode === 'finalizar' ? !report.ok || isSubmitting : isSubmitting

  return (
    <div
      className="booking-modal-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={title}
      data-testid="operation-closure-confirm-modal"
    >
      <div
        className="booking-modal-content _max-w-modal-md"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="booking-modal-header">
          <h2>{title}</h2>
          <button type="button" className="booking-modal-close" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="booking-modal-body _p-modal">
          <p className="_mb-md">{intro}</p>

          {sourceStateError ? (
            <div
              className="_panel-card"
              style={{
                border: '1px solid rgba(220, 53, 69, 0.45)',
                background: 'rgba(220, 53, 69, 0.08)',
                marginBottom: '1rem',
              }}
              data-testid="operation-closure-source-error"
            >
              <strong>No se puede cerrar la operacion:</strong> {sourceStateError}
            </div>
          ) : null}

          {mode === 'finalizar' ? (
            <ul className="_list-reset" style={{ display: 'grid', gap: '0.5rem' }}>
              <li className="_panel-card">
                <strong>Sesiones:</strong>{' '}
                <span className={`status-badge status-badge--${sesionesTone}`} data-testid="precondition-sesiones">
                  {sesionesLabel}
                </span>
                <small className="field__hint _mt-xs _block">
                  Confirmadas: {report.sesiones.confirmed} · Reservadas: {report.sesiones.reserved} ·
                  Pendientes de verificacion: {report.sesiones.pending} · Esperadas: {report.sesiones.expected}
                </small>
              </li>
              <li className="_panel-card">
                <strong>Cuotas:</strong>{' '}
                <span className={`status-badge status-badge--${cuotasTone}`} data-testid="precondition-cuotas">
                  {cuotasLabel}
                </span>
                {!report.cuotas.ok ? (
                  <ul className="field__hint _mt-xs">
                    {report.cuotas.pending.map((c) => (
                      <li key={`pending-${c.nroCuota}`}>
                        Cuota #{c.nroCuota}: {c.estado}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
              <li className="_panel-card">
                <strong>Monto:</strong>{' '}
                <span className={`status-badge status-badge--${montoTone}`} data-testid="precondition-monto">
                  {montoLabel}
                </span>
                <small className="field__hint _mt-xs _block">
                  Precio total: Bs {report.monto.precioTotal} · Suma programada: Bs{' '}
                  {report.monto.sumaMontoProgramado}
                </small>
              </li>
            </ul>
          ) : (
            <div className="_panel-card">
              <strong>Vas a suspender el tratamiento.</strong>
              <p className="field__hint _mt-sm _mb-0">
                Esta accion no exige precondiciones pero deja la operacion en estado
                terminal. Las citas y cuotas existentes se conservan.
              </p>
            </div>
          )}
        </div>
        <footer
          className="booking-modal-footer"
          style={{ padding: '1rem 1.5rem 1.5rem', display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}
        >
          <button
            type="button"
            className="button button--ghost"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancelar
          </button>
          <button
            type="button"
            className={mode === 'finalizar' ? 'button button--primary' : 'button button--danger'}
            onClick={onConfirm}
            disabled={confirmDisabled}
            data-testid="operation-closure-confirm-button"
          >
            {isSubmitting ? 'Procesando...' : confirmLabel}
          </button>
        </footer>
      </div>
    </div>
  )
}
