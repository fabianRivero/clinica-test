/**
 * Stateless multi-input search grid.
 *
 * Renders N labeled `<input type="search">` fields inside a `form-grid` whose
 * modifier class is controlled by `gridClassName` (defaults to
 * `form-grid--five` to match `AdminClientsPage`). The component is fully
 * controlled: the parent owns `values` and merges updates via `onChange`.
 *
 * Using a stable id derived from `field.key` keeps React happy across renders
 * and avoids `useId()` allocations inside the `.map`.
 */

import { useId } from 'react'

export type MultiFieldSearchField = {
  key: string
  label: string
  placeholder?: string
}

type MultiFieldSearchProps = {
  fields: ReadonlyArray<MultiFieldSearchField>
  values: Record<string, string>
  onChange: (key: string, value: string) => void
  gridClassName?: string
}

export function MultiFieldSearch({
  fields,
  values,
  onChange,
  gridClassName = 'form-grid--five',
}: MultiFieldSearchProps) {
  const baseId = useId()
  return (
    <div className={`form-grid ${gridClassName}`}>
      {fields.map((field) => {
        const inputId = `${baseId}-${field.key}`
        return (
          <label key={field.key} className="field" htmlFor={inputId}>
            <span>{field.label}</span>
            <input
              id={inputId}
              className="input"
              type="search"
              autoComplete="off"
              placeholder={field.placeholder}
              aria-label={field.label}
              value={values[field.key] ?? ''}
              onChange={(event) => onChange(field.key, event.target.value)}
            />
          </label>
        )
      })}
    </div>
  )
}
