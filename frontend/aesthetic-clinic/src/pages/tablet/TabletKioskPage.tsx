import { useEffect, useMemo, useState } from 'react'

import {
  tabletClientLogin,
  tabletClientReset,
  tabletConfirmProcedure,
  tabletCurrentAppointment,
  tabletKioskLogin,
  tabletSyncOfflineEvents,
} from '../../services/api/tablet'
import {
  countPendingOfflineEvents,
  listPendingOfflineEvents,
  loadTabletSnapshot,
  markOfflineEventStatus,
  queueOfflineConfirmation,
  saveTabletSnapshot,
} from '../../services/tabletOfflineStore'
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
  const [isOfflineMode, setIsOfflineMode] = useState(!navigator.onLine)
  const [pendingOfflineEvents, setPendingOfflineEvents] = useState(0)

  const procedures = useMemo(() => summary?.procedureOptions ?? [], [summary])

  async function refreshPendingCount() {
    setPendingOfflineEvents(await countPendingOfflineEvents())
  }

  async function trySyncOfflineQueue() {
    if (!navigator.onLine) return
    const pending = await listPendingOfflineEvents()
    if (!pending.length) return

    const response = await tabletSyncOfflineEvents(
      pending.map((event) => ({ eventId: event.eventId, operationId: event.operationId, createdAt: event.createdAt })),
    )

    await Promise.all(
      response.results.map((result) => {
        if (!result.eventId) return Promise.resolve()
        if (result.status === 'accepted' || result.status === 'duplicate') {
          return markOfflineEventStatus(result.eventId, 'synced')
        }
        if (result.status === 'conflict') {
          return markOfflineEventStatus(result.eventId, 'conflict')
        }
        return markOfflineEventStatus(result.eventId, 'rejected')
      }),
    )

    await refreshPendingCount()
  }

  useEffect(() => {
    function onOnline() {
      setIsOfflineMode(false)
      void trySyncOfflineQueue().catch(() => undefined)
    }

    function onOffline() {
      setIsOfflineMode(true)
    }

    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    void refreshPendingCount().catch(() => undefined)
    void trySyncOfflineQueue().catch(() => undefined)

    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
    }
  }, [])

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
      if (isOfflineMode) {
        const cached = await loadTabletSnapshot()
        if (!cached) throw new Error('No hay snapshot offline disponible para hoy.')
        setSummary(cached.data)
        setStep('appointments')
        return
      }

      await tabletClientLogin(clientUsername, clientPassword)
      const data = await tabletCurrentAppointment()
      setSummary(data)
      await saveTabletSnapshot(data)
      await trySyncOfflineQueue()
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
      if (isOfflineMode) {
        await queueOfflineConfirmation(operationId)
        await refreshPendingCount()
        setSuccess('Verificación registrada en cola offline. Se sincronizará al volver la red.')
        setStep('done')
        return
      }

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
    <div className="auth-shell tablet-shell">
      <div className="auth-card tablet-shell__card">
        <h2>Interfaz Tablet · Confirmación de cita</h2>
        {isOfflineMode ? (
          <div className="auth-highlight" style={{ marginBottom: 12 }}>
            <strong>Modo offline activo</strong>
            <p>Se usará snapshot local y las confirmaciones quedarán en cola para sincronización.</p>
          </div>
        ) : null}
        {pendingOfflineEvents > 0 ? (
          <div className="auth-highlight" style={{ marginBottom: 12 }}>
            <strong>Pendientes de sincronizar: {pendingOfflineEvents}</strong>
          </div>
        ) : null}
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
