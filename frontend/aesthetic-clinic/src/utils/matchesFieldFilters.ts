/**
 * Generic AND-tokenized filter helper for client-side list filtering.
 *
 * Semantics:
 *   - AND across fields: every non-empty field filter must match.
 *   - Within a field with `type: "tokenized"`: the value is split on whitespace
 *     and every token must appear as a case-insensitive substring of the
 *     target. This mirrors `AdminClientsPage.matchesTokens`.
 *   - Within a field with `type: "includes"`: the value must appear as a
 *     case-insensitive substring of the target. Use this for short IDs
 *     (e.g. `CLI-0007`) or formatted strings where tokenization is undesirable.
 *   - Empty filter values are skipped (field is treated as inactive).
 *   - Empty target values fail any non-empty filter for that field.
 */

export type FieldMatchType = 'tokenized' | 'includes'

export type FieldDef = {
  key: string
  type: FieldMatchType
}

export type FieldFilters = Record<string, string>

export function matchesFieldFilters<T extends Record<string, unknown>>(
  item: T,
  filters: FieldFilters,
  fieldsByKey: Record<string, FieldDef>,
): boolean {
  return Object.entries(filters).every(([key, raw]) => {
    const value = (raw ?? '').trim()
    if (!value) return true
    const def = fieldsByKey[key]
    if (!def) return true
    const target = String(item[key] ?? '').toLowerCase()
    const v = value.toLowerCase()
    if (def.type === 'tokenized') {
      return v.split(/\s+/).every((token) => target.includes(token))
    }
    return target.includes(v)
  })
}
