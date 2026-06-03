import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../../providers/AuthProvider'

export function LoginPage() {
  const { user, isLoading, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const requestedPath =
    typeof location.state === 'object' &&
      location.state &&
      'from' in location.state &&
      typeof location.state.from === 'string'
      ? location.state.from
      : ''

  useEffect(() => {
    if (!isLoading && user) {
      navigate(user.dashboardPath, { replace: true })
    }
  }, [isLoading, navigate, user])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      const authenticatedUser = await login({ username, password })
      navigate(requestedPath || authenticatedUser.dashboardPath, { replace: true })
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'No pudimos iniciar sesión con esas credenciales.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-shell__panel">
        <div className="auth-shell__intro">
          <span className="auth-shell__eyebrow">Clinica estetica</span>
          <h1>Nataly Ferrufino Estetic & Academy</h1>
          <p>
            Plataforma de gestión de operaciones, agenda y pagos. Accede con tus credenciales para comenzar.
          </p>
        </div>

        <div className="auth-shell__highlights">
          <article className="auth-highlight">
            <strong>Agenda tus reservas</strong>
            <p>Realiza reservas para tus tratamientos activos facilmente.</p>
          </article>
          <article className="auth-highlight">
            <strong>Administra tus pagos</strong>
            <p>Puedes gestionar y rastrear todos tus pagos desde un solo lugar.</p>
          </article>
          <article className="auth-highlight">
            <strong>Comunícate con nosotros</strong>
            <p>Puedes comunicarte con nosotros sobre tus dudas o inquietudes. Tambien recibiras notificaciones y mensajes importantes sobre tus pagos o tratamientos.</p>
          </article>
        </div>
      </div>

      <div className="auth-card">
        <div className="auth-card__header">
          <span className="auth-card__eyebrow">Acceso seguro</span>
          <h2>Iniciar sesión</h2>
          <p>Ingresa con tu usuario y contraseña para acceder al sistema.</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Usuario</span>
            <input
              className="input"
              name="username"
              autoComplete="username"
              placeholder="admin"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>

          <label className="field">
            <span>Contraseña</span>
            <input
              className="input"
              name="password"
              type="password"
              autoComplete="current-password"
              placeholder="********"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          {error ? <div className="form-error">{error}</div> : null}

          <button className="button auth-form__submit" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Ingresando...' : 'Entrar'}
          </button>
        </form>

        <div className="demo-credentials">
          <strong>Credenciales demo</strong>
          <ul>
            <li>`admin.general / admin123456`</li>
            <li>`admin.norte / admin123456`</li>
            <li>`paciente.demo / paciente123456`</li>
            <li>`lucia.laser / laser123456`</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
