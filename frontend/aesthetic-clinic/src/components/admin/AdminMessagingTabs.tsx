import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/admin/mensajes/permisos', label: 'Creación y permiso de fichas' },
  { to: '/admin/mensajes/fichas', label: 'Fichas existentes' },
] as const

export function AdminMessagingTabs() {
  return (
    <nav className="section-tabs" aria-label="Subsecciones de mensajeria">
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
