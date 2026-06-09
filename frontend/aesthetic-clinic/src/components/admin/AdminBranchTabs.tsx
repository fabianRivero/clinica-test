import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/cms/sucursales/editar', label: 'Editar sucursales' },
  { to: '/cms/sucursales/crear', label: 'Crear sucursal' },
] as const

export function AdminBranchTabs() {
  return (
    <nav className="section-tabs" aria-label="Subsecciones de sucursales">
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
