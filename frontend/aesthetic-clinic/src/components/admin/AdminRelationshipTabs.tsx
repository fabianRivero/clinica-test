import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/admin/prospectos', label: 'Prospectos' },
  { to: '/admin/clientes', label: 'Clientes' },
] as const

export function AdminRelationshipTabs() {
  return (
    <nav className="section-tabs" aria-label="Subsecciones de prospectos y clientes">
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
