import { useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '../providers/AuthProvider'
import { BranchProvider, useBranchContext } from '../providers/BranchProvider'
import { NOTIFICATIONS_UPDATED_EVENT } from '../services/api/notifications'

const fullNavigation = [
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
    label: 'Gastos',
    children: [
      { to: '/admin/gastos/crear', label: 'Crear gastos' },
      { to: '/admin/gastos/lista', label: 'Lista de gastos' },
    ],
  },
  {
    label: 'Disponibilidad',
    children: [
      { to: '/admin/disponibilidad/bloques', label: 'Excepciones de horarios' },
      { to: '/admin/disponibilidad/gestionar', label: 'Gestionar horarios' },
    ],
  },
  {
    label: 'Pagos y cuotas',
    children: [
      { to: '/admin/pagos/qr', label: 'Configurar QR' },
      { to: '/admin/pagos/pendientes', label: 'Pagos' },
      { to: '/admin/pagos/cuotas', label: 'Todas las cuotas' },
    ],
  },
  { to: '/admin/notificaciones', label: 'Notificaciones' },
  {
    label: 'Gestion de sucursales',
    mainAdminOnly: true,
    children: [
      { to: '/admin/sucursales/editar', label: 'Editar sucursales' },
      { to: '/admin/sucursales/crear', label: 'Crear sucursal' },
    ],
  },
  {
    label: 'Mensajeria',
    children: [
      { to: '/admin/mensajes/permisos', label: 'Habilitar/Bloquear fichas' },
      { to: '/admin/mensajes/fichas', label: 'Fichas existentes' },
    ],
  },
  {
    label: 'Catalogos',
    mainAdminOnly: true,
    children: [
      { to: '/admin/catalogos/todos-los-servicios', label: 'Todos los servicios' },
      { to: '/admin/catalogos/procedimientos-esteticos', label: 'Procedimientos esteticos' },
      { to: '/admin/catalogos/tipos-servicio', label: 'Tipos de servicio' },
      { to: '/admin/catalogos/especialidades', label: 'Especialidades' },
      { to: '/admin/catalogos/categorias-gasto', label: 'Categorías de gasto' },
    ],
  },
  {
    label: 'Equipo',
    children: [
      { to: '/admin/equipo/crear', label: 'Crear especialista' },
      { to: '/admin/equipo/gestionar', label: 'Gestionar especialistas' },
      { to: '/admin/equipo/admin-sucursal/crear', label: 'Crear admin sucursal' },
      { to: '/admin/equipo/admin-sucursal/gestionar', label: 'Gestionar admins sucursal' },
    ],
  },
] as const

type NavItem = (typeof fullNavigation)[number]

function BranchSelector() {
  const { branches, activeBranch, isLoading, setActiveBranch } = useBranchContext()

  if (isLoading || branches.length === 0) return null

  return (
    <div className="_ml-sm _flex-center _flex-gap-sm">
      <label htmlFor="global-branch-selector" className="_text-sm _text-muted">
        Sucursal:
      </label>
      <select
        id="global-branch-selector"
        value={activeBranch?.id || ''}
        onChange={(e) => setActiveBranch(Number(e.target.value))}
        className="input _branch-select"
      >
        {branches.map((b) => (
          <option key={b.id} value={b.id}>
            {b.nombre} {b.es_principal ? '(Principal)' : ''}
          </option>
        ))}
      </select>
    </div>
  )
}

function AdminLayoutInner() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()
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
  const activePath = location.pathname
  const isMainAdmin = user?.isMainAdmin ?? false

  const navigation = useMemo(() => {
    if (isMainAdmin) return fullNavigation
    return fullNavigation.filter((item) => !('mainAdminOnly' in item && item.mainAdminOnly))
  }, [isMainAdmin]) as readonly NavItem[]

  const openGroups = useMemo(
    () =>
      new Set(
        navigation
          .filter((item) => 'children' in item && item.children.some((child) => activePath.startsWith(child.to)))
          .map((item) => item.label),
      ),
    [activePath, navigation],
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
              <span className="topbar__eyebrow">{isMainAdmin ? 'Administracion clinica' : `Sucursal: ${user?.branchName || ''}`}</span>
              <strong>{user?.fullName || 'Administrador'}</strong>
            </div>
            {isMainAdmin ? <BranchSelector /> : null}
          </div>

          <div className="topbar__right">
            <NavLink to="/admin/notificaciones" className="button button--ghost button--compact">🔔 {unreadCount}</NavLink>
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

export function AdminLayout() {
  return (
    <BranchProvider>
      <AdminLayoutInner />
    </BranchProvider>
  )
}
