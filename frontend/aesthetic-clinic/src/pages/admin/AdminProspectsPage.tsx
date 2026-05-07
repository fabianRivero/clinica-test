import { useMemo, useState } from 'react'

import { DataState } from '../../components/admin/DataState'
import { AdminRelationshipTabs } from '../../components/admin/AdminRelationshipTabs'
import { MetricCard } from '../../components/admin/MetricCard'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useNotifications } from '../../providers/NotificationProvider'
import {
  cancelAdminProspectMedicalAppointment,
  createAdminProspectMedicalAppointment,
  getAdminProspectMedicalAvailability,
  getAdminProspects,
} from '../../services/api/admin'
import type {
  AdminProspectMedicalAvailabilityResponse,
  AdminConcurrencyCheckResponse,
  ProspectLead
} from '../../types/admin'
import { useBranchContext } from '../../providers/BranchProvider'
import { checkAdminConcurrency } from '../../services/api/admin'
import { Link, useLocation } from 'react-router-dom'


const PROSPECT_STATUS_OPTIONS = ['Pasajero', 'Convertido', 'Descartado']


export function AdminProspectsPage() {
  const location = useLocation()
  const { showNotification } = useNotifications()
  const { data, isLoading, error, reload } = useApiResource(getAdminProspects)
  const { activeBranch } = useBranchContext()
  const [bookingProspect, setBookingProspect] = useState<ProspectLead | null>(null)
  
  const [selectedDate, setSelectedDate] = useState('')
  const [selectedTime, setSelectedTime] = useState('')
  const [concurrencyInfo, setConcurrencyInfo] = useState<AdminConcurrencyCheckResponse | null>(null)
  const [isChecking, setIsChecking] = useState(false)
  
  const [availability, setAvailability] = useState<AdminProspectMedicalAvailabilityResponse | null>(null)
  const [bookingError, setBookingError] = useState<string | null>(null)
  const [isLoadingAvailability, setIsLoadingAvailability] = useState(false)
  const [isBookingKey, setIsBookingKey] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('TODOS')
  const flashMessage =
    typeof location.state === 'object' && location.state && 'flashMessage' in location.state
      ? String(location.state.flashMessage)
      : null


  const filteredProspects = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase()
    return (data?.prospects ?? []).filter((lead) => {
      const matchesSearch =
        !normalizedSearch ||
        lead.name.toLowerCase().includes(normalizedSearch)
      const matchesStatus = statusFilter === 'TODOS' || lead.state === statusFilter
      return matchesSearch && matchesStatus
    })
  }, [data, searchTerm, statusFilter])

  async function handleOpenBooking(lead: ProspectLead) {
    if (!lead.rawId) return
    setBookingProspect(lead)
    setAvailability(null)
    setBookingError(null)
    setIsLoadingAvailability(true)
    try {
      const response = await getAdminProspectMedicalAvailability(lead.rawId)
      setAvailability(response)
    } catch (requestError: any) {
      setBookingError(requestError.message || 'No se pudo cargar la disponibilidad.')
    } finally {
      setIsLoadingAvailability(false)
    }
  }

  async function handleCheckConcurrency() {
    if (!activeBranch || !selectedDate || !selectedTime) {
      showNotification({ title: 'Atencion', message: 'Selecciona fecha y hora.', tone: 'warning' })
      return
    }
    setIsChecking(true)
    try {
      const parts = selectedTime.split(':')
      const endHour = String(Number(parts[0]) + 1).padStart(2, '0')
      const endTime = `${endHour}:${parts[1]}`
      const info = await checkAdminConcurrency(activeBranch.id, selectedDate, selectedTime, endTime)
      setConcurrencyInfo(info)
    } catch (err: any) {
      showNotification({ title: 'Error', message: err.message, tone: 'danger' })
    } finally {
      setIsChecking(false)
    }
  }

  async function handleReserve() {
    if (!bookingProspect?.rawId || !activeBranch) return
    setIsBookingKey('booking')

    try {
      const response = await createAdminProspectMedicalAppointment(bookingProspect.rawId, {
        branchId: activeBranch.id,
        dateTime: `${selectedDate}T${selectedTime}:00`
      } as any)
      showNotification({ title: 'Cita medica agendada', message: response.detail, tone: 'success' })
      setBookingProspect(null)
      setAvailability(null)
      setSelectedDate('')
      setSelectedTime('')
      setConcurrencyInfo(null)
      reload()
    } catch (requestError: any) {
      showNotification({
        title: 'No se pudo agendar',
        message: requestError.message,
        tone: 'danger',
      })
    } finally {
      setIsBookingKey(null)
    }
  }

  async function handleCancelAppointment(appointmentId: number) {
    const confirmed = window.confirm('Se cancelara la cita medica del prospecto. ¿Deseas continuar?')
    if (!confirmed) return

    try {
      const response = await cancelAdminProspectMedicalAppointment(appointmentId)
      showNotification({ title: 'Cita cancelada', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo cancelar',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Relacion comercial"
        title="Prospectos y clientes"
        description="Administra prospectos pasajeros, su avance comercial y el momento en que pasan a clientes formales."
        actions={[
          { label: 'Registrar prospecto', variant: 'primary', to: '/admin/prospectos/nuevo' },
          { label: 'Importar contactos', variant: 'ghost' },
        ]}
      />

      <AdminRelationshipTabs />

      {flashMessage ? <DataState title="Registro actualizado" message={flashMessage} /> : null}

      {isLoading && !data ? (
        <SectionCard title="Cargando relacion comercial">
          <DataState
            title="Sincronizando prospectos"
            message="Estamos trayendo prospectos, conversiones y clientes con cuenta."
          />
        </SectionCard>
      ) : null}

      {error && !data ? (
        <SectionCard title="No pudimos cargar la relacion comercial">
          <DataState title="Conexion no disponible" message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {data ? (
        <>
          <section className="metrics-grid metrics-grid--compact">
            {data.metrics.slice(0, 2).map((metric) => (
              <MetricCard key={metric.id} metric={metric} />
            ))}
          </section>

          <SectionCard
            eyebrow="Seguimiento"
            title="Prospectos registrados"
            description="Registros internos que todavia no son clientes formales o ya fueron convertidos."
          >
            <div className="form-grid">
              <label className="field">
                <span>Buscar prospecto</span>
                <input
                  className="input"
                  placeholder="Nombre"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Estado</span>
                <select
                  className="input"
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                >
                  <option value="TODOS">Todos</option>
                  {PROSPECT_STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {filteredProspects.length ? (
              <div className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Telefono</th>
                      <th>Interes</th>
                      <th>Registrado por</th>
                      <th>Etapa</th>
                      <th>Estado</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredProspects.map((lead) => (
                      <tr key={lead.id}>
                        <td>
                          <strong>{lead.name}</strong>
                          <span>{lead.createdAt}</span>
                        </td>
                        <td>{lead.phone}</td>
                        <td>{lead.interest}</td>
                        <td>{lead.registeredBy}</td>
                        <td>
                          <StatusBadge tone="primary">{lead.stage}</StatusBadge>
                        </td>
                        <td>{lead.state}</td>
                        <td>
                          {lead.state === 'Pasajero' ? (
                            <div className="table-actions">
                              <Link className="button button--ghost button--compact" to={`/admin/prospectos/${lead.rawId}/convertir`}>
                                Convertir
                              </Link>
                              {lead.scheduledMedicalAppointment ? (
                                <>
                                  <div className="table-muted">
                                    {lead.scheduledMedicalAppointment.dateTime} | {lead.scheduledMedicalAppointment.specialist}
                                  </div>
                                  {lead.scheduledMedicalAppointment.canCancel ? (
                                    <button
                                      className="button button--ghost button--compact"
                                      type="button"
                                      onClick={() => void handleCancelAppointment(lead.scheduledMedicalAppointment!.rawId)}
                                    >
                                      Cancelar cita
                                    </button>
                                  ) : null}
                                </>
                              ) : (
                                <button
                                  className="button button--ghost button--compact"
                                  type="button"
                                  onClick={() => void handleOpenBooking(lead)}
                                >
                                  Agendar cita medica
                                </button>
                              )}
                            </div>
                          ) : (
                            <span>-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <DataState
                title={data.prospects.length ? 'Sin resultados' : 'Sin prospectos cargados'}
                message={
                  data.prospects.length
                    ? 'No hay prospectos que coincidan con la busqueda o el filtro seleccionado.'
                    : 'Todavia no hay pasajeros o conversiones registradas en la base real.'
                }
              />
            )}
          </SectionCard>

          {bookingProspect ? (
            <section className="dashboard-grid">
              <SectionCard
                eyebrow="Cita medica"
                title={`Agendar cita para ${bookingProspect.name}`}
                description={availability ? `Servicio: ${availability.service.name}` : 'Buscando cupos publicados para cita medica.'}
              >
                <div className="client-inline-meta">
                  <button className="button button--ghost button--compact" type="button" onClick={() => setBookingProspect(null)}>
                    Cerrar
                  </button>
                  <span>{bookingProspect.phone}</span>
                </div>

                {isLoadingAvailability ? (
                  <DataState title="Cargando cupos" message="Consultando disponibilidad para cita medica." />
                ) : null}
                {bookingError ? (
                  <DataState title="No se pudo cargar disponibilidad" message={bookingError} tone="danger" />
                ) : null}

                {availability ? (
                  <div className="form-grid">
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                      <label className="field">
                        <span>Fecha</span>
                        <input type="date" className="input" value={selectedDate} onChange={e => { setSelectedDate(e.target.value); setConcurrencyInfo(null); }} />
                      </label>
                      <label className="field">
                        <span>Hora de Inicio</span>
                        <input type="time" className="input" value={selectedTime} onChange={e => { setSelectedTime(e.target.value); setConcurrencyInfo(null); }} />
                      </label>
                    </div>
                    
                    <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
                      <button type="button" className="button button--secondary" disabled={!selectedDate || !selectedTime || isChecking} onClick={() => void handleCheckConcurrency()}>
                        {isChecking ? 'Verificando...' : 'Verificar Disponibilidad'}
                      </button>
                    </div>
                  </div>
                ) : null}
              </SectionCard>

              {concurrencyInfo && (
                <SectionCard title="Resultados de disponibilidad">
                  <div style={{ padding: '1rem', background: 'var(--c-neutral-100)', borderRadius: '8px' }}>
                    <p style={{ marginBottom: '0.5rem' }}>
                      <strong>Citas simultaneas a esa hora:</strong> {concurrencyInfo.concurrency}
                    </p>
                    <p style={{ marginBottom: '0.5rem' }}>
                      <strong>Especialistas en turno:</strong> {concurrencyInfo.presentes.length > 0 ? concurrencyInfo.presentes.map(p => p.usuario__primer_nombre).join(', ') : 'Ninguno registrado'}
                    </p>
                    {concurrencyInfo.concurrency >= concurrencyInfo.presentes.length && concurrencyInfo.presentes.length > 0 && (
                      <p style={{ color: 'var(--c-danger-600)', marginTop: '0.5rem', fontWeight: 600 }}>
                        Aviso: Hay mas citas ({concurrencyInfo.concurrency}) que especialistas en turno ({concurrencyInfo.presentes.length}).
                      </p>
                    )}
                    {concurrencyInfo.presentes.length === 0 && (
                      <p style={{ color: 'var(--c-warning-600)', marginTop: '0.5rem', fontWeight: 600 }}>
                        Aviso: No hay especialistas en turno configurados para esta sucursal a esa hora.
                      </p>
                    )}
                    <div style={{ marginTop: '1.5rem' }}>
                       <button type="button" className="button button--primary" onClick={() => void handleReserve()} disabled={Boolean(isBookingKey)}>
                         {isBookingKey ? 'Agendando...' : 'Confirmar Cita Medica'}
                       </button>
                    </div>
                  </div>
                </SectionCard>
              )}
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  )
}
