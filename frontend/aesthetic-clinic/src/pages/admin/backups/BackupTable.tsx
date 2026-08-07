import { useMemo } from 'react'
import type { ReactNode } from 'react'

import { StatusBadge } from '../../../components/admin/StatusBadge'
import type { BackupFile } from '../../../types/admin'
import { adminBackupDownloadLink } from '../../../services/api/admin'

type BackupTableProps = {
  rows: BackupFile[]
  /**
   * The filename currently being deleted, if any. Used so the table can
   * disable only the affected row's button while a sibling action is in
   * flight.
   */
  pendingDeleteName: string | null
  onRequestDelete: (row: BackupFile) => void
}

const BACKUP_DATE_FORMATTER = new Intl.DateTimeFormat('es-BO', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'America/La_Paz',
})

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / Math.pow(1024, exponent)
  const decimals = exponent === 0 ? 0 : value >= 100 ? 0 : value >= 10 ? 1 : 2
  return `${value.toFixed(decimals)} ${units[exponent]}`
}

function formatBackupDate(modifiedAt: string): string {
  if (!modifiedAt) return '-'
  const parsed = new Date(modifiedAt)
  if (Number.isNaN(parsed.getTime())) return '-'
  try {
    return BACKUP_DATE_FORMATTER.format(parsed)
  } catch {
    return '-'
  }
}

/**
 * Read-only table mirroring the look of `ReportTable`: same `table-wrapper
 * expense-table-wrapper` wrapper, same `admin-table admin-table--expenses`
 * modifiers so the column widths and uppercase headers stay consistent with
 * the rest of the admin area. Renders nothing when there are zero rows so
 * the page can show a `DataState` empty card instead.
 */
export function BackupTable({ rows, pendingDeleteName, onRequestDelete }: BackupTableProps) {
  const hasRows = rows.length > 0

  const headerCells = useMemo<{ key: keyof BackupFile | 'actions'; label: string }[]>(
    () => [
      { key: 'name', label: 'Nombre' },
      { key: 'size', label: 'Tamaño' },
      { key: 'modifiedAt', label: 'Fecha' },
      { key: 'ageLabel', label: 'Hace' },
      { key: 'isWeekly', label: 'Tipo' },
      { key: 'actions', label: 'Acciones' },
    ],
    [],
  )

  if (!hasRows) return null

  return (
    <div className="table-wrapper expense-table-wrapper">
      <table className="admin-table admin-table--expenses">
        <thead>
          <tr>
            {headerCells.map((cell) => (
              <th key={cell.key}>{cell.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const rowKey = row.id || row.name
            const isDeleting = pendingDeleteName === rowKey
            return (
              <tr key={rowKey}>
                <td className="_white-space-no-wrap" title={row.name}>
                  {row.name}
                </td>
                <td>{formatBytes(row.size)}</td>
                <td>{formatBackupDate(row.modifiedAt)}</td>
                <td>{row.ageLabel || '-'}</td>
                <td>
                  {row.isWeekly ? (
                    <StatusBadge tone="primary">Semanal</StatusBadge>
                  ) : (
                    <StatusBadge tone="neutral">Diario</StatusBadge>
                  )}
                </td>
                <td>
                  <div className="_flex _flex-gap-sm">
                    <a
                      aria-label={`Descargar respaldo ${row.name}`}
                      className="button button--ghost button--compact"
                      data-testid={`backup-download-${rowKey}`}
                      download={row.name}
                      href={adminBackupDownloadLink(row.name)}
                    >
                      Descargar
                    </a>
                    <button
                      aria-label={`Eliminar respaldo ${row.name}`}
                      className="button button--danger button--compact"
                      data-testid={`backup-delete-${rowKey}`}
                      disabled={isDeleting}
                      type="button"
                      onClick={() => onRequestDelete(row)}
                    >
                      {isDeleting ? 'Eliminando...' : 'Eliminar'}
                    </button>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  ) as ReactNode
}
