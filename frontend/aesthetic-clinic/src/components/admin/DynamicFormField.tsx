import { FieldError } from './FieldError'

type DynamicFormFieldProps = {
  field: {
    id: number
    label: string
    type: string
    allowsDetail?: boolean
    options: Array<{ id: number; name: string; value: string }>
  }
  value: string | boolean | string[] | number[] | null
  detailValue?: string
  onChange: (value: string | boolean | string[] | number[] | null) => void
  onDetailChange?: (detail: string) => void
  error?: string | null
}

export function DynamicFormField({
  field,
  value,
  detailValue,
  onChange,
  onDetailChange,
  error,
}: DynamicFormFieldProps) {
  const detailInput = field.allowsDetail ? (
    <textarea
      className="input textarea"
      rows={3}
      value={detailValue ?? ''}
      onChange={(event) => onDetailChange?.(event.target.value)}
      placeholder="Detalle adicional"
    />
  ) : null

  if (field.type === 'TEXTO') {
    return (
      <label className="field field--full" key={field.id}>
        <span>
          {field.label} <span style={{ color: 'var(--color-danger)' }}>*</span>
        </span>
        <input
          className="input"
          value={String(value ?? '')}
          onChange={(event) => onChange(event.target.value)}
        />
        <FieldError message={error} />
        {detailInput}
      </label>
    )
  }

  if (field.type === 'NUMERO') {
    return (
      <label className="field" key={field.id}>
        <span>
          {field.label} <span style={{ color: 'var(--color-danger)' }}>*</span>
        </span>
        <input
          className="input"
          type="number"
          value={String(value ?? '')}
          onChange={(event) => onChange(event.target.value)}
        />
        <FieldError message={error} />
        {detailInput}
      </label>
    )
  }

  if (field.type === 'FECHA') {
    return (
      <label className="field" key={field.id}>
        <span>
          {field.label} <span style={{ color: 'var(--color-danger)' }}>*</span>
        </span>
        <input
          className="input"
          type="date"
          value={String(value ?? '')}
          onChange={(event) => onChange(event.target.value)}
        />
        <FieldError message={error} />
        {detailInput}
      </label>
    )
  }

  if (field.type === 'BOOLEANO') {
    return (
      <label className="field" key={field.id}>
        <span>
          {field.label} <span style={{ color: 'var(--color-danger)' }}>*</span>
        </span>
        <select
          className="input"
          value={value === null || value === undefined ? '' : value ? 'true' : 'false'}
          onChange={(event) =>
            onChange(
              event.target.value === '' ? null : event.target.value === 'true',
            )
          }
        >
          <option value="">Seleccionar</option>
          <option value="true">Si</option>
          <option value="false">No</option>
        </select>
        <FieldError message={error} />
        {detailInput}
      </label>
    )
  }

  if (field.type === 'SELECCION') {
    const selectedIds = Array.isArray(value) ? value.map(v => typeof v === 'string' ? parseInt(v, 10) : v) : []
    return (
      <label className="field" key={field.id}>
        <span>
          {field.label} <span style={{ color: 'var(--color-danger)' }}>*</span>
        </span>
        <select
          className="input"
          value={selectedIds[0] ? String(selectedIds[0]) : ''}
          onChange={(event) =>
            onChange(event.target.value ? [Number(event.target.value)] : [])
          }
        >
          <option value="">Seleccionar</option>
          {field.options.map((option) => (
            <option key={option.id} value={option.id}>
              {option.name}
            </option>
          ))}
        </select>
        <FieldError message={error} />
        {detailInput}
      </label>
    )
  }

  // MULTISELECCION
  const selectedIds = Array.isArray(value) ? value.map(v => typeof v === 'string' ? parseInt(v, 10) : v) : []
  return (
    <div className="field field--full" key={field.id}>
      <span>
        {field.label} <span style={{ color: 'var(--color-danger)' }}>*</span>
      </span>
      <div className="checkbox-grid">
        {field.options.map((option) => {
          const checked = selectedIds.includes(option.id)
          return (
            <label className="checkbox-pill" key={option.id}>
              <input
                checked={checked}
                type="checkbox"
                onChange={(event) =>
                  onChange(
                    event.target.checked
                      ? [...selectedIds, option.id]
                      : selectedIds.filter((item) => item !== option.id),
                  )
                }
              />
              <span>{option.name}</span>
            </label>
          )
        })}
      </div>
      <FieldError message={error} />
      {detailInput}
    </div>
  )
}