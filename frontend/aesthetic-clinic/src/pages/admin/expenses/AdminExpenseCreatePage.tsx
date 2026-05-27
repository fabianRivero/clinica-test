import { useCallback, useState, type ChangeEvent, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { DataState } from '../../../components/admin/DataState'
import { PageHeader } from '../../../components/admin/PageHeader'
import { SectionCard } from '../../../components/admin/SectionCard'
import { useApiResource } from '../../../hooks/useApiResource'
import { useNotifications } from '../../../providers/NotificationProvider'
import { useBranchContext } from '../../../providers/BranchProvider'
import { createAdminExpense, getAdminExpenses, updateAdminExpense } from '../../../services/api/admin'
import type { ExpenseItem, UpsertAdminExpensePayload } from '../../../types/admin'
import { decimalProduct, emptyForm, expenseToForm } from './expenseUtils'

type ExpenseRouteState = { expense?: ExpenseItem }

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

  const handleFormSubmit = async (event: FormEvent) => {
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
          <form className="catalog-form" onSubmit={handleFormSubmit}>
            <label className="field">
              <span>Fecha</span>
              <input className="input" type="date" value={form.date} onChange={(event) => updateForm('date', event.target.value)} />
              {fieldErrors.date ? <small className="field__error">{fieldErrors.date}</small> : null}
            </label>
            <label className="field">
              <span>Categoria</span>
              <select className="input" value={form.categoryId} onChange={(event) => updateForm('categoryId', event.target.value)}>
                <option value="">Selecciona una categoria</option>
                {data.categories.map((category) => (
                  <option key={category.id} value={category.id}>{category.name}</option>
                ))}
              </select>
              {fieldErrors.categoryId ? <small className="field__error">{fieldErrors.categoryId}</small> : null}
            </label>
            <label className="field field--full">
              <span>Concepto</span>
              <input className="input" value={form.concept} onChange={(event) => updateForm('concept', event.target.value)} placeholder="Ej. Compra de guantes nitrilo" />
              {fieldErrors.concept ? <small className="field__error">{fieldErrors.concept}</small> : null}
            </label>
            <label className="field">
              <span>Unidades</span>
              <input className="input" min="0" step="0.01" type="number" value={form.units} onChange={(event) => updateForm('units', event.target.value)} />
              {fieldErrors.units ? <small className="field__error">{fieldErrors.units}</small> : null}
            </label>
            <label className="field">
              <span>Costo por unidad</span>
              <input className="input" min="0" step="0.01" type="number" value={form.unitCost} onChange={(event) => updateForm('unitCost', event.target.value)} />
              {fieldErrors.unitCost ? <small className="field__error">{fieldErrors.unitCost}</small> : null}
            </label>
            <label className="field">
              <span>Gasto total</span>
              <input className="input" min="0" step="0.01" type="number" value={form.total} onChange={(event) => updateForm('total', event.target.value)} />
              {fieldErrors.total ? <small className="field__error">{fieldErrors.total}</small> : null}
            </label>
            <label className="field">
              <span>Proveedor</span>
              <input className="input" value={form.provider} onChange={(event) => updateForm('provider', event.target.value)} placeholder="Nombre del proveedor" />
            </label>
            <label className="field field--full">
              <span>Factura</span>
              <input accept=".pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/png,image/jpeg,image/webp" className="input input--file" type="file" onChange={(event: ChangeEvent<HTMLInputElement>) => updateForm('invoice', event.target.files?.[0] || null)} />
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
    </div>
  )
}

import { useLocation } from 'react-router-dom'