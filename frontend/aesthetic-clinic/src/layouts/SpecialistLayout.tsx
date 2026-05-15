import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../providers/AuthProvider'

const navigation = [
  { to: '/trabajador/agenda', label: 'Agenda semanal' },
  { to: '/trabajador/mensajes', label: 'Mensajeria interna' },
] as const

export function SpecialistLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { user, logout } = useAuth()

  return (
    <div className="client-shell">
      <aside className={`sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <div className="brand-card">
          <span className="brand-card__eyebrow">Portal de especialista</span>
          <strong>Nataly Ferrufino Estetic & Academy</strong>
          <p>Disponibilidad semanal y coordinacion con administracion.</p>
        </div>

        <nav className="side-nav" aria-label="Navegacion principal del especialista">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `side-nav__link ${isActive ? 'is-active' : ''}`}
              onClick={() => setSidebarOpen(false)}
            >
              <span className="side-nav__marker" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      {sidebarOpen ? <button aria-label="Cerrar navegacion" className="client-shell__backdrop" onClick={() => setSidebarOpen(false)} type="button" /> : null}

      <main className="client-shell__main">
        <header className="topbar topbar--client">
          <div className="topbar__left">
            <button className="topbar__menu-button" onClick={() => setSidebarOpen((value) => !value)} type="button">
              <span />
              <span />
              <span />
            </button>
            <div>
              <span className="topbar__eyebrow">Portal de especialista</span>
              <strong>{user?.fullName || 'Especialista'}</strong>
            </div>
          </div>
          <div className="topbar__right">
            <div className="search-pill search-pill--client">Agenda abierta, disponibilidad y mensajes internos</div>
            <div className="profile-chip profile-chip--client">
              <div className="profile-chip__meta">
                <strong>{user?.fullName}</strong>
                <span>{user?.role || 'TRABAJADOR'}</span>
              </div>
              <button className="button button--ghost button--compact" type="button" onClick={() => void logout()}>
                Cerrar sesion
              </button>
            </div>
          </div>
        </header>

        <Outlet />
      </main>
    </div>
  )
}
