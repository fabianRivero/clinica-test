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