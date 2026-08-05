import type { ReactNode } from 'react'

export type ReportTableColumn = {
  key: string
  label: string
  render?: (row: Record<string, unknown>) => ReactNode
}

type ReportTableProps = {
  columns: ReportTableColumn[]
  rows: Record<string, unknown>[]
}

/**
 * Generic, read-only report table shared by every page under
 * `/cms/reportes/*`. Renders `rows` with the column definitions supplied by
 * the page, mirroring the table shape used by `AdminExpenseListPage.tsx`:
 *   - `table-wrapper expense-table-wrapper` outer wrapper for horizontal scroll.
 *   - `admin-table admin-table--expenses` modifiers, which provide the same
 *     column widths, padding, and uppercase header styling as the gastos list.
 *
 * The XLSX export button is rendered by `ReportLayout`'s header so it can sit
 * inside the same `expense-period-controls` cluster used in
 * `AdminExpenseListPage.tsx`. The export logic lives in
 * `useReportExcelExport`.
 */
export function ReportTable({ columns, rows }: ReportTableProps) {
  if (!rows.length) {
    return null
  }

  return (
    <div className="table-wrapper expense-table-wrapper">
      <table className="admin-table admin-table--expenses">
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
  )
}