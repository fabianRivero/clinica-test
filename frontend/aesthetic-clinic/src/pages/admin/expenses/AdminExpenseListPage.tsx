import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

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
  const { showNotification } = useNotifications()
  const { confirm, ConfirmDialog: ConfirmDialogModal } = useConfirmDialog()

  const loader = useCallback(() => getAdminExpenses(month, year), [month, year, branchId])
  const { data, isLoading, error, reload } = useApiResource(loader)
  const viewedMonthLabel = `${monthNames[month - 1]} ${year}`

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

  const changeMonth = (direction: -1 | 1) => {
    setMonth((current) => {
      const next = current + direction
      if (next < 1) {
        setYear((currentYear) => currentYear - 1)
        return 12
      }
      if (next > 12) {
        setYear((currentYear) => currentYear + 1)
        return 1
      }
      return next
    })
  }

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
                <div>
                  <span className="eyebrow">Mes seleccionado</span>
                  <h3>{viewedMonthLabel}</h3>
                </div>
                <button className="button button--ghost" type="button" onClick={() => changeMonth(1)}>→</button>
              </div>
            }
          >
            {data.expenses.length ? (
              <div className="table-wrapper expense-table-wrapper">
                <table className="admin-table admin-table--expenses">
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Categoria</th>
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
                            <button className="button button--ghost button--sm" type="button" onClick={() => navigate('/admin/gastos/crear', { state: { expense } })}>Editar</button>
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
            description="Distribucion del gasto por categoria en el mes seleccionado."
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
    </div>
  )
}