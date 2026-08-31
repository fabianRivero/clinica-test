import { useMemo, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useApiResource } from '../../hooks/useApiResource'
import { useConfirmDialog } from '../../hooks/useConfirmDialog'
import { useNotifications } from '../../providers/NotificationProvider'
import { useBranchContext } from '../../providers/BranchProvider'
import { ReservationModal } from './components/ReservationModal'
import { CerrarCitaModal, type CerrarCitaPayload } from './components/CerrarCitaModal'
import { AppointmentNotesPanel } from './components/AppointmentNotesPanel'
import {
  cancelAdminAppointment,
  cancelAdminAppointmentVerification,
  createAdminClientReservation,
  deleteAdminOperationQuota,
  getAdminOperationDetail,
  markAdminAppointmentPendingBiometric,
  rescheduleAdminAppointment,
  updateAdminOperationDetails,
  updateAdminOperationPricePlan,
} from '../../services/api/admin'
import type { AdminReservationExtendedPayload } from '../../types/admin'

function getStatusTone(status: string) {
  const normalized = status.toLowerCase()
  if (normalized.includes('final')) return 'success'
  if (normalized.includes('cancel')) return 'danger'
  if (normalized.includes('borrador')) return 'warning'
  return 'primary'
}

function numberFromCurrency(value: string) {
  return value.replace(/[^\d.]/g, '')
}

/**
 * Convierte el label localizado de fecha (`dd/mm/yyyy`) que devuelve la
 * API a formato ISO (`YYYY-MM-DD`) que entiende `<input type="date">`.
 * Si la cadena no encaja en el formato esperado, devuelve string vacio
 * para no asumir valores incorrectos.
 */
function parseDueDate(label: string): string {
  const match = label.match(/^(\d{2})\/(\d{2})\/(\d{4})$/)
  if (!match) return ''
  return `${match[3]}-${match[2]}-${match[1]}`
}

export function AdminOperationDetailPage() {
  const { operationId = '' } = useParams()
  const loader = useMemo(() => () => getAdminOperationDetail(operationId), [operationId])
  const { data, isLoading, error, reload } = useApiResource(loader)
  const { showNotification } = useNotifications()
  const { confirm, ConfirmDialog } = useConfirmDialog()
  const { activeBranch } = useBranchContext()
  const [appointmentActionId, setAppointmentActionId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [closingAppointmentId, setClosingAppointmentId] = useState<number | null>(null)
  // Tracks which cita's "Datos reales al cierre" panel is open so the
  // admin can compare planning vs real close data side by side. Only one
  // panel is open at a time.
  const [realTimeOpenCitaId, setRealTimeOpenCitaId] = useState<number | null>(null)
  // Photo lightbox: opens when the admin clicks "Ver foto antes/despues"
  // inside the comparison modal. null = closed.
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null)
  const [rescheduleCitaId, setRescheduleCitaId] = useState<number | null>(null)
  const [rescheduleModalOpen, setRescheduleModalOpen] = useState(false)
  const [isRescheduling, setIsRescheduling] = useState(false)
  const [isEditingDetails, setIsEditingDetails] = useState(false)
  const [isSavingDetails, setIsSavingDetails] = useState(false)
  const [isSavingPrice, setIsSavingPrice] = useState(false)
  const [detailsForm, setDetailsForm] = useState({
    details: '',
    recommendations: '',
  })
  // Estado para reservar una nueva cita dentro del bloque "Citas medicas".
  // El formulario inline se reemplazo por un `ReservationModal`; solo
  // conservamos el flag que indica si la reserva esta en curso + el control
  // de apertura/cierre del modal.
  const [reservationModalOpen, setReservationModalOpen] = useState(false)
  const [isBookingReservation, setIsBookingReservation] = useState(false)
  // Estado para editar el numero de sesiones desde el bloque "Citas medicas".
  // `currentSessions` se deriva siempre de la respuesta del backend (sin
  // setState en useEffect) y `sessionsDraft` guarda solo la edicion local
  // del admin; al guardar y recargar `data`, `currentSessions` se
  // actualiza automaticamente.
  const [sessionsDraft, setSessionsDraft] = useState<string>('')
  const [isSavingSessions, setIsSavingSessions] = useState(false)
  // Estado para editar cuotas en modo batch ("Editar fechas y montos"):
  // el admin edita varias a la vez y guarda todas juntas.
  const [isEditingQuotas, setIsEditingQuotas] = useState(false)
  const [quotasDraft, setQuotasDraft] = useState<Array<{ nroCuota: number; montoProgramado: string; fechaVencimiento: string }>>([])
  const [quotasFormError, setQuotasFormError] = useState<string | null>(null)
  // Estado para agregar UNA cuota sola ("Crear cuota" / "Crear la
  // siguiente"). El admin llena monto/fecha y pulsa "Guardar" para
  // crear solo esa fila; el backend no exige suma exacta en este modo,
  // asi que el saldo restante se ira cubriendo con cuotas siguientes.
  const [isAddingQuota, setIsAddingQuota] = useState(false)
  const [newQuotaDraft, setNewQuotaDraft] = useState<{ nroCuota: number; montoProgramado: string; fechaVencimiento: string } | null>(null)
  const [newQuotaFormError, setNewQuotaFormError] = useState<string | null>(null)
  // ``deletingQuotaNumber`` indica cual cuota se esta eliminando
  // (para deshabilitar el boton y mostrar "Eliminando..."). El backend
  // bloquea PAGADAS y con comprobante en revision; el frontend oculta
  // el boton en esos casos.
  const [deletingQuotaNumber, setDeletingQuotaNumber] = useState<number | null>(null)
  // El precio y los montos por cuota se editan desde el bloque "Citas y
// cuotas" (sub-bloque Plan de pagos). El save reutiliza el mismo
// endpoint `actualizar-precio` con la lista `quotas` opcional.

  const handleCancelAppointment = async (appointmentId: number) => {
    setAppointmentActionId(appointmentId)
    setActionError(null)
    try {
      await cancelAdminAppointment(appointmentId)
      reload()
    } catch (requestError) {
      setActionError(requestError instanceof Error ? requestError.message : 'No se pudo cancelar la cita.')
    } finally {
      setAppointmentActionId(null)
    }
  }
  // Step 1 of the close split: pure state transition
  // (PROGRAMADA -> REALIZADA_PENDIENTE_VERIFICACION). No real-time fields
  // are captured here; they move to CerrarCitaModal after the client
  // confirms attendance.
  const handleMarkPending = async (appointmentId: number) => {
    setAppointmentActionId(appointmentId)
    setActionError(null)
    try {
      await markAdminAppointmentPendingBiometric(appointmentId)
      reload()
    } catch (requestError) {
      setActionError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo marcar la cita como pendiente.',
      )
    } finally {
      setAppointmentActionId(null)
    }
  }

  // Same confirm dialog as in AdminClientDetailPage's mark-pending flow.
  // The admin should explicitly confirm before transitioning a cita to
  // REALIZADA_PENDIENTE_DE_VERIFICACION.
  const handleMarkPendingWithConfirm = async (appointmentId: number) => {
    const confirmed = await confirm({
      title: 'Confirmar cambio de estado',
      message:
        'Solo se debe cambiar a este estado cuando el cliente asiste al tratamiento. ¿Deseas continuar?',
      tone: 'warning',
    })
    if (!confirmed) return
    await handleMarkPending(appointmentId)
  }

  // Realizada Pendiente de Verificación → revertir a PROGRAMADA. Útil
  // cuando el admin marcó la cita por error. Mismo endpoint que el spec
  // appointment-states documenta en su flujo "Cancelar verificación".
  const handleRevertPending = async (appointmentId: number) => {
    setAppointmentActionId(appointmentId)
    setActionError(null)
    try {
      const response = await cancelAdminAppointmentVerification(appointmentId)
      showNotification({
        title: 'Verificación cancelada',
        message: response.detail,
        tone: 'info',
      })
      reload()
    } catch (requestError) {
      setActionError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo cancelar la verificación.',
      )
    } finally {
      setAppointmentActionId(null)
    }
  }

  // `handleReschedule` reuses the ReservationModal in reschedule mode. The
  // modal calls onConfirm with the same AdminReservationExtendedPayload
  // shape as a new reservation; we forward it to the reschedule endpoint
  // instead. The cita's dateTime moves, the planning fields replace
  // whatever was previously stored on the cita, and the cita stays in
  // PROGRAMADA (the backend enforces that).
  const handleReschedule = async (payload?: AdminReservationExtendedPayload) => {
    if (!data || rescheduleCitaId === null) return
    if (!payload) {
      setActionError('Falta el payload de la reprogramacion.')
      return
    }
    setIsRescheduling(true)
    setActionError(null)
    try {
      const response = await rescheduleAdminAppointment(rescheduleCitaId, payload)
      showNotification({
        title: 'Cita reprogramada',
        message:
          (response as { detail?: string } | null)?.detail ??
          'La reserva fue reprogramada correctamente.',
        tone: 'success',
      })
      setRescheduleModalOpen(false)
      setRescheduleCitaId(null)
      reload()
    } catch (requestError) {
      showNotification({
        title: 'No se pudo reprogramar la cita',
        message:
          requestError instanceof Error
            ? requestError.message
            : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    } finally {
      setIsRescheduling(false)
    }
  }

  const startEditingDetails = () => {
    if (!data || !canEditPricePlan) return
    setActionError(null)
    setDetailsForm({
      details: data.operation.detallesOperacion === 'Sin detalles registrados.' ? '' : data.operation.detallesOperacion,
      recommendations: data.operation.recomendaciones === 'Sin recomendaciones registradas.' ? '' : data.operation.recomendaciones,
    })
    setIsEditingDetails(true)
  }

  // Total de sesiones vigente segun el backend. Lo derivamos con useMemo
  // para no llamar setState dentro de un effect; el admin edita en un
  // input local (sessionsDraft) y al guardar + recargar el dato se
  // actualiza solo.
  const currentSessions = useMemo<number | null>(() => {
    if (!data) return null
    const match = data.operation.sessions.match(/^(\d+)/)
    return match ? Number(match[1]) : null
  }, [data])

  const handleSaveDetails = async (event: FormEvent) => {
    event.preventDefault()
    if (!data) return

    setIsSavingDetails(true)
    setActionError(null)
    try {
      await updateAdminOperationDetails(data.operation.rawId, detailsForm)
      setIsEditingDetails(false)
      reload()
    } catch (requestError) {
      setActionError(requestError instanceof Error ? requestError.message : 'No se pudo actualizar la operación.')
    } finally {
      setIsSavingDetails(false)
    }
  }

  // -------- handlers del bloque "Citas y cuotas" ----------

const handleSaveSessions = async () => {
    if (!data) return
    const parsed = sessionsDraft.trim() === '' ? NaN : Number(sessionsDraft)
    if (!Number.isFinite(parsed) || parsed < 1) return
    setIsSavingSessions(true)
    setActionError(null)
    try {
      await updateAdminOperationDetails(data.operation.rawId, {
        details: data.operation.detallesOperacion,
        recommendations: data.operation.recomendaciones,
        sessionsTotal: parsed,
      })
      reload()
      setSessionsDraft('')
    } catch (requestError) {
      setActionError(requestError instanceof Error ? requestError.message : 'No se pudo actualizar el numero de sesiones.')
    } finally {
      setIsSavingSessions(false)
    }
  }

  // `handleCheckReservation` se elimino: la verificacion de disponibilidad
  // ahora vive dentro del `ReservationModal` (que combina el chequeo de
  // concurrencia existente con el nuevo `check-maquinaria`).

  const handleReserve = async (payload?: AdminReservationExtendedPayload) => {
    if (!data) return
    // El detail NO expone branchId en algunas rutas; caemos al campo
    // anidado si llega a faltar en el futuro.
    const branchId = data.operation.branchId
    const patientId = data.operation.patientId
    if (!branchId || !patientId) {
      const message = 'Falta la sede o el cliente asociado a esta operacion.'
      setActionError(message)
      showNotification({ title: 'No se pudo registrar la reserva', message, tone: 'danger' })
      return
    }
    if (!payload) {
      setActionError('Falta el payload de la reserva.')
      return
    }
    // El modal ya armo el payload con `branchId` del context; si por
    // algun motivo no lo trae, usamos el del detail.
    const finalPayload: AdminReservationExtendedPayload = {
      ...payload,
      branchId: payload.branchId ?? branchId,
    }
    setIsBookingReservation(true)
    setActionError(null)
    try {
      const response = await createAdminClientReservation(patientId, data.operation.rawId, finalPayload)
      reload()
      setReservationModalOpen(false)
      const successMessage = (response as { detail?: string } | null)?.detail ?? 'La cita fue reservada correctamente.'
      showNotification({ title: 'Reserva registrada', message: successMessage, tone: 'success' })
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : 'No se pudo registrar la reserva.'
      setActionError(message)
      showNotification({ title: 'No se pudo registrar la reserva', message, tone: 'danger' })
    } finally {
      setIsBookingReservation(false)
    }
  }

  const startEditingQuotas = () => {
    if (!data) return
    // Abre el editor inline. Si ya habia cuotas, precarga el draft
    // con esas; si no hay ninguna, precarga con un item vacio #1
    // para que el admin pueda crear la primera cuota desde cero.
    setIsEditingQuotas(true)
    if (data.operation.quotas.length === 0) {
      // Sin cuotas existentes: arrancamos con un item vacio #1 para
      // que el admin pueda crear la primera cuota desde cero.
      const today = new Date()
      const due = new Date(today)
      due.setDate(due.getDate() + 30)
      setQuotasDraft([
        {
          nroCuota: 1,
          montoProgramado: '',
          fechaVencimiento: due.toISOString().slice(0, 10),
        },
      ])
    } else {
      setQuotasDraft(
        data.operation.quotas.map((q) => ({
          nroCuota: q.number,
          montoProgramado: q.amountValue ?? '',
          fechaVencimiento: parseDueDate(q.dueDate),
        })),
      )
    }
    setQuotasFormError(null)
  }

  const updateQuotaDraftField = (
    index: number,
    field: 'montoProgramado' | 'fechaVencimiento',
    value: string,
  ) => {
    setQuotasDraft((current) =>
      current.map((item, idx) => (idx === index ? { ...item, [field]: value } : item)),
    )
  }

  // ---- Modo "agregar 1 sola cuota" ----

  // Abre el formulario para crear UNA cuota nueva. Calculamos el
  // siguiente nro libre con la lista ya refrescada (DB) + cualquier
  // cuota recien creada en esta sesion via el mismo flujo (usamos
  // data.operation.quotas como fuente de verdad porque reload() corre
  // despues de cada guardado).
  const startAddingQuota = () => {
    if (!data) return
    const maxExisting = Math.max(...data.operation.quotas.map((q) => q.number), 0)
    const today = new Date()
    const due = new Date(today)
    due.setDate(due.getDate() + 30)
    setNewQuotaDraft({
      nroCuota: maxExisting + 1,
      montoProgramado: '',
      fechaVencimiento: due.toISOString().slice(0, 10),
    })
    setNewQuotaFormError(null)
    setIsAddingQuota(true)
  }

  const cancelAddingQuota = () => {
    setIsAddingQuota(false)
    setNewQuotaDraft(null)
    setNewQuotaFormError(null)
  }

  // Valida antes de mandar al backend. La validacion "fuerte" (suma
  // exacta contra precio total) vive en el endpoint; aca solo
  // protegemos UX: monto positivo, fecha valida y monto no mayor al
  // precio total del tratamiento.
  const handleSaveNewQuota = async () => {
    if (!data || !newQuotaDraft) return
    setNewQuotaFormError(null)

    const precioTotal = Number(numberFromCurrency(data.operation.price))
    if (!Number.isFinite(precioTotal) || precioTotal <= 0) {
      setNewQuotaFormError('El precio total de la operacion no es valido.')
      return
    }
    const monto = Number(newQuotaDraft.montoProgramado)
    if (!Number.isFinite(monto) || monto < 0) {
      setNewQuotaFormError('Ingresa un monto valido (mayor o igual a 0).')
      return
    }
    if (monto > precioTotal) {
      setNewQuotaFormError(
        `El monto (Bs ${monto.toFixed(2)}) no puede ser mayor al precio total (Bs ${precioTotal.toFixed(2)}).`,
      )
      return
    }
    if (!newQuotaDraft.fechaVencimiento) {
      setNewQuotaFormError('Indica la fecha de vencimiento.')
      return
    }

    setIsSavingPrice(true)
    setActionError(null)
    try {
      await updateAdminOperationPricePlan(data.operation.rawId, {
        priceTotal: precioTotal.toFixed(2),
        quotaCount: newQuotaDraft.nroCuota,
        // Enviamos UNA sola cuota nueva; el backend detecta el modo
        // "single-add" (item no existente en DB) y no exige suma
        // exacta.
        quotas: [
          {
            nroCuota: newQuotaDraft.nroCuota,
            montoProgramado: newQuotaDraft.montoProgramado,
            fechaVencimiento: newQuotaDraft.fechaVencimiento,
          },
        ],
      })
      // Cerramos el editor y volvemos a la lista de cuotas. El admin
      // debe volver a pulsar "Agregar cuota" si quiere sumar otra;
      // evitamos asi que una cuota quede persistida por accidente si
      // el admin ya termino.
      const savedNroCuota = newQuotaDraft.nroCuota
      const savedMonto = newQuotaDraft.montoProgramado
      setIsAddingQuota(false)
      setNewQuotaDraft(null)
      setNewQuotaFormError(null)
      reload()
      showNotification({
        title: 'Cuota creada',
        message: `Cuota #${savedNroCuota} (Bs ${Number(savedMonto).toFixed(2)}) creada correctamente.`,
        tone: 'success',
      })
    } catch (requestError) {
      // En error dejamos el editor abierto con los valores que el
      // admin tipeo, asi puede corregir y volver a intentar.
      const message = requestError instanceof Error ? requestError.message : 'No se pudo guardar la cuota.'
      setNewQuotaFormError(message)
      showNotification({ title: 'No se pudo crear la cuota', message, tone: 'danger' })
    } finally {
      setIsSavingPrice(false)
    }
  }

  // Elimina una cuota del plan de pagos. El backend valida PAGADA /
  // comprobante PENDIENTE; el frontend oculta el boton en esos casos
  // y muestra ``window.confirm`` para evitar clicks accidentales.
  const handleDeleteQuota = async (nroCuota: number) => {
    if (!data) return
    const confirmed = window.confirm(
      `\u00bfEliminar la cuota #${nroCuota}? Las cuotas siguientes se renumeraran para mantener el orden. Esta accion no se puede deshacer.`,
    )
    if (!confirmed) return

    setDeletingQuotaNumber(nroCuota)
    setActionError(null)
    try {
      await deleteAdminOperationQuota(data.operation.rawId, { nroCuota })
      reload()
      showNotification({
        title: 'Cuota eliminada',
        message: `Cuota #${nroCuota} eliminada correctamente. Las demas cuotas se renumeraron.`,
        tone: 'success',
      })
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : 'No se pudo eliminar la cuota.'
      setActionError(message)
      showNotification({ title: 'No se pudo eliminar la cuota', message, tone: 'danger' })
    } finally {
      setDeletingQuotaNumber(null)
    }
  }

  const handleSaveQuotas = async () => {
    if (!data) return
    setQuotasFormError(null)

    // Validacion cliente basica: monto + fecha completos para todos
    // los items que vamos a mandar. El backend luego valida suma
    // exacta contra el saldo pendiente.
    const editableItems = quotasDraft.filter(
      (item) => operation.quotas.find((q) => q.number === item.nroCuota)?.status !== 'Pagado',
    )
    for (const item of editableItems) {
      if (!item.montoProgramado || !item.fechaVencimiento) {
        setQuotasFormError('Completa monto y fecha para cada cuota.')
        return
      }
    }
    if (editableItems.length === 0) {
      setQuotasFormError('No hay cuotas editables para guardar.')
      return
    }

    const priceTotal = Number(numberFromCurrency(data.operation.price))
    setIsSavingPrice(true)
    setActionError(null)
    try {
      await updateAdminOperationPricePlan(data.operation.rawId, {
        priceTotal: priceTotal.toFixed(2),
        quotaCount: data.operation.quotas.length,
        // Modo batch: solo enviamos las cuotas NO pagadas (las pagadas
        // no se pueden editar). El backend valida por item (PAGADA /
        // comprobante PENDIENTE bloquean) y rechaza si la suma de los
        // montos enviados SUPERA el precio total. Sumas menores pasan
        // (saldo restante queda sin asignar).
        quotas: editableItems.map((q) => ({
          nroCuota: q.nroCuota,
          montoProgramado: q.montoProgramado,
          fechaVencimiento: q.fechaVencimiento,
        })),
      })
      setIsEditingQuotas(false)
      reload()
      showNotification({
        title: 'Plan de pagos guardado',
        message: 'Las fechas y montos de las cuotas se actualizaron correctamente.',
        tone: 'success',
      })
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : 'No se pudo actualizar el plan de pagos.'
      setQuotasFormError(message)
      showNotification({ title: 'No se pudo guardar el plan', message, tone: 'danger' })
    } finally {
      setIsSavingPrice(false)
    }
  }

  if (isLoading && !data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Detalle de operación"
          title="Cargando tratamiento"
          description="Estamos recuperando la información clínica, financiera y documental de la operación."
          actions={[{ label: 'Volver a operaciones', variant: 'ghost', to: '/cms/operaciones' }]}
        />
        <SectionCard title="Cargando detalle">
          <DataState
            title="Consultando operación"
            message="Sincronizando citas, cuotas y ficha clínica desde Django."
          />
        </SectionCard>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Detalle de operación"
          title="No pudimos cargar la operación"
          description="Puede que la operación no exista o que la conexión no esté disponible."
          actions={[{ label: 'Volver a operaciones', variant: 'ghost', to: '/cms/operaciones' }]}
        />
        <SectionCard title="Detalle no disponible">
          <DataState
            title="Operación no disponible"
            message={error || 'No encontramos datos suficientes para mostrar el detalle.'}
            tone="danger"
          />
        </SectionCard>
      </div>
    )
  }

  const { operation } = data
  const canEditPricePlan = operation.status.toLowerCase() === 'en proceso'

  // Etiqueta que aclara que la reserva corresponde a la siguiente cita
  // (en funcion de las que ya estan registradas) y, si el admin ya
  // configuro el total de sesiones, tambien muestra el denominador.
  // Solo cuentan para el ordinal las citas que ocupan un slot de sesion
  // (PROGRAMADA, REALIZADA_PENDIENTE_VERIFICACION, CONFIRMADA). Las
  // CANCELADA y NO_ASISTIO quedan fuera del conteo porque no consumen
  // sesion (misma regla que CitaMedica.clean() en el backend).
  const totalSesionesConfiguradas = currentSessions !== null && currentSessions > 0 ? currentSessions : null
  const activeAppointments = operation.appointments.filter((apt) =>
    ['programada', 'realizada pendiente de verificación', 'confirmada'].includes(
      (apt.status ?? '').toLowerCase(),
    ),
  )
  const siguienteNumeroCita = activeAppointments.length + 1
  const reservationCaption = totalSesionesConfiguradas !== null
    ? `Esta reserva corresponde a la cita N\u00B0 ${siguienteNumeroCita} de ${totalSesionesConfiguradas} sesiones configuradas.`
    : `Esta reserva corresponde a la cita N\u00B0 ${siguienteNumeroCita}.`
  // Bloqueo del formulario de reserva: si el backend informa que no
  // quedan cupos (o si la operacion aun no tiene sede), no se debe
  // permitir cargar fecha/hora ni verificar disponibilidad. El backend
  // ya rechaza el POST con un 400, pero bloqueamos en el cliente para
  // evitar el ciclo "toco -> verifico -> reservo -> toast rojo".
  const availableAppointments = operation.availableAppointments ?? null
  // Tambien bloqueamos si la siguiente ordinal ya excede el total de
  // sesiones configuradas (defensa en el cliente: el backend ya
  // valida con CitaMedica.clean() y devuelve 400, pero mejor no dejar
  // llegar al POST). Solo aplica si el admin ya configuro el total.
  const excedeSesionesConfiguradas =
    totalSesionesConfiguradas !== null && siguienteNumeroCita > totalSesionesConfiguradas
  const canBookNewAppointment =
    operation.branchId !== null &&
    operation.patientId !== undefined &&
    availableAppointments !== null &&
    availableAppointments > 0 &&
    !excedeSesionesConfiguradas

  // Editor batch de cuotas: cantidad de items que el admin puede
  // editar (no Pagadas). Si es 0, deshabilitamos el boton "Guardar
  // plan" para evitar un POST que retornaria 400 por suma/cuotas.
  const editableQuotaCount = operation.quotas.filter((q) => q.status !== 'Pagado').length
  // Hay cambios si algun item del draft difiere del estado actual
  // (monto o fecha de vencimiento). Si no, no hay nada que guardar.
  const batchHasChanges = quotasDraft.some((draft) => {
    const live = operation.quotas.find((q) => q.number === draft.nroCuota)
    if (!live) return true
    if (draft.montoProgramado !== (live.amountValue ?? '')) return true
    if (draft.fechaVencimiento !== parseDueDate(live.dueDate)) return true
    return false
  })

  // Single-add: el monto tipeado + las pendientes existentes NO debe
  // exceder el precio total. Lo calculamos aqui para deshabilitar el
  // boton "Guardar" y mostrar un hint en vivo (rojo si excede).
  const singleAddMonto = newQuotaDraft ? Number(newQuotaDraft.montoProgramado) || 0 : 0
  const singleAddExcede =
    isAddingQuota &&
    singleAddMonto > 0 &&
    Number.isFinite(Number(numberFromCurrency(operation.price))) &&
    singleAddMonto +
      operation.quotas.reduce((acc, q) => acc + (Number(q.amountValue) || 0), 0) >
      Number(numberFromCurrency(operation.price))

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Detalle de operación"
        title={`${operation.procedure} · ${operation.patient}`}
        description="Aquí puedes revisar la ficha clínica, el documento escaneado, las cuotas y el seguimiento de citas."
        actions={[{ label: 'Volver a operaciones', variant: 'ghost', to: '/cms/operaciones' }]}
      />

      <SectionCard
        eyebrow="Resumen clínico"
        title="Información principal"
        description="Estado global del tratamiento, paciente, procedimiento y seguimiento activo."
      >
        {actionError ? (
          <DataState title="No se pudo confirmar verificación" message={actionError} tone="danger" />
        ) : null}
        <div className="operation-detail-grid">
          <article className="operation-detail-panel">
            <div className="operation-detail-panel__header">
              <div>
                <span>Estado actual</span>
                <strong>{operation.status}</strong>
              </div>
              <StatusBadge tone={getStatusTone(operation.status)}>{operation.status}</StatusBadge>
            </div>
            <dl className="operation-detail-list">
              <div>
                <dt>Paciente</dt>
                <dd>{operation.patient}</dd>
              </div>
              <div>
                <dt>Sucursal</dt>
                <dd>{operation.branch}</dd>
              </div>
              <div>
                <dt>Tipo de servicio</dt>
                <dd>{operation.serviceType}</dd>
              </div>
              <div>
                <dt>Tipo de procedimiento</dt>
                <dd>{operation.procedureType}</dd>
              </div>
              <div>
                <dt>Precio pactado</dt>
                <dd>{operation.price}</dd>
              </div>
              <div>
                <dt>Próxima cita</dt>
                <dd>{operation.nextAppointment}</dd>
              </div>
            </dl>
          </article>

          <article className="operation-detail-panel">
            <div className="operation-detail-panel__header">
              <div>
                <span>Datos operativos</span>
                <strong>Seguimiento del tratamiento</strong>
              </div>
            </div>
            <dl className="operation-detail-list">
              <div>
                <dt>Sesiones</dt>
                <dd>{operation.sessions}</dd>
              </div>
              <div>
                <dt>Cuotas</dt>
                <dd>{operation.quotaStatus}</dd>
              </div>
              <div>
                <dt>Inicio</dt>
                <dd>{operation.startDate}</dd>
              </div>
              <div>
                <dt>Fin</dt>
                <dd>{operation.endDate}</dd>
              </div>
              <div>
                <dt>Zona general</dt>
                <dd>{operation.zonaGeneral}</dd>
              </div>
              <div>
                <dt>Zona especifica</dt>
                <dd>{operation.zonaEspecifica}</dd>
              </div>
            </dl>
          </article>
        </div>

        <div className="operation-card__note-grid">
          <article>
            <span>Detalles de la operación</span>
            <p>{operation.detallesOperacion}</p>
          </article>
          <article>
            <span>Recomendaciones</span>
            <p>{operation.recomendaciones}</p>
          </article>
        </div>
        <div className="form-actions">
          <button className="button button--ghost" type="button" onClick={startEditingDetails} disabled={!canEditPricePlan}>
            Cambiar detalles y recomendaciones
          </button>
        </div>

        {isEditingDetails && canEditPricePlan ? (
          <form className="form-grid" onSubmit={handleSaveDetails}>
            <label className="field field--full">
              <span>Detalles de la operación</span>
              <textarea
                className="input textarea"
                rows={4}
                value={detailsForm.details}
                onChange={(event) => setDetailsForm({ ...detailsForm, details: event.target.value })}
              />
            </label>
            <label className="field field--full">
              <span>Recomendaciones</span>
              <textarea
                className="input textarea"
                rows={4}
                value={detailsForm.recommendations}
                onChange={(event) => setDetailsForm({ ...detailsForm, recommendations: event.target.value })}
              />
            </label>
            <small className="field__hint field--full">
              El numero de sesiones se edita en el bloque "Citas y cuotas".
            </small>
            <div className="form-actions field--full">
              <button className="button button--ghost" disabled={isSavingDetails} type="button" onClick={() => setIsEditingDetails(false)}>
                Cancelar
              </button>
              <button className="button" disabled={isSavingDetails} type="submit">
                {isSavingDetails ? 'Guardando...' : 'Guardar cambios'}
              </button>
            </div>
          </form>
        ) : null}

        {!canEditPricePlan ? (
          <small className="field__hint">Solo las operaciones en proceso permiten editar el plan de pagos y las sesiones.</small>
        ) : null}
      </SectionCard>

      <SectionCard
        eyebrow="Ficha clínica"
        title="Documento y observaciones"
        description="Vista del PDF escaneado y de los datos generales registrados en la ficha medica."
      >
        <div className="operation-detail-grid">
          <article className="operation-detail-panel">
            <div className="operation-detail-panel__header">
              <div>
                <span>Ficha registrada</span>
                <strong>{operation.medicalRecordDate}</strong>
              </div>
            </div>
            <dl className="operation-detail-list">
              <div>
                <dt>Motivo de consulta</dt>
                <dd>{operation.medicalRecordReason}</dd>
              </div>
              <div>
                <dt>Observaciones</dt>
                <dd>{operation.medicalRecordNotes}</dd>
              </div>
              <div>
                <dt>Documento PDF</dt>
                <dd>{operation.documentPdfName || 'Sin archivo adjunto'}</dd>
              </div>
            </dl>
          </article>

          <article className="operation-detail-panel">
            <div className="operation-detail-panel__header">
              <div>
                <span>Documento escaneado</span>
                <strong>{operation.documentPdfUrl ? 'Disponible para revisión' : 'No adjuntado'}</strong>
              </div>
            </div>
            {operation.documentPdfUrl ? (
              <div className="document-viewer">
                <div className="document-viewer__actions">
                  <a
                    className="button button--ghost button--compact"
                    href={operation.documentPdfUrl}
                    rel="noreferrer"
                    target="_blank"
                  >
                    Ver PDF
                  </a>
                  <a
                    className="button button--compact"
                    download={operation.documentPdfName || undefined}
                    href={operation.documentPdfUrl}
                  >
                    Descargar PDF
                  </a>
                </div>
              </div>
            ) : (
              <DataState
                title="Sin documento escaneado"
                message="Esta operación todavía no tiene un PDF adjunto en la ficha clínica."
              />
            )}
          </article>
        </div>
      </SectionCard>

      <SectionCard
        eyebrow="Seguimiento"
        title="Citas y cuotas"
        description="Gestiona las sesiones de la operacion, las reservas de citas medicas y el plan de pagos asociado."
      >
        <div className="operation-detail-grid">
          {/* ------------------------------------------------------------- */}
          {/* Citas medicas: sesiones + reserva + reprogramacion/cancelacion */}
          {/* ------------------------------------------------------------- */}
          <article className="operation-detail-panel">
            <div className="operation-detail-panel__header">
              <div>
                <span>Citas medicas</span>
                <strong>{operation.appointments.length} registro(s)</strong>
              </div>
            </div>

            {/* Editor del numero de sesiones, vive aca (no en Informacion principal) */}
            <div className="form-grid _mt-md">
              <label className="field">
                <span>
                  Numero de sesiones ({currentSessions ?? 'sin definir'} actual)
                </span>
                <input
                  className="input"
                  type="number"
                  placeholder={currentSessions !== null ? String(currentSessions) : 'Sin definir'}
                  value={sessionsDraft}
                  disabled={!canEditPricePlan}
                  onChange={(event) => setSessionsDraft(event.target.value)}
                />
              </label>
              <div className="form-actions">
                <button
                  className="button button--ghost"
                  type="button"
                  disabled={
                    !canEditPricePlan ||
                    isSavingSessions ||
                    sessionsDraft.trim() === '' ||
                    Number(sessionsDraft) < 1
                  }
                  onClick={() => void handleSaveSessions()}
                >
                  {isSavingSessions ? 'Guardando...' : 'Actualizar sesiones'}
                </button>
              </div>
            </div>

            <h4 className="_mt-md">Reservar nueva cita</h4>
            {canBookNewAppointment ? (
              <small className="field__hint _mb-sm">{reservationCaption}</small>
            ) : (
              <small className="field__hint _mb-sm">
                {excedeSesionesConfiguradas
                  ? `Ya alcanzaste las ${totalSesionesConfiguradas} sesiones configuradas para esta operacion.`
                  : availableAppointments !== null && availableAppointments <= 0
                  ? 'Esta operacion no tiene mas sesiones disponibles.'
                  : !operation.branchId
                    ? 'Esta operacion aun no tiene una sede asignada; no se pueden reservar citas hasta que se asigne una.'
                    : 'No se pueden reservar citas nuevas en este estado.'}
              </small>
            )}
            <div className="form-actions">
              <button
                className="button"
                type="button"
                onClick={() => setReservationModalOpen(true)}
                disabled={!canBookNewAppointment || isBookingReservation}
                data-testid="open-reservation-modal-operation"
              >
                {isBookingReservation ? 'Reservando...' : 'Reservar cita'}
              </button>
            </div>

            {operation.appointments.length ? (
              <div className="operation-detail-items _mt-md">
                {operation.appointments.map((appointment) => (
                  <article className="operation-detail-item" key={appointment.id}>
                    <strong>{appointment.dateTime}</strong>
                    <p>{appointment.specialist}</p>
                    <span>{appointment.status}</span>
                    <small>Verificación: {appointment.biometricStatus}</small>
                    {(() => {
                    const normalized = appointment.status?.toLowerCase?.() ?? ''
                    const isCancelable = ['programada', 'no asistio'].includes(
                      normalized,
                    )
                    const isCloseable = normalized === 'confirmada'
                    const isMarkPending = normalized === 'programada'
                    // Realizada Pendiente de Verificación: el admin puede
                    // revertir a PROGRAMADA si marcó la cita por error
                    // (mismo flujo que el endpoint POST /citas/<id>/
                    // cancelar-verificacion/ del spec appointment-states).
                    const isRevertible =
                      normalized === 'realizada pendiente de verificación'
                    if (
                      !isCancelable &&
                      !isCloseable &&
                      !isMarkPending &&
                      !isRevertible
                    ) {
                      return null
                    }
                    return (
                      <div className="table-actions">
                        {isCancelable ? (
                          <button
                            className="button button--ghost button--compact"
                            type="button"
                            onClick={() => {
                              setRescheduleCitaId(appointment.rawId)
                              setRescheduleModalOpen(true)
                            }}
                          >
                            Reprogramar reserva
                          </button>
                        ) : null}
                        {isCancelable && appointment.canManage ? (
                          <button
                            className="button button--ghost button--compact"
                            disabled={appointmentActionId !== null}
                            type="button"
                            onClick={() => void handleCancelAppointment(appointment.rawId)}
                          >
                            {appointmentActionId === appointment.rawId
                              ? 'Cancelando...'
                              : 'Cancelar reserva'}
                          </button>
                        ) : null}
                        {isMarkPending && appointment.canManage ? (
                          <button
                            className="button button--primary button--compact"
                            type="button"
                            disabled={appointmentActionId !== null}
                            onClick={() => void handleMarkPendingWithConfirm(appointment.rawId)}
                          >
                            {appointmentActionId === appointment.rawId
                              ? 'Marcando...'
                              : 'Cambiar a pendiente de verificación'}
                          </button>
                        ) : null}
                        {isCloseable ? (
                          <button
                            className="button button--primary button--compact"
                            type="button"
                            onClick={() => setClosingAppointmentId(appointment.rawId)}
                          >
                            Establecer datos reales
                          </button>
                        ) : null}
                        {appointment.hasRealTimeData ? (
                          <button
                            className="button button--ghost button--compact"
                            type="button"
                            onClick={() =>
                              setRealTimeOpenCitaId(
                                realTimeOpenCitaId === appointment.rawId
                                  ? null
                                  : appointment.rawId,
                              )
                            }
                            aria-expanded={realTimeOpenCitaId === appointment.rawId}
                          >
                            {realTimeOpenCitaId === appointment.rawId
                              ? 'Ocultar datos'
                              : 'Ver datos'}
                          </button>
                        ) : null}
                        {isRevertible ? (
                          <button
                            className="button button--ghost button--compact"
                            disabled={appointmentActionId !== null}
                            type="button"
                            onClick={() => void handleRevertPending(appointment.rawId)}
                          >
                            {appointmentActionId === appointment.rawId
                              ? 'Revirtiendo...'
                              : 'Cancelar verificación'}
                          </button>
                        ) : null}
                      </div>
                    )
                  })()}
                  </article>
                ))}
              </div>
            ) : (
              <DataState
                title="Sin citas registradas"
                message="Todavia no hay citas asociadas a esta operación."
              />
            )}
          </article>

          {/* ------------------------------------------------------------- */}
          {/* Plan de pagos: editor por cuota (monto + fecha)                */}
          {/* ------------------------------------------------------------- */}
          <article className="operation-detail-panel">
            <div className="operation-detail-panel__header">
              <div>
                <span>Plan de pagos</span>
                <strong>{operation.quotas.length} cuota(s)</strong>
              </div>
              {isAddingQuota ? (
                <div className="table-actions">
                  <button
                    className="button button--ghost button--compact"
                    type="button"
                    onClick={cancelAddingQuota}
                    disabled={isSavingPrice}
                  >
                    Cancelar
                  </button>
                  <button
                    className="button button--compact"
                    type="button"
                    onClick={() => void handleSaveNewQuota()}
                    disabled={isSavingPrice || !newQuotaDraft || singleAddExcede}
                    title={
                      singleAddExcede
                        ? 'El monto excede el saldo del tratamiento. Ajustalo antes de guardar.'
                        : undefined
                    }
                  >
                    {isSavingPrice ? 'Guardando...' : 'Guardar'}
                  </button>
                </div>
              ) : isEditingQuotas ? (
                <div className="table-actions">
                  <button
                    className="button button--ghost button--compact"
                    type="button"
                    onClick={() => {
                      setIsEditingQuotas(false)
                      setQuotasFormError(null)
                    }}
                    disabled={isSavingPrice}
                  >
                    Cancelar
                  </button>
                  <button
                    className="button button--compact"
                    type="button"
                    onClick={() => void handleSaveQuotas()}
                    disabled={isSavingPrice || editableQuotaCount === 0 || !batchHasChanges}
                    title={
                      editableQuotaCount === 0
                        ? 'Todas las cuotas estan pagadas; no hay nada que editar.'
                        : !batchHasChanges
                          ? 'No has hecho cambios para guardar.'
                          : undefined
                    }
                  >
                    {isSavingPrice ? 'Guardando...' : 'Guardar plan'}
                  </button>
                </div>
              ) : operation.quotas.length > 0 && canEditPricePlan ? (
                <div className="table-actions">
                  <button
                    className="button button--ghost button--compact"
                    type="button"
                    onClick={startAddingQuota}
                  >
                    Agregar cuota
                  </button>
                  <button
                    className="button button--ghost button--compact"
                    type="button"
                    onClick={startEditingQuotas}
                  >
                    Editar fechas y montos
                  </button>
                </div>
              ) : canEditPricePlan ? (
                <button
                  className="button button--ghost button--compact"
                  type="button"
                  onClick={startAddingQuota}
                >
                  Crear primera cuota
                </button>
              ) : null}
            </div>

            {quotasFormError && !isAddingQuota ? (
              <small className="field__error _mt-sm">{quotasFormError}</small>
            ) : null}
            {newQuotaFormError && isAddingQuota ? (
              <small className="field__error _mt-sm">{newQuotaFormError}</small>
            ) : null}

            {isAddingQuota && newQuotaDraft ? (
              <div className="operation-detail-items _mt-md">
                <article className="operation-detail-item">
                  <div className="operation-detail-item__header">
                    <strong>Cuota {newQuotaDraft.nroCuota} (nueva)</strong>
                  </div>
                  <div className="form-grid _mt-sm">
                    <label className="field">
                      <span>Monto (Bs)</span>
                      <input
                        className="input"
                        type="number"
                        min="0"
                        step="0.01"
                        value={newQuotaDraft.montoProgramado}
                        onChange={(event) =>
                          setNewQuotaDraft({ ...newQuotaDraft, montoProgramado: event.target.value })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Fecha de vencimiento</span>
                      <input
                        className="input"
                        type="date"
                        value={newQuotaDraft.fechaVencimiento}
                        onChange={(event) =>
                          setNewQuotaDraft({ ...newQuotaDraft, fechaVencimiento: event.target.value })
                        }
                      />
                    </label>
                  </div>
                  <small className="field__hint">
                    {(() => {
                      // Saldo restante = precio total - suma de montos ya
                      // programados (los existentes + el nuevo que el admin
                      // esta tipeando). Sirve de pista: despues de guardar
                      // esta cuota, ese sera el monto que aun queda por
                      // distribuir entre las siguientes cuotas. Si el
                      // restante es negativo, la suma EXCEDE el precio
                      // total y el backend rechazara el guardado.
                      const precioTotal = Number(numberFromCurrency(operation.price))
                      if (!Number.isFinite(precioTotal) || precioTotal <= 0) return null
                      const programadoExistente = operation.quotas.reduce(
                        (acc, q) => acc + (Number(q.amountValue) || 0),
                        0,
                      )
                      const digitado = Number(newQuotaDraft.montoProgramado) || 0
                      const restante = precioTotal - programadoExistente - digitado
                      if (restante < 0) {
                        return (
                          <span className="field__error">
                            La suma ({precioTotal.toFixed(2)} de precio + {digitado.toFixed(2)} de esta cuota menos lo ya programado de {programadoExistente.toFixed(2)}) excederia el precio total en Bs {Math.abs(restante).toFixed(2)}.
                          </span>
                        )
                      }
                      return (
                        <>
                          Saldo restante despues de esta cuota:{' '}
                          <strong>Bs {restante.toFixed(2)}</strong> (de Bs {precioTotal.toFixed(2)}).
                        </>
                      )
                    })()}
                  </small>
                </article>
              </div>
            ) : isEditingQuotas ? (
              <div className="operation-detail-items _mt-md">
                {quotasDraft.map((q, idx) => {
                  // El editor batch SOLO contiene cuotas existentes (no
                  // se permite agregar aqui). Las pagadas no se pueden
                  // editar; las que tienen comprobante en revision
                  // pueden pasar el frontend pero el backend dara el
                  // error exacto al guardar.
                  const backendQuota = operation.quotas.find((q2) => q2.number === q.nroCuota)
                  const isPagada = backendQuota?.status === 'Pagado'
                  const hasPayments = (backendQuota?.paymentsCount ?? 0) > 0
                  const lockReason = isPagada
                    ? 'Esta cuota ya fue pagada y no se puede editar.'
                    : hasPayments
                      ? 'Esta cuota tiene un comprobante registrado; el backend puede bloquear la edicion si esta en revision.'
                      : null
                  return (
                    <article className="operation-detail-item" key={`quota-edit-${q.nroCuota}`}>
                      <div className="operation-detail-item__header">
                        <strong>Cuota {q.nroCuota}</strong>
                        {lockReason ? (
                          <StatusBadge tone={isPagada ? 'success' : 'warning'}>
                            {isPagada ? 'Pagada' : 'Con comprobante'}
                          </StatusBadge>
                        ) : null}
                      </div>
                      <div className="form-grid _mt-sm">
                        <label className="field">
                          <span>Monto (Bs)</span>
                          <input
                            className="input"
                            type="number"
                            min="0"
                            step="0.01"
                            value={q.montoProgramado}
                            disabled={isPagada || isSavingPrice}
                            onChange={(event) => updateQuotaDraftField(idx, 'montoProgramado', event.target.value)}
                          />
                        </label>
                        <label className="field">
                          <span>Fecha de vencimiento</span>
                          <input
                            className="input"
                            type="date"
                            value={q.fechaVencimiento}
                            disabled={isPagada || isSavingPrice}
                            onChange={(event) => updateQuotaDraftField(idx, 'fechaVencimiento', event.target.value)}
                          />
                        </label>
                      </div>
                      <small className={lockReason ? 'field__error' : 'field__hint'}>
                        {lockReason ?? `Estado actual: ${backendQuota?.status ?? 'Pendiente'} | ${backendQuota?.paymentsCount ?? 0} pago(s) registrado(s)`}
                      </small>
                    </article>
                  )
                })}
              </div>
            ) : operation.quotas.length ? (
              <div className="operation-detail-items _mt-md">
                {operation.quotas.map((quota) => {
                  // El backend bloquea PAGADAS y con comprobante
                  // PENDIENTE. Aqui deshabilitamos el boton en esos
                  // mismos casos para evitar enviar un POST que
                  // retornaria 400.
                  const isPagada = quota.status === 'Pagado'
                  const hasPayments = (quota.paymentsCount ?? 0) > 0
                  const canDelete = !isPagada && !hasPayments && canEditPricePlan
                  const isDeleting = deletingQuotaNumber === quota.number
                  return (
                    <article className="operation-detail-item" key={quota.id}>
                      <div className="operation-detail-item__header">
                        <strong>Cuota {quota.number}</strong>
                        {canDelete ? (
                          <button
                            className="button button--ghost button--compact"
                            type="button"
                            onClick={() => void handleDeleteQuota(quota.number)}
                            disabled={isDeleting || deletingQuotaNumber !== null}
                            aria-label={`Quitar cuota ${quota.number}`}
                          >
                            {isDeleting ? 'Eliminando...' : 'Quitar'}
                          </button>
                        ) : (
                          <small className="field__hint">
                            {isPagada
                              ? 'Pagada: no se puede eliminar.'
                              : hasPayments
                                ? 'Con comprobante: revisar antes de eliminar.'
                                : null}
                          </small>
                        )}
                      </div>
                      <p>{quota.amount} | vence: {quota.dueDate}</p>
                      <span>{quota.status}</span>
                      <small>Pagos registrados: {quota.paymentsCount}</small>
                    </article>
                  )
                })}
              </div>
            ) : (
              <DataState
                title="Sin cuotas creadas"
                message="Esta operación no tiene cuotas registradas por el momento."
              />
            )}
          </article>
        </div>
      </SectionCard>

      <ReservationModal
        isOpen={reservationModalOpen}
        onClose={() => setReservationModalOpen(false)}
        reservableOperations={[
          { id: data.operation.rawId, rawId: data.operation.rawId, selectLabel: data.operation.procedure },
        ]}
        branchId={activeBranch?.id ?? data.operation.branchId ?? 0}
        onConfirm={handleReserve}
        isBooking={isBookingReservation}
      />

      <ReservationModal
        mode="reschedule"
        isOpen={rescheduleModalOpen}
        onClose={() => {
          setRescheduleModalOpen(false)
          setRescheduleCitaId(null)
        }}
        reservableOperations={[
          { id: data.operation.rawId, rawId: data.operation.rawId, selectLabel: data.operation.procedure },
        ]}
        branchId={activeBranch?.id ?? data.operation.branchId ?? 0}
        prefillCita={
          rescheduleCitaId !== null
            ? (data.operation.appointments.find(
                (apt) => apt.rawId === rescheduleCitaId,
              ) ?? undefined)
            : undefined
        }
        onConfirm={handleReschedule}
        isBooking={isRescheduling}
      />

      <CerrarCitaModal
        isOpen={closingAppointmentId !== null}
        onClose={() => setClosingAppointmentId(null)}
        cita={
          closingAppointmentId !== null
            ? (((data.operation.appointments.find(
                (apt) => apt.rawId === closingAppointmentId,
              )) ?? null) as CerrarCitaPayload | null)
            : null
        }
        branchId={activeBranch?.id ?? data.operation.branchId ?? 0}
        onSuccess={() => {
          setClosingAppointmentId(null)
          reload()
        }}
      />

      {realTimeOpenCitaId !== null ? (
        (() => {
          const selectedAppointment = data.operation.appointments.find(
            (apt) => apt.rawId === realTimeOpenCitaId,
          )
          if (!selectedAppointment || !selectedAppointment.hasRealTimeData) return null
          return (
            <div
              className="booking-modal-overlay"
              role="dialog"
              aria-modal="true"
              aria-label="Datos reales al cierre"
              onClick={() => setRealTimeOpenCitaId(null)}
              data-testid="real-time-modal-operation"
            >
              <div
                className="booking-modal-content"
                onClick={(event) => event.stopPropagation()}
              >
                <header className="booking-modal-header">
                  <h2 className="_m-0">Datos reales al cierre</h2>
                  <button
                    type="button"
                    className="booking-modal-close"
                    onClick={() => setRealTimeOpenCitaId(null)}
                    aria-label="Cerrar"
                  >
                    ✕
                  </button>
                </header>
                <div className="booking-modal-body">
                  <p
                    className="_text-soft _mb-sm"
                    style={{ fontSize: '0.85rem' }}
                  >
                    Cita {selectedAppointment.dateTime} · {data.operation.procedure}
                  </p>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 1fr',
                      gap: 'var(--spacing-4)',
                    }}
                  >
                    <section
                      style={{
                        border: '1px solid var(--color-border)',
                        borderRadius: '8px',
                        padding: 'var(--spacing-3)',
                      }}
                    >
                      <h4 className="_mt-0 _mb-sm">Planificado</h4>
                      <dl className="_m-0">
                        <dt>Duración estimada</dt>
                        <dd>
                          {selectedAppointment.duracionEstimadaMinutos
                            ? `${selectedAppointment.duracionEstimadaMinutos} min`
                            : '—'}
                        </dd>
                        <dt>Descripción general</dt>
                        <dd>{selectedAppointment.descripcionGeneral || '—'}</dd>
                        <dt>Notas previas</dt>
                        <dd>{selectedAppointment.notasPrevias || '—'}</dd>
                        <dt>Procedimiento</dt>
                        <dd>{selectedAppointment.procedimientoPlanificado || '—'}</dd>
                        <dt>Zona</dt>
                        <dd>{selectedAppointment.zonaCuerpoPlanificada || '—'}</dd>
                        <dt>Especialistas</dt>
                        <dd>
                          {selectedAppointment.especialistasPlanificados?.length
                            ? selectedAppointment.especialistasPlanificados
                                .map(
                                  (e: number | { especialista_id: number }) => {
                                    if (typeof e === 'number') return `id ${e}`
                                    const esp = e as {
                                      especialista_id: number
                                      especialista__usuario__first_name?: string
                                      especialista__usuario__last_name?: string
                                      especialista__usuario__username?: string
                                    }
                                    return (
                                      [
                                        esp.especialista__usuario__first_name,
                                        esp.especialista__usuario__last_name,
                                      ]
                                        .filter(Boolean)
                                        .join(' ')
                                        .trim() ||
                                      esp.especialista__usuario__username ||
                                      `id ${esp.especialista_id}`
                                    )
                                  },
                                )
                                .join(', ')
                            : '—'}
                        </dd>
                        <dt>Maquinaria</dt>
                        <dd>
                          {selectedAppointment.maquinariaPlanificada?.length
                            ? selectedAppointment.maquinariaPlanificada
                                .map(
                                  (m) =>
                                    `${m.maquinaria__nombre ?? `id ${m.maquinariaId}`}${
                                      m.maquinaria__marca ? ` (${m.maquinaria__marca})` : ''
                                    } x${m.cantidad}`,
                                )
                                .join(', ')
                            : '—'}
                        </dd>
                      </dl>
                    </section>
                    <section
                      style={{
                        border: '1px solid var(--color-border)',
                        borderRadius: '8px',
                        padding: 'var(--spacing-3)',
                      }}
                    >
                      <h4 className="_mt-0 _mb-sm">Real al cierre</h4>
                      <dl className="_m-0">
                        <dt>Hora real inicio</dt>
                        <dd>{selectedAppointment.horaRealInicio || '—'}</dd>
                        <dt>Hora real fin</dt>
                        <dd>{selectedAppointment.horaRealFin || '—'}</dd>
                        <dt>Procedimiento realizado</dt>
                        <dd>{selectedAppointment.procedimientoRealizado || '—'}</dd>
                        <dt>Zona del cuerpo realizada</dt>
                        <dd>{selectedAppointment.zonaCuerpoRealizada || '—'}</dd>
                        <dt>Especialistas que atendieron</dt>
                        <dd>
                          {selectedAppointment.especialistasAtendieron?.length
                            ? selectedAppointment.especialistasAtendieron
                                .map(
                                  (e: number | { especialista_id: number }) => {
                                    if (typeof e === 'number') return `id ${e}`
                                    const esp = e as {
                                      especialista_id: number
                                      especialista__usuario__first_name?: string
                                      especialista__usuario__last_name?: string
                                      especialista__usuario__username?: string
                                    }
                                    return (
                                      [
                                        esp.especialista__usuario__first_name,
                                        esp.especialista__usuario__last_name,
                                      ]
                                        .filter(Boolean)
                                        .join(' ')
                                        .trim() ||
                                      esp.especialista__usuario__username ||
                                      `id ${esp.especialista_id}`
                                    )
                                  },
                                )
                                .join(', ')
                            : '—'}
                        </dd>
                        <dt>Maquinaria utilizada</dt>
                        <dd>
                          {selectedAppointment.maquinariaUtilizada?.length
                            ? selectedAppointment.maquinariaUtilizada
                                .map(
                                  (m) =>
                                    `${m.maquinaria__nombre ?? `id ${m.maquinaria_id}`}${
                                      m.maquinaria__marca ? ` (${m.maquinaria__marca})` : ''
                                    } x${m.cantidad}`,
                                )
                                .join(', ')
                            : '—'}
                        </dd>
                        <dt>Notas post</dt>
                        <dd>{selectedAppointment.notasPost || '—'}</dd>
                      </dl>
                      <div
                        style={{
                          display: 'flex',
                          gap: 'var(--spacing-2)',
                          marginTop: 'var(--spacing-3)',
                          flexWrap: 'wrap',
                        }}
                      >
                        <button
                          type="button"
                          className="button button--ghost button--compact"
                          disabled={!selectedAppointment.fotoAntesUrl}
                          onClick={() =>
                            setPhotoPreviewUrl(
                              selectedAppointment.fotoAntesUrl || null,
                            )
                          }
                          aria-label="Ver foto antes"
                        >
                          Ver foto antes
                        </button>
                        <button
                          type="button"
                          className="button button--ghost button--compact"
                          disabled={!selectedAppointment.fotoDespuesUrl}
                          onClick={() =>
                            setPhotoPreviewUrl(
                              selectedAppointment.fotoDespuesUrl || null,
                            )
                          }
                          aria-label="Ver foto después"
                        >
                          Ver foto después
                        </button>
                      </div>
                    </section>
                  </div>
                </div>
              </div>
            </div>
          )
        })()
      ) : null}

      <AppointmentNotesPanel
        cita={{
          rawId: data.operation.rawId,
          descripcionGeneral: (data.operation as { descripcionGeneral?: string }).descripcionGeneral,
          notasPrevias: (data.operation as { notasPrevias?: string }).notasPrevias,
          notasPost: (data.operation as { notasPost?: string }).notasPost,
        }}
        canEdit={true}
      />

      <ConfirmDialog />

      {photoPreviewUrl ? (
        <div
          className="booking-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Foto de la cita"
          onClick={() => setPhotoPreviewUrl(null)}
          data-testid="photo-lightbox-operation"
        >
          <div
            className="booking-modal-content"
            onClick={(event) => event.stopPropagation()}
            style={{ maxWidth: '40rem' }}
          >
            <header className="booking-modal-header">
              <h2 className="_m-0">Foto</h2>
              <button
                type="button"
                className="booking-modal-close"
                onClick={() => setPhotoPreviewUrl(null)}
                aria-label="Cerrar"
              >
                �
              </button>
            </header>
            <div
              className="booking-modal-body"
              style={{ textAlign: 'center' }}
            >
              <img
                src={photoPreviewUrl}
                alt="Foto de la cita"
                style={{
                  maxWidth: '100%',
                  maxHeight: '70vh',
                  borderRadius: '8px',
                }}
              />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
