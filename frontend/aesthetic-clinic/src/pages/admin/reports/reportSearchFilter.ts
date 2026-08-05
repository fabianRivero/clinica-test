/**
 * Lower-case substring match across the supplied keys. Returns `true` when
 * `value` is empty so the page does not filter rows when the user clears
 * the input.
 */
export function matchesReportSearch(
  value: string,
  row: Record<string, unknown>,
  keys: readonly string[],
): boolean {
  const normalized = value.trim().toLowerCase()
  if (!normalized) return true
  return keys.some((key) => {
    const raw = row[key]
    if (raw === null || raw === undefined) return false
    return String(raw).toLowerCase().includes(normalized)
  })
}