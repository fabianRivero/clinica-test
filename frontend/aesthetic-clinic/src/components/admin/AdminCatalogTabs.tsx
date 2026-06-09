import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/cms/catalogos/todos-los-servicios', label: 'Todos los servicios' },
  { to: '/cms/catalogos/procedimientos-esteticos', label: 'Procedimientos estéticos' },
  { to: '/cms/catalogos/tipos-servicio', label: 'Tipos de servicio' },
  { to: '/cms/catalogos/especialidades', label: 'Especialidades' },
  { to: '/cms/catalogos/categorias-gasto', label: 'Categorías de gasto' },
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
