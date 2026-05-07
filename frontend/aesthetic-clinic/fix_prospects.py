import re

filepath = "src/pages/admin/AdminProspectsPage.tsx"
with open(filepath, "r") as f:
    content = f.read()

# Fix imports
content = content.replace("import type { AdminProspectMedicalAvailabilityResponse, ProspectLead } from '../../types/admin'",
                          "import type {\n  AdminProspectMedicalAvailabilityResponse,\n  AdminConcurrencyCheckResponse,\n  ProspectLead\n} from '../../types/admin'\nimport { useBranchContext } from '../../providers/BranchProvider'\nimport { checkAdminConcurrency } from '../../services/api/admin'")

# Replace calendar state
calendar_state_re = r"  const \[bookingProspect, setBookingProspect\] = useState<ProspectLead \| null>\(null\).*?const flashMessage ="

new_state = """  const { activeBranch } = useBranchContext()
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
  const flashMessage ="""

content = re.sub(calendar_state_re, new_state, content, flags=re.DOTALL)

# Remove calendar vars
calendar_vars_re = r"  const availableDateSet = useMemo\([\s\S]*?const canGoNextMonth = maxMonth \? visibleMonth\.getTime\(\) < maxMonth\.getTime\(\) : false"
content = re.sub(calendar_vars_re, "", content, flags=re.DOTALL)

# Replace handleOpenBooking and handleReserve
handlers_re = r"  async function handleOpenBooking\(lead: ProspectLead\) \{[\s\S]*?finally \{\n      setIsBookingKey\(null\)\n    \}\n  \}"

new_handlers = """  async function handleOpenBooking(lead: ProspectLead) {
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
  }"""
content = re.sub(handlers_re, new_handlers, content, flags=re.DOTALL)

# Replace UI Section
ui_re = r"                  <div className=\"reservation-calendar\">\n                    <div className=\"reservation-calendar__header\">.*?                  </DataState>\n                \)}\n              </SectionCard>\n            </section>"

new_ui = """                  <div className="form-grid">
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
            </section>"""

content = re.sub(ui_re, new_ui, content, flags=re.DOTALL)

with open(filepath, "w") as f:
    f.write(content)

print("AdminProspectsPage replaced successfully")
