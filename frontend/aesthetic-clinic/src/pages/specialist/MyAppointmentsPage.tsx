import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { getMyAppointments } from '../../services/api/specialist'
import type { MisCitasItem } from '../../types/admin'


function Spinner() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
      <span className="status-badge status-badge--primary">Cargando...</span>
    </div>
  )
}

function formatMaquinaria(items: MisCitasItem['maquinaria']): string {
  if (!items || items.length === 0) return 'Sin maquinaria'
  return items.map((m) => `${m.nombre} x${m.cantidad}`).join(', ')
}

function statusTone(estado: string): 'success' | 'warning' | 'neutral' | 'danger' {
  const value = estado.toLowerCase()
  if (value.includes('confirmad') || value.includes('realizad')) return 'success'
  if (value.includes('cancelad') || value.includes('no asistio')) return 'danger'
  if (value.includes('pendiente') || value.includes('verificacion')) return 'warning'
  return 'neutral'
}

export function MyAppointmentsPage() {
  const [citas, setCitas] = useState<MisCitasItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retryKey, setRetryKey] = useState(0)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const refetch = useCallback(() => setRetryKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect -- matches useSpecialistAvailability pattern
    setLoading(true)
    setError(null)
    getMyAppointments()
      .then((data) => {
        if (cancelled) return
        setCitas(data.citas ?? [])
        setLoading(false)
      })
      .catch((err: Error) => {
        if (cancelled) return
        setError(err.message || 'Error cargando citas')
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [retryKey])

  const sortedCitas = useMemo(() => {
    return [...citas].sort((a, b) => {
      const dateA = `${a.fecha}T${a.horaInicio}`
      const dateB = `${b.fecha}T${b.horaInicio}`
      return dateA.localeCompare(dateB)
    })
  }, [citas])

  if (loading) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Portal de especialista"
          title="Mis citas"
          description="Listado de las citas en las que participas como especialista."
        />
        <Spinner />
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Portal de especialista"
          title="Mis citas"
          description="Listado de las citas en las que participas como especialista."
        />
        <DataState
          title="Error"
          message={error}
          tone="danger"
        />
        <div style={{ textAlign: 'center', marginTop: '1rem' }}>
          <button className="button" type="button" onClick={refetch}>
            Reintentar
          </button>
        </div>
      </div>
    )
  }

  if (sortedCitas.length === 0) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Portal de especialista"
          title="Mis citas"
          description="Listado de las citas en las que participas como especialista."
        />
        <DataState
          title="Sin citas asignadas"
          message="No tienes citas asignadas por el momento."
          tone="neutral"
        />
      </div>
    )
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Portal de especialista"
        title="Mis citas"
        description="Listado de solo lectura de las citas en las que participas como especialista."
      />

      <SectionCard
        eyebrow="Asignadas"
        title={`${sortedCitas.length} cita(s)`}
        description="Haz clic en una fila para ver el detalle completo."
      >
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>Cliente</th>
                <th>Fecha</th>
                <th>Hora</th>
                <th>Estado</th>
                <th>Procedimiento</th>
                <th>Zona</th>
                <th>Sucursal</th>
                <th>Maquinaria</th>
              </tr>
            </thead>
            <tbody>
              {sortedCitas.map((cita) => {
                const expanded = expandedId === cita.rawId
                return (
                  <Fragment key={`cita-${cita.rawId}`}>
                    <tr
                      onClick={() => setExpandedId(expanded ? null : cita.rawId)}
                      style={{ cursor: 'pointer' }}
                      data-testid={`mis-citas-row-${cita.rawId}`}
                    >
                      <td>{cita.cliente ?? 'Sin cliente asignado'}</td>
                      <td>{cita.fecha}</td>
                      <td>{cita.horaInicio}</td>
                      <td>
                        <StatusBadge tone={statusTone(cita.estado)}>
                          {cita.estado}
                        </StatusBadge>
                      </td>
                      <td>{cita.procedimientoPlanificado || 'Sin procedimiento'}</td>
                      <td>{cita.zonaCuerpoPlanificada || 'Sin zona'}</td>
                      <td>{cita.sucursal ?? 'Sin sucursal'}</td>
                      <td>{formatMaquinaria(cita.maquinaria)}</td>
                    </tr>
                    {expanded ? (
                      <tr data-testid={`mis-citas-detail-${cita.rawId}`}>
                        <td colSpan={8}>
                          <div className="_panel-card _mt-md">
                            <div className="form-grid">
                              <div>
                                <strong>Descripcion general</strong>
                                <p>{cita.descripcionGeneral || 'Sin descripcion.'}</p>
                              </div>
                              <div>
                                <strong>Notas previas</strong>
                                <p>{cita.notasPrevias || 'Sin notas previas.'}</p>
                              </div>
                              <div>
                                <strong>Notas post</strong>
                                <p>{cita.notasPost || 'Sin notas post.'}</p>
                              </div>
                              <div>
                                <strong>Duracion estimada</strong>
                                <p>
                                  {cita.duracionEstimadaMinutos
                                    ? `${cita.duracionEstimadaMinutos} minutos`
                                    : 'Sin duracion registrada'}
                                </p>
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  )
}
