import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useApiResource } from '../../../hooks/useApiResource'
import { useConfirmDialog } from '../../../hooks/useConfirmDialog'
import { useNotifications } from '../../../providers/NotificationProvider'
import { monthNames } from '../expenses/expenseUtils'
import {
  cancelAdminAppointment,
  cancelAdminAppointmentVerification,
  cancelAdminFreeMedicalAppointment,
  confirmAdminFreeMedicalAppointment,
  checkAdminConcurrency,
  createAdminClientFreeMedicalAppointment,
  createAdminClientReservation,
  getAdminClientDetail,
  inactivateAdminClient,
  markAdminAppointmentPendingBiometric,
  rescheduleAdminAppointment,
  updateAdminPaymentStatus,
} from '../../../services/api/admin'
import {
  biometricClient,
  isBiometricSuspended,
  type AgentListItem,
} from '../../../services/fingerprint/biometricClient'
import type { AdminConcurrencyCheckResponse, AdminReservationExtendedPayload } from '../../../types/admin'
import { useBranchContext } from '../../../providers/BranchProvider'
import { migrateAdminClient } from '../../../services/api/admin'
import { useAuth } from '../../../providers/AuthProvider'

export function useClientDetail(clientId: string) {
  const navigate = useNavigate()
  const { showNotification } = useNotifications()
  const { confirm, ConfirmDialog: ConfirmDialogModal } = useConfirmDialog()
  const loader = useCallback(() => getAdminClientDetail(clientId), [clientId])
  const { data, isLoading, error, reload } = useApiResource(loader)

  const [selectedOperationId, setSelectedOperationId] = useState<number | ''>('')
  const { activeBranch } = useBranchContext()
  const [selectedDate, setSelectedDate] = useState('')
  const [selectedTime, setSelectedTime] = useState('')
  const [concurrencyInfo, setConcurrencyInfo] = useState<AdminConcurrencyCheckResponse | null>(null)

  const [freeSelectedDate, setFreeSelectedDate] = useState('')
  const [freeSelectedTime, setFreeSelectedTime] = useState('')
  const [freeConcurrencyInfo, setFreeConcurrencyInfo] = useState<AdminConcurrencyCheckResponse | null>(null)

  const [isChecking, setIsChecking] = useState(false)
  const [isBookingKey, setIsBookingKey] = useState<string | null>(null)
  const [isFreeBookingKey, setIsFreeBookingKey] = useState<string | null>(null)
  const [isInactivating, setIsInactivating] = useState(false)
  const [appointmentActionId, setAppointmentActionId] = useState<number | null>(null)
  const [rescheduleAppointmentId, setRescheduleAppointmentId] = useState<number | null>(null)
  const [rescheduleDate, setRescheduleDate] = useState('')
  const [rescheduleTime, setRescheduleTime] = useState('')
  const [rescheduleCheck, setRescheduleCheck] = useState<AdminConcurrencyCheckResponse | null>(null)
  const [isCheckingReschedule, setIsCheckingReschedule] = useState(false)
  const [paymentNotes, setPaymentNotes] = useState<Record<number, string>>({})
  const [paymentActionId, setPaymentActionId] = useState<number | null>(null)
  const [operationStatusFilter, setOperationStatusFilter] = useState<string>('')
  // Filtro por mes/anio de inicio del tratamiento. `YYYY-MM` o `''` para
  // "Todos los periodos".
  const [operationPeriodFilter, setOperationPeriodFilter] = useState<string>('')
  const [pendingQuotaProcedureFilter, setPendingQuotaProcedureFilter] = useState<string>('')
  const [isMigrating, setIsMigrating] = useState(false)
  const { user } = useAuth()
  const isMainAdmin = user?.isMainAdmin || user?.isSuperuser
  const { branches } = useBranchContext()

  // Appointment month navigation state
  const now = new Date()
  const [appointmentMonth, setAppointmentMonth] = useState(now.getMonth() + 1)
  const [appointmentYear, setAppointmentYear] = useState(now.getFullYear())
  const [appointmentStatusFilter, setAppointmentStatusFilter] = useState('')
  const [visibleAppointmentCount, setVisibleAppointmentCount] = useState(5)

  // Pagination state for other sections
  const [visiblePaymentsCount, setVisiblePaymentsCount] = useState(5)
  const [visibleSessionsCount, setVisibleSessionsCount] = useState(5)
  const [visibleOperationsCount, setVisibleOperationsCount] = useState(5)
  const [sessionStatusFilter, setSessionStatusFilter] = useState('')
  const [sessionProcedureFilter, setSessionProcedureFilter] = useState('')

  // Month navigation function with year wrap logic
  const changeAppointmentMonth = (direction: -1 | 1) => {
    setAppointmentMonth(current => {
      const next = current + direction
      if (next < 1) { setAppointmentYear(y => y - 1); return 12 }
      if (next > 12) { setAppointmentYear(y => y + 1); return 1 }
      return next
    })
    setVisibleAppointmentCount(5)
  }

  // Month label for display
  const viewedMonthLabel = `${monthNames[appointmentMonth - 1]} ${appointmentYear}`

  // Extract unique statuses from appointments
  const appointmentStatuses = useMemo(() => {
    const appointments = data?.appointments ?? []
    const statuses = [...new Set(appointments.map(a => a.status))]
    return statuses.sort()
  }, [data])

  // Filter appointments by month/year/status
  // dateTime format is "DD/MM HH:MM" (e.g., "31/05 01:00")
  const filteredAppointments = useMemo(() => {
    const appointments = data?.appointments ?? []
    return appointments.filter(a => {
      // Parse "DD/MM HH:MM" format
      const parts = a.dateTime.split(' ')[0].split('/') // ["DD", "MM"]
      const appointmentMonthNum = parseInt(parts[1], 10)
      const matchesMonth = appointmentMonthNum === appointmentMonth
      const matchesYear = true // No year in dateTime format, show all years
      const matchesStatus = !appointmentStatusFilter || a.status === appointmentStatusFilter
      return matchesMonth && matchesYear && matchesStatus
    })
  }, [data, appointmentMonth, appointmentYear, appointmentStatusFilter])

  // Visible slice for pagination
  const visibleAppointments = filteredAppointments.slice(0, visibleAppointmentCount)
  const hasMore = visibleAppointmentCount < filteredAppointments.length
  const hasLess = visibleAppointmentCount > 5

  // Payments pagination
  const visiblePayments = (data?.payments ?? []).slice(0, visiblePaymentsCount)
  const hasMorePayments = visiblePaymentsCount < (data?.payments?.length ?? 0)
  const hasLessPayments = visiblePaymentsCount > 5

  // Sessions filtering
  const sessionStatuses = useMemo(
    () => (data ? Array.from(new Set(data.sessions.map((session) => session.status))) : []),
    [data],
  )
  const sessionProcedures = useMemo(
    () => (data ? Array.from(new Set(data.sessions.map((session) => session.operation))) : []),
    [data],
  )
  const filteredSessions = useMemo(
    () =>
      data
        ? data.sessions.filter((session) => {
            const statusMatch = sessionStatusFilter ? session.status === sessionStatusFilter : true
            const procedureMatch = sessionProcedureFilter ? session.operation === sessionProcedureFilter : true
            return statusMatch && procedureMatch
          })
        : [],
    [data, sessionStatusFilter, sessionProcedureFilter],
  )

  // Sessions pagination
  const visibleSessions = filteredSessions.slice(0, visibleSessionsCount)
  const hasMoreSessions = visibleSessionsCount < filteredSessions.length
  const hasLessSessions = visibleSessionsCount > 5

  const reservableOperations = useMemo(
    () => data?.operations.filter((operation: any) => operation.status === 'En proceso') ?? [],
    [data],
  )
  const effectiveOperationId = (selectedOperationId ?? reservableOperations[0]?.rawId) ?? ''

  async function handleCancelAppointment(appointmentId: number) {
    const shouldCancel = await confirm({
      title: 'Cancelar reserva',
      message: 'Se cancelara esta reserva y el cupo volvera a quedar disponible. ¿Deseas continuar?',
      tone: 'warning',
    })
    if (!shouldCancel) return

    try {
      const response = await cancelAdminAppointment(appointmentId)
      showNotification({ title: 'Cita cancelada', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo cancelar la cita',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  async function handleCancelFreeMedicalAppointment(appointmentId: number) {
    const shouldCancel = await confirm({
      title: 'Cancelar reserva',
      message: 'Se cancelara esta reserva y el cupo volvera a quedar disponible. ¿Deseas continuar?',
      tone: 'warning',
    })
    if (!shouldCancel) return

    try {
      const response = await cancelAdminFreeMedicalAppointment(appointmentId)
      showNotification({ title: 'Cita cancelada', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo cancelar la cita',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  async function handleConfirmFreeMedicalAppointment(appointmentId: number) {
    const confirmed = await confirm({
      title: 'Confirmar cita',
      message: '¿Está seguro que desea marcar esta cita como realizada?',
      tone: 'info',
    })
    if (!confirmed) return

    try {
      const response = await confirmAdminFreeMedicalAppointment(appointmentId)
      showNotification({ title: 'Cita confirmada', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo confirmar la cita',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  async function handleMarkPendingBiometric(appointmentId: number) {
    const confirmed = await confirm({
      title: 'Confirmar cambio de estado',
      message: 'Solo se debe cambiar a este estado cuando el cliente asiste al tratamiento. ¿Deseas continuar?',
      tone: 'warning',
    })
    if (!confirmed) return

    setAppointmentActionId(appointmentId)
    try {
      const response = await markAdminAppointmentPendingBiometric(appointmentId)
      showNotification({
        title: 'Cita pendiente de verificación',
        message: response.detail,
        tone: 'info',
      })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo actualizar la cita',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    } finally {
      setAppointmentActionId(null)
    }
  }

  // The biometric confirm flow is now driven by BiometricVerifyCaptureModal.
  // We only own the modal open/close state here; the modal owns the
  // verify-init + verify-confirm round-trip and reports back via
  // onConfirmResult. The modal lifecycle is also what keeps the button
  // disabled (appointmentActionId is set while the modal is open).
  const [verifyModalCitaId, setVerifyModalCitaId] = useState<number | null>(null)

  function openVerifyBiometric(appointmentId: number) {
    setAppointmentActionId(appointmentId)
    setVerifyModalCitaId(appointmentId)
  }

  function closeVerifyBiometric() {
    setVerifyModalCitaId(null)
    setAppointmentActionId(null)
  }

  // -----------------------------------------------------------------
  // Agent online/offline detection (5-minute heartbeat window).
  // -----------------------------------------------------------------
  const [agents, setAgents] = useState<AgentListItem[]>([])

  const refreshAgents = useCallback(async () => {
    // `listAgents` short-circuits to `[]` while suspended, so calling
    // it here is safe and keeps the banner logic uniform.
    try {
      const list = await biometricClient.listAgents()
      setAgents(list)
    } catch {
      // Silently swallow: the banner is purely informational and the
      // backend may be temporarily unavailable during navigation.
    }
  }, [])

  // Computed once per render — the value is baked at build time and
  // does not change at runtime, but the call is cheap.
  const biometricSuspended = isBiometricSuspended()

  useEffect(() => {
    // Skipping the polling entirely while suspended avoids touching
    // the backend and keeps the agent list cleared so the offline
    // banner computation reads `false`. No runtime flag toggling —
    // rebuilding the bundle is required to flip the flag, by design.
    // The two `setAgents(...)` / `refreshAgents` calls are the
    // documented sync-from-external-system pattern; the lint rule
    // fires on the direct setState inside the effect body, so we
    // disable just that line.
    if (biometricSuspended) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAgents([])
      return
    }
    // Fetching on mount then polling every minute. `refreshAgents` is
    // an async callback that calls `setAgents` internally — the lint
    // rule does not fire on async-derived updates, so no disable is
    // needed here.
    void refreshAgents()
    const interval = window.setInterval(() => {
      void refreshAgents()
    }, 60_000)
    return () => window.clearInterval(interval)
  }, [biometricSuspended, refreshAgents])

  const hasAnyAgent = agents.length > 0
  const allAgentsOffline =
    hasAnyAgent && agents.every((agent) => !biometricClient.isAgentOnline(agent.last_seen_at))

  async function handleCancelFromVerification(appointmentId: number) {
    const confirmed = await confirm({
      title: '¿Está seguro?',
      message: '¿Está seguro que desea cancelar la verificación?',
      tone: 'warning',
    })
    if (!confirmed) return

    setAppointmentActionId(appointmentId)
    try {
      const response = await cancelAdminAppointmentVerification(appointmentId)
      showNotification({
        title: 'Verificación cancelada',
        message: response.detail,
        tone: 'success',
      })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo cancelar la verificación',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    } finally {
      setAppointmentActionId(null)
    }
  }

  async function handleCheckRescheduleAvailability() {
    if (!activeBranch || !rescheduleDate || !rescheduleTime) {
      showNotification({ title: 'Atencion', message: 'Selecciona fecha y hora.', tone: 'warning' })
      return
    }
    setIsCheckingReschedule(true)
    try {
      const info = await checkAdminConcurrency(activeBranch.id, rescheduleDate, rescheduleTime, rescheduleTime)
      setRescheduleCheck(info)
    } catch (err: any) {
      showNotification({ title: 'Error', message: err.message, tone: 'danger' })
    } finally {
      setIsCheckingReschedule(false)
    }
  }

  async function handleRescheduleAppointment(onSuccess?: () => void) {
    if (!rescheduleAppointmentId || !rescheduleCheck) return
    setAppointmentActionId(rescheduleAppointmentId)
    try {
      const response = await rescheduleAdminAppointment(rescheduleAppointmentId, {
        dateTime: `${rescheduleDate}T${rescheduleTime}:00`,
      })
      showNotification({ title: 'Reserva reprogramada', message: response.detail, tone: 'success' })
      setRescheduleAppointmentId(null)
      setRescheduleDate('')
      setRescheduleTime('')
      setRescheduleCheck(null)
      reload()
      onSuccess?.()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo reprogramar',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    } finally {
      setAppointmentActionId(null)
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

  async function handleCheckFreeConcurrency() {
    if (!activeBranch || !freeSelectedDate || !freeSelectedTime) {
      showNotification({ title: 'Atencion', message: 'Selecciona fecha y hora.', tone: 'warning' })
      return
    }
    setIsChecking(true)
    try {
      const info = await checkAdminConcurrency(activeBranch.id, freeSelectedDate, freeSelectedTime, freeSelectedTime)
      setFreeConcurrencyInfo(info)
    } catch (err: any) {
      showNotification({ title: 'Error', message: err.message, tone: 'danger' })
    } finally {
      setIsChecking(false)
    }
  }

  async function handleReserve(payload?: AdminReservationExtendedPayload) {
    // El modal ya arma el payload completo; cuando se invoca sin argumentos
    // (legacy) caemos a los inputs locales del componente inline.
    const operationId = selectedOperationId
    if (!data || !operationId || !activeBranch) {
      showNotification({ title: 'Atencion', message: 'Selecciona un procedimiento.', tone: 'warning' })
      return
    }
    const finalPayload: AdminReservationExtendedPayload = payload ?? {
      branchId: activeBranch.id,
      dateTime: `${selectedDate}T${selectedTime}:00`,
    }
    if (payload) {
      // Si la operacion vino en el payload, la tomamos del modal; si no,
      // usamos la seleccion legacy del componente inline.
      finalPayload.branchId = payload.branchId ?? activeBranch.id
      finalPayload.dateTime = payload.dateTime ?? `${selectedDate}T${selectedTime}:00`
    }
    setIsBookingKey('booking')

    try {
      const response = await createAdminClientReservation(data.client.rawId, operationId, finalPayload)
      showNotification({ title: 'Reserva registrada', message: response.detail, tone: 'success' })
      reload()
      setSelectedOperationId('')
      setSelectedDate('')
      setSelectedTime('')
      setConcurrencyInfo(null)
    } catch (requestError: unknown) {
      const message = requestError instanceof Error ? requestError.message : 'No se pudo reservar.'
      showNotification({
        title: 'No se pudo reservar',
        message,
        tone: 'danger',
      })
    } finally {
      setIsBookingKey(null)
    }
  }

  async function handleReserveFreeMedicalAppointment() {
    if (!data || !activeBranch) return
    setIsFreeBookingKey('booking')

    try {
      const response = await createAdminClientFreeMedicalAppointment(data.client.rawId, {
        branchId: activeBranch.id,
        dateTime: `${freeSelectedDate}T${freeSelectedTime}:00`
      })
      showNotification({ title: 'Cita medica registrada', message: response.detail, tone: 'success' })
      reload()
      setFreeSelectedDate('')
      setFreeSelectedTime('')
      setFreeConcurrencyInfo(null)
    } catch (requestError: any) {
      showNotification({
        title: 'No se pudo reservar',
        message: requestError.message,
        tone: 'danger',
      })
    } finally {
      setIsFreeBookingKey(null)
    }
  }

  async function handleInactivateClient() {
    if (!data) return
    const activeOperations = data.operations.filter((operation) => operation.status === 'En proceso')
    const pendingSessions = activeOperations.reduce(
      (total, operation) =>
        total + Math.max(operation.sessions.total - operation.sessions.confirmed, 0),
      0,
    )
    const pendingQuotas = data.pendingQuotas.length
    const warningDetail =
      pendingSessions || pendingQuotas
        ? `Advertencia: este cliente aun tiene ${pendingSessions} sesion(es) y ${pendingQuotas} cuota(s) pendiente(s). `
        : ''
    const confirmed = await confirm({
      title: 'Inactivar cliente',
      message: `${warningDetail}El cliente pasara a inactivo, se cancelaran sus procedimientos en proceso y sus citas programadas. ¿Deseas continuar?`,
      tone: 'danger',
    })
    if (!confirmed) return

    setIsInactivating(true)
    try {
      const response = await inactivateAdminClient(data.client.rawId)
      showNotification({ title: 'Cliente inactivo', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo inactivar',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    } finally {
      setIsInactivating(false)
    }
  }

  async function handleMigrateClient(branchId: number) {
    if (!data) return
    const branchName = branches.find(b => b.id === branchId)?.nombre || 'esta sucursal'
    const confirmed = await confirm({
      title: 'Migrar cliente',
      message: `¿Seguro que deseas migrar este cliente a la sucursal ${branchName}? Podra ser gestionado por los administradores de esa sucursal.`,
    })
    if (!confirmed) return

    setIsMigrating(true)
    try {
      const response = await migrateAdminClient(data.client.rawId, branchId)
      showNotification({ title: 'Cliente migrado', message: response.detail, tone: 'success' })
      reload()
    } catch (requestError: any) {
      showNotification({
        title: 'Error al migrar',
        message: requestError.message,
        tone: 'danger',
      })
    } finally {
      setIsMigrating(false)
    }
  }

  const getPaymentNote = (paymentId: number, fallbackNote?: string) =>
    paymentNotes[paymentId] ?? fallbackNote ?? ''

  const handlePaymentNoteChange = (paymentId: number, note: string) => {
    setPaymentNotes((current) => ({
      ...current,
      [paymentId]: note,
    }))
  }

  async function handlePaymentStatusUpdate(
    paymentId: number,
    currentStatus: string,
    status: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO',
    fallbackNote?: string,
  ) {
    const normalizedCurrentStatus = currentStatus.trim().toUpperCase()
    if (normalizedCurrentStatus === 'APROBADO') {
      showNotification({
        title: 'Pago bloqueado',
        message: 'Los pagos aprobados ya no se pueden modificar.',
        tone: 'warning',
      })
      return
    }
    setPaymentActionId(paymentId)
    try {
      const note = status === 'PENDIENTE' ? '' : getPaymentNote(paymentId, fallbackNote)
      const response = await updateAdminPaymentStatus(paymentId, { status, note })
      showNotification({
        title: 'Pago actualizado',
        message: response.detail,
        tone:
          status === 'APROBADO'
            ? 'success'
            : status === 'RECHAZADO' || status === 'CANCELADO'
              ? 'warning'
              : 'info',
      })
      setPaymentNotes((current) => ({ ...current, [paymentId]: response.payment.note || '' }))
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo actualizar el pago',
        message: requestError instanceof Error ? requestError.message : 'Ocurrio un error al cambiar el estado del pago.',
        tone: 'danger',
      })
    } finally {
      setPaymentActionId(null)
    }
  }

  // Computed values that depend on data
  const operationStatuses = useMemo(
    () => (data ? Array.from(new Set(data.operations.map((operation) => operation.status))) : []),
    [data],
  )
  const filteredOperations = useMemo(
    () =>
      data
        ? data.operations.filter((operation) => {
            if (operationStatusFilter && operation.status !== operationStatusFilter) {
              return false
            }
            if (operationPeriodFilter) {
              // `startedAtIso` viene como `YYYY-MM-DD` desde el backend;
              // comparamos los primeros 7 caracteres contra `YYYY-MM` del
              // filtro. Las operaciones sin fecha de inicio no matchean.
              const startedAtIso = (operation as { startedAtIso?: string | null }).startedAtIso
              if (!startedAtIso || !startedAtIso.startsWith(operationPeriodFilter)) {
                return false
              }
            }
            return true
          })
        : [],
    [data, operationStatusFilter, operationPeriodFilter],
  )

  // Operations pagination
  const visibleOperations = filteredOperations.slice(0, visibleOperationsCount)
  const hasMoreOperations = visibleOperationsCount < filteredOperations.length
  const hasLessOperations = visibleOperationsCount > 5

  const pendingQuotaProcedures = data ? Array.from(new Set(data.pendingQuotas.map((quota) => quota.operation))) : []
  const filteredPendingQuotas = data
    ? data.pendingQuotas.filter((quota) =>
        pendingQuotaProcedureFilter ? quota.operation === pendingQuotaProcedureFilter : true,
      )
    : []

  return {
    // Data
    data,
    isLoading,
    error,
    reload,
    clientId,

    // Navigation
    navigate,

    // Confirm dialog
    ConfirmDialogModal,

    // Reservation state
    selectedOperationId,
    setSelectedOperationId,
    selectedDate,
    setSelectedDate,
    selectedTime,
    setSelectedTime,
    concurrencyInfo,
    setConcurrencyInfo,
    isChecking,
    isBookingKey,
    effectiveOperationId,
    reservableOperations,

    // Free medical appointment state
    freeSelectedDate,
    setFreeSelectedDate,
    freeSelectedTime,
    setFreeSelectedTime,
    freeConcurrencyInfo,
    setFreeConcurrencyInfo,
    isFreeBookingKey,

    // Client status
    isInactivating,
    isMigrating,
    isMainAdmin,
    branches,

    // Appointment state
    appointmentActionId,
    rescheduleAppointmentId,
    setRescheduleAppointmentId,
    rescheduleDate,
    setRescheduleDate,
    rescheduleTime,
    setRescheduleTime,
    rescheduleCheck,
    setRescheduleCheck,
    isCheckingReschedule,

    // Payment state
    paymentNotes,
    paymentActionId,

    // Operation state
    operationStatusFilter,
    setOperationStatusFilter,
    operationPeriodFilter,
    setOperationPeriodFilter,
    operationStatuses,
    filteredOperations,

    // Pending quota state
    pendingQuotaProcedureFilter,
    setPendingQuotaProcedureFilter,
    pendingQuotaProcedures,
    filteredPendingQuotas,

    // Handlers
    handleCancelAppointment,
    handleCancelFreeMedicalAppointment,
    handleConfirmFreeMedicalAppointment,
    handleMarkPendingBiometric,
    handleCancelFromVerification,
    refreshAgents,

    // Biometric verify modal state
    verifyModalCitaId,
    openVerifyBiometric,
    closeVerifyBiometric,

    // Agent online/offline state (5-minute heartbeat window)
    agents,
    hasAnyAgent,
    allAgentsOffline,
    biometricSuspended,
    handleCheckRescheduleAvailability,
    handleRescheduleAppointment,
    handleCheckConcurrency,
    handleCheckFreeConcurrency,
    handleReserve,
    handleReserveFreeMedicalAppointment,
    handleInactivateClient,
    handleMigrateClient,
    getPaymentNote,
    handlePaymentNoteChange,
    handlePaymentStatusUpdate,

    // Appointment month navigation
    appointmentMonth,
    appointmentYear,
    changeAppointmentMonth,
    viewedMonthLabel,
    appointmentStatusFilter,
    setAppointmentStatusFilter,
    appointmentStatuses,
    visibleAppointments,
    visibleAppointmentCount,
    setVisibleAppointmentCount,
    filteredAppointments,
    hasMore,
    hasLess,

    // Payments pagination
    visiblePayments,
    visiblePaymentsCount,
    setVisiblePaymentsCount,
    hasMorePayments,
    hasLessPayments,

    // Sessions pagination
    visibleSessions,
    visibleSessionsCount,
    setVisibleSessionsCount,
    hasMoreSessions,
    hasLessSessions,
    sessionStatusFilter,
    setSessionStatusFilter,
    sessionStatuses,
    sessionProcedureFilter,
    setSessionProcedureFilter,
    sessionProcedures,
    filteredSessions,

    // Operations pagination
    visibleOperations,
    visibleOperationsCount,
    setVisibleOperationsCount,
    hasMoreOperations,
    hasLessOperations,

    // Biometric enrollment status (true when the client has an active huella)
    hasBiometricEnrollment: Boolean(data?.client?.hasBiometricEnrollment),
  }
}