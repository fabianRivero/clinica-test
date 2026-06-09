import { NavLink } from 'react-router-dom'
import { useLocation } from 'react-router-dom'

import { useAuth } from '../../providers/AuthProvider'

const specialistTabs = [
  { to: '/cms/equipo/crear', label: 'Crear especialista' },
  { to: '/cms/equipo/gestionar', label: 'Gestionar especialistas' },
] as const

const branchAdminTabs = [
  { to: '/cms/equipo/admin-sucursal/crear', label: 'Crear admin sucursal' },
  { to: '/cms/equipo/admin-sucursal/gestionar', label: 'Gestionar admins sucursal' },
] as const

export function AdminStaffTabs() {
  const { user } = useAuth()
  const isMainAdmin = user?.isMainAdmin ?? false
  const { pathname } = useLocation()

  const isSpecialistSection = pathname.startsWith('/cms/equipo/crear') || pathname.startsWith('/cms/equipo/gestionar')
  const isBranchAdminSection = pathname.startsWith('/cms/equipo/admin-sucursal/')

  return (
    <div className="staff-section-tabs">
      {isSpecialistSection && (
        <nav className="section-tabs" aria-label="Subsecciones del equipo">
          {specialistTabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) => `section-tabs__link ${isActive ? 'is-active' : ''}`}
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      )}

      {isMainAdmin && isBranchAdminSection && (
        <nav className="section-tabs" aria-label="Subsecciones de admins sucursal">
          {branchAdminTabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) => `section-tabs__link ${isActive ? 'is-active' : ''}`}
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  )
}
