import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/admin/catalogos/todos-los-servicios', label: 'Todos los servicios' },
  { to: '/admin/catalogos/procedimientos-esteticos', label: 'Procedimientos esteticos' },
  { to: '/admin/catalogos/tipos-servicio', label: 'Tipos de servicio' },
  { to: '/admin/catalogos/patologias-cutaneas', label: 'Patologias cutaneas' },
  { to: '/admin/catalogos/especialidades', label: 'Especialidades' },
] as const

export function AdminCatalogTabs() {
  return (
    <nav className="section-tabs" aria-label="Subsecciones de catalogos">
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
