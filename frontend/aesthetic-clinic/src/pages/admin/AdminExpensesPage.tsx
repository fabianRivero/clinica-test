import { useCallback, useMemo, useState, type ChangeEvent, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { useApiResource } from '../../hooks/useApiResource'
import { useBranchContext } from '../../providers/BranchProvider'
import { useNotifications } from '../../providers/NotificationProvider'
import {
  createAdminExpense,
  deleteAdminExpense,
  getAdminExpenses,
  updateAdminExpense,
} from '../../services/api/admin'
import type { ExpenseItem, UpsertAdminExpensePayload } from '../../types/admin'

const monthNames = [
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

const emptyForm: UpsertAdminExpensePayload = {
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

type ExpenseTab = 'create' | 'list'

function decimalProduct(left: string, right: string) {
  const a = Number(left || 0)
  const b = Number(right || 0)
  if (!Number.isFinite(a) || !Number.isFinite(b)) return '0.00'
  return (a * b).toFixed(2)
}

function formatMoney(value: number) {
  return `Bs ${value.toFixed(2)}`
}

function expenseToForm(expense: ExpenseItem): UpsertAdminExpensePayload {
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

export function AdminExpensesPage() {
  const now = new Date()
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [year, setYear] = useState(now.getFullYear())
  const [form, setForm] = useState<UpsertAdminExpensePayload>(emptyForm)
  const [editingExpense, setEditingExpense] = useState<ExpenseItem | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<ExpenseTab>('list')
  const { showNotification } = useNotifications()

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
    setFieldErrors((current) => ({ ...current, [field]: '' }))
    setSubmitError(null)
  }

  const handleInvoiceChange = (event: ChangeEvent<HTMLInputElement>) => {
    updateForm('invoice', event.target.files?.[0] || null)
  }

  const resetForm = () => {
    setForm({ ...emptyForm, date: new Date().toISOString().slice(0, 10) })
    setEditingExpense(null)
    setFieldErrors({})
    setSubmitError(null)
  }

  const handleEdit = (expense: ExpenseItem) => {
    setEditingExpense(expense)
    setForm(expenseToForm(expense))
    setFieldErrors({})
    setSubmitError(null)
    setActiveTab('create')
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setIsSubmitting(true)
    setSubmitError(null)
    setFieldErrors({})
    try {
      const response = editingExpense
        ? await updateAdminExpense(editingExpense.rawId, form)
        : await createAdminExpense(form)
      showNotification({
        title: editingExpense ? 'Gasto actualizado' : 'Gasto registrado',
        message: response.detail,
        tone: 'success',
      })
      resetForm()
      setActiveTab('list')
      reload()
    } catch (requestError) {
      const errorWithFields = requestError as Error & { fieldErrors?: Record<string, string> }
      setSubmitError(errorWithFields.message || 'No se pudo guardar el gasto.')
      setFieldErrors(errorWithFields.fieldErrors || {})
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (expense: ExpenseItem) => {
    const confirmed = window.confirm(`Eliminar el gasto "${expense.concept}" de ${expense.totalLabel}?`)
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
              <form className="catalog-form" onSubmit={handleSubmit}>
              <label className="field">
                <span>Fecha</span>
                <input
                  className="input"
                  type="date"
                  value={form.date}
                  onChange={(event) => updateForm('date', event.target.value)}
                />
                {fieldErrors.date ? <small className="field__error">{fieldErrors.date}</small> : null}
              </label>

              <label className="field">
                <span>Categoria</span>
                <select
                  className="input"
                  value={form.categoryId}
                  onChange={(event) => updateForm('categoryId', event.target.value)}
                >
                  <option value="">Selecciona una categoria</option>
                  {data.categories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                    </option>
                  ))}
                </select>
                {fieldErrors.categoryId ? <small className="field__error">{fieldErrors.categoryId}</small> : null}
              </label>

              <label className="field field--full">
                <span>Concepto</span>
                <input
                  className="input"
                  value={form.concept}
                  onChange={(event) => updateForm('concept', event.target.value)}
                  placeholder="Ej. Compra de guantes nitrilo"
                />
                {fieldErrors.concept ? <small className="field__error">{fieldErrors.concept}</small> : null}
              </label>

              <label className="field">
                <span>Unidades</span>
                <input
                  className="input"
                  min="0"
                  step="0.01"
                  type="number"
                  value={form.units}
                  onChange={(event) => updateForm('units', event.target.value)}
                />
                {fieldErrors.units ? <small className="field__error">{fieldErrors.units}</small> : null}
              </label>

              <label className="field">
                <span>Costo por unidad</span>
                <input
                  className="input"
                  min="0"
                  step="0.01"
                  type="number"
                  value={form.unitCost}
                  onChange={(event) => updateForm('unitCost', event.target.value)}
                />
                {fieldErrors.unitCost ? <small className="field__error">{fieldErrors.unitCost}</small> : null}
              </label>

              <label className="field">
                <span>Gasto total</span>
                <input
                  className="input"
                  min="0"
                  step="0.01"
                  type="number"
                  value={form.total}
                  onChange={(event) => updateForm('total', event.target.value)}
                />
                {fieldErrors.total ? <small className="field__error">{fieldErrors.total}</small> : null}
              </label>

              <label className="field">
                <span>Proveedor</span>
                <input
                  className="input"
                  value={form.provider}
                  onChange={(event) => updateForm('provider', event.target.value)}
                  placeholder="Nombre del proveedor"
                />
              </label>

              <label className="field field--full">
                <span>Factura</span>
                <input
                  accept=".pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/png,image/jpeg,image/webp"
                  className="input input--file"
                  type="file"
                  onChange={handleInvoiceChange}
                />
                <small className="field__hint">
                  {form.invoice
                    ? `Archivo seleccionado: ${form.invoice.name}`
                    : editingExpense?.invoiceName
                      ? `Factura actual: ${editingExpense.invoiceName}`
                      : 'Opcional. PDF o imagen.'}
                </small>
              </label>

              <label className="field field--full">
                <span>Detalles</span>
                <textarea
                  className="input textarea textarea--compact"
                  value={form.details}
                  onChange={(event) => updateForm('details', event.target.value)}
                  placeholder="Notas internas del gasto"
                />
              </label>

              {submitError ? <div className="form-error">{submitError}</div> : null}

              <div className="form-actions">
                {editingExpense ? (
                  <button className="button button--ghost" type="button" onClick={resetForm}>
                    Cancelar edicion
                  </button>
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
                    <button className="button button--ghost" type="button" onClick={() => changeMonth(-1)}>
                      ←
                    </button>
                    <div>
                      <span className="eyebrow">Mes seleccionado</span>
                      <h3>{viewedMonthLabel}</h3>
                    </div>
                    <button className="button button--ghost" type="button" onClick={() => changeMonth(1)}>
                      →
                    </button>
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
                            <td>
                              <strong>{expense.concept}</strong>
                              <small>{expense.units} x Bs {expense.unitCost}</small>
                            </td>
                            <td>{expense.provider || 'Sin proveedor'}</td>
                            <td>{expense.totalLabel}</td>
                            <td>
                              {expense.invoiceUrl ? (
                                <a href={expense.invoiceUrl} rel="noreferrer" target="_blank">
                                  Ver factura
                                </a>
                              ) : (
                                'Sin factura'
                              )}
                            </td>
                            <td>
                              <div className="table-actions">
                                <button className="button button--ghost button--sm" type="button" onClick={() => handleEdit(expense)}>
                                  Editar
                                </button>
                                <button
                                  className="button button--ghost button--sm"
                                  disabled={deletingId === expense.rawId}
                                  type="button"
                                  onClick={() => handleDelete(expense)}
                                >
                                  Eliminar
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
                    title="Sin gastos en este mes"
                    message="Registra el primer gasto de la sucursal para comenzar el control mensual."
                  />
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
                            <div>
                              <strong>{item.category}</strong>
                              <p>{item.count} gasto(s)</p>
                            </div>
                            <strong>{formatMoney(item.total)}</strong>
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <DataState
                    title="Sin resumen disponible"
                    message="No hay gastos registrados en el mes seleccionado."
                  />
                )}
              </SectionCard>
            </>
          ) : null}
        </>
      ) : null}
    </div>
  )
}

type ExpenseRouteState = {
  expense?: ExpenseItem
}

export function AdminExpenseCreatePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const routeState = (location.state || {}) as ExpenseRouteState
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  const [editingExpense, setEditingExpense] = useState<ExpenseItem | null>(routeState.expense || null)
  const [form, setForm] = useState<UpsertAdminExpensePayload>(
    routeState.expense ? expenseToForm(routeState.expense) : emptyForm,
  )
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const { showNotification } = useNotifications()
  const [initialPeriod] = useState(() => {
    const today = new Date()
    return { month: today.getMonth() + 1, year: today.getFullYear() }
  })

  const loader = useCallback(
    () => getAdminExpenses(initialPeriod.month, initialPeriod.year),
    [branchId, initialPeriod],
  )
  const { data, isLoading, error, reload } = useApiResource(loader)

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
    setFieldErrors((current) => ({ ...current, [field]: '' }))
    setSubmitError(null)
  }

  const resetForm = () => {
    setForm({ ...emptyForm, date: new Date().toISOString().slice(0, 10) })
    setEditingExpense(null)
    setFieldErrors({})
    setSubmitError(null)
    window.history.replaceState({}, document.title)
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setIsSubmitting(true)
    setSubmitError(null)
    setFieldErrors({})
    try {
      const response = editingExpense
        ? await updateAdminExpense(editingExpense.rawId, form)
        : await createAdminExpense(form)
      showNotification({
        title: editingExpense ? 'Gasto actualizado' : 'Gasto registrado',
        message: response.detail,
        tone: 'success',
      })
      resetForm()
      reload()
      navigate('/admin/gastos/lista')
    } catch (requestError) {
      const errorWithFields = requestError as Error & { fieldErrors?: Record<string, string> }
      setSubmitError(errorWithFields.message || 'No se pudo guardar el gasto.')
      setFieldErrors(errorWithFields.fieldErrors || {})
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Administracion"
        title={editingExpense ? 'Editar gasto' : 'Crear gasto'}
        description={`Registra gastos${activeBranch ? ` para ${activeBranch.nombre}` : ''}.`}
      />

      {isLoading && !data ? (
        <SectionCard title="Cargando categorias">
          <DataState title="Sincronizando categorias" message="Preparando el formulario de gastos." />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar categorias">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <SectionCard
          eyebrow={editingExpense ? 'Edicion' : 'Nuevo registro'}
          title={editingExpense ? editingExpense.concept : 'Registrar gasto'}
          description="El gasto se guardara en la sucursal activa del selector global."
        >
          <form className="catalog-form" onSubmit={handleSubmit}>
            <label className="field">
              <span>Fecha</span>
              <input
                className="input"
                type="date"
                value={form.date}
                onChange={(event) => updateForm('date', event.target.value)}
              />
              {fieldErrors.date ? <small className="field__error">{fieldErrors.date}</small> : null}
            </label>

            <label className="field">
              <span>Categoria</span>
              <select
                className="input"
                value={form.categoryId}
                onChange={(event) => updateForm('categoryId', event.target.value)}
              >
                <option value="">Selecciona una categoria</option>
                {data.categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
              {fieldErrors.categoryId ? <small className="field__error">{fieldErrors.categoryId}</small> : null}
            </label>

            <label className="field field--full">
              <span>Concepto</span>
              <input
                className="input"
                value={form.concept}
                onChange={(event) => updateForm('concept', event.target.value)}
                placeholder="Ej. Compra de guantes nitrilo"
              />
              {fieldErrors.concept ? <small className="field__error">{fieldErrors.concept}</small> : null}
            </label>

            <label className="field">
              <span>Unidades</span>
              <input
                className="input"
                min="0"
                step="0.01"
                type="number"
                value={form.units}
                onChange={(event) => updateForm('units', event.target.value)}
              />
              {fieldErrors.units ? <small className="field__error">{fieldErrors.units}</small> : null}
            </label>

            <label className="field">
              <span>Costo por unidad</span>
              <input
                className="input"
                min="0"
                step="0.01"
                type="number"
                value={form.unitCost}
                onChange={(event) => updateForm('unitCost', event.target.value)}
              />
              {fieldErrors.unitCost ? <small className="field__error">{fieldErrors.unitCost}</small> : null}
            </label>

            <label className="field">
              <span>Gasto total</span>
              <input
                className="input"
                min="0"
                step="0.01"
                type="number"
                value={form.total}
                onChange={(event) => updateForm('total', event.target.value)}
              />
              {fieldErrors.total ? <small className="field__error">{fieldErrors.total}</small> : null}
            </label>

            <label className="field">
              <span>Proveedor</span>
              <input
                className="input"
                value={form.provider}
                onChange={(event) => updateForm('provider', event.target.value)}
                placeholder="Nombre del proveedor"
              />
            </label>

            <label className="field field--full">
              <span>Factura</span>
              <input
                accept=".pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/png,image/jpeg,image/webp"
                className="input input--file"
                type="file"
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  updateForm('invoice', event.target.files?.[0] || null)
                }
              />
              <small className="field__hint">
                {form.invoice
                  ? `Archivo seleccionado: ${form.invoice.name}`
                  : editingExpense?.invoiceName
                    ? `Factura actual: ${editingExpense.invoiceName}`
                    : 'Opcional. PDF o imagen.'}
              </small>
            </label>

            <label className="field field--full">
              <span>Detalles</span>
              <textarea
                className="input textarea textarea--compact"
                value={form.details}
                onChange={(event) => updateForm('details', event.target.value)}
                placeholder="Notas internas del gasto"
              />
            </label>

            {submitError ? <div className="form-error">{submitError}</div> : null}

            <div className="form-actions">
              {editingExpense ? (
                <button className="button button--ghost" type="button" onClick={resetForm}>
                  Cancelar edicion
                </button>
              ) : null}
              <button className="button" disabled={isSubmitting} type="submit">
                {isSubmitting ? 'Guardando...' : editingExpense ? 'Guardar cambios' : 'Registrar gasto'}
              </button>
            </div>
          </form>
        </SectionCard>
      ) : null}
    </div>
  )
}

export function AdminExpenseListPage() {
  const now = new Date()
  const navigate = useNavigate()
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [year, setYear] = useState(now.getFullYear())
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const { showNotification } = useNotifications()

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
    const confirmed = window.confirm(`Eliminar el gasto "${expense.concept}" de ${expense.totalLabel}?`)
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
                <button className="button button--ghost" type="button" onClick={() => changeMonth(-1)}>
                  ←
                </button>
                <div>
                  <span className="eyebrow">Mes seleccionado</span>
                  <h3>{viewedMonthLabel}</h3>
                </div>
                <button className="button button--ghost" type="button" onClick={() => changeMonth(1)}>
                  →
                </button>
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
                        <td>
                          <strong>{expense.concept}</strong>
                          <small>{expense.units} x Bs {expense.unitCost}</small>
                        </td>
                        <td>{expense.provider || 'Sin proveedor'}</td>
                        <td>{expense.totalLabel}</td>
                        <td>
                          {expense.invoiceUrl ? (
                            <a href={expense.invoiceUrl} rel="noreferrer" target="_blank">
                              Ver factura
                            </a>
                          ) : (
                            'Sin factura'
                          )}
                        </td>
                        <td>
                          <div className="table-actions">
                            <button
                              className="button button--ghost button--sm"
                              type="button"
                              onClick={() => navigate('/admin/gastos/crear', { state: { expense } })}
                            >
                              Editar
                            </button>
                            <button
                              className="button button--ghost button--sm"
                              disabled={deletingId === expense.rawId}
                              type="button"
                              onClick={() => handleDelete(expense)}
                            >
                              Eliminar
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
                title="Sin gastos en este mes"
                message="Registra el primer gasto de la sucursal para comenzar el control mensual."
              />
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
                        <div>
                          <strong>{item.category}</strong>
                          <p>{item.count} gasto(s)</p>
                        </div>
                        <strong>{formatMoney(item.total)}</strong>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <DataState
                title="Sin resumen disponible"
                message="No hay gastos registrados en el mes seleccionado."
              />
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  )
}
