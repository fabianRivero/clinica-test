import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/admin/equipo/crear', label: 'Crear especialista' },
  { to: '/admin/equipo/gestionar', label: 'Gestionar especialistas' },
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
