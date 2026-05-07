import re

filepath = "src/pages/admin/AdminOperationDetailPage.tsx"
with open(filepath, "r") as f:
    content = f.read()

# Fix imports
content = content.replace("import type { AdminClientReservationAvailabilityResponse } from '../../types/admin'",
                          "import type {\n  AdminClientReservationAvailabilityResponse,\n  AdminConcurrencyCheckResponse,\n} from '../../types/admin'\nimport { useBranchContext } from '../../providers/BranchProvider'\nimport { checkAdminConcurrency } from '../../services/api/admin'")

# Replace state variables
calendar_state_re = r"  const \[availability, setAvailability\] = useState<AdminClientReservationAvailabilityResponse \| null>\(null\).*?const \[appointmentActionId, setAppointmentActionId\] = useState<number \| null>\(null\)"

new_state = """  const { activeBranch } = useBranchContext()
  const [selectedDate, setSelectedDate] = useState('')
  const [selectedTime, setSelectedTime] = useState('')
  const [concurrencyInfo, setConcurrencyInfo] = useState<AdminConcurrencyCheckResponse | null>(null)
  const [isChecking, setIsChecking] = useState(false)
  const [isBookingKey, setIsBookingKey] = useState<string | null>(null)
  const [appointmentActionId, setAppointmentActionId] = useState<number | null>(null)"""

content = re.sub(calendar_state_re, new_state, content, flags=re.DOTALL)

# Remove useEffect for loading availability
use_effects_re = r"  useEffect\(\(\) => \{\n    let cancelled = false\n\n    async function loadAvailability\(\) \{\n.*?return \(\) => \{\n      cancelled = true\n    \}\n  \}, \[data, operationId, activeTab\]\)"
content = re.sub(use_effects_re, "", content, flags=re.DOTALL)

# Remove calendar vars
calendar_vars_re = r"  const availableDateSet = useMemo\([\s\S]*?const canGoNextMonth = maxMonth \? visibleMonth\.getTime\(\) < maxMonth\.getTime\(\) : false"
content = re.sub(calendar_vars_re, "", content, flags=re.DOTALL)

# Replace handleReserve
handle_reserve_re = r"  async function handleReserve\(slotId: number\) \{[\s\S]*?finally \{\n      setIsBookingKey\(null\)\n    \}\n  \}"
new_handle_reserve = """  async function handleCheckConcurrency() {
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
    if (!data || !data.operation.patient || !activeBranch) return
    setIsBookingKey('booking')

    try {
      const response = await createAdminClientReservation(data.operation.patient.rawId, data.operation.rawId, {
        branchId: activeBranch.id,
        dateTime: `${selectedDate}T${selectedTime}:00`
      } as any)
      showNotification({ title: 'Reserva registrada', message: response.detail, tone: 'success' })
      reload()
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
  }"""
content = re.sub(handle_reserve_re, new_handle_reserve, content, flags=re.DOTALL)

# Replace UI
ui_re = r"        <div className=\"dashboard-grid\">\n          <SectionCard eyebrow=\"Reservas\" title=\"Hacer reserva\" description=\"Selecciona un cupo publicado por administracion.\">.*?          </SectionCard>\n        </div>"

new_ui = """        <div className="dashboard-grid">
          <SectionCard eyebrow="Reservas" title="Hacer reserva" description="Agendar hora libre (Agenda abierta).">
            {data.operation.quotaStatus !== 'Bloqueada' ? (
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
            ) : (
              <DataState title="Operacion bloqueada" message="Esta operacion no permite nuevas reservas." />
            )}
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
                     {isBookingKey ? 'Confirmando...' : 'Confirmar Reserva en esta Hora'}
                   </button>
                </div>
              </div>
            </SectionCard>
          )}
        </div>"""

content = re.sub(ui_re, new_ui, content, flags=re.DOTALL)

with open(filepath, "w") as f:
    f.write(content)

print("AdminOperationDetailPage replaced successfully")
