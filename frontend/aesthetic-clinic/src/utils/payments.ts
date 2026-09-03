/**
 * Shared helpers for payment UI components (client + admin).
 *
 * `formatPaymentBreakdown` renders the secondary "Físico: Bs X | Virtual: Bs Y"
 * line that appears in payment history tables when the payment method is not
 * `VIRTUAL`. The backend already returns pre-formatted strings in
 * `physicalAmount` / `virtualAmount`, so this is purely a presentation guard
 * (the line is empty for VIRTUAL payments).
 */

type BreakdownPayment = {
  paymentMethod?: string
  physicalAmount?: string
  virtualAmount?: string
}

/**
 * Returns the breakdown string ready to render, or `null` when the payment is
 * `VIRTUAL` (or has no method) and the row should render only the regular
 * `amount` cell.
 */
export function formatPaymentBreakdown(payment: BreakdownPayment): string | null {
  if (!payment.paymentMethod || payment.paymentMethod === 'VIRTUAL') {
    return null
  }
  const fisico = payment.physicalAmount ?? 'Bs 0.00'
  const virtual = payment.virtualAmount ?? 'Bs 0.00'
  return `Físico: ${fisico} | Virtual: ${virtual}`
}
