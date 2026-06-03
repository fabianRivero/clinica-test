import { useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../providers/AuthProvider'
import { NOTIFICATIONS_UPDATED_EVENT } from '../services/api/notifications'

const navigation = [
  { to: '/trabajador/agenda', label: 'Agenda semanal' },
  {
    label: 'Mensajeria interna',
    children: [
      { to: '/trabajador/mensajes/fichas', label: 'Fichas existentes' },
      { to: '/trabajador/mensajes/nueva', label: 'Crear ficha nueva' },
    ],
  },
  { to: '/trabajador/notificaciones', label: 'Notificaciones' },
] as const

export function SpecialistLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { user, logout } = useAuth()
  const [unreadCount, setUnreadCount] = useState(0)

  const loadUnreadCount = () => {
    void fetch('/api/notifications/', { credentials: 'include' })
      .then((r) => r.json())
      .then((data) => setUnreadCount(data.unreadCount || 0))
      .catch(() => undefined)
  }

  useEffect(() => {
    loadUnreadCount()
    const handleNotificationsUpdated = () => loadUnreadCount()
    window.addEventListener(NOTIFICATIONS_UPDATED_EVENT, handleNotificationsUpdated)
    return () => window.removeEventListener(NOTIFICATIONS_UPDATED_EVENT, handleNotificationsUpdated)
  }, [])
  const location = useLocation()
  const activePath = location.pathname
  const openGroups = useMemo(() => new Set(navigation.filter((item) => 'children' in item && item.children.some((child) => activePath.startsWith(child.to))).map((item) => item.label)), [activePath])

  return (
    <div className="client-shell">
      <aside className={`sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <div className="brand-card">
          <span className="brand-card__eyebrow">Portal de especialista</span>
          <strong>Nataly Ferrufino Estetic & Academy</strong>
          <p>Disponibilidad semanal y coordinacion con administracion.</p>
        </div>

        <nav className="side-nav" aria-label="Navegacion principal del especialista">
          {navigation.map((item) =>
            'children' in item ? (
              <div key={item.label} className={`side-nav__group ${openGroups.has(item.label) ? 'is-active' : ''}`}>
                <div className="side-nav__group-label">
                  <span className="side-nav__marker" />
                  <span>{item.label}</span>
                </div>
                <div className="side-nav__children">
                  {item.children.map((child) => (
                    <NavLink
                      key={child.to}
                      to={child.to}
                      className={({ isActive }) => `side-nav__link side-nav__link--child ${isActive ? 'is-active' : ''}`}
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
            <NavLink to="/trabajador/notificaciones" className="button button--ghost button--compact">🔔 {unreadCount}</NavLink>
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
