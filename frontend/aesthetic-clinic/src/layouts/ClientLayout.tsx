import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../providers/AuthProvider'

const navigation = [
  { to: '/cliente', label: 'Resumen' },
  { to: '/cliente/tratamientos', label: 'Tratamientos' },
  { to: '/cliente/pagos', label: 'Pagos y cuotas' },
  { to: '/cliente/reservas', label: 'Reservas' },
] as const

export function ClientLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { user, logout } = useAuth()

  return (
    <div className="client-shell">
      <aside className={`sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <div className="brand-card">
          <span className="brand-card__eyebrow">Portal del paciente</span>
          <strong>Nataly Ferrufino Estetic & Academy</strong>
        </div>

        <nav className="side-nav side-nav--client" aria-label="Navegacion principal del cliente">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/cliente'}
              className={({ isActive }) => `side-nav__link ${isActive ? 'is-active' : ''}`}
              onClick={() => setSidebarOpen(false)}
            >
              <span className="side-nav__marker" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-note">
          <h2>Acciones disponibles</h2>
          <p>Revisa tus pagos, verifica tus cuotas y confirma si tus tratamientos aun tienen sesiones para reservar.</p>
        </div>
      </aside>

      {sidebarOpen ? (
        <button
          aria-label="Cerrar navegacion"
          className="client-shell__backdrop"
          onClick={() => setSidebarOpen(false)}
          type="button"
        />
      ) : null}

      <main className="client-shell__main">
        <header className="topbar topbar--client">
          <div className="topbar__left">
            <button
              className="topbar__menu-button"
              onClick={() => setSidebarOpen((value) => !value)}
              type="button"
            >
              <span />
              <span />
              <span />
            </button>
            <div>
              <span className="topbar__eyebrow">Portal del cliente</span>
              <strong>{user?.fullName || 'Paciente'}</strong>
            </div>
          </div>

          <div className="topbar__right">
            <div className="search-pill search-pill--client">Seguimiento de pagos, cuotas y sesiones</div>
            <div className="profile-chip profile-chip--client">
              <div className="profile-chip__meta">
                <strong>{user?.fullName}</strong>
                <span>{user?.role || 'CLIENTE'}</span>
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
