import * as XLSX from 'xlsx'

import type { ReportTableColumn } from './ReportTable'

/**
 * Builds an Excel export handler for a read-only report page.
 *
 * Mirrors the export behaviour from `AdminExpenseListPage.tsx`:
 *   - `XLSX.utils.aoa_to_sheet` + `XLSX.utils.book_new` +
 *     `XLSX.utils.book_append_sheet` + `XLSX.writeFile`.
 *   - When the row carries an `invoiceUrl`/`invoiceName` field, the worksheet
 *     gets a `HYPERLINK(...)` formula so Excel renders a clickable link.
 *
 * Pages pass the result of this helper to `ReportLayout`'s `buildExport`
 * prop. The layout renders the same `↓ Excel` button used in
 * `AdminExpenseListPage.tsx`.
 */
export function buildReportExcelExport({
  columns,
  rows,
  filename,
  sheetName = 'Reporte',
  withHyperlinks = true,
}: {
  columns: ReportTableColumn[]
  rows: Record<string, unknown>[]
  filename: string
  sheetName?: string
  withHyperlinks?: boolean
}): () => void {
  return () => {
    if (!rows.length) return

    const aoa: (string | number)[][] = []
    aoa.push(columns.map((column) => column.label))

    rows.forEach((row) => {
      const rowOut: (string | number)[] = columns.map((column) => {
        const value = (row as Record<string, unknown>)[column.key]
        if (value === null || value === undefined) return ''
        if (typeof value === 'string' || typeof value === 'number') {
          return value as string | number
        }
        if (typeof value === 'boolean') return value ? 'Sí' : 'No'
        return String(value)
      })

      aoa.push(rowOut)
    })

    const ws = XLSX.utils.aoa_to_sheet(aoa)

    if (withHyperlinks) {
      rows.forEach((row, rowIndex) => {
        const invoiceUrl = row.invoiceUrl
        if (typeof invoiceUrl !== 'string' || invoiceUrl.trim().length === 0) {
          return
        }
        const excelRow = rowIndex + 2
        const labelField =
          typeof row.invoiceName === 'string' && row.invoiceName
            ? row.invoiceName
            : 'Ver factura'
        const targetCell = ws[XLSX.utils.encode_cell({ r: excelRow - 1, c: 0 })]
        // Build a HYPERLINK formula Excel recognizes and renders as clickable.
        targetCell.f = `HYPERLINK("${invoiceUrl.replace(/"/g, '""')}","${labelField.replace(/"/g, '""')}")`
        targetCell.t = 's'
      })
    }

    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, sheetName.slice(0, 31) || 'Reporte')
    XLSX.writeFile(wb, filename)
  }
}