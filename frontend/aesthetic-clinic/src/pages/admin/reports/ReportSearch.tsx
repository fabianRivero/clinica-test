import { useId } from 'react'

type ReportSearchProps = {
  /** Free-text search term. Updated via `onChange`. */
  value: string
  onChange: (next: string) => void
  /** Placeholder string for the input. */
  placeholder: string
  /** Accessible label, also used as the input's aria-label. */
  label: string
}

/**
 * Lightweight search input used by every page under `/cms/reportes/*`
 * that supports text filtering (currently clients and prospects).
 *
 * Filtering happens client-side over the dataset the page already loaded.
 * The component does not own the filter pipeline; pages pair it with
 * `matchesReportSearch` from `./reportSearchFilter`.
 *
 * Kept intentionally minimal so it matches the rest of the admin area's
 * search inputs (e.g. `AdminClientsPage.tsx`'s "Buscar cliente" field).
 */
export function ReportSearch({ value, onChange, placeholder, label }: ReportSearchProps) {
  const inputId = useId()
  return (
    <label className="field" htmlFor={inputId} style={{ marginBottom: '0.75rem' }}>
      <span>{label}</span>
      <input
        id={inputId}
        className="input"
        type="search"
        placeholder={placeholder}
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete="off"
        maxLength={120}
      />
    </label>
  )
}