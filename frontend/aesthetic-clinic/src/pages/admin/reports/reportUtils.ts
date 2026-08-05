/**
 * Helpers shared by the four `/cms/reportes/*` pages.
 */

/**
 * Convert a branch display name (e.g. "Sucursal Principal") into a
 * filesystem-safe slug used for the exported XLSX filename
 * (`clientes_<slug>.xlsx`, `prospectos_<slug>.xlsx`).
 *
 * - lowercases the input
 * - strips diacritics so "Gestión" becomes "gestion"
 * - replaces any run of non-alphanumeric chars with a single underscore
 * - falls back to `general` when the result is empty
 */
export function branchNameToSlug(name: string | null | undefined): string {
  if (!name) return 'general'
  const normalized = name
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return normalized || 'general'
}

const REPORT_DATE_FORMATTER = new Intl.DateTimeFormat('es-BO', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'America/La_Paz',
})

/**
 * Format an ISO 8601 datetime string into a human-readable label such as
 * "04/08/2026 15:30" using the project's locale (es-BO, America/La_Paz).
 * Returns a dash for null / invalid values so the table stays uniform.
 */
export function formatReportDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '-'
  try {
    return REPORT_DATE_FORMATTER.format(parsed)
  } catch {
    return '-'
  }
}

/**
 * Build a `ReportTableColumn.render` function for an ISO 8601 datetime cell.
 * Centralised so every page renders the same value in the same format.
 */
export function dateTimeCell(key: string) {
  return (row: Record<string, unknown>) => {
    const raw = row[key]
    return formatReportDateTime(typeof raw === 'string' ? raw : null)
  }
}