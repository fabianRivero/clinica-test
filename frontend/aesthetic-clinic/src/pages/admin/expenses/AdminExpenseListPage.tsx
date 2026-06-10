import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as XLSX from 'xlsx'

import { DataState } from '../../../components/admin/DataState'
import { PageHeader } from '../../../components/admin/PageHeader'
import { SectionCard } from '../../../components/admin/SectionCard'
import { useApiResource } from '../../../hooks/useApiResource'
import { useConfirmDialog } from '../../../hooks/useConfirmDialog'
import { useNotifications } from '../../../providers/NotificationProvider'
import { useBranchContext } from '../../../providers/BranchProvider'
import { deleteAdminExpense, getAdminExpenses } from '../../../services/api/admin'
import type { ExpenseItem } from '../../../types/admin'
import { formatMoney, monthNames } from './expenseUtils'

export function AdminExpenseListPage() {
  const navigate = useNavigate()
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  const now = new Date()
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [year, setYear] = useState(now.getFullYear())
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [showMonthPicker, setShowMonthPicker] = useState(false)
  const [pickerMonth, setPickerMonth] = useState(month)
  const [pickerYear, setPickerYear] = useState(year)
  const { showNotification } = useNotifications()
  const { confirm, ConfirmDialog: ConfirmDialogModal } = useConfirmDialog()

  const loader = useCallback(() => getAdminExpenses(month, year), [month, year, branchId])
  const { data, isLoading, error, reload } = useApiResource(loader)
  const viewedMonthLabel = `${monthNames[month - 1]} ${year}`

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

  const exportToExcel = useCallback(() => {
    if (!data) return
    const sheetData = data.expenses.map((expense) => ({
      Fecha: expense.dateLabel,
      Categoría: expense.category,
      Concepto: expense.concept,
      'Unidades x Unitario': `${expense.units} x Bs ${expense.unitCost}`,
      Proveedor: expense.provider || 'Sin proveedor',
      Total: expense.totalLabel,
      Factura: expense.invoiceUrl ? 'Sí' : 'Sin factura',
    }))
    const ws = XLSX.utils.json_to_sheet(sheetData)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, viewedMonthLabel)
    XLSX.writeFile(wb, `gastos_${month}_${year}.xlsx`)
  }, [data, month, year, viewedMonthLabel])

  const categorySummary = useMemo(() => {
    if (!data) return []
    const totals = new Map<string, { category: string; total: number; count: number }>()
    data.expenses.forEach((expense) => {
      const current = totals.get(expense.category) || { category: expense.category, total: 0, count: 0 }
      current.total += Number(expense.total || 0)
      current.count += 1
      totals.set(expense.category, current)
    })
    return Array.from(totals.values()).sort((a, b) => {
      if (a.category.toLowerCase() === 'otros') return -1
      if (b.category.toLowerCase() === 'otros') return 1
      return a.category.localeCompare(b.category, 'es')
    })
  }, [data])

  const totalForMonth = useMemo(
    () => categorySummary.reduce((accumulator, item) => accumulator + item.total, 0),
    [categorySummary],
  )

  const handleDelete = async (expense: ExpenseItem) => {
    const confirmed = await confirm({
      title: 'Confirmar eliminacion',
      message: `Eliminar el gasto "${expense.concept}" de ${expense.totalLabel}?`,
      tone: 'danger',
    })
    if (!confirmed) return
    setDeletingId(expense.rawId)
    try {
      const response = await deleteAdminExpense(expense.rawId)
      showNotification({ title: 'Gasto eliminado', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo eliminar',
        message: requestError instanceof Error ? requestError.message : 'Ocurrio un error al eliminar el gasto.',
        tone: 'danger',
      })
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Administracion"
        title="Lista de gastos"
        description={`Revisa gastos mensuales${activeBranch ? ` de ${activeBranch.nombre}` : ''}.`}
      />

      {isLoading && !data ? (
        <SectionCard title="Cargando gastos">
          <DataState title="Sincronizando gastos" message="Cargando registros del periodo seleccionado." />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar gastos">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <>
          <SectionCard
            title={`Gastos de ${monthNames[data.month - 1]} ${data.year}`}
            action={
              <div className="expense-period-controls">
                <button className="button button--ghost" type="button" onClick={() => changeMonth(-1)}>←</button>
                <div style={{ cursor: 'pointer' }} onClick={openMonthPicker}>
                  <span className="eyebrow">Mes seleccionado</span>
                  <h3 style={{ cursor: 'pointer' }}>{viewedMonthLabel}</h3>
                </div>
                <button className="button button--ghost" type="button" onClick={() => changeMonth(1)}>→</button>
                {data && data.expenses.length > 0 && (
                  <button className="button button--ghost" style={{ minWidth: '4.5rem', minHeight: '2.6rem', padding: '0 0.75rem' }} type="button" onClick={exportToExcel} title="Descargar Excel">
                    ↓ Excel
                  </button>
                )}
              </div>
            }
          >
            {data.expenses.length ? (
              <div className="table-wrapper expense-table-wrapper">
                <table className="admin-table admin-table--expenses">
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Categoría</th>
                      <th>Concepto</th>
                      <th>Proveedor</th>
                      <th>Total</th>
                      <th>Factura</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.expenses.map((expense) => (
                      <tr key={expense.rawId}>
                        <td>{expense.dateLabel}</td>
                        <td>{expense.category}</td>
                        <td><strong>{expense.concept}</strong><small>{expense.units} x Bs {expense.unitCost}</small></td>
                        <td>{expense.provider || 'Sin proveedor'}</td>
                        <td>{expense.totalLabel}</td>
                        <td>{expense.invoiceUrl ? <a href={expense.invoiceUrl} rel="noreferrer" target="_blank">Ver factura</a> : 'Sin factura'}</td>
                        <td>
                          <div className="table-actions">
                            <button className="button button--ghost button--sm" type="button" onClick={() => navigate('/cms/gastos/crear', { state: { expense } })}>Editar</button>
                            <button className="button button--ghost button--sm" disabled={deletingId === expense.rawId} type="button" onClick={() => handleDelete(expense)}>Eliminar</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <DataState title="Sin gastos en este mes" message="Registra el primer gasto de la sucursal para comenzar el control mensual." />
            )}
          </SectionCard>

          <SectionCard
            eyebrow="Resumen mensual"
            title={`Total de ${viewedMonthLabel}: ${formatMoney(totalForMonth)}`}
            description="Distribucion del gasto por categoría en el mes seleccionado."
          >
            {categorySummary.length ? (
              <div className="catalog-admin-grid">
                {categorySummary.map((item) => (
                  <article className="catalog-admin-card" key={item.category}>
                    <div className="catalog-admin-card__content">
                      <div className="catalog-admin-card__header">
                        <div><strong>{item.category}</strong><p>{item.count} gasto(s)</p></div>
                        <strong>{formatMoney(item.total)}</strong>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <DataState title="Sin resumen disponible" message="No hay gastos registrados en el mes seleccionado." />
            )}
          </SectionCard>
        </>
      ) : null}
      <ConfirmDialogModal />

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
    </div>
  )
}