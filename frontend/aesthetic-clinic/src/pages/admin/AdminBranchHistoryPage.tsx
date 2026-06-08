import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { PageHeader } from '../../components/admin/PageHeader'
import { getAdminBranchAuditLogs } from '../../services/api/admin'

type AuditRow = { id: number; createdAt: string; action: string; detail: string; branchName: string; actor: string }

export function AdminBranchHistoryPage() {
  const [auditRows, setAuditRows] = useState<AuditRow[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        setError(null)
        const audit = await getAdminBranchAuditLogs()
        setAuditRows(audit.items)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'No se pudo cargar historial')
      }
    }
    void load()
  }, [])

  const groupedByMonth = useMemo(() => {
    const groups = new Map<string, AuditRow[]>()
    auditRows.forEach((row) => {
      const date = new Date(row.createdAt)
      const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
      const bucket = groups.get(key) ?? []
      bucket.push(row)
      groups.set(key, bucket)
    })

    return Array.from(groups.entries()).map(([key, rows]) => ({
      key,
      label: new Date(`${key}-01T00:00:00`).toLocaleDateString('es-BO', { month: 'long', year: 'numeric' }),
      rows,
    }))
  }, [auditRows])

  return (
    <section className="page-stack">
      <PageHeader
        eyebrow="Administracion"
        title="Historial completo de sucursales"
        description="Registro completo de cambios administrativos, agrupado por mes."
      />

      <div className="_flex-start">
        <Link className="button button--ghost" to="/cms/sucursales/editar">Volver a editar sucursales</Link>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      {groupedByMonth.map((group) => (
        <div className="section-card" key={group.key}>
          <h3 className="_text-capitalize">{group.label}</h3>
          <div className="table-card">
            <table>
              <thead><tr><th>Fecha</th><th>Sucursal</th><th>Accion</th><th>Detalle</th><th>Actor</th></tr></thead>
              <tbody>
                {group.rows.map((row) => (
                  <tr key={row.id}>
                    <td>{new Date(row.createdAt).toLocaleString()}</td>
                    <td>{row.branchName}</td>
                    <td>{row.action}</td>
                    <td>{row.detail}</td>
                    <td>{row.actor}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  )
}
