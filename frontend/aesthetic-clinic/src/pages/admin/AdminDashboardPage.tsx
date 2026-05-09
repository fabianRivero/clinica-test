import { useCallback, useState } from 'react'
import { DataState } from '../../components/admin/DataState'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { getAdminDashboard } from '../../services/api/admin'
import { Link } from 'react-router-dom'

const agendaTone = {
  programada: 'neutral',
  biometria: 'warning',
  confirmada: 'success',
} as const

export function AdminDashboardPage() {
  const [pMonth, setPMonth] = useState(new Date().getMonth() + 1)
  const [pYear, setPYear] = useState(new Date().getFullYear())
  const [aMonth, setAMonth] = useState(new Date().getMonth() + 1)
  const [aYear, setAYear] = useState(new Date().getFullYear())

  const loader = useCallback(() => getAdminDashboard({
    p_month: pMonth,
    p_year: pYear,
    a_month: aMonth,
    a_year: aYear
  }), [pMonth, pYear, aMonth, aYear])

  const { data, isLoading, error } = useApiResource(loader)

  const monthNames = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
  ]

  const getNewPeriod = (m: number, y: number, delta: number) => {
    let nm = m + delta
    let ny = y
    if (nm < 1) { nm = 12; ny-- }
    if (nm > 12) { nm = 1; ny++ }
    return { nm, ny }
  }

  const isPast = (m: number, y: number) => {
    const today = new Date()
    const crM = today.getMonth() + 1
    const crY = today.getFullYear()
    return y < crY || (y === crY && m < crM)
  }

  const isCurrent = (m: number, y: number) => {
    const today = new Date()
    return m === (today.getMonth() + 1) && y === today.getFullYear()
  }

  const MonthNavigator = ({ month, year, onPrev, onNext }: { month: number, year: number, onPrev: () => void, onNext: () => void }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', background: 'rgba(255,255,255,0.9)', padding: '0.4rem 0.8rem', borderRadius: '0.75rem', border: '1px solid rgba(217, 232, 236, 0.9)', boxShadow: '0 2px 8px rgba(0,0,0,0.02)' }}>
      <button 
        className="button button--ghost button--compact" 
        onClick={onPrev}
        disabled={isCurrent(month, year)}
        style={{ minWidth: '32px', height: '32px', padding: 0, borderRadius: '8px' }}
      >
        &larr;
      </button>
      <span style={{ fontWeight: 700, minWidth: '110px', textAlign: 'center', fontSize: '0.95rem', color: 'var(--color-primary-dark)' }}>
        {monthNames[month - 1]} {year}
      </span>
      <button 
        className="button button--ghost button--compact" 
        onClick={onNext}
        style={{ minWidth: '32px', height: '32px', padding: 0, borderRadius: '8px' }}
      >
        &rarr;
      </button>
    </div>
  )

  return (
    <div className="admin-dashboard">
      <header className="page-header" style={{ marginBottom: '2rem' }}>
        <div style={{ maxWidth: '1400px', margin: '0 auto', width: '100%' }}>
          <h1 className="page-title">Resumen Administrativo</h1>
          <p className="page-description">
            Gestiona cobros y citas programadas con filtros de tiempo independientes.
          </p>
        </div>
      </header>

      {isLoading && !data ? (
        <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
          <SectionCard title="Sincronizando panel" description="Consultando datos administrativos...">
            <DataState
              title="Cargando informacion"
              message="Estamos preparando las listas de cobros y agenda medica."
            />
          </SectionCard>
        </div>
      ) : null}

      {error && !data ? (
        <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
          <SectionCard title="Error de conexion">
            <DataState title="No pudimos cargar los datos" message={error} tone="danger" />
          </SectionCard>
        </div>
      ) : null}

      {data ? (
        <div className="page-stack" style={{ maxWidth: '1400px', margin: '0 auto', width: '100%' }}>
          <SectionCard
            eyebrow="Cobros"
            title="Pagos proximos"
            description="Cuotas de tratamiento pendientes por vencer."
            action={
              <MonthNavigator 
                month={pMonth} 
                year={pYear} 
                onPrev={() => {
                  const { nm, ny } = getNewPeriod(pMonth, pYear, -1)
                  if (!isPast(nm, ny)) { setPMonth(nm); setPYear(ny) }
                }}
                onNext={() => {
                  const { nm, ny } = getNewPeriod(pMonth, pYear, 1)
                  setPMonth(nm); setPYear(ny)
                }}
              />
            }
          >
            {data.upcomingPayments.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Fecha vcto.</th>
                      <th>Monto</th>
                      <th>Cliente</th>
                      <th>Operacion</th>
                      <th>Cuota</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.upcomingPayments.map((p) => {
                      const bgColor = p.isToday
                        ? 'rgba(239, 68, 68, 0.08)'
                        : p.isThisWeek
                          ? 'rgba(245, 158, 11, 0.08)'
                          : undefined

                      return (
                        <tr key={p.id} style={{ backgroundColor: bgColor }}>
                          <td>
                            <div className="table-cell-stack">
                              <strong>{p.dueDateLabel}</strong>
                              {p.isToday && <span style={{ color: 'var(--color-danger)', fontSize: '0.75rem', fontWeight: 800 }}>VENCE HOY</span>}
                            </div>
                          </td>
                          <td style={{ fontFamily: 'monospace', fontWeight: 600 }}>{p.amount}</td>
                          <td>
                            <Link to={`/admin/clientes/${p.clientId}`} className="table-strong-link">
                              {p.client}
                            </Link>
                          </td>
                          <td>
                            <Link to={`/admin/operaciones/${p.operationId}`} className="table-strong-link" style={{ fontWeight: 400 }}>
                              {p.operation}
                            </Link>
                          </td>
                          <td style={{ color: 'var(--color-text-soft)' }}>Nro {p.quotaNumber}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <DataState
                title="Sin cobros pendientes"
                message={`No hay cuotas programadas para ${monthNames[pMonth - 1]} ${pYear}.`}
                tone="neutral"
              />
            )}
          </SectionCard>

          <SectionCard
            eyebrow="Operaciones"
            title="Citas proximas"
            description="Agenda de tratamientos programados."
            action={
              <MonthNavigator 
                month={aMonth} 
                year={aYear} 
                onPrev={() => {
                  const { nm, ny } = getNewPeriod(aMonth, aYear, -1)
                  if (!isPast(nm, ny)) { setAMonth(nm); setAYear(ny) }
                }}
                onNext={() => {
                  const { nm, ny } = getNewPeriod(aMonth, aYear, 1)
                  setAMonth(nm); setAYear(ny)
                }}
              />
            }
          >
            {data.agenda.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Hora</th>
                      <th>Paciente</th>
                      <th>Operacion</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.agenda.map((item) => {
                      const bgColor = item.isToday
                        ? 'rgba(239, 68, 68, 0.08)'
                        : item.isThisWeek
                          ? 'rgba(245, 158, 11, 0.08)'
                          : undefined

                      return (
                        <tr key={item.id} style={{ backgroundColor: bgColor }}>
                          <td>
                            <div className="table-cell-stack">
                              <strong>{item.dateLabel}</strong>
                              {item.isToday && <span style={{ color: 'var(--color-danger)', fontSize: '0.75rem', fontWeight: 800 }}>HOY</span>}
                            </div>
                          </td>
                          <td style={{ fontWeight: 600 }}>{item.time}</td>
                          <td>
                            <Link to={`/admin/clientes/${item.clientId}`} className="table-strong-link">
                              {item.patient}
                            </Link>
                          </td>
                          <td>
                            <Link to={`/admin/operaciones/${item.operationId}`} className="table-strong-link" style={{ fontWeight: 400 }}>
                              {item.procedure}
                            </Link>
                          </td>
                          <td>
                            <StatusBadge tone={agendaTone[item.status]}>{item.status}</StatusBadge>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <DataState
                title="Agenda vacia"
                message={`No hay citas programadas para ${monthNames[aMonth - 1]} ${aYear}.`}
                tone="neutral"
              />
            )}
          </SectionCard>
        </div>
      ) : null}
    </div>
  )
}
