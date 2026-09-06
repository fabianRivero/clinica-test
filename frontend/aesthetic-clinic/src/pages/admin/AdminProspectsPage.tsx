import { useCallback, useEffect, useMemo, useState } from 'react'

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
  chargeAdminProspectAppointment,
  createAdminProspectMedicalAppointment,
  getAdminProspectMedicalAvailability,
  getAdminProspects,
  updateAdminProspect,
  updateAdminProspectAppointmentPrice,
  migrateAdminProspect,
  updateAdminProspectAppointmentStatus,
} from '../../services/api/admin'
import { useAuth } from '../../providers/AuthProvider'
import type {
  AdminProspectMedicalAvailabilityResponse,
  AdminConcurrencyCheckResponse,
  ProspectLead,
  ProspectMedicalAppointment,
} from '../../types/admin'
import { AdminRegisterAppointmentPaymentModal } from '../../components/admin/AdminRegisterAppointmentPaymentModal'
import { EditAppointmentPriceModal } from '../../components/admin/EditAppointmentPriceModal'
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
  const [bookingPrecio, setBookingPrecio] = useState('')  // citas-pagos follow-on
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
  const [origenFilter, setOrigenFilter] = useState<'TODOS' | 'NUEVO' | 'RECURRENTE_PRE_SISTEMA'>('TODOS')
  const [editingProspectId, setEditingProspectId] = useState<number | null>(null)
  // Derived from the current `data.prospects` so the modal always
  // receives the freshest copy after ``reload()`` — eliminates the
  // duplicated ``setEditingProspect(updatedProspect)`` plumbing that
  // every action handler used to maintain (and which silently went
  // stale because ``reload()`` is fire-and-forget).
  const editingProspect = useMemo(
    () => (data?.prospects ?? []).find((p) => p.rawId === editingProspectId) ?? null,
    [data, editingProspectId],
  )
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
      const matchesOrigen = origenFilter === 'TODOS' || lead.origen === origenFilter
      return matchesSearch && matchesStatus && matchesOrigen
    })
  }, [data, searchTerm, statusFilter, origenFilter])

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
      setEditingProspectId(null)
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
        dateTime: `${selectedDate}T${selectedTime}:00`,
        // citas-pagos follow-on: optional precio captured at booking time.
        // Empty string is treated as 0 by the backend (cita stays non-billable
        // until the admin explicitly sets a price later).
        precio: bookingPrecio || undefined,
      })
      showNotification({ title: 'Cita medica agendada', message: response.detail, tone: 'success' })
      setBookingProspect(null)
      setAvailability(null)
      setSelectedDate('')
      setSelectedTime('')
      setBookingPrecio('')
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
    } catch (requestError) {
      showNotification({
        title: 'No se pudo actualizar',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  // --- citas-pagos follow-on: cobrar cita + editar precio ------------
  const [chargingCita, setChargingCita] = useState<ProspectMedicalAppointment | null>(null)
  const [editingPrecioCita, setEditingPrecioCita] = useState<ProspectMedicalAppointment | null>(null)

  // Wrappers used by the child ``EditProspectModal`` — TS strict mode
  // forbids unused local symbols, and the child's callbacks need the
  // cita row from inside the EditProspectModal scope, not from here.
  function handleChargeAppointmentFromChild(cita: ProspectMedicalAppointment) {
    // Resolve the fresh cita from the current prospects array so the
    // cobro modal shows the up-to-date precio / saldoPendiente
    // (not the stale reference the admin clicked before ``reload()``
    // completed after a previous cobro).
    const fresh =
      (data?.prospects ?? [])
        .find((p) => p.rawId === cita.prospectRawId)
        ?.medicalAppointments?.find((c) => c.rawId === cita.rawId) ?? cita;
    setChargingCita(fresh);
  }

  function handleEditPriceFromChild(cita: ProspectMedicalAppointment) {
    // Always resolve the FRESH cita object from the current prospects
    // array so the modal shows the up-to-date precio (not the stale
    // reference the admin clicked on before ``reload()`` completed).
    const fresh =
      (data?.prospects ?? [])
        .find((p) => p.rawId === cita.prospectRawId)
        ?.medicalAppointments?.find((c) => c.rawId === cita.rawId) ?? cita;
    setEditingPrecioCita(fresh);
  }

  async function handleConfirmCharge(payload: {
    paymentMethod: 'VIRTUAL' | 'FISICO' | 'MIXTO'
    amount: string
    montoFisico?: string
    montoVirtual?: string
    receiptFile?: File
    details?: string
  }) {
    if (!chargingCita) return
    try {
      await chargeAdminProspectAppointment(chargingCita.rawId, payload)
      showNotification({
        title: 'Pago registrado',
        message: 'El cobro de la cita fue aprobado correctamente.',
        tone: 'success',
      })
      setChargingCita(null)
      reload()
    } catch (requestError: any) {
      showNotification({
        title: 'No se pudo cobrar',
        message: requestError.message,
        tone: 'danger',
      })
    }
  }

  async function handleConfirmEditPrice(newPrecio: string) {
    if (!editingPrecioCita) return
    try {
      await updateAdminProspectAppointmentPrice(editingPrecioCita.rawId, newPrecio)
      showNotification({
        title: 'Precio actualizado',
        message: 'El precio de la cita fue actualizado.',
        tone: 'success',
      })
      setEditingPrecioCita(null)
      reload()
    } catch (requestError: any) {
      showNotification({
        title: 'No se pudo actualizar',
        message: requestError.message,
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
              <label className="field">
                <span>Origen</span>
                <select
                  className="input"
                  value={origenFilter}
                  onChange={(event) =>
                    setOrigenFilter(event.target.value as 'TODOS' | 'NUEVO' | 'RECURRENTE_PRE_SISTEMA')
                  }
                >
                  <option value="TODOS">Todos</option>
                  <option value="NUEVO">Nuevo</option>
                  <option value="RECURRENTE_PRE_SISTEMA">Recurrente pre-sistema</option>
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
                      <th>Origen</th>
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
                              onClick={() => lead.rawId && setEditingProspectId(lead.rawId)}
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
                              tone={lead.origen === 'RECURRENTE_PRE_SISTEMA' ? 'warning' : 'info'}
                            >
                              {lead.origen === 'RECURRENTE_PRE_SISTEMA' ? 'Recurrente pre-sistema' : 'Nuevo'}
                            </StatusBadge>
                          </td>
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
              onClose={() => setEditingProspectId(null)}
              onSave={handleUpdateProspect}
              isUpdating={isUpdating}
              handleCancelAppointment={(appointmentId) => handleCancelAppointment(appointmentId, editingProspect.rawId)}
              handleMarkAppointmentAsCompleted={(appointmentId) => handleMarkAppointmentAsCompleted(appointmentId, editingProspect.rawId)}
              onChargeAppointment={handleChargeAppointmentFromChild}
              onEditAppointmentPrice={handleEditPriceFromChild}
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
                setBookingPrecio('')
                setConcurrencyInfo(null)
              }}
              onReserve={handleReserve}
              selectedDate={selectedDate}
              setSelectedDate={setSelectedDate}
              selectedTime={selectedTime}
              setSelectedTime={setSelectedTime}
              bookingPrecio={bookingPrecio}
              setBookingPrecio={setBookingPrecio}
              concurrencyInfo={concurrencyInfo}
              setConcurrencyInfo={setConcurrencyInfo}
              handleCheckConcurrency={handleCheckConcurrency}
              isChecking={isChecking}
              isBooking={Boolean(isBookingKey)}
            />
          ) : null}

          {/* citas-pagos follow-on: cobrar cita + editar precio */}
          {chargingCita ? (
            (() => {
              // Resolve the prospect name once — used as the modal
              // header label via the existing `operation` field.
              const prospect = bookingProspect
                ?? (data?.prospects ?? []).find(p => p.rawId === chargingCita.prospectRawId)
              const headerLabel = prospect?.name ?? 'Prospecto'
              return (
                <AdminRegisterAppointmentPaymentModal
                  appointment={{
                    rawId: chargingCita.rawId,
                    id: chargingCita.id,
                    operationRawId: null,
                    operation: headerLabel,
                    specialist: chargingCita.specialist,
                    dateTime: chargingCita.dateTime,
                    status: chargingCita.status,
                    statusTone: chargingCita.statusTone ?? 'approved',
                    verificationStatus: 'no_requerida',
                    verificationMethod: null,
                    details: '',
                    canManage: false,
                    canMarkPendingBiometric: false,
                    canConfirmBiometric: false,
                    canCancelFromVerification: false,
                    precio: chargingCita.precio,
                    saldoPendiente: chargingCita.saldoPendiente,
                    pagos_count: chargingCita.pagos_count,
                    pagos: chargingCita.pagos,
                  }}
                  isOpen={Boolean(chargingCita)}
                  isSubmitting={false}
                  errorMessage={null}
                  onClose={() => setChargingCita(null)}
                  onSubmit={handleConfirmCharge}
                />
              )
            })()
          ) : null}
          {editingPrecioCita ? (
            // ``key={editingPrecioCita.rawId}`` forces the modal to remount
            // when the admin switches between citas without unmounting in
            // between — without it, the controlled <input> can latch onto
            // a stale ``draft`` from the previous cita (price 0 when the
            // new cita has precio 80).
            <EditAppointmentPriceModal
              key={editingPrecioCita.rawId}
              citaRawId={editingPrecioCita.rawId}
              currentPrecio={editingPrecioCita.precio ?? 'Bs 0.00'}
              onClose={() => setEditingPrecioCita(null)}
              onSubmit={handleConfirmEditPrice}
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
  bookingPrecio,
  setBookingPrecio,
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
  bookingPrecio: string
  setBookingPrecio: (p: string) => void
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

                    <label className="field" style={{ marginTop: '1rem' }}>
                      <span>Precio de la cita (opcional)</span>
                      <input
                        type="number"
                        className="input"
                        min="0"
                        step="0.01"
                        placeholder="0.00"
                        value={bookingPrecio}
                        onChange={(e) => setBookingPrecio(e.target.value)}
                      />
                      <small className="field__hint">
                        Deja en 0 para agendar sin cobrar. Podras asignar el precio despues.
                      </small>
                    </label>

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
  onChargeAppointment,
  onEditAppointmentPrice,
}: {
  prospect: ProspectLead
  onClose: () => void
  onSave: (data: any) => Promise<void>
  isUpdating: boolean
  handleCancelAppointment: (id: number) => Promise<void>
  handleMarkAppointmentAsCompleted: (appointmentId: number, prospectId?: number) => Promise<void>
  onChargeAppointment: (cita: ProspectMedicalAppointment) => void
  onEditAppointmentPrice: (cita: ProspectMedicalAppointment) => void
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

  // Re-seed the editable inputs only when the modal is opened with a
  // DIFFERENT prospect. We deliberately do NOT sync on every prop
  // change — once the admin has started typing in a field, the parent's
  // ``reload()`` would otherwise wipe their in-progress edits. Display
  // data (name, header, appointment list, derived cobro state) reads
  // directly off ``prospect`` so it always reflects the freshest copy
  // without any extra plumbing.
  useEffect(() => {
    setPrimerNombre(prospect.primerNombre || prospect.firstName || '')
    setSegundoNombre(prospect.segundoNombre || '')
    setApellidoPaterno(prospect.apellidoPaterno || prospect.lastName || '')
    setApellidoMaterno(prospect.apellidoMaterno || '')
    setPhone(prospect.phone || '')
    setObservations(prospect.observations || '')
    setStateValue(prospect.stateValue === 'DESCARTADO' ? 'DESCARTADO' : 'PASAJERO')
    setTempStatuses({})
    setEditingStatusId(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prospect.rawId])

  const isEditable = prospect.state !== 'Convertido'

  // citas-pagos follow-on: derive cobro state per cita so the JSX
  // can disable 'Cobrar cita' / 'Editar precio' once the cita is
  // fully paid, and surface a small 'cobrada' hint below the status
  // badge. Backend already locks ``precio`` after the first APROBADO
  // row — the UI just needs to mirror that contract.
  const parseCurrencyLocal = (raw: string | undefined | null): number => {
    if (raw === undefined || raw === null || raw === '') return 0
    const cleaned = String(raw).replace(/^Bs\s*/i, '').replace(/,/g, '').trim()
    const num = Number(cleaned)
    return Number.isFinite(num) ? num : 0
  }
  function deriveCobroState(cita: ProspectMedicalAppointment) {
    const precio = parseCurrencyLocal(cita.precio)
    const saldo = parseCurrencyLocal(cita.saldoPendiente)
    const pagosCount = cita.pagos_count ?? 0
    const approvedSum = (cita.pagos ?? []).reduce((acc, p) => {
      if (p.estado_verificacion !== 'APROBADO') return acc
      return acc + (Number(p.monto_pagado) || 0)
    }, 0)
    return {
      precio,
      saldo,
      approvedSum,
      pagosCount,
      isFullyPaid: precio > 0 && saldo <= 0,
      isPartiallyPaid: approvedSum > 0 && saldo > 0,
    }
  }

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
                        {/* citas-pagos follow-on: precio / saldoPendiente per cita */}
                        <div style={{ marginTop: '0.4rem', fontSize: '0.85rem', color: 'var(--color-text-soft)' }}>
                          Precio: {cita.precio ?? 'Bs 0.00'} — Saldo pendiente: {cita.saldoPendiente ?? 'Bs 0.00'}
                        </div>
                        {(() => {
                          const cobro = deriveCobroState(cita)
                          if (cobro.isFullyPaid) {
                            const pagoWord = cobro.pagosCount === 1 ? 'pago' : 'pagos'
                            return (
                              <div
                                style={{
                                  marginTop: '0.4rem',
                                  fontSize: '0.8rem',
                                  color: 'var(--color-text-soft)',
                                  fontWeight: 500,
                                }}
                              >
                                Ya cobrada — Bs {cobro.approvedSum.toFixed(2)} ({cobro.pagosCount} {pagoWord}).
                              </div>
                            )
                          }
                          if (cobro.isPartiallyPaid) {
                            return (
                              <div
                                style={{
                                  marginTop: '0.4rem',
                                  fontSize: '0.8rem',
                                  color: 'var(--color-text-soft)',
                                  fontWeight: 500,
                                }}
                              >
                                Cobrado Bs {cobro.approvedSum.toFixed(2)} — falta Bs {cobro.saldo.toFixed(2)}.
                              </div>
                            )
                          }
                          return null
                        })()}
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
                      {isEditable && !tempStatuses[cita.rawId] && (
                        <>
                          {/* citas-pagos follow-on: cobrar cita + editar precio.
                              These are visible whenever the cita is in
                              PROGRAMADA, regardless of the hora — admins
                              must still be able to cobrar/edit/mark a cita
                              that is happening right now (e.g. the
                              ``02/09 19:20`` cita at 19:30). They get
                              disabled once the cita is fully paid (the
                              backend locks the price after the first
                              APROBADO row). Partial payments keep the
                              buttons live so the admin can complete the
                              cobro. */}
                          {(() => {
                            const cobro = deriveCobroState(cita)
                            const isFullyPaid = cobro.isFullyPaid
                            const buttonsDisabled = isFullyPaid
                            return (
                              <>
                                {currentStatusValue === 'PROGRAMADA' && (
                                  <button
                                    className="button button--compact"
                                    style={{
                                      background: 'var(--color-success, #16a34a)',
                                      color: '#fff',
                                      opacity: buttonsDisabled ? 0.5 : 1,
                                      cursor: buttonsDisabled ? 'not-allowed' : 'pointer',
                                    }}
                                    disabled={buttonsDisabled}
                                    title={
                                      buttonsDisabled
                                        ? 'La cita ya esta cobrada en su totalidad.'
                                        : undefined
                                    }
                                    onClick={() => onChargeAppointment(cita)}
                                  >
                                    Cobrar cita
                                  </button>
                                )}
                                {currentStatusValue === 'PROGRAMADA' && (
                                  <button
                                    className="button button--ghost button--compact"
                                    disabled={buttonsDisabled}
                                    title={
                                      buttonsDisabled
                                        ? 'No puedes cambiar el precio despues de un cobro aprobado.'
                                        : undefined
                                    }
                                    onClick={() => onEditAppointmentPrice(cita)}
                                  >
                                    Editar precio
                                  </button>
                                )}
                              </>
                            )
                          })()}
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
                          {/* Anular is gated by ``canCancel`` because
                              cancelling a past appointment makes no sense —
                              the backend would also reject it. The cobro /
                              edit / realizada buttons above do NOT need
                              that gate. */}
                          {cita.canCancel && (
                            <button
                              className="button button--danger button--compact"
                              onClick={() => {
                                void handleCancelAppointment(cita.rawId)
                                onClose()
                              }}
                            >
                              Anular
                            </button>
                          )}
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
