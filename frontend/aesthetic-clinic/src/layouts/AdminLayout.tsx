import { useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '../providers/AuthProvider'
import { BranchProvider, useBranchContext } from '../providers/BranchProvider'
import { NOTIFICATIONS_UPDATED_EVENT } from '../services/api/notifications'
import { ProfileEditModal } from '../components/profile/ProfileEditModal'

const fullNavigation = [
  { to: '/cms', label: 'Resumen' },
  {
    label: 'Prospectos y clientes',
    children: [
      { to: '/cms/prospectos', label: 'Prospectos' },
      { to: '/cms/clientes', label: 'Clientes' },
    ],
  },
  { to: '/cms/operaciones', label: 'Operaciones' },
  {
    label: 'Gastos',
    children: [
      { to: '/cms/gastos/crear', label: 'Crear gastos' },
      { to: '/cms/gastos/lista', label: 'Lista de gastos' },
    ],
  },
  {
    label: 'Disponibilidad',
    children: [
      { to: '/cms/disponibilidad/bloques', label: 'Excepciones de horarios' },
      { to: '/cms/disponibilidad/gestionar', label: 'Gestionar horarios' },
    ],
  },
  {
    label: 'Pagos y cuotas',
    children: [
      { to: '/cms/pagos/qr', label: 'Configurar QR' },
      { to: '/cms/pagos/pendientes', label: 'Pagos' },
      { to: '/cms/pagos/cuotas', label: 'Todas las cuotas' },
    ],
  },
  {
    label: 'Reportes',
    children: [
      { to: '/cms/reportes/clientes', label: 'Clientes' },
      { to: '/cms/reportes/prospectos', label: 'Prospectos' },
      { to: '/cms/reportes/ingresos', label: 'Ingresos' },
      { to: '/cms/reportes/gastos', label: 'Gastos' },
    ],
  },
  { to: '/cms/notificaciones', label: 'Notificaciones' },
  {
    label: 'Gestion de sucursales',
    mainAdminOnly: true,
    children: [
      { to: '/cms/sucursales/editar', label: 'Editar sucursales' },
      { to: '/cms/sucursales/crear', label: 'Crear sucursal' },
    ],
  },
  {
    label: 'Mensajeria',
    children: [
      { to: '/cms/mensajes/permisos', label: 'Habilitar/Bloquear fichas' },
      { to: '/cms/mensajes/fichas', label: 'Fichas existentes' },
    ],
  },
  {
    label: 'Equipo',
    children: [
      { to: '/cms/equipo/crear', label: 'Crear especialista' },
      { to: '/cms/equipo/gestionar', label: 'Gestionar especialistas' },
    ],
  },
  {
    label: 'Admins sucursal',
    mainAdminOnly: true,
    children: [
      { to: '/cms/equipo/admin-sucursal/crear', label: 'Crear admin sucursal' },
      { to: '/cms/equipo/admin-sucursal/gestionar', label: 'Gestionar admins sucursal' },
    ],
  },
    {
    label: 'Catalogos',
    mainAdminOnly: true,
    children: [
      { to: '/cms/catalogos/todos-los-servicios', label: 'Todos los servicios' },
      { to: '/cms/catalogos/especialidades', label: 'Especialidades' },
      { to: '/cms/catalogos/categorias-gasto', label: 'Categorías de gasto' },
      { to: '/cms/catalogos/patologias-cutaneas', label: 'Patologías cutáneas' },
      { to: '/cms/catalogos/tipos-servicio', label: 'Tipos de servicio' },
      { to: '/cms/catalogos/tipos-procedimiento', label: 'Tipos de procedimiento' },
      { to: '/cms/catalogos/secciones-ficha', label: 'Secciones de ficha' },
      { to: '/cms/catalogos/campos-ficha', label: 'Campos de ficha' },
      { to: '/cms/catalogos/grupos-opciones', label: 'Grupos de opciones' },
      { to: '/cms/catalogos/procedimientos-esteticos', label: 'Procedimientos estéticos' },
      { to: '/cms/catalogos/sectores', label: 'Sectores' },
    ],
  },
  {
    label: 'Respaldos',
    mainAdminOnly: true,
    children: [
      { to: '/cms/backups', label: 'Respaldos de base de datos' },
    ],
  },
] as const

type NavItem = (typeof fullNavigation)[number]

function BranchSelector() {
  const { branches, activeBranch, isLoading, setActiveBranch } = useBranchContext()

  if (isLoading || branches.length === 0) return null

  return (
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
  )
}

function AdminLayoutInner() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const location = useLocation()
  const { user, logout } = useAuth()
  const { activeBranch } = useBranchContext()
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
          <p>Operación clínica, pagos y catálogos en una sola vista.</p>
        </div>

        <nav className="side-nav" aria-label="Navegación principal de administración">
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
                end={item.to === '/cms'}
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
              <span className="topbar__eyebrow">
              {isMainAdmin
                ? activeBranch
                  ? `Administración clínica - ${activeBranch.nombre}`
                  : 'Administración clínica'
                : `Sucursal: ${user?.branchName || ''}`}
            </span>
              <strong>{user?.fullName || 'Administrador'}</strong>
            </div>
            {isMainAdmin ? <BranchSelector /> : null}
          </div>

          <div className="topbar__right">
            <NavLink to="/cms/notificaciones" className="button button--ghost button--compact">🔔 {unreadCount}</NavLink>
            <div className="profile-chip" onClick={() => setProfileModalOpen(true)}>
              <div className="profile-chip__meta">
                <strong>{user?.fullName}</strong>
                <span>{user?.role || 'ADMINISTRADOR'}</span>
              </div>
              <button className="button button--ghost button--compact" type="button" onClick={(e) => { e.stopPropagation(); setProfileModalOpen(true) }}>
                Perfil
              </button>
              <button className="button button--ghost button--compact" type="button" onClick={(e) => { e.stopPropagation(); void logout() }}>
                Cerrar sesión
              </button>
            </div>
          </div>
        </header>

        <ProfileEditModal isOpen={profileModalOpen} onClose={() => setProfileModalOpen(false)} />

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
