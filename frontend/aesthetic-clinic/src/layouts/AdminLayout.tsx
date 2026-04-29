import { useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '../providers/AuthProvider'

const navigation = [
  { to: '/admin', label: 'Resumen' },
  {
    label: 'Prospectos y clientes',
    children: [
      { to: '/admin/prospectos', label: 'Prospectos' },
      { to: '/admin/clientes', label: 'Clientes' },
    ],
  },
  { to: '/admin/operaciones', label: 'Operaciones' },
  {
    label: 'Disponibilidad',
    children: [
      { to: '/admin/disponibilidad/visibles', label: 'Dias y horarios visibles' },
      { to: '/admin/disponibilidad/bloques', label: 'Bloques de horarios' },
      { to: '/admin/disponibilidad/gestionar', label: 'Gestionar horarios' },
    ],
  },
  { to: '/admin/pagos', label: 'Pagos' },
  {
    label: 'Catalogos',
    children: [
      { to: '/admin/catalogos/todos-los-servicios', label: 'Todos los servicios' },
      { to: '/admin/catalogos/procedimientos-esteticos', label: 'Procedimientos esteticos' },
      { to: '/admin/catalogos/tipos-servicio', label: 'Tipos de servicio' },
      { to: '/admin/catalogos/patologias-cutaneas', label: 'Patologias cutaneas' },
      { to: '/admin/catalogos/especialidades', label: 'Especialidades' },
    ],
  },
  {
    label: 'Equipo',
    children: [
      { to: '/admin/equipo/crear', label: 'Crear especialista' },
      { to: '/admin/equipo/gestionar', label: 'Gestionar especialistas' },
    ],
  },
] as const

export function AdminLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()
  const { user, logout } = useAuth()
  const activePath = location.pathname
  const openGroups = useMemo(
    () =>
      new Set(
        navigation
          .filter((item) => 'children' in item && item.children.some((child) => activePath.startsWith(child.to)))
          .map((item) => item.label),
      ),
    [activePath],
  )

  return (
    <div className="admin-shell">
      <aside className={`sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <div className="brand-card">
          <span className="brand-card__eyebrow">Panel administrativo</span>
          <strong>Nataly Ferrufino Estetic & Academy</strong>
          <p>Operacion clinica, pagos y catalogos en una sola vista.</p>
        </div>

        <nav className="side-nav" aria-label="Navegacion principal de administracion">
          {navigation.map((item) =>
            'children' in item ? (
              <div
                key={item.label}
                className={`side-nav__group ${openGroups.has(item.label) ? 'is-active' : ''}`}
              >
                <div className="side-nav__group-label">
                  <span className="side-nav__marker" />
                  <span>{item.label}</span>
                </div>
                <div className="side-nav__children">
                  {item.children.map((child) => (
                    <NavLink
                      key={child.to}
                      to={child.to}
                      className={({ isActive }) =>
                        `side-nav__link side-nav__link--child ${isActive ? 'is-active' : ''}`
                      }
                      onClick={() => setSidebarOpen(false)}
                    >
                      <span className="side-nav__marker" />
                      <span>{child.label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            ) : (
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
            ),
          )}
        </nav>
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
