import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/admin/equipo/crear', label: 'Crear especialista' },
  { to: '/admin/equipo/gestionar', label: 'Gestionar especialistas' },
  { to: '/admin/equipo/admin-sucursal/crear', label: 'Crear admin sucursal' },
  { to: '/admin/equipo/admin-sucursal/gestionar', label: 'Gestionar admins sucursal' },
] as const

export function AdminStaffTabs() {
  return (
    <nav className="section-tabs" aria-label="Subsecciones del equipo">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={({ isActive }) => `section-tabs__link ${isActive ? 'is-active' : ''}`}
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
