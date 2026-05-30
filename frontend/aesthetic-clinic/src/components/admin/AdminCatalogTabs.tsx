import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/admin/catalogos/todos-los-servicios', label: 'Todos los servicios' },
  { to: '/admin/catalogos/procedimientos-esteticos', label: 'Procedimientos estéticos' },
  { to: '/admin/catalogos/tipos-servicio', label: 'Tipos de servicio' },
  { to: '/admin/catalogos/especialidades', label: 'Especialidades' },
  { to: '/admin/catalogos/categorias-gasto', label: 'Categorías de gasto' },
] as const

export function AdminCatalogTabs() {
  return (
    <nav className="section-tabs" aria-label="Subsecciones de catálogos">
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
