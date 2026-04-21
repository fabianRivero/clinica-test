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
          : 'No pudimos iniciar sesion con esas credenciales.',
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
            Lorem, ipsum dolor sit amet consectetur adipisicing elit. Iusto sint quaerat voluptas fuga non, minus tenetur eligendi qui dolores excepturi natus magnam porro? Voluptas itaque sequi unde alias ratione in.
          </p>
        </div>

        <div className="auth-shell__highlights">
          <article className="auth-highlight">
            <strong>Lorem</strong>
            <p>Lorem ipsum dolor sit amet consectetur adipisicing elit. Ab, facere odit dolorem magni doloremque suscipit provident mollitia maiores voluptas. Perferendis quia non dicta voluptates veritatis et consequuntur culpa laboriosam voluptate!</p>
          </article>
          <article className="auth-highlight">
            <strong>Lorem</strong>
            <p>Lorem ipsum dolor sit amet consectetur adipisicing elit. Dolor obcaecati, aliquam vero aliquid nemo fugiat? Culpa sequi necessitatibus accusamus amet doloremque recusandae sint explicabo consectetur deserunt animi. Repellendus, voluptas modi?</p>
          </article>
          <article className="auth-highlight">
            <strong>Lorem</strong>
            <p>Lorem ipsum dolor sit, amet consectetur adipisicing elit. Commodi perferendis numquam quos, deserunt recusandae ut eius ipsa? Vitae dolor sapiente corrupti! Voluptas, officiis dolores? Quis eaque culpa exercitationem ad vel.</p>
          </article>
        </div>
      </div>

      <div className="auth-card">
        <div className="auth-card__header">
          <span className="auth-card__eyebrow">Acceso seguro</span>
          <h2>Iniciar sesion</h2>
          <p>Usa las credenciales que ya existen en la base de pruebas.</p>
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
            <li>`admin / admin123456`</li>
            <li>`doctor.laser / doctor123456`</li>
            <li>`paciente.demo / paciente123456`</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
