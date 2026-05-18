import { useMemo, useState } from 'react'

import {
  tabletClientLogin,
  tabletClientReset,
  tabletConfirmProcedure,
  tabletCurrentAppointment,
  tabletKioskLogin,
} from '../../services/api/tablet'
import type { TabletCurrentAppointmentResponse } from '../../types/tablet'

type Step = 'kiosk' | 'client' | 'appointments' | 'done'

export function TabletKioskPage() {
  const [step, setStep] = useState<Step>('kiosk')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const [kioskCode, setKioskCode] = useState('KIOSKO-PRINCIPAL')
  const [kioskPassword, setKioskPassword] = useState('tablet-principal-123')
  const [clientUsername, setClientUsername] = useState('paciente.demo')
  const [clientPassword, setClientPassword] = useState('paciente123456')
  const [summary, setSummary] = useState<TabletCurrentAppointmentResponse | null>(null)

  const procedures = useMemo(() => summary?.procedureOptions ?? [], [summary])

  async function handleKioskLogin(event: React.FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      await tabletKioskLogin(kioskCode, kioskPassword)
      setStep('client')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo autenticar el kiosko.')
    } finally {
      setLoading(false)
    }
  }

  async function handleClientLogin(event: React.FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      await tabletClientLogin(clientUsername, clientPassword)
      const data = await tabletCurrentAppointment()
      setSummary(data)
      setStep('appointments')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo autenticar el cliente.')
    } finally {
      setLoading(false)
    }
  }

  async function handleConfirm(operationId: number) {
    setLoading(true)
    setError('')
    setSuccess('')
    try {
      const response = await tabletConfirmProcedure(operationId)
      setSuccess(response.detail)
      setStep('done')
      await tabletClientReset()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo confirmar la cita.')
    } finally {
      setLoading(false)
    }
  }

  function backToClientLogin() {
    setClientPassword('')
    setError('')
    setSuccess('')
    setSummary(null)
    setStep('client')
  }

  return (
    <div className="auth-shell">
      <div className="auth-card" style={{ maxWidth: 720 }}>
        <h2>Interfaz Tablet · Confirmación de cita</h2>
        {step === 'kiosk' && (
          <form className="auth-form" onSubmit={handleKioskLogin}>
            <label className="field">
              <span>Código kiosko</span>
              <input className="input" value={kioskCode} onChange={(e) => setKioskCode(e.target.value)} />
            </label>
            <label className="field">
              <span>Clave kiosko</span>
              <input
                className="input"
                type="password"
                value={kioskPassword}
                onChange={(e) => setKioskPassword(e.target.value)}
              />
            </label>
            <button className="button auth-form__submit" disabled={loading}>
              {loading ? 'Ingresando...' : 'Ingresar kiosko'}
            </button>
          </form>
        )}
        {step === 'client' && (
          <form className="auth-form" onSubmit={handleClientLogin}>
            <label className="field">
              <span>Usuario cliente</span>
              <input className="input" value={clientUsername} onChange={(e) => setClientUsername(e.target.value)} />
            </label>
            <label className="field">
              <span>Contraseña cliente</span>
              <input
                className="input"
                type="password"
                value={clientPassword}
                onChange={(e) => setClientPassword(e.target.value)}
              />
            </label>
            <button className="button auth-form__submit" disabled={loading}>
              {loading ? 'Validando...' : 'Validar cliente'}
            </button>
          </form>
        )}
        {step === 'appointments' && (
          <div>
            <p>
              Citas pendientes para hoy/futuras: <strong>{summary?.pendingAppointmentsCount ?? 0}</strong>
            </p>
            {procedures.length === 0 ? <p>No hay procedimientos confirmables hoy.</p> : null}
            {procedures.map((option) => (
              <article key={option.operation.rawId} className="auth-highlight" style={{ marginBottom: 12 }}>
                <strong>{option.operation.procedure}</strong>
                <p>{option.operation.reserveMessage}</p>
                <p>Citas hoy: {option.appointments.map((a) => `${a.dateTime} (${a.status})`).join(' · ')}</p>
                <button className="button" disabled={loading} onClick={() => handleConfirm(option.operation.rawId)}>
                  {loading ? 'Confirmando...' : 'Confirmar cita de este procedimiento'}
                </button>
              </article>
            ))}
          </div>
        )}
        {step === 'done' && (
          <div>
            <p>{success || 'Cita realizada'}</p>
            <button className="button" onClick={backToClientLogin}>
              Volver a ingreso de cliente
            </button>
          </div>
        )}
        {error ? <div className="form-error">{error}</div> : null}
      </div>
    </div>
  )
}
