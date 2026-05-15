import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/trabajador/mensajes/fichas', label: 'Fichas existentes' },
  { to: '/trabajador/mensajes/nueva', label: 'Crear ficha nueva' },
] as const

export function SpecialistMessagingTabs() {
  return (
    <nav className="section-tabs" aria-label="Subsecciones de mensajeria de especialista">
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
