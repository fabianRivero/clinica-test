import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/cms/catalogos/todos-los-servicios', label: 'Todos los servicios' },
  { to: '/cms/catalogos/especialidades', label: 'Especialidades' },
  { to: '/cms/catalogos/categorias-gasto', label: 'Categorías de gasto' },
  { to: '/cms/catalogos/patologias-cutaneas', label: 'Patologías cutaneas' },
  { to: '/cms/catalogos/tipos-servicio', label: 'Tipos de servicio' },
  { to: '/cms/catalogos/tipos-procedimiento', label: 'Tipos de procedimiento' },
  { to: '/cms/catalogos/secciones-ficha', label: 'Secciones de ficha' },
  { to: '/cms/catalogos/campos-ficha', label: 'Campos de ficha' },
  { to: '/cms/catalogos/grupos-opciones', label: 'Grupos de opciones' },
  { to: '/cms/catalogos/procedimientos-esteticos', label: 'Procedimientos estéticos' },
  { to: '/cms/catalogos/sectores', label: 'Sectores' },
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
