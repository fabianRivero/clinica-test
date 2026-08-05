import { useCallback, type ReactNode } from 'react'
import * as XLSX from 'xlsx'

export type ReportTableColumn = {
  key: string
  label: string
  render?: (row: Record<string, unknown>) => ReactNode
}

type ReportTableProps = {
  columns: ReportTableColumn[]
  rows: Record<string, unknown>[]
  filename: string
  sheetName?: string
  exportLabel?: string
  /** When true, link-shaped cells get a `HYPERLINK` formula in the exported sheet. */
  withHyperlinks?: boolean
}

/**
 * Generic, read-only report table shared by every page under
 * `/cms/reportes/*`. Renders `rows` with the column definitions supplied by
 * the page (mirroring the column shape used by `AdminExpenseListPage.tsx`)
 * and exposes an XLSX export button.
 *
 * Export behaviour (mirrors `AdminExpenseListPage.tsx`):
 *   - `XLSX.utils.json_to_sheet` + `XLSX.utils.book_new` +
 *     `XLSX.utils.book_append_sheet` + `XLSX.writeFile`.
 *   - When a cell produced by `column.render` is an `<a href="...">`, OR
 *     when the row carries an `invoiceUrl`/`invoiceName` field, the worksheet
 *     gets a `HYPERLINK(...)` formula so Excel renders a clickable link.
 *   - The export button is hidden when there are no rows (existing convention).
 */
export function ReportTable({
  columns,
  rows,
  filename,
  sheetName = 'Reporte',
  exportLabel = '↓ Excel',
  withHyperlinks = true,
}: ReportTableProps) {
  const extractHyperlink = (row: Record<string, unknown>): string | null => {
    const invoiceUrl = row.invoiceUrl
    if (typeof invoiceUrl === 'string' && invoiceUrl.trim().length > 0) {
      return invoiceUrl
    }
    return null
  }

  const exportToExcel = useCallback(() => {
    if (!rows.length) return

    const aoa: (string | number)[][] = []
    aoa.push(columns.map((column) => column.label))

    rows.forEach((row) => {
      const rowOut: string[] = columns.map((column) => {
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
        const excelRow = rowIndex + 2
        const link = extractHyperlink(row)
        if (link) {
          const labelField = typeof row.invoiceName === 'string' && row.invoiceName
            ? row.invoiceName
            : 'Ver factura'
          const targetCell = ws[XLSX.utils.encode_cell({ r: excelRow - 1, c: 0 })]
          // Build a HYPERLINK formula Excel recognizes and renders as clickable.
          targetCell.f = `HYPERLINK("${link.replace(/"/g, '""')}","${labelField.replace(/"/g, '""')}")`
          targetCell.t = 's'
        }
      })
    }

    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, sheetName.slice(0, 31) || 'Reporte')
    XLSX.writeFile(wb, filename)
  }, [columns, rows, filename, sheetName, withHyperlinks])

  if (!rows.length) {
    return null
  }

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.75rem' }}>
        <button
          className="button button--ghost"
          style={{ minWidth: '4.5rem', minHeight: '2.6rem', padding: '0 0.75rem' }}
          type="button"
          onClick={exportToExcel}
          title="Descargar Excel"
        >
          {exportLabel}
        </button>
      </div>
      <div className="table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key}>{column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {columns.map((column) => {
                  const raw = (row as Record<string, unknown>)[column.key]
                  const rendered = column.render
                    ? column.render(row)
                    : raw === null || raw === undefined
                      ? ''
                      : String(raw)
                  return <td key={column.key}>{rendered as ReactNode}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
