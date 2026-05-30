import { useCallback, useState } from 'react'
import { DataState } from '../../components/admin/DataState'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { appointmentStatusLabel, appointmentStatusTone } from '../../constants/verification'
import { useApiResource } from '../../hooks/useApiResource'
import { getAdminDashboardPayments, getAdminDashboardAgenda } from '../../services/api/admin'
import { useBranchContext } from '../../providers/BranchProvider'
import { Link } from 'react-router-dom'

export function AdminDashboardPage() {
  const { activeBranch } = useBranchContext()
  const branchId = activeBranch?.id ?? null
  const [pMonth, setPMonth] = useState(new Date().getMonth() + 1)
  const [pYear, setPYear] = useState(new Date().getFullYear())
  const [aMonth, setAMonth] = useState(new Date().getMonth() + 1)
  const [aYear, setAYear] = useState(new Date().getFullYear())

  // Pagos independientes
  const paymentsLoader = useCallback(() => getAdminDashboardPayments(pMonth, pYear), [pMonth, pYear, branchId])
  const { data: paymentsData, isLoading: loadingPayments } = useApiResource(paymentsLoader)

  // Agenda independiente
  const agendaLoader = useCallback(() => getAdminDashboardAgenda(aMonth, aYear), [aMonth, aYear, branchId])
  const { data: agendaData, isLoading: loadingAgenda } = useApiResource(agendaLoader)

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

  const MonthNavigator = ({ month, year, onPrev, onNext, isLoading }: { month: number, year: number, onPrev: () => void, onNext: () => void, isLoading?: boolean }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', background: 'rgba(255,255,255,0.9)', padding: '0.4rem 0.8rem', borderRadius: '0.75rem', border: '1px solid rgba(217, 232, 236, 0.9)', boxShadow: '0 2px 8px rgba(0,0,0,0.02)' }}>
      <button 
        className="button button--ghost button--compact" 
        onClick={onPrev}
        disabled={isCurrent(month, year) || isLoading}
        style={{ minWidth: '32px', height: '32px', padding: 0, borderRadius: '8px' }}
      >
        &larr;
      </button>
      <span style={{ fontWeight: 700, minWidth: '110px', textAlign: 'center', fontSize: '0.95rem', color: isLoading ? 'var(--color-text-soft)' : 'var(--color-primary-dark)' }}>
        {monthNames[month - 1]} {year}
      </span>
      <button 
        className="button button--ghost button--compact" 
        onClick={onNext}
        disabled={isLoading}
        style={{ minWidth: '32px', height: '32px', padding: 0, borderRadius: '8px' }}
      >
        &rarr;
      </button>
    </div>
  )

  return (
    <div className="admin-dashboard">
      <header className="page-header _mb-lg">
        <div style={{ maxWidth: '1400px', margin: '0 auto', width: '100%' }}>
          <h1 className="page-title">Resumen Administrativo</h1>
          <p className="page-description">
            Gestiona cobros y citas programadas con filtros de tiempo independientes.
          </p>
        </div>
      </header>

      <div className="page-stack" style={{ maxWidth: '1400px', margin: '0 auto', width: '100%' }}>
        
        <SectionCard
          eyebrow="Cobros"
          title="Pagos proximos"
          description="Cuotas de tratamiento pendientes por vencer."
          action={
            <MonthNavigator 
              month={pMonth} 
              year={pYear} 
              isLoading={loadingPayments}
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
          {loadingPayments ? (
            <DataState title="Actualizando pagos" message={`Consultando cobros de ${monthNames[pMonth - 1]}...`} />
          ) : paymentsData?.payments.length ? (
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
                  {paymentsData.payments.map((p) => {
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
                            {p.isToday && <span className="_text-danger _text-xs _font-bold">VENCE HOY</span>}
                          </div>
                        </td>
                        <td className="_font-bold">{p.amount}</td>
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
                        <td className="_text-muted">Nro {p.quotaNumber}</td>
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
              isLoading={loadingAgenda}
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
          {loadingAgenda ? (
            <DataState title="Actualizando agenda" message={`Consultando citas de ${monthNames[aMonth - 1]}...`} />
          ) : agendaData?.agenda.length ? (
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
                  {agendaData.agenda.map((item) => {
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
                            {item.isToday && <span className="_text-danger _text-xs _font-bold">HOY</span>}
                          </div>
                        </td>
                        <td className="_font-bold">{item.time}</td>
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
                          <StatusBadge tone={appointmentStatusTone[item.status]}>{appointmentStatusLabel[item.status]}</StatusBadge>
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
    </div>
  )
}
