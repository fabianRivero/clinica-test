import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react'

import { StatusBadge } from './StatusBadge'
import { useNotifications } from '../../providers/NotificationProvider'
import {
  createGroupOption,
  getGroupOptions,
  toggleGroupOptionState,
  updateGroupOption,
  type GroupOptionItem,
} from '../../services/api/admin'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

type GroupOptionModalProps = {
  grupo: { id: number; nombre: string; codigo: string }
  open: boolean
  onClose: () => void
}

type FilterValue = 'true' | 'false' | 'all'

type SubFormMode = 'closed' | 'create' | 'edit'

type SubFormState = {
  codigo: string
  nombre: string
  valor: string
  orden: string
  activo: boolean
}

const EMPTY_SUB_FORM: SubFormState = {
  codigo: '',
  nombre: '',
  valor: '',
  orden: '',
  activo: true,
}

function buildSubFormFromItem(item: GroupOptionItem): SubFormState {
  return {
    codigo: item.codigo,
    nombre: item.nombre,
    valor: item.valor,
    orden: item.orden === null || typeof item.orden === 'undefined' ? '' : String(item.orden),
    activo: item.activo,
  }
}

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

export function OptionGroupModal({ grupo, open, onClose }: GroupOptionModalProps) {
  const { showNotification } = useNotifications()
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  const [items, setItems] = useState<GroupOptionItem[]>([])
  const [listLoading, setListLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [filter, setFilter] = useState<FilterValue>('true')
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  const [subFormMode, setSubFormMode] = useState<SubFormMode>('closed')
  const [editingOptionId, setEditingOptionId] = useState<number | null>(null)
  const [subForm, setSubForm] = useState<SubFormState>(EMPTY_SUB_FORM)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [formLoading, setFormLoading] = useState(false)
  const [pendingToggleId, setPendingToggleId] = useState<number | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

  const titleId = useId()

  // Debounce search input so we don't refetch on every keystroke.
  useEffect(() => {
    const handle = window.setTimeout(() => setSearchQuery(searchInput.trim()), 250)
    return () => window.clearTimeout(handle)
  }, [searchInput])

  const loadOptions = useCallback(
    async (nextFilter: FilterValue, nextQuery: string) => {
      setListLoading(true)
      setListError(null)
      try {
        const response = await getGroupOptions(grupo.id, {
          active: nextFilter,
          q: nextQuery,
        })
        setItems(response.items)
        // Drop selections that no longer match the current filter.
        setSelectedIds((current) => {
          const visibleIds = new Set(response.items.map((item) => item.id))
          const next = new Set<number>()
          current.forEach((id) => {
            if (visibleIds.has(id)) next.add(id)
          })
          return next
        })
      } catch (error) {
        setListError(getErrorMessage(error, 'No se pudieron cargar las opciones.'))
      } finally {
        setListLoading(false)
      }
    },
    [grupo.id],
  )

  // Fetch whenever the modal opens or the filter/search changes.
  useEffect(() => {
    if (!open) return
    void loadOptions(filter, searchQuery)
  }, [open, filter, searchQuery, loadOptions])

  // Reset internal state when the modal closes so the next open is clean.
  useEffect(() => {
    if (open) return
    setSubFormMode('closed')
    setEditingOptionId(null)
    setSubForm(EMPTY_SUB_FORM)
    setFieldErrors({})
    setFormError(null)
    setSearchInput('')
    setSearchQuery('')
    setFilter('true')
    setSelectedIds(new Set())
    setListError(null)
    setItems([])
  }, [open])

  // Focus management + ESC handler.
  useEffect(() => {
    if (!open) return

    const dialogNode = dialogRef.current
    if (!dialogNode) return

    previousFocusRef.current = document.activeElement as HTMLElement | null

    // Move focus to the first focusable element inside the modal.
    const focusable = dialogNode.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
    const first = focusable[0]
    if (first) {
      first.focus()
    } else {
      dialogNode.focus()
    }

    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab') return

      if (!dialogNode) return
      const focusables = dialogNode.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      if (focusables.length === 0) {
        event.preventDefault()
        return
      }
      const firstFocusable = focusables[0]
      const lastFocusable = focusables[focusables.length - 1]
      const active = document.activeElement as HTMLElement | null
      if (event.shiftKey && active === firstFocusable) {
        event.preventDefault()
        lastFocusable.focus()
      } else if (!event.shiftKey && active === lastFocusable) {
        event.preventDefault()
        firstFocusable.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      const previous = previousFocusRef.current
      if (previous && typeof previous.focus === 'function') {
        previous.focus()
      }
    }
  }, [open, onClose])

  const closeSubForm = useCallback(() => {
    setSubFormMode('closed')
    setEditingOptionId(null)
    setSubForm(EMPTY_SUB_FORM)
    setFieldErrors({})
    setFormError(null)
  }, [])

  const openCreateForm = useCallback(() => {
    setSubFormMode('create')
    setEditingOptionId(null)
    setSubForm(EMPTY_SUB_FORM)
    setFieldErrors({})
    setFormError(null)
  }, [])

  const openEditForm = useCallback((item: GroupOptionItem) => {
    setSubFormMode('edit')
    setEditingOptionId(item.id)
    setSubForm(buildSubFormFromItem(item))
    setFieldErrors({})
    setFormError(null)
  }, [])

  function handleSubFormChange<K extends keyof SubFormState>(
    key: K,
    value: SubFormState[K],
  ) {
    setSubForm((current) => ({ ...current, [key]: value }))
    setFieldErrors((current) => {
      if (!current[key as string]) return current
      const next = { ...current }
      delete next[key as string]
      return next
    })
  }

  async function handleSubFormSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (formLoading) return

    // Client-side validation: required fields mirror backend requirements.
    const errors: Record<string, string> = {}
    if (subFormMode === 'create' && !subForm.codigo.trim()) {
      errors.codigo = 'El codigo es obligatorio.'
    }
    if (!subForm.nombre.trim()) errors.nombre = 'El nombre es obligatorio.'
    if (!subForm.valor.trim()) errors.valor = 'El valor es obligatorio.'
    if (subForm.orden.trim()) {
      const parsed = Number(subForm.orden)
      if (Number.isNaN(parsed) || parsed < 0 || !Number.isInteger(parsed)) {
        errors.orden = 'El orden debe ser un entero no negativo.'
      }
    }
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors)
      return
    }

    const orden = subForm.orden.trim() ? Number(subForm.orden) : null
    setFormLoading(true)
    setFormError(null)
    setFieldErrors({})
    try {
      if (subFormMode === 'create') {
        await createGroupOption(grupo.id, {
          codigo: subForm.codigo.trim(),
          nombre: subForm.nombre.trim(),
          valor: subForm.valor.trim(),
          orden,
          activo: subForm.activo,
        })
        showNotification({
          title: 'Opcion creada',
          message: 'La nueva opcion ya esta disponible.',
          tone: 'success',
        })
      } else if (subFormMode === 'edit' && editingOptionId !== null) {
        await updateGroupOption(grupo.id, editingOptionId, {
          nombre: subForm.nombre.trim(),
          valor: subForm.valor.trim(),
          orden,
          activo: subForm.activo,
        })
        showNotification({
          title: 'Opcion actualizada',
          message: 'Los cambios se guardaron correctamente.',
          tone: 'success',
        })
      }
      closeSubForm()
      await loadOptions(filter, searchQuery)
    } catch (error) {
      const apiError = error as Error & { fieldErrors?: Record<string, string> }
      if (apiError.fieldErrors) {
        setFieldErrors(apiError.fieldErrors)
      }
      const message = getErrorMessage(error, 'No se pudo guardar la opcion.')
      setFormError(message)
      showNotification({
        title: 'No se pudo guardar',
        message,
        tone: 'danger',
      })
    } finally {
      setFormLoading(false)
    }
  }

  async function handleToggle(item: GroupOptionItem) {
    if (pendingToggleId !== null) return
    setPendingToggleId(item.id)
    try {
      await toggleGroupOptionState(grupo.id, item.id, !item.activo)
      showNotification({
        title: item.activo ? 'Opcion desactivada' : 'Opcion reactivada',
        message: item.activo
          ? 'La opcion dejara de mostrarse en nuevas fichas.'
          : 'La opcion volvio a estar disponible.',
        tone: 'success',
      })
      await loadOptions(filter, searchQuery)
    } catch (error) {
      showNotification({
        title: 'No se pudo cambiar el estado',
        message: getErrorMessage(error, 'Intenta nuevamente en unos segundos.'),
        tone: 'danger',
      })
    } finally {
      setPendingToggleId(null)
    }
  }

  function handleBackdropClick(event: React.MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) {
      onClose()
    }
  }

  function handleBackdropKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.stopPropagation()
      onClose()
    }
  }

  function toggleSelection(id: number) {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const hasOptions = items.length > 0
  const isEditing = subFormMode === 'edit'

  const titleNode = useMemo(
    () => (
      <header className="option-group-modal__header">
        <div>
          <span className="option-group-modal__eyebrow">Opciones de grupo</span>
          <h2 id={titleId} className="option-group-modal__title">
            {grupo.nombre}
          </h2>
          <p className="option-group-modal__subtitle">
            Codigo interno: <code>{grupo.codigo}</code>
          </p>
        </div>
        <button
          aria-label="Cerrar modal de opciones"
          className="option-group-modal__close"
          type="button"
          onClick={onClose}
        >
          <span aria-hidden="true">x</span>
        </button>
      </header>
    ),
    [grupo.nombre, grupo.codigo, titleId, onClose],
  )

  if (!open) return null

  return (
    <div
      aria-hidden={!open}
      className="booking-modal-overlay option-group-modal"
      data-testid="option-group-modal"
      onClick={handleBackdropClick}
      onKeyDown={handleBackdropKeyDown}
      role="presentation"
    >
      <div
        aria-labelledby={titleId}
        aria-modal="true"
        className="booking-modal-content option-group-modal__content"
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        {titleNode}

        <div className="booking-modal-body option-group-modal__body">
          <div className="option-group-modal__filters">
            <label className="field" htmlFor={`${titleId}-filter`}>
              <span>Filtrar por estado</span>
              <select
                aria-label="Filtrar opciones por estado"
                className="input"
                id={`${titleId}-filter`}
                value={filter}
                onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                  setFilter(event.target.value as FilterValue)
                }
              >
                <option value="true">Solo activas</option>
                <option value="false">Solo inactivas</option>
                <option value="all">Todas</option>
              </select>
            </label>
            <label className="field" htmlFor={`${titleId}-search`}>
              <span>Buscar opciones</span>
              <input
                aria-label="Buscar opciones por codigo, nombre o valor"
                className="input"
                id={`${titleId}-search`}
                placeholder="Buscar..."
                type="search"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
              />
            </label>
          </div>

          <div className="option-group-modal__list-status" aria-live="polite">
            {listLoading ? 'Cargando opciones...' : null}
            {!listLoading && listError ? (
              <span className="option-group-modal__error">{listError}</span>
            ) : null}
            {!listLoading && !listError && !hasOptions ? 'Sin opciones' : null}
          </div>

          {hasOptions ? (
            <ul className="option-group-modal__list" role="list">
              {items.map((item) => {
                const isSelected = selectedIds.has(item.id)
                const isPending = pendingToggleId === item.id
                return (
                  <li
                    className="option-group-modal__row"
                    data-testid={`option-row-${item.id}`}
                    key={item.id}
                  >
                    <label
                      aria-label={`Seleccionar opcion ${item.nombre}`}
                      className="option-group-modal__select"
                    >
                      <input
                        checked={isSelected}
                        type="checkbox"
                        onChange={() => toggleSelection(item.id)}
                      />
                    </label>
                    <div className="option-group-modal__row-content">
                      <div className="option-group-modal__row-header">
                        <strong>{item.nombre}</strong>
                        <StatusBadge tone={item.activo ? 'success' : 'neutral'}>
                          {item.activo ? 'Activa' : 'Inactiva'}
                        </StatusBadge>
                      </div>
                      <dl className="option-group-modal__row-meta">
                        <div>
                          <dt>Codigo</dt>
                          <dd>
                            <code>{item.codigo}</code>
                          </dd>
                        </div>
                        <div>
                          <dt>Valor</dt>
                          <dd>{item.valor}</dd>
                        </div>
                        <div>
                          <dt>Orden</dt>
                          <dd>{item.orden}</dd>
                        </div>
                      </dl>
                    </div>
                    <div className="option-group-modal__row-actions">
                      <button
                        aria-label={`Editar opcion ${item.nombre}`}
                        className="button button--ghost button--compact"
                        type="button"
                        onClick={() => openEditForm(item)}
                      >
                        Editar
                      </button>
                      <button
                        aria-label={
                          item.activo
                            ? `Desactivar opcion ${item.nombre}`
                            : `Activar opcion ${item.nombre}`
                        }
                        className={`button button--compact ${
                          item.activo ? 'button--warning' : 'button--success'
                        }`}
                        disabled={isPending}
                        type="button"
                        onClick={() => void handleToggle(item)}
                      >
                        {isPending
                          ? 'Actualizando...'
                          : item.activo
                            ? 'Desactivar'
                            : 'Activar'}
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : null}

          {subFormMode !== 'closed' ? (
            <form
              aria-labelledby={`${titleId}-form-title`}
              className="option-group-modal__form"
              data-testid={isEditing ? 'edit-option-form' : 'add-option-form'}
              onSubmit={(event) => void handleSubFormSubmit(event)}
            >
              <h3 id={`${titleId}-form-title`} className="option-group-modal__form-title">
                {isEditing ? 'Editar opcion' : 'Nueva opcion'}
              </h3>
              <div className="form-grid">
                <label className="field" htmlFor={`${titleId}-codigo`}>
                  <span>Codigo</span>
                  <input
                    aria-label="Codigo de la opcion"
                    className="input"
                    disabled={isEditing}
                    id={`${titleId}-codigo`}
                    placeholder="Ej. A"
                    required={!isEditing}
                    type="text"
                    value={subForm.codigo}
                    onChange={(event) => handleSubFormChange('codigo', event.target.value)}
                  />
                  {fieldErrors.codigo ? (
                    <small className="field__error">{fieldErrors.codigo}</small>
                  ) : null}
                </label>
                <label className="field" htmlFor={`${titleId}-nombre`}>
                  <span>Nombre</span>
                  <input
                    aria-label="Nombre de la opcion"
                    className="input"
                    id={`${titleId}-nombre`}
                    placeholder="Ej. Opcion A"
                    required
                    type="text"
                    value={subForm.nombre}
                    onChange={(event) => handleSubFormChange('nombre', event.target.value)}
                  />
                  {fieldErrors.nombre ? (
                    <small className="field__error">{fieldErrors.nombre}</small>
                  ) : null}
                </label>
                <label className="field" htmlFor={`${titleId}-valor`}>
                  <span>Valor</span>
                  <input
                    aria-label="Valor de la opcion"
                    className="input"
                    id={`${titleId}-valor`}
                    placeholder="Ej. a"
                    required
                    type="text"
                    value={subForm.valor}
                    onChange={(event) => handleSubFormChange('valor', event.target.value)}
                  />
                  {fieldErrors.valor ? (
                    <small className="field__error">{fieldErrors.valor}</small>
                  ) : null}
                </label>
                <label className="field" htmlFor={`${titleId}-orden`}>
                  <span>Orden</span>
                  <input
                    aria-label="Orden de la opcion"
                    className="input"
                    id={`${titleId}-orden`}
                    min={0}
                    placeholder="Opcional"
                    type="number"
                    value={subForm.orden}
                    onChange={(event) => handleSubFormChange('orden', event.target.value)}
                  />
                  {fieldErrors.orden ? (
                    <small className="field__error">{fieldErrors.orden}</small>
                  ) : null}
                </label>
                <label className="field field--full checkbox-pill" htmlFor={`${titleId}-activo`}>
                  <input
                    checked={subForm.activo}
                    id={`${titleId}-activo`}
                    type="checkbox"
                    onChange={(event) => handleSubFormChange('activo', event.target.checked)}
                  />
                  <span>Activo</span>
                </label>
                {formError ? (
                  <div className="form-error field--full">{formError}</div>
                ) : null}
                <div className="form-actions field--full">
                  <button
                    className="button button--ghost"
                    disabled={formLoading}
                    type="button"
                    onClick={closeSubForm}
                  >
                    Cancelar
                  </button>
                  <button
                    className="button"
                    data-testid="save-option-button"
                    disabled={formLoading}
                    type="submit"
                  >
                    {formLoading ? 'Guardando...' : 'Guardar'}
                  </button>
                </div>
              </div>
            </form>
          ) : null}
        </div>

        <footer className="option-group-modal__footer">
          {subFormMode === 'closed' ? (
            <button
              className="button"
              data-testid="add-option-button"
              disabled={listLoading}
              type="button"
              onClick={openCreateForm}
            >
              Agregar opcion
            </button>
          ) : (
            <span className="option-group-modal__footer-hint">
              Completa el formulario para guardar.
            </span>
          )}
        </footer>
      </div>
    </div>
  )
}
