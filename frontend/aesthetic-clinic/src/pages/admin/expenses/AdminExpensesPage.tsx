import { useCallback, useMemo, useState, type ChangeEvent, type FormEvent } from 'react'

import { DataState } from '../../../components/admin/DataState'
import { PageHeader } from '../../../components/admin/PageHeader'
import { SectionCard } from '../../../components/admin/SectionCard'
import { FieldError } from '../../../components/admin/FieldError'
import { useApiResource } from '../../../hooks/useApiResource'
import { useConfirmDialog } from '../../../hooks/useConfirmDialog'
import { useFormSubmission } from '../../../hooks/useFormSubmission'
import { useBranchContext } from '../../../providers/BranchProvider'
import { useNotifications } from '../../../providers/NotificationProvider'
import {
  createAdminExpense,
  deleteAdminExpense,
  getAdminExpenses,
  updateAdminExpense,
} from '../../../services/api/admin'
import type { ExpenseItem, UpsertAdminExpensePayload } from '../../../types/admin'
import { decimalProduct, emptyForm, expenseToForm, formatMoney, monthNames } from './expenseUtils'
import type { ExpenseTab } from './expenseUtils'

export function AdminExpensesPage() {
  const now = new Date()
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [year, setYear] = useState(now.getFullYear())
  const [form, setForm] = useState<UpsertAdminExpensePayload>(emptyForm)
  const [editingExpense, setEditingExpense] = useState<ExpenseItem | null>(null)
  const { showNotification } = useNotifications()
  const { isSubmitting, submitError, fieldErrors, setFieldErrors, clearFieldError, handleSubmit } = useFormSubmission(showNotification)
  const { confirm, ConfirmDialog: ConfirmDialogModal } = useConfirmDialog()
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<ExpenseTab>('list')
  const [showMonthPicker, setShowMonthPicker] = useState(false)
  const [pickerMonth, setPickerMonth] = useState(month)
  const [pickerYear, setPickerYear] = useState(year)

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

  const updateForm = (field: keyof UpsertAdminExpensePayload, value: string | File | null) => {
    setForm((current) => {
      const next = { ...current, [field]: value }
      if (field === 'units' || field === 'unitCost') {
        next.total = decimalProduct(
          field === 'units' ? String(value) : next.units,
          field === 'unitCost' ? String(value) : next.unitCost,
        )
      }
      return next
    })
    clearFieldError(field)
  }

  const handleInvoiceChange = (event: ChangeEvent<HTMLInputElement>) => {
    updateForm('invoice', event.target.files?.[0] || null)
  }

  const resetForm = () => {
    setForm({ ...emptyForm, date: new Date().toISOString().slice(0, 10) })
    setEditingExpense(null)
    setFieldErrors({})
  }

  const handleEdit = (expense: ExpenseItem) => {
    setEditingExpense(expense)
    setForm(expenseToForm(expense))
    setFieldErrors({})
    setActiveTab('create')
  }

  const handleFormSubmit = async (event: FormEvent) => {
    event.preventDefault()
    await handleSubmit(
      async () => {
        const response = editingExpense
          ? await updateAdminExpense(editingExpense.rawId, form)
          : await createAdminExpense(form)
        return response
      },
      {
        successTitle: editingExpense ? 'Gasto actualizado' : 'Gasto registrado',
        successMessage: (response) => (response as { detail: string }).detail,
        onSuccess: () => {
          resetForm()
          setActiveTab('list')
          reload()
        },
      },
    ).catch?.()
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
      if (editingExpense?.rawId === expense.rawId) resetForm()
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
        title="Gastos de sucursal"
        description={`Registra y revisa gastos mensuales${activeBranch ? ` de ${activeBranch.nombre}` : ''}.`}
      />

      <nav className="section-tabs" aria-label="Subsecciones de gastos">
        <button
          className={`section-tabs__link ${activeTab === 'create' ? 'is-active' : ''}`}
          type="button"
          onClick={() => setActiveTab('create')}
        >
          Crear gasto
        </button>
        <button
          className={`section-tabs__link ${activeTab === 'list' ? 'is-active' : ''}`}
          type="button"
          onClick={() => setActiveTab('list')}
        >
          Lista de gastos
        </button>
      </nav>

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
          {activeTab === 'create' ? (
            <SectionCard
              eyebrow={editingExpense ? 'Editar gasto' : 'Nuevo gasto'}
              title={editingExpense ? editingExpense.concept : 'Registrar gasto'}
              description="Los gastos se guardan en la sucursal activa del selector global."
            >
              <form className="catalog-form" onSubmit={handleFormSubmit}>
                <label className="field">
                  <span>Fecha</span>
                  <input className="input" type="date" value={form.date} onChange={(event) => updateForm('date', event.target.value)} />
                  <FieldError message={fieldErrors.date} />
                </label>
                <label className="field">
                  <span>Categoría</span>
                  <select className="input" value={form.categoryId} onChange={(event) => updateForm('categoryId', event.target.value)}>
                    <option value="">Selecciona una categoría</option>
                    {data.categories.map((category) => (
                      <option key={category.id} value={category.id}>{category.name}</option>
                    ))}
                  </select>
                  <FieldError message={fieldErrors.categoryId} />
                </label>
                <label className="field field--full">
                  <span>Concepto</span>
                  <input className="input" value={form.concept} onChange={(event) => updateForm('concept', event.target.value)} placeholder="Ej. Compra de guantes nitrilo" />
                  <FieldError message={fieldErrors.concept} />
                </label>
                <label className="field">
                  <span>Unidades</span>
                  <input className="input" min="0" step="0.01" type="number" value={form.units} onChange={(event) => updateForm('units', event.target.value)} />
                  <FieldError message={fieldErrors.units} />
                </label>
                <label className="field">
                  <span>Costo por unidad</span>
                  <input className="input" min="0" step="0.01" type="number" value={form.unitCost} onChange={(event) => updateForm('unitCost', event.target.value)} />
                  <FieldError message={fieldErrors.unitCost} />
                </label>
                <label className="field">
                  <span>Gasto total</span>
                  <input className="input" min="0" step="0.01" type="number" value={form.total} onChange={(event) => updateForm('total', event.target.value)} />
                  <FieldError message={fieldErrors.total} />
                </label>
                <label className="field">
                  <span>Proveedor</span>
                  <input className="input" value={form.provider} onChange={(event) => updateForm('provider', event.target.value)} placeholder="Nombre del proveedor" />
                </label>
                <label className="field field--full">
                  <span>Factura</span>
                  <input accept=".pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/png,image/jpeg,image/webp" className="input input--file" type="file" onChange={handleInvoiceChange} />
                  <small className="field__hint">
                    {form.invoice ? `Archivo seleccionado: ${form.invoice.name}` : editingExpense?.invoiceName ? `Factura actual: ${editingExpense.invoiceName}` : 'Opcional. PDF o imagen.'}
                  </small>
                </label>
                <label className="field field--full">
                  <span>Detalles</span>
                  <textarea className="input textarea textarea--compact" value={form.details} onChange={(event) => updateForm('details', event.target.value)} placeholder="Notas internas del gasto" />
                </label>
                {submitError ? <div className="form-error">{submitError}</div> : null}
                <div className="form-actions">
                  {editingExpense ? (
                    <button className="button button--ghost" type="button" onClick={resetForm}>Cancelar edicion</button>
                  ) : null}
                  <button className="button" disabled={isSubmitting} type="submit">
                    {isSubmitting ? 'Guardando...' : editingExpense ? 'Guardar cambios' : 'Registrar gasto'}
                  </button>
                </div>
              </form>
            </SectionCard>
          ) : null}

          {activeTab === 'list' ? (
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
                                <button className="button button--ghost button--sm" type="button" onClick={() => handleEdit(expense)}>Editar</button>
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

export { AdminExpenseCreatePage } from './AdminExpenseCreatePage'
export { AdminExpenseListPage } from './AdminExpenseListPage'