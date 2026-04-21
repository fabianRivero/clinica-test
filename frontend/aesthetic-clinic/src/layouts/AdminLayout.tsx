import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../providers/AuthProvider'

const navigation = [
  { to: '/admin', label: 'Resumen', shortLabel: 'Dashboard' },
  { to: '/admin/prospectos', label: 'Prospectos y clientes', shortLabel: 'Prospectos' },
  { to: '/admin/operaciones', label: 'Operaciones', shortLabel: 'Operaciones' },
  { to: '/admin/pagos', label: 'Pagos', shortLabel: 'Pagos' },
  { to: '/admin/catalogos', label: 'Catalogos', shortLabel: 'Catalogos' },
  { to: '/admin/equipo', label: 'Equipo', shortLabel: 'Equipo' },
] as const

export function AdminLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { user, logout } = useAuth()

  return (
    <div className="admin-shell">
      <aside className={`admin-shell__sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <div className="brand-card">
          <span className="brand-card__eyebrow">Panel administrativo</span>
          <strong>Nataly Ferrufino Estetic & Academy</strong>
          <p>Operacion clinica, pagos y catalogos en una sola vista.</p>
        </div>

        <nav className="side-nav" aria-label="Navegacion principal de administracion">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/admin'}
              className={({ isActive }) => `side-nav__link ${isActive ? 'is-active' : ''}`}
              onClick={() => setSidebarOpen(false)}
            >
              <span className="side-nav__marker" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-note">
          <h2>Rol activo</h2>
          <p>Administrador con permisos para pagos, operaciones, clientes y configuracion.</p>
        </div>
      </aside>

      {sidebarOpen ? (
        <button
          aria-label="Cerrar navegacion"
          className="admin-shell__backdrop"
          onClick={() => setSidebarOpen(false)}
          type="button"
        />
      ) : null}

      <main className="admin-shell__main">
        <header className="topbar">
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
              <span className="topbar__eyebrow">Administracion clinica</span>
              <strong>{user?.fullName || 'Administrador'}</strong>
            </div>
          </div>

          <div className="topbar__right">
            <div className="search-pill">Buscar pacientes, pagos u operaciones</div>
            <div className="profile-chip">
              <div className="profile-chip__meta">
                <strong>{user?.fullName}</strong>
                <span>{user?.role || 'ADMINISTRADOR'}</span>
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
