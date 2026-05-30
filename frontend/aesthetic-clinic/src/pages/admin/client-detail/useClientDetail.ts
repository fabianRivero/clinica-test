import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useApiResource } from '../../../hooks/useApiResource'
import { useConfirmDialog } from '../../../hooks/useConfirmDialog'
import { useNotifications } from '../../../providers/NotificationProvider'
import {
  cancelAdminAppointment,
  cancelAdminAppointmentVerification,
  checkAdminConcurrency,
  confirmAdminAppointmentBiometric,
  createAdminClientFreeMedicalAppointment,
  createAdminClientReservation,
  getAdminClientDetail,
  inactivateAdminClient,
  markAdminAppointmentPendingBiometric,
  rescheduleAdminAppointment,
  updateAdminPaymentStatus,
} from '../../../services/api/admin'
import { verifyMockFingerprint } from '../../../services/fingerprint/mockFingerprint'
import type { AdminConcurrencyCheckResponse } from '../../../types/admin'
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
  const [pendingQuotaProcedureFilter, setPendingQuotaProcedureFilter] = useState<string>('')
  const [isMigrating, setIsMigrating] = useState(false)
  const { user } = useAuth()
  const isMainAdmin = user?.isMainAdmin || user?.isSuperuser
  const { branches } = useBranchContext()

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
        tone: 'success',
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

  async function handleConfirmBiometric(appointmentId: number, biometricMockTemplate: string) {
    if (!biometricMockTemplate) {
      showNotification({
        title: 'Sin huella registrada',
        message: 'Este cliente no tiene una huella mock disponible para comparar.',
        tone: 'danger',
      })
      return
    }

    setAppointmentActionId(appointmentId)
    try {
      const capture = await verifyMockFingerprint(biometricMockTemplate)
      const response = await confirmAdminAppointmentBiometric(appointmentId, {
        provider: capture.provider,
        template: capture.template,
        quality: capture.quality,
        deviceSerial: capture.deviceSerial,
      })
      showNotification({
        title: 'Huella confirmada',
        message: 'La cita fue confirmada con la huella biometrica simulada.',
        tone: 'success',
      })
      reload()
      void response
    } catch (requestError) {
      showNotification({
        title: 'No se pudo confirmar la huella',
        message: requestError instanceof Error ? requestError.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    } finally {
      setAppointmentActionId(null)
    }
  }

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

  async function handleRescheduleAppointment() {
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

  async function handleReserve() {
    if (!data || !effectiveOperationId || !activeBranch) return
    setIsBookingKey('booking')

    try {
      const response = await createAdminClientReservation(data.client.rawId, effectiveOperationId, {
        branchId: activeBranch.id,
        dateTime: `${selectedDate}T${selectedTime}:00`
      })
      showNotification({ title: 'Reserva registrada', message: response.detail, tone: 'success' })
      reload()
      setSelectedOperationId('')
      setSelectedDate('')
      setSelectedTime('')
      setConcurrencyInfo(null)
    } catch (requestError: any) {
      showNotification({
        title: 'No se pudo reservar',
        message: requestError.message,
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
  const operationStatuses = data ? Array.from(new Set(data.operations.map((operation) => operation.status))) : []
  const filteredOperations = data
    ? data.operations.filter((operation) =>
        operationStatusFilter ? operation.status === operationStatusFilter : true,
      )
    : []
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
    operationStatuses,
    filteredOperations,

    // Pending quota state
    pendingQuotaProcedureFilter,
    setPendingQuotaProcedureFilter,
    pendingQuotaProcedures,
    filteredPendingQuotas,

    // Handlers
    handleCancelAppointment,
    handleMarkPendingBiometric,
    handleConfirmBiometric,
    handleCancelFromVerification,
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
  }
}