import { useMemo, useState, type FormEvent } from 'react'

import { AdminCatalogTabs } from '../../components/admin/AdminCatalogTabs'
import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useDebounce } from '../../hooks/useDebounce'
import { useNotifications } from '../../providers/NotificationProvider'
import {
  createAdminCatalogItem,
  getAdminCatalogDetail,
  updateAdminCatalogItem,
  updateAdminCatalogItemState,
} from '../../services/api/admin'
import type {
  AdminCatalogEntry,
  AdminCatalogFieldDefinition,
  AdminCatalogFormValue,
  AdminCatalogKey,
} from '../../types/admin'

const catalogFallbackInfo: Record<
  AdminCatalogKey,
  { title: string; description: string; createLabel: string }
> = {
  'todos-los-servicios': {
    title: 'Todos los servicios',
    description:
      'Administra cada servicio disponible con su precio base y el procedimiento estético asociado.',
    createLabel: 'Crear servicio',
  },
  'procedimientos-esteticos': {
    title: 'Procedimientos estéticos',
    description:
      'Gestiona procedimientos específicos que luego puedes vincular a servicios y fichas clínicas.',
    createLabel: 'Crear procedimiento',
  },
  'tipos-servicio': {
    title: 'Tipos de servicio',
    description:
      'Administra las categorías comerciales visibles al registrar operaciones y configuraciones de servicio.',
    createLabel: 'Crear tipo de servicio',
  },
  'tipos-procedimiento': {
    title: 'Tipos de procedimiento',
    description:
      'Administra los tipos de procedimiento estetico disponibles para asociar a los procedimientos.',
    createLabel: 'Crear tipo de procedimiento',
  },
  'campos-ficha': {
    title: 'Campos de ficha',
    description:
      'Configura preguntas y respuestas visibles en las fichas clínicas por procedimiento.',
    createLabel: 'Crear campo de ficha',
  },
  'patologias-cutaneas': {
    title: 'Patologías cutaneas',
    description: 'Mantiene actualizado el catálogo de patologías usadas en el análisis estético.',
    createLabel: 'Crear patología cutanea',
  },
  especialidades: {
    title: 'Especialidades',
    description: 'Define las especialidades que puede tener el equipo operativo y médico.',
    createLabel: 'Crear especialidad',
  },
  'categorias-gasto': {
    title: 'Categorías de gasto',
    description: 'Define las categorías usadas para clasificar gastos de cada sucursal.',
    createLabel: 'Crear categoría',
  },
  'grupos-opciones': {
    title: 'Grupos de opciones',
    description:
      'Agrupa respuestas reutilizables para campos de seleccion y otros formularios configurables.',
    createLabel: 'Crear grupo de opciones',
  },
}

function buildEmptyForm(fields: AdminCatalogFieldDefinition[]) {
  return fields.reduce<Record<string, AdminCatalogFormValue>>((accumulator, field) => {
    if (field.inputType === 'checkbox') {
      accumulator[field.name] = false
      return accumulator
    }

    accumulator[field.name] = ''
    return accumulator
  }, {})
}

function buildFormState(
  fields: AdminCatalogFieldDefinition[],
  values?: Record<string, AdminCatalogFormValue>,
) {
  const emptyState = buildEmptyForm(fields)

  if (!values) {
    return emptyState
  }

  return fields.reduce<Record<string, AdminCatalogFormValue>>((accumulator, field) => {
    const value = values[field.name]
    if (field.inputType === 'checkbox') {
      accumulator[field.name] = Boolean(value)
      return accumulator
    }

    accumulator[field.name] = value ?? ''
    return accumulator
  }, emptyState)
}

function serializePayload(
  fields: AdminCatalogFieldDefinition[],
  formState: Record<string, AdminCatalogFormValue>,
) {
  return fields.reduce<Record<string, unknown>>((accumulator, field) => {
    const rawValue = formState[field.name]

    if (field.inputType === 'checkbox') {
      accumulator[field.name] = Boolean(rawValue)
      return accumulator
    }

    if (field.valueType === 'number') {
      if (rawValue === '' || rawValue === null || typeof rawValue === 'undefined') {
        accumulator[field.name] = null
        return accumulator
      }
      accumulator[field.name] = Number(rawValue)
      return accumulator
    }

    accumulator[field.name] = typeof rawValue === 'string' ? rawValue.trim() : rawValue ?? ''
    return accumulator
  }, {})
}

function isTruthyFieldError(error: unknown): error is Error & { fieldErrors?: Record<string, string> } {
  return Boolean(error && typeof error === 'object' && 'fieldErrors' in error)
}

function CatalogFormField({
  field,
  value,
  error,
  onChange,
}: {
  field: AdminCatalogFieldDefinition
  value: AdminCatalogFormValue
  error?: string
  onChange: (fieldName: string, nextValue: AdminCatalogFormValue) => void
}) {
  const fieldId = `catalog-field-${field.name}`
  const inputValue = typeof value === 'string' || typeof value === 'number' ? String(value) : ''

  if (field.inputType === 'checkbox') {
    return (
      <label className="field field--full checkbox-pill" htmlFor={fieldId}>
        <input
          id={fieldId}
          checked={Boolean(value)}
          type="checkbox"
          onChange={(event) => onChange(field.name, event.target.checked)}
        />
        <span>{field.label}</span>
        {error ? <small className="field__error">{error}</small> : null}
      </label>
    )
  }

  if (field.inputType === 'textarea') {
    return (
      <label className="field field--full" htmlFor={fieldId}>
        <span>{field.label}</span>
        <textarea
          id={fieldId}
          className="input textarea textarea--compact"
          placeholder={field.placeholder}
          value={inputValue}
          onChange={(event) => onChange(field.name, event.target.value)}
        />
        {field.hint ? <small className="field__hint">{field.hint}</small> : null}
        {error ? <small className="field__error">{error}</small> : null}
      </label>
    )
  }

  if (field.inputType === 'select') {
    return (
      <label className="field" htmlFor={fieldId}>
        <span>{field.label}</span>
        <select
          id={fieldId}
          className="input"
          value={inputValue}
          onChange={(event) => {
            if (event.target.value === '') {
              onChange(field.name, '')
              return
            }
            if (field.valueType === 'number') {
              onChange(field.name, Number(event.target.value))
              return
            }
            onChange(field.name, event.target.value)
          }}
        >
          <option value="">
            {field.allowEmpty ? 'Sin seleccionar' : 'Selecciona una opción'}
          </option>
          {field.options?.map((option) => (
            <option key={`${field.name}-${option.value}`} value={option.value}>
              {option.secondaryLabel ? `${option.label} · ${option.secondaryLabel}` : option.label}
            </option>
          ))}
        </select>
        {field.hint ? <small className="field__hint">{field.hint}</small> : null}
        {error ? <small className="field__error">{error}</small> : null}
      </label>
    )
  }

  return (
    <label className="field" htmlFor={fieldId}>
      <span>{field.label}</span>
      <input
        id={fieldId}
        className="input"
        min={field.minValue}
        placeholder={field.placeholder}
        type={field.inputType === 'number' ? 'number' : 'text'}
        value={inputValue}
        onChange={(event) => onChange(field.name, event.target.value)}
      />
      {field.hint ? <small className="field__hint">{field.hint}</small> : null}
      {error ? <small className="field__error">{error}</small> : null}
    </label>
  )
}

function CatalogEditorForm({
  catalogKey,
  fields,
  editingItem,
  createLabel,
  onCancelEditing,
  onSaved,
}: {
  catalogKey: AdminCatalogKey
  fields: AdminCatalogFieldDefinition[]
  editingItem: AdminCatalogEntry | null
  createLabel: string
  onCancelEditing: () => void
  onSaved: () => void
}) {
  const { showNotification } = useNotifications()
  const [formState, setFormState] = useState<Record<string, AdminCatalogFormValue>>(() =>
    buildFormState(fields, editingItem?.values),
  )
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [isSubmitting, setIsSubmitting] = useState(false)

  function handleFieldChange(fieldName: string, nextValue: AdminCatalogFormValue) {
    setFormState((current) => ({
      ...current,
      [fieldName]: nextValue,
    }))
    setFieldErrors((current) => {
      if (!current[fieldName]) {
        return current
      }
      const nextErrors = { ...current }
      delete nextErrors[fieldName]
      return nextErrors
    })
  }

  function resetCreateForm() {
    setFormState(buildFormState(fields))
    setFieldErrors({})
    setSubmitError(null)
  }

  function handleCancel() {
    if (editingItem) {
      onCancelEditing()
      return
    }
    resetCreateForm()
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSubmitting(true)
    setSubmitError(null)
    setFieldErrors({})

    try {
      const payload = serializePayload(fields, formState)
      if (editingItem) {
        await updateAdminCatalogItem(catalogKey, editingItem.id, payload)
        showNotification({
          title: 'Catálogo actualizado',
          message: 'Los cambios se guardaron corréctamente.',
          tone: 'success',
        })
      } else {
        await createAdminCatalogItem(catalogKey, payload)
        showNotification({
          title: 'Registro creado',
          message: 'El nuevo elemento del catálogo ya esta disponible.',
          tone: 'success',
        })
      }
      onSaved()
    } catch (error) {
      if (isTruthyFieldError(error) && error.fieldErrors) {
        setFieldErrors(error.fieldErrors)
      }
      const message =
        error instanceof Error ? error.message : 'No se pudo guardar el registro.'
      setSubmitError(message)
      showNotification({
        title: 'No se pudo guardar',
        message,
        tone: 'danger',
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <SectionCard
      eyebrow="Edicion"
      title={editingItem ? `Editar: ${editingItem.title}` : createLabel}
      description="Guarda cambios sobre este catálogo sin salir de la pantalla."
    >
      <form className="form-grid" onSubmit={(event) => void handleSubmit(event)}>
        {fields.map((field) => (
          <CatalogFormField
            key={field.name}
            error={fieldErrors[field.name]}
            field={field}
            value={formState[field.name] ?? (field.inputType === 'checkbox' ? false : '')}
            onChange={handleFieldChange}
          />
        ))}

        {submitError ? <div className="form-error field--full">{submitError}</div> : null}

        <div className="form-actions field--full">
          {editingItem ? (
            <button className="button button--ghost" type="button" onClick={handleCancel}>
              Cancelar edicion
            </button>
          ) : null}
          <button className="button" disabled={isSubmitting} type="submit">
            {isSubmitting
              ? 'Guardando...'
              : editingItem
                ? 'Guardar cambios'
                : createLabel}
          </button>
        </div>
      </form>
    </SectionCard>
  )
}

function CatalogPage({ catalogKey }: { catalogKey: AdminCatalogKey }) {
  const [searchQuery, setSearchQuery] = useState('')
  const [activeFilter, setActiveFilter] = useState<'all' | 'true' | 'false'>('all')
  const debouncedQuery = useDebounce(searchQuery, 300)

  const loader = useMemo(
    () => () =>
      getAdminCatalogDetail(catalogKey, {
        q: debouncedQuery,
        active: activeFilter,
      }),
    [catalogKey, debouncedQuery, activeFilter],
  )
  const { data, isLoading, error, reload } = useApiResource(loader)
  const { showNotification } = useNotifications()
  const [editingItemId, setEditingItemId] = useState<number | null>(null)
  const [editorVersion, setEditorVersion] = useState(0)

  const pageInfo = data?.catalog ?? catalogFallbackInfo[catalogKey]
  const editingItem = data?.items.find((item) => item.id === editingItemId) ?? null

  async function handleToggleItemState(item: AdminCatalogEntry) {
    try {
      await updateAdminCatalogItemState(catalogKey, item.id, {
        active: !item.active,
      })
      showNotification({
        title: item.active ? 'Registro desactivado' : 'Registro reactivado',
        message: item.active
          ? 'El elemento ya no aparecera como disponible para nuevas configuraciones.'
          : 'El elemento volvio a quedar activo para nuevas configuraciones.',
        tone: 'success',
      })
      if (editingItemId === item.id && item.active) {
        setEditingItemId(null)
      }
      reload()
    } catch (error) {
      showNotification({
        title: 'No se pudo cambiar el estado',
        message:
          error instanceof Error ? error.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  const pageActions = [
    {
      label: editingItem ? 'Cancelar edicion' : pageInfo.createLabel,
      variant: (editingItem ? 'ghost' : 'primary') as 'ghost' | 'primary',
      onClick: () => {
        if (editingItem) {
          setEditingItemId(null)
          return
        }
        setEditorVersion((current) => current + 1)
      },
    },
  ]

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Configuracion"
        title={pageInfo.title}
        description={pageInfo.description}
        actions={pageActions}
      />

      <AdminCatalogTabs />

      {isLoading && !data ? (
        <SectionCard title={`Cargando ${pageInfo.title.toLowerCase()}`}>
          <DataState
            title="Sincronizando catálogo"
            message="Estamos cargando la configuración editable desde la base conectada."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar el catálogo">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <>
          <CatalogEditorForm
            key={editingItem ? `edit-${editingItem.id}` : `create-${editorVersion}`}
            catalogKey={catalogKey}
            createLabel={pageInfo.createLabel}
            editingItem={editingItem}
            fields={data.fields}
            onCancelEditing={() => setEditingItemId(null)}
            onSaved={() => {
              setEditingItemId(null)
              setEditorVersion((current) => current + 1)
              reload()
            }}
          />

          <SectionCard
            eyebrow="Catálogo"
            title={`Registros de ${pageInfo.title.toLowerCase()}`}
            description="Edita, desactiva o reactiva registros segun la necesidad operativa."
          >
            <div className="catalog-admin-toolbar">
              <input
                aria-label="Buscar registros"
                className="input"
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Buscar por titulo..."
                type="search"
                value={searchQuery}
              />
              <select
                aria-label="Filtrar por estado"
                className="input"
                onChange={(event) => setActiveFilter(event.target.value as 'all' | 'true' | 'false')}
                value={activeFilter}
              >
                <option value="all">Todos</option>
                <option value="true">Activos</option>
                <option value="false">Inactivos</option>
              </select>
            </div>
            {data.items.length ? (
              <div className="catalog-admin-list">
                {data.items.map((item) => (
                  <article className="catalog-admin-card" key={item.id}>
                    <div className="catalog-admin-card__content">
                      <div className="catalog-admin-card__header">
                        <div>
                          <strong>{item.title}</strong>
                          <p>{item.subtitle}</p>
                        </div>
                        <StatusBadge tone={item.active ? 'success' : 'neutral'}>
                          {item.activeLabel}
                        </StatusBadge>
                      </div>
                      <dl className="catalog-admin-card__meta">
                        {item.metadata.map((meta) => (
                          <div key={`${item.id}-${meta.label}`}>
                            <dt>{meta.label}</dt>
                            <dd>{meta.value}</dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                    <div className="catalog-admin-card__actions">
                      <button
                        className="button button--ghost button--compact"
                        type="button"
                        onClick={() => setEditingItemId(item.id)}
                      >
                        Editar
                      </button>
                      <button
                        className={`button button--compact ${item.active ? 'button--warning' : 'button--success'}`}
                        type="button"
                        onClick={() => void handleToggleItemState(item)}
                      >
                        {item.active ? 'Desactivar' : 'Activar'}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <DataState
                title="Sin registros"
                message="Este catálogo aun no tiene elementos que coincidan con el filtro actual."
              />
            )}
          </SectionCard>
        </>
      ) : null}
    </div>
  )
}

export function AdminProceduresCatalogPage() {
  return <CatalogPage catalogKey="procedimientos-esteticos" />
}

export function AdminAllServicesCatalogPage() {
  return <CatalogPage catalogKey="todos-los-servicios" />
}

export function AdminServiceTypesCatalogPage() {
  return <CatalogPage catalogKey="tipos-servicio" />
}

export function AdminProcedureTypesCatalogPage() {
  return <CatalogPage catalogKey="tipos-procedimiento" />
}

export function AdminFormFieldsCatalogPage() {
  return <CatalogPage catalogKey="campos-ficha" />
}

export function AdminSkinPathologiesCatalogPage() {
  return <CatalogPage catalogKey="patologias-cutaneas" />
}

export function AdminSpecialtiesCatalogPage() {
  return <CatalogPage catalogKey="especialidades" />
}

export function AdminExpenseCategoriesCatalogPage() {
  return <CatalogPage catalogKey="categorias-gasto" />
}

export function AdminOptionGroupsCatalogPage() {
  return <CatalogPage catalogKey="grupos-opciones" />
}
