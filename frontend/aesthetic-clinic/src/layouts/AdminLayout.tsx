import { useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

const navigation = [
  { to: '/admin', label: 'Resumen', shortLabel: 'Dashboard' },
  { to: '/admin/prospectos', label: 'Prospectos y clientes', shortLabel: 'Prospectos' },
  { to: '/admin/operaciones', label: 'Operaciones', shortLabel: 'Operaciones' },
  { to: '/admin/pagos', label: 'Pagos', shortLabel: 'Pagos' },
  { to: '/admin/catalogos', label: 'Catálogos', shortLabel: 'Catálogos' },
  { to: '/admin/equipo', label: 'Equipo', shortLabel: 'Equipo' },
] as const

export function AdminLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()

  const activeSection = useMemo(
    () => navigation.find((item) => item.to === location.pathname)?.shortLabel ?? 'Resumen',
    [location.pathname],
  )

  return (
    <div className="admin-shell">
      <aside className={`admin-shell__sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <div className="brand-card">
          <span className="brand-card__eyebrow">Panel administrativo</span>
          <strong>Nataly Ferrufino Estetic & Academy</strong>
          <p>Operación clínica, pagos y catálogos en una sola vista.</p>
        </div>

        <nav className="side-nav" aria-label="Navegación principal de administración">
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
          <p>Administrador con permisos para pagos, operaciones, clientes y configuración.</p>
        </div>
      </aside>

      {sidebarOpen ? (
        <button
          aria-label="Cerrar navegación"
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
              <span className="topbar__eyebrow">Administración clínica</span>
              <strong>{activeSection}</strong>
            </div>
          </div>

          <div className="topbar__right">
            <div className="search-pill">Buscar pacientes, pagos o operaciones</div>
            <div className="profile-chip">
              <span className="profile-chip__avatar">FL</span>
              <div>
                <strong>Fabián Rivero</strong>
                <span>Administrador principal</span>
              </div>
            </div>
          </div>
        </header>

        <Outlet />
      </main>
    </div>
  )
}
