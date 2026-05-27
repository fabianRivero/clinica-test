import type { ExpenseItem, UpsertAdminExpensePayload } from '../../../types/admin'

export type ExpenseTab = 'create' | 'list'

export const monthNames = [
  'Enero',
  'Febrero',
  'Marzo',
  'Abril',
  'Mayo',
  'Junio',
  'Julio',
  'Agosto',
  'Septiembre',
  'Octubre',
  'Noviembre',
  'Diciembre',
]

export function decimalProduct(left: string, right: string) {
  const a = Number(left || 0)
  const b = Number(right || 0)
  if (!Number.isFinite(a) || !Number.isFinite(b)) return '0.00'
  return (a * b).toFixed(2)
}

export function formatMoney(value: number) {
  return `Bs ${value.toFixed(2)}`
}

export function expenseToForm(expense: ExpenseItem): UpsertAdminExpensePayload {
  return {
    date: expense.date,
    categoryId: expense.categoryId,
    concept: expense.concept,
    units: expense.units,
    unitCost: expense.unitCost,
    total: expense.total,
    provider: expense.provider,
    details: expense.details,
    invoice: null,
  }
}

export const emptyForm: UpsertAdminExpensePayload = {
  date: new Date().toISOString().slice(0, 10),
  categoryId: '',
  concept: '',
  units: '1',
  unitCost: '0',
  total: '0',
  provider: '',
  details: '',
  invoice: null,
}