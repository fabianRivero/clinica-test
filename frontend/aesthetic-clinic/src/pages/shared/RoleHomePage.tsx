import { useAuth } from '../../providers/AuthProvider'

type RoleHomePageProps = {
  eyebrow: string
  title: string
  description: string
}

export function RoleHomePage({ eyebrow, title, description }: RoleHomePageProps) {
  const { user, logout } = useAuth()

  return (
    <div className="role-shell">
      <section className="role-card">
        <span className="role-card__eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>

        <div className="role-card__summary">
          <div>
            <span>Usuario autenticado</span>
            <strong>{user?.fullName}</strong>
          </div>
          <div>
            <span>Rol</span>
            <strong>{user?.role || 'Sin rol'}</strong>
          </div>
        </div>

        <div className="role-card__actions">
          <button className="button" type="button" onClick={() => void logout()}>
            Cerrar sesion
          </button>
        </div>
      </section>
    </div>
  )
}
