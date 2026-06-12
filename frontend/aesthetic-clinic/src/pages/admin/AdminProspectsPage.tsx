import { useCallback, useMemo, useState } from 'react'

import { DataState } from '../../components/admin/DataState'
import { AdminRelationshipTabs } from '../../components/admin/AdminRelationshipTabs'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useConfirmDialog } from '../../hooks/useConfirmDialog'
import { useNotifications } from '../../providers/NotificationProvider'
import {
  cancelAdminProspectMedicalAppointment,
  createAdminProspectMedicalAppointment,
  getAdminProspectMedicalAvailability,
  getAdminProspects,
  updateAdminProspect,
  migrateAdminProspect,
  updateAdminProspectAppointmentStatus,
} from '../../services/api/admin'
import { useAuth } from '../../providers/AuthProvider'
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
  const { activeBranch } = useBranchContext()
  const { confirm, ConfirmDialog: ConfirmDialogModal } = useConfirmDialog()

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const loader = useCallback(() => getAdminProspects(activeBranch?.id), [activeBranch?.id])
  const { data, isLoading, error, reload } = useApiResource(loader)
  const [bookingProspect, setBookingProspect] = useState<ProspectLead | null>(null)

  const [selectedDate, setSelectedDate] = useState('')
  const [selectedTime, setSelectedTime] = useState('')
  const [concurrencyInfo, setConcurrencyInfo] = useState<AdminConcurrencyCheckResponse | null>(null)
  const [isChecking, setIsChecking] = useState(false)

  const [availability, setAvailability] = useState<AdminProspectMedicalAvailabilityResponse | null>(null)
  const [bookingError, setBookingError] = useState<string | null>(null)
  const [isLoadingAvailability, setIsLoadingAvailability] = useState(false)
  const [isBookingKey, setIsBookingKey] = useState<string | null>(null)
  const [isMigratingKey, setIsMigratingKey] = useState<number | null>(null)
  const { user } = useAuth()
  const isMainAdmin = user?.isMainAdmin || user?.isSuperuser
  const { branches } = useBranchContext()
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('TODOS')
  const [editingProspect, setEditingProspect] = useState<ProspectLead | null>(null)
  const [isUpdating, setIsUpdating] = useState(false)
  const [visibleCount, setVisibleCount] = useState(10)
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

  const visibleProspects = useMemo(() => {
    return filteredProspects.slice(0, visibleCount)
  }, [filteredProspects, visibleCount])

  function handleShowMore() {
    setVisibleCount((prev) => prev + 10)
  }

  function handleShowLess() {
    setVisibleCount((prev) => Math.max(10, prev - 10))
  }

  async function handleOpenBooking(lead: ProspectLead) {
    if (!lead.rawId) return
    setBookingProspect(lead)
    setAvailability(null)
    setBookingError(null)
    setIsLoadingAvailability(true)
    try {
      const response = await getAdminProspectMedicalAvailability(lead.rawId, activeBranch?.id || 1)
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
      const info = await checkAdminConcurrency(activeBranch.id, selectedDate, selectedTime, selectedTime)
      setConcurrencyInfo(info)
    } catch (err: any) {
      showNotification({ title: 'Error', message: err.message, tone: 'danger' })
    } finally {
      setIsChecking(false)
    }
  }

  async function handleUpdateProspect(data: {
    primerNombre: string
    segundoNombre: string
    apellidoPaterno: string
    apellidoMaterno: string
    phone: string
    observations: string
    stateValue: 'PASAJERO' | 'DESCARTADO'
    appointmentStatuses: Record<number, string>
  }) {
    if (!editingProspect?.rawId) return
    setIsUpdating(true)
    try {
      await updateAdminProspect(editingProspect.rawId, data)
      showNotification({ title: 'Actualizado', message: 'Datos del prospecto actualizados.', tone: 'success' })
      setEditingProspect(null)
      reload()
    } catch (err: any) {
      showNotification({ title: 'Error', message: err.message, tone: 'danger' })
    } finally {
      setIsUpdating(false)
    }
  }

  async function handleReserve() {
    if (!bookingProspect?.rawId || !activeBranch) return
    setIsBookingKey('booking')

    try {
      const response = await createAdminProspectMedicalAppointment(bookingProspect.rawId, {
        branchId: activeBranch.id,
        dateTime: `${selectedDate}T${selectedTime}:00`
      })
      showNotification({ title: 'Cita medica agendada', message: response.detail, tone: 'success' })
      setBookingProspect(null)
      setAvailability(null)
      setSelectedDate('')
      setSelectedTime('')
      setConcurrencyInfo(null)
      reload()
      // Actualizar editingProspect con datos frescos si este prospecto está en edición
      if (editingProspect && data?.prospects) {
        const updatedProspect = data.prospects.find(p => p.rawId === bookingProspect.rawId)
        if (updatedProspect) {
          setEditingProspect(updatedProspect)
        }
      }
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

  async function handleCancelAppointment(appointmentId: number, prospectId?: number) {
    const confirmed = await confirm({
      title: 'Cancelar cita',
      message: 'Se cancelara la cita medica del prospecto. ¿Deseas continuar?',
      tone: 'warning',
    })
    if (!confirmed) return

    try {
      const response = await cancelAdminProspectMedicalAppointment(appointmentId)
      showNotification({ title: 'Cita cancelada', message: response.detail, tone: 'success' })
      reload()
      // Actualizar editingProspect con datos frescos si este prospecto está en edición
      if (editingProspect && prospectId && editingProspect.rawId === prospectId && data?.prospects) {
        const updatedProspect = data.prospects.find(p => p.rawId === prospectId)
        if (updatedProspect) {
          setEditingProspect(updatedProspect)
        }
      }
    } catch (requestError) {
      showNotification({
        title: 'No se pudo cancelar',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  async function handleMarkAppointmentAsCompleted(appointmentId: number, prospectId?: number) {
    const confirmed = await confirm({
      title: 'Marcar cita como realizada',
      message: '¿Deseas marcar esta cita como realizada?',
      tone: 'info',
    })
    if (!confirmed) return

    try {
      await updateAdminProspectAppointmentStatus(appointmentId, 'REALIZADA')
      showNotification({ title: 'Cita marcada como realizada', message: 'La cita ha sido actualizada.', tone: 'success' })
      reload()
      // Actualizar editingProspect con datos frescos si este prospecto está en edición
      if (editingProspect && prospectId && editingProspect.rawId === prospectId && data?.prospects) {
        const updatedProspect = data.prospects.find(p => p.rawId === prospectId)
        if (updatedProspect) {
          setEditingProspect(updatedProspect)
        }
      }
    } catch (requestError) {
      showNotification({
        title: 'No se pudo actualizar',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  async function handleMigrateProspect(prospectId: number, branchId: number) {
    const branchName = branches.find(b => b.id === branchId)?.nombre || 'esta sucursal'
    const confirmed = await confirm({
      title: 'Migrar prospecto',
      message: `¿Seguro que deseas migrar este prospecto a la sucursal ${branchName}?`,
    })
    if (!confirmed) return

    setIsMigratingKey(prospectId)
    try {
      const response = await migrateAdminProspect(prospectId, branchId)
      showNotification({ title: 'Prospecto migrado', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError: any) {
      showNotification({
        title: 'Error al migrar',
        message: requestError.message,
        tone: 'danger',
      })
    } finally {
      setIsMigratingKey(null)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Relacion comercial"
        title="Prospectos y clientes"
        description="Administra prospectos pasajeros, su avance comercial y el momento en que pasan a clientes formales."
        actions={[
          { label: 'Registrar prospecto', variant: 'primary', to: '/cms/prospectos/nuevo' },
        ]}
      />

      <AdminRelationshipTabs />

      {flashMessage ? <DataState title={flashMessage.includes('convertido') || flashMessage.includes('finalizo') ? 'Conversion exitosa' : 'Registro actualizado'} message={flashMessage} /> : null}

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
                      <th>Teléfono</th>
                      <th>Interés</th>
                      <th>Registrado por</th>
                      <th>Etapa</th>
                      <th>Estado</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleProspects.map((lead) => {
                      const hasScheduled = lead.medicalAppointments?.some(a => a.statusValue === 'PROGRAMADA');

                      return (
                        <tr key={lead.id}>
                          <td>
                            <button
                              className="table-link-button"
                              onClick={() => setEditingProspect(lead)}
                            >
                              <strong>{lead.name}</strong>
                            </button>
                            <span>{lead.createdAt}</span>
                          </td>
                          <td>{lead.phone}</td>
                          <td>{lead.interest}</td>
                          <td>{lead.registeredBy}</td>
                          <td>
                            <StatusBadge
                              tone={
                                lead.stage === 'Convertido' ? 'success' :
                                  lead.stage === 'Cita Programada' ? 'primary' :
                                    'primary'
                              }
                            >
                              {lead.stage}
                            </StatusBadge>
                          </td>
                          <td>{lead.state}</td>
                          <td>
                            {lead.state === 'Pasajero' ? (
                              <div className="table-actions" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                <div style={{ display: 'flex', gap: '0.5rem' }}>
                                  <Link className="button button--primary button--compact" to={`/cms/prospectos/${lead.rawId}/convertir`}>
                                    Convertir
                                  </Link>
                                  {hasScheduled ? (
                                    <button
                                      className="button button--secondary button--compact"
                                      disabled
                                      style={{ opacity: 0.5, cursor: 'not-allowed' }}
                                      title="Ya tiene una cita programada activa"
                                    >
                                      Agendar cita
                                    </button>
                                  ) : (
                                    <button
                                      className="button button--secondary button--compact"
                                      type="button"
                                      onClick={() => void handleOpenBooking(lead)}
                                    >
                                      Agendar cita
                                    </button>
                                  )}
                                  {isMainAdmin && (
                                    <button
                                      className="button button--ghost button--compact"
                                      type="button"
                                      disabled={isMigratingKey === lead.rawId}
                                      onClick={() => {
                                        const targetBranchId = window.prompt(
                                          `Ingresa el ID de la sucursal destino:\n\n` +
                                          branches.filter(b => b.id !== activeBranch?.id).map(b => `[ ${b.id} ] - ${b.nombre}`).join('\n')
                                        )
                                        if (targetBranchId && lead.rawId) {
                                          handleMigrateProspect(lead.rawId, Number(targetBranchId))
                                        }
                                      }}
                                    >
                                      {isMigratingKey === lead.rawId ? 'Migrando...' : 'Migrar'}
                                    </button>
                                  )}
                                </div>
                              </div>
                            ) : (
                              <div className="table-actions">
                                {lead.medicalAppointments && lead.medicalAppointments.length > 0 && (
                                  <div className="table-muted">
                                    Ultima cita: {lead.medicalAppointments[0].dateTime} ({lead.medicalAppointments[0].status})
                                  </div>
                                )}
                                <span style={{ color: 'var(--color-text-soft)' }}>Convertido/Finalizado</span>
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <div className="pagination-controls">
                  <span className="pagination-info">
                    Mostrando {visibleProspects.length} de {filteredProspects.length} prospectos
                  </span>
                  <div className="pagination-buttons">
                    {visibleCount > 10 && (
                      <button
                        className="button button--secondary button--compact"
                        type="button"
                        onClick={handleShowLess}
                      >
                        Ver menos
                      </button>
                    )}
                    {visibleCount < filteredProspects.length && (
                      <button
                        className="button button--secondary button--compact"
                        type="button"
                        onClick={handleShowMore}
                      >
                        Ver más
                      </button>
                    )}
                  </div>
                </div>
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

          {editingProspect && (
            <EditProspectModal
              prospect={editingProspect}
              onClose={() => setEditingProspect(null)}
              onSave={handleUpdateProspect}
              isUpdating={isUpdating}
              handleCancelAppointment={(appointmentId) => handleCancelAppointment(appointmentId, editingProspect.rawId)}
              handleMarkAppointmentAsCompleted={(appointmentId) => handleMarkAppointmentAsCompleted(appointmentId, editingProspect.rawId)}
            />
          )}

          {bookingProspect ? (
            <BookingModal
              prospect={bookingProspect}
              availability={availability}
              isLoadingAvailability={isLoadingAvailability}
              bookingError={bookingError}
              onClose={() => {
                setBookingProspect(null)
                setAvailability(null)
                setSelectedDate('')
                setSelectedTime('')
                setConcurrencyInfo(null)
              }}
              onReserve={handleReserve}
              selectedDate={selectedDate}
              setSelectedDate={setSelectedDate}
              selectedTime={selectedTime}
              setSelectedTime={setSelectedTime}
              concurrencyInfo={concurrencyInfo}
              setConcurrencyInfo={setConcurrencyInfo}
              handleCheckConcurrency={handleCheckConcurrency}
              isChecking={isChecking}
              isBooking={Boolean(isBookingKey)}
            />
          ) : null}
        </>
      ) : null}
      <ConfirmDialogModal />
    </div>
  )
}

function BookingModal({
  prospect,
  availability,
  isLoadingAvailability,
  bookingError,
  onClose,
  onReserve,
  selectedDate,
  setSelectedDate,
  selectedTime,
  setSelectedTime,
  concurrencyInfo,
  setConcurrencyInfo,
  handleCheckConcurrency,
  isChecking,
  isBooking,
}: {
  prospect: ProspectLead
  availability: AdminProspectMedicalAvailabilityResponse | null
  isLoadingAvailability: boolean
  bookingError: string | null
  onClose: () => void
  onReserve: () => Promise<void>
  selectedDate: string
  setSelectedDate: (d: string) => void
  selectedTime: string
  setSelectedTime: (t: string) => void
  concurrencyInfo: AdminConcurrencyCheckResponse | null
  setConcurrencyInfo: (info: AdminConcurrencyCheckResponse | null) => void
  handleCheckConcurrency: () => Promise<void>
  isChecking: boolean
  isBooking: boolean
}) {
  const availableDatesMap = useMemo(() => {
    const map: Record<string, number> = {}
    availability?.calendar?.availableDates?.forEach((d) => {
      map[d.date] = d.slotCount
    })
    return map
  }, [availability])

  const [currentMonth, setCurrentMonth] = useState(new Date())

  const calendarDays = useMemo(() => {
    const year = currentMonth.getFullYear()
    const month = currentMonth.getMonth()
    const firstDay = new Date(year, month, 1).getDay()
    const daysInMonth = new Date(year, month + 1, 0).getDate()

    const days = []
    // Padding for first week
    for (let i = 0; i < firstDay; i++) {
      days.push(null)
    }
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
      days.push({
        day: d,
        date: dateStr,
        slots: availableDatesMap[dateStr] || 0,
      })
    }
    return days
  }, [currentMonth, availableDatesMap])

  return (
    <div className="booking-modal-overlay">
      <div className="booking-modal-content">
        <header className="booking-modal-header">
          <div>
            <span className="section-card__eyebrow">Cita medica</span>
            <h2>Agendar para {prospect.name}</h2>
          </div>
          <button className="booking-modal-close" onClick={onClose}>
            &times;
          </button>
        </header>

        <div className="booking-modal-body">
          {isLoadingAvailability ? (
            <DataState title="Cargando disponibilidad" message="Consultando cupos publicados..." />
          ) : bookingError ? (
            <DataState title="Error" message={bookingError} tone="danger" />
          ) : availability ? (
            <div className="booking-grid">
              <div className="calendar-section">
                <div className="calendar-header">
                  <button
                    type="button"
                    onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1))}
                  >
                    &larr;
                  </button>
                  <h3>
                    {currentMonth.toLocaleString('es-ES', { month: 'long', year: 'numeric' })}
                  </h3>
                  <button
                    type="button"
                    onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1))}
                  >
                    &rarr;
                  </button>
                </div>
                <div className="calendar-grid">
                  {['Dom', 'Lun', 'Mar', 'Mie', 'Jue', 'Vie', 'Sab'].map((d) => (
                    <div key={d} className="calendar-weekday">
                      {d}
                    </div>
                  ))}
                  {calendarDays.map((day, idx) => (
                    <div
                      key={idx}
                      className={`calendar-day ${!day ? 'calendar-day--empty' : ''} ${day?.slots ? 'calendar-day--available' : ''
                        } ${selectedDate === day?.date ? 'is-selected' : ''}`}
                      onClick={() => {
                        if (day?.slots) {
                          setSelectedDate(day.date)
                          setConcurrencyInfo(null)
                        }
                      }}
                    >
                      {day ? (
                        <>
                          <span className="day-number">{day.day}</span>
                          {day.slots > 0 && (
                            <div className="day-availability-indicator">
                              <span className="day-slots">Disponible</span>
                            </div>
                          )}
                        </>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>

              <div className="booking-details-section">
                <label className="field">
                  <span>Fecha seleccionada</span>
                  <input type="date" className="input" value={selectedDate} readOnly />
                </label>

                <label className="field">
                  <span>Hora de la cita</span>
                  <input
                    type="time"
                    className="input"
                    value={selectedTime}
                    onChange={(e) => {
                      setSelectedTime(e.target.value)
                      setConcurrencyInfo(null)
                    }}
                  />
                </label>

                <button
                  type="button"
                  className="button button--secondary"
                  disabled={!selectedDate || !selectedTime || isChecking}
                  onClick={() => void handleCheckConcurrency()}
                  style={{ width: '100%' }}
                >
                  {isChecking ? 'Verificando...' : 'Verificar Disponibilidad'}
                </button>

                {concurrencyInfo && (
                  <div className="concurrency-results">
                    <p>
                      <strong>Citas simultaneas de 1 hora antes a 1 hora despues ({concurrencyInfo.hora_inicio} a {concurrencyInfo.hora_fin}):</strong> {concurrencyInfo.concurrency}
                    </p>

                    {concurrencyInfo.appointments && concurrencyInfo.appointments.length > 0 ? (
                      <div style={{ marginTop: '0.75rem', paddingLeft: '0.5rem', borderLeft: '2px solid var(--color-border)' }}>
                        <p style={{ marginBottom: '0.5rem' }}><strong>Citas simultáneas:</strong></p>
                        <ul style={{ fontSize: '0.82rem', color: 'var(--color-text-soft)', paddingLeft: '1.2rem', margin: 0 }}>
                          {concurrencyInfo.appointments.map((apt, idx) => (
                            <li key={idx} style={{ marginBottom: '0.3rem' }}>
                              <span style={{ fontWeight: 500 }}>{apt.cliente_nombre ?? 'Cliente no registrado'}</span>
                              {' — '}
                              {apt.tratamiento_nombre ?? 'Sin tratamiento'}
                              {' — '}
                              {new Date(apt.hora).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })}
                              <span style={{
                                marginLeft: '0.4rem',
                                fontSize: '0.72rem',
                                padding: '0.1rem 0.35rem',
                                borderRadius: '3px',
                                backgroundColor: apt.tipo === 'CitasMedicas' ? 'var(--color-primary)' : apt.tipo === 'CitasProspectos' ? '#6c757d' : '#17a2b8',
                                color: '#fff',
                              }}>
                                {apt.tipo === 'CitasMedicas' ? 'Médica' : apt.tipo === 'CitasProspectos' ? 'Prospecto' : 'Libre'}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <p style={{ fontSize: '0.85rem', color: 'var(--color-text-soft)', marginTop: '0.5rem' }}>Sin citas simultáneas</p>
                    )}

                    <p>
                      <strong>Especialistas en turno {concurrencyInfo.hora_seleccionada}:</strong>
                    </p>
                    <ul style={{ fontSize: '0.85rem', color: 'var(--color-text-soft)', paddingLeft: '1.2rem', margin: '0.5rem 0' }}>
                      {concurrencyInfo.presentes.map(esp => (
                        <li key={esp.id}>
                          {esp.usuario__primer_nombre} {esp.usuario__apellido_paterno} ({esp.especialidad})
                        </li>
                      ))}
                    </ul>
                    {concurrencyInfo.concurrency >= concurrencyInfo.presentes.length && concurrencyInfo.presentes.length > 0 && (
                      <p className="concurrency-warning">Alta concurrencia detectada.</p>
                    )}
                    {concurrencyInfo.presentes.length === 0 && (
                      <p className="concurrency-warning">No hay especialistas en este horario.</p>
                    )}

                    <button
                      type="button"
                      className="button button--primary"
                      onClick={() => void onReserve()}
                      disabled={isBooking}
                      style={{ width: '100%', marginTop: '1rem' }}
                    >
                      {isBooking ? 'Agendando...' : 'Confirmar Cita'}
                    </button>
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function EditProspectModal({
  prospect,
  onClose,
  onSave,
  isUpdating,
  handleCancelAppointment,
  handleMarkAppointmentAsCompleted,
}: {
  prospect: ProspectLead
  onClose: () => void
  onSave: (data: any) => Promise<void>
  isUpdating: boolean
  handleCancelAppointment: (id: number) => Promise<void>
  handleMarkAppointmentAsCompleted: (appointmentId: number, prospectId?: number) => Promise<void>
}) {
  const [primerNombre, setPrimerNombre] = useState(prospect.primerNombre || prospect.firstName || '')
  const [segundoNombre, setSegundoNombre] = useState(prospect.segundoNombre || '')
  const [apellidoPaterno, setApellidoPaterno] = useState(prospect.apellidoPaterno || prospect.lastName || '')
  const [apellidoMaterno, setApellidoMaterno] = useState(prospect.apellidoMaterno || '')
  const [phone, setPhone] = useState(prospect.phone || '')
  const [observations, setObservations] = useState(prospect.observations || '')
  const [stateValue, setStateValue] = useState<'PASAJERO' | 'DESCARTADO'>(
    prospect.stateValue === 'DESCARTADO' ? 'DESCARTADO' : 'PASAJERO',
  )
  const [tempStatuses, setTempStatuses] = useState<Record<number, string>>({})
  const [editingStatusId, setEditingStatusId] = useState<number | null>(null)

  const isEditable = prospect.state !== 'Convertido'

  return (
    <div className="booking-modal-overlay">
      <div className="booking-modal-content">
        <header className="booking-modal-header">
          <div>
            <span className="section-card__eyebrow">Prospecto</span>
            <h2>{isEditable ? 'Editar' : 'Detalles de'} {prospect.name}</h2>
          </div>
          <button className="booking-modal-close" onClick={onClose}>
            &times;
          </button>
        </header>

        <div className="booking-modal-body" style={{ padding: '2rem' }}>
          {!isEditable && (
            <div className="form-error" style={{ marginBottom: '1.5rem', background: 'var(--color-surface-alt)', color: 'var(--color-text)' }}>
              Los datos de este prospecto ya no son editables porque su estado es <strong>{prospect.state}</strong>.
            </div>
          )}

          <div className="form-grid">
            <label className="field">
              <span>Primer nombre</span>
              <input
                className="input"
                value={primerNombre}
                onChange={e => setPrimerNombre(e.target.value)}
                disabled={!isEditable}
              />
            </label>
            <label className="field">
              <span>Segundo nombre</span>
              <input
                className="input"
                value={segundoNombre}
                onChange={e => setSegundoNombre(e.target.value)}
                disabled={!isEditable}
              />
            </label>
            <label className="field">
              <span>Apellido paterno</span>
              <input
                className="input"
                value={apellidoPaterno}
                onChange={e => setApellidoPaterno(e.target.value)}
                disabled={!isEditable}
              />
            </label>
            <label className="field">
              <span>Apellido materno</span>
              <input
                className="input"
                value={apellidoMaterno}
                onChange={e => setApellidoMaterno(e.target.value)}
                disabled={!isEditable}
              />
            </label>
            <label className="field">
              <span>Teléfono</span>
              <input
                className="input"
                value={phone}
                onChange={e => setPhone(e.target.value)}
                disabled={!isEditable}
              />
            </label>
          </div>
          <label className="field" style={{ marginTop: '1rem' }}>
            <span>Observaciones</span>
            <textarea
              className="input"
              rows={3}
              value={observations}
              onChange={e => setObservations(e.target.value)}
              disabled={!isEditable}
            />
          </label>
          <label className="field" style={{ marginTop: '1rem' }}>
            <span>Estado del prospecto</span>
            <select
              className="input"
              value={stateValue}
              onChange={(e) => setStateValue(e.target.value as 'PASAJERO' | 'DESCARTADO')}
              disabled={!isEditable}
            >
              <option value="PASAJERO">Pasajero</option>
              <option value="DESCARTADO">Descartado</option>
            </select>
          </label>

          {prospect.medicalAppointments && prospect.medicalAppointments.length > 0 && (
            <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--color-border)', paddingTop: '1rem' }}>
              <h3>Historial de Citas (Etapa Prospecto)</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.75rem' }}>
                {prospect.medicalAppointments.map((cita) => {
                  const currentStatusValue = tempStatuses[cita.rawId] || cita.statusValue;
                  const isBeingEdited = editingStatusId === cita.rawId;

                  return (
                    <div key={cita.rawId} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', background: 'var(--color-surface-alt)', borderRadius: '12px' }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 'bold' }}>{cita.dateTime}</div>
                        <div style={{ marginTop: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                          {isBeingEdited ? (
                            <select
                              className="input"
                              style={{ padding: '0.25rem 0.5rem', height: 'auto', fontSize: '0.85rem', width: 'auto', minWidth: '140px' }}
                              value={currentStatusValue}
                              onChange={(e) => {
                                setTempStatuses(prev => ({ ...prev, [cita.rawId]: e.target.value }));
                                setEditingStatusId(null);
                              }}
                              onBlur={() => setEditingStatusId(null)}
                              autoFocus
                            >
                              <option value="PROGRAMADA">Programada</option>
                              <option value="REALIZADA">Realizada</option>
                              <option value="CANCELADA">Cancelada</option>
                              <option value="NO_ASISTIO">No asistió</option>
                            </select>
                          ) : (
                            <>
                              <StatusBadge tone={
                                currentStatusValue === 'REALIZADA' ? 'success' :
                                  currentStatusValue === 'CANCELADA' ? 'danger' :
                                    currentStatusValue === 'NO_ASISTIO' ? 'warning' : 'primary'
                              }>
                                {
                                  currentStatusValue === 'PROGRAMADA' ? 'Programada' :
                                    currentStatusValue === 'REALIZADA' ? 'Realizada' :
                                      currentStatusValue === 'CANCELADA' ? 'Cancelada' : 'No asistió'
                                }
                              </StatusBadge>
                              {isEditable && (
                                <button
                                  className="button button--ghost button--compact"
                                  style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}
                                  onClick={() => setEditingStatusId(cita.rawId)}
                                >
                                  Cambiar estado
                                </button>
                              )}
                            </>
                          )}
                        </div>
                      </div>
                      {isEditable && cita.canCancel && !tempStatuses[cita.rawId] && (
                        <>
                          {currentStatusValue === 'PROGRAMADA' && (
                            <button
                              className="button button--primary button--compact"
                              onClick={() => {
                                void handleMarkAppointmentAsCompleted(cita.rawId)
                                onClose()
                              }}
                            >
                              Realizada
                            </button>
                          )}
                          <button
                            className="button button--danger button--compact"
                            onClick={() => {
                              void handleCancelAppointment(cita.rawId)
                              onClose()
                            }}
                          >
                            Anular
                          </button>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="booking-modal-footer" style={{ padding: '1.5rem 2rem 3rem' }}>
          <button className="button button--ghost" onClick={onClose}>
            {isEditable ? 'Cancelar' : 'Cerrar'}
          </button>
          {isEditable && (
            <button
              className="button button--primary"
              disabled={isUpdating}
              onClick={() =>
                void onSave({
                  primerNombre,
                  segundoNombre,
                  apellidoPaterno,
                  apellidoMaterno,
                  phone,
                  observations,
                  stateValue,
                  appointmentStatuses: tempStatuses,
                })
              }
            >
              {isUpdating ? 'Guardando...' : 'Guardar Cambios'}
            </button>
          )}
        </div>
      </div>

      <style>{`
        .table-link-button {
          background: none;
          border: none;
          padding: 0;
          color: var(--color-primary);
          text-align: left;
          cursor: pointer;
          font-family: inherit;
          font-size: inherit;
        }
        .table-link-button:hover {
          text-decoration: underline;
        }
        .table-appointment-status {
          margin: 0.25rem 0;
        }
        .booking-modal-close {
          position: absolute;
          top: 1.5rem;
          right: 1.5rem;
          background: var(--color-surface-alt);
          border: none;
          width: 32px;
          height: 32px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          font-size: 1.5rem;
          color: var(--color-text-soft);
          transition: all 0.2s;
          z-index: 10;
        }
        .booking-modal-close:hover {
          background: var(--color-border);
          color: var(--color-text);
        }
        .booking-modal-body h3 {
          margin-bottom: 0.5rem;
          font-size: 1rem;
        }
      `}</style>
    </div>
  )
}
