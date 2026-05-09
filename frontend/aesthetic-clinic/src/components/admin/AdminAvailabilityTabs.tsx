import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/admin/disponibilidad/bloques', label: 'Excepciones generales de horarios' },
  { to: '/admin/disponibilidad/gestionar', label: 'Gestionar horarios' },
] as const

export function AdminAvailabilityTabs() {
  return (
    <nav className="section-tabs" aria-label="Subsecciones de disponibilidad">
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
