import re

filepath = "src/pages/admin/AdminClientDetailPage.tsx"
with open(filepath, "r") as f:
    content = f.read()

# First, let's fix imports
content = content.replace("import type {\n  AdminClientFreeMedicalAvailabilityResponse,\n  AdminClientReservationAvailabilityResponse,\n} from '../../types/admin'", 
                          "import type {\n  AdminClientFreeMedicalAvailabilityResponse,\n  AdminClientReservationAvailabilityResponse,\n  AdminConcurrencyCheckResponse,\n} from '../../types/admin'\nimport { useBranchContext } from '../../providers/BranchProvider'\nimport { checkAdminConcurrency } from '../../services/api/admin'")

# We need to replace the state hooks related to the calendar with simpler ones
calendar_state_re = r"  const \[availability, setAvailability\] = useState<AdminClientReservationAvailabilityResponse \| null>\(null\).*?const \[appointmentActionId, setAppointmentActionId\] = useState<number \| null>\(null\)"

new_state = """  const { activeBranch } = useBranchContext()
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
  const [appointmentActionId, setAppointmentActionId] = useState<number | null>(null)"""

content = re.sub(calendar_state_re, new_state, content, flags=re.DOTALL)

# Delete useEffects that auto load availability
use_effects_re = r"  useEffect\(\(\) => \{\n    let cancelled = false\n\n    async function loadAvailability\(\) \{\n.*?return \(\) => \{\n      cancelled = true\n    \}\n  \}, \[data\]\)"
content = re.sub(use_effects_re, "", content, flags=re.DOTALL)

# Delete memoized calendar vars
calendar_vars_re = r"  const availableDateSet = useMemo\([\s\S]*?const canGoNextFreeMonth = freeMaxMonth \? freeVisibleMonth\.getTime\(\) < freeMaxMonth\.getTime\(\) : false"
content = re.sub(calendar_vars_re, "", content, flags=re.DOTALL)

# Let's replace handleReserve
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

  async function handleCheckFreeConcurrency() {
    if (!activeBranch || !freeSelectedDate || !freeSelectedTime) {
      showNotification({ title: 'Atencion', message: 'Selecciona fecha y hora.', tone: 'warning' })
      return
    }
    setIsChecking(true)
    try {
      const parts = freeSelectedTime.split(':')
      const endHour = String(Number(parts[0]) + 1).padStart(2, '0')
      const endTime = `${endHour}:${parts[1]}`
      const info = await checkAdminConcurrency(activeBranch.id, freeSelectedDate, freeSelectedTime, endTime)
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
      } as any)
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
  }"""
content = re.sub(handle_reserve_re, new_handle_reserve, content, flags=re.DOTALL)

# Let's replace handleReserveFreeMedicalAppointment
handle_reserve_free_re = r"  async function handleReserveFreeMedicalAppointment\(slotId: number\) \{[\s\S]*?finally \{\n      setIsFreeBookingKey\(null\)\n    \}\n  \}"
new_handle_reserve_free = """  async function handleReserveFreeMedicalAppointment() {
    if (!data || !activeBranch) return
    setIsFreeBookingKey('booking')

    try {
      const response = await createAdminClientFreeMedicalAppointment(data.client.rawId, {
        branchId: activeBranch.id,
        dateTime: `${freeSelectedDate}T${freeSelectedTime}:00`
      } as any)
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
  }"""
content = re.sub(handle_reserve_free_re, new_handle_reserve_free, content, flags=re.DOTALL)

# Replace the Reservation UI
res_ui_re = r"        <SectionCard eyebrow=\"Reservas\" title=\"Hacer reserva para este cliente\".*?        </SectionCard>\n      </section>"
new_res_ui = """        <SectionCard eyebrow="Reservas" title="Hacer reserva para este cliente" description="Agendar hora libre (Agenda abierta).">
          {reservableOperations.length ? (
            <div className="form-grid">
              <label className="field field--full">
                <span>Procedimiento</span>
                <select className="input" value={effectiveOperationId} onChange={(event) => setSelectedOperationId(Number(event.target.value))}>
                  {reservableOperations.map((operation) => (
                    <option key={operation.id} value={operation.rawId}>
                      {operation.procedure} | {operation.reserveMessage}
                    </option>
                  ))}
                </select>
              </label>
              
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
            <DataState title="Sin procedimientos en proceso" message="Este cliente no tiene tratamientos activos para nuevas reservas." />
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
      </section>"""
content = re.sub(res_ui_re, new_res_ui, content, flags=re.DOTALL)

# Replace Free Medical Appointment UI
free_ui_re = r"        <SectionCard eyebrow=\"Cita medica\" title=\"Reservar cita medica libre\".*?        </SectionCard>\n      </section>"
new_free_ui = """        <SectionCard eyebrow="Cita medica" title="Reservar cita medica libre" description="Agenda una consulta sin asociarla a un tratamiento activo. Disponible tambien para clientes inactivos.">
          <div className="form-grid">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <label className="field">
                <span>Fecha</span>
                <input type="date" className="input" value={freeSelectedDate} onChange={e => { setFreeSelectedDate(e.target.value); setFreeConcurrencyInfo(null); }} />
              </label>
              <label className="field">
                <span>Hora de Inicio</span>
                <input type="time" className="input" value={freeSelectedTime} onChange={e => { setFreeSelectedTime(e.target.value); setFreeConcurrencyInfo(null); }} />
              </label>
            </div>
            
            <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="button button--secondary" disabled={!freeSelectedDate || !freeSelectedTime || isChecking} onClick={() => void handleCheckFreeConcurrency()}>
                {isChecking ? 'Verificando...' : 'Verificar Disponibilidad'}
              </button>
            </div>
          </div>
        </SectionCard>

        {freeConcurrencyInfo && (
          <SectionCard title="Resultados de disponibilidad">
            <div style={{ padding: '1rem', background: 'var(--c-neutral-100)', borderRadius: '8px' }}>
              <p style={{ marginBottom: '0.5rem' }}>
                <strong>Citas simultaneas a esa hora:</strong> {freeConcurrencyInfo.concurrency}
              </p>
              <p style={{ marginBottom: '0.5rem' }}>
                <strong>Especialistas en turno:</strong> {freeConcurrencyInfo.presentes.length > 0 ? freeConcurrencyInfo.presentes.map(p => p.usuario__primer_nombre).join(', ') : 'Ninguno registrado'}
              </p>
              <div style={{ marginTop: '1.5rem' }}>
                 <button type="button" className="button button--primary" onClick={() => void handleReserveFreeMedicalAppointment()} disabled={Boolean(isFreeBookingKey)}>
                   {isFreeBookingKey ? 'Confirmando...' : 'Confirmar Cita Medica'}
                 </button>
              </div>
            </div>
          </SectionCard>
        )}
      </section>"""
content = re.sub(free_ui_re, new_free_ui, content, flags=re.DOTALL)

with open(filepath, "w") as f:
    f.write(content)

print("AdminClientDetailPage replaced successfully")
